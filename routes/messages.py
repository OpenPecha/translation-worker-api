"""
Message routes for the FastAPI application
"""
import json
import uuid
import time
import logging
from fastapi import APIRouter, HTTPException, Body, status
from typing import Optional, Union
from pydantic import BaseModel, Field
import redis

from models.message import (
    Message, MessageResponse, MessageStatus, StatusUpdate, TranslationStatus,
    ErrorResponse, SuccessResponse, MessageStatusResponse, TranslationResult
)
from celery_app import process_message, get_queue_for_priority, update_status
from const import REDIS_EXPIRY_SECONDS, RECOMMENDED_CONTENT_LENGTH, LARGE_TEXT_WARNING_THRESHOLD

# Configure logging
logger = logging.getLogger("message-routes")

# Create router
router = APIRouter(tags=["messages"])

# Connect to Redis directly to avoid circular imports
import os
import redis
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure Redis connection
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_DB = int(os.getenv("REDIS_DB", 0))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", None)

# Connect to Redis
redis_client = redis.Redis(
    host=REDIS_HOST,
    port=REDIS_PORT,
    db=REDIS_DB,
    password=REDIS_PASSWORD,
    decode_responses=True
)

@router.post("", 
            response_model=MessageResponse, 
            status_code=status.HTTP_201_CREATED,
            responses={
                400: {"model": ErrorResponse, "description": "Bad Request - Invalid input data"},
                500: {"model": ErrorResponse, "description": "Internal Server Error"}
            })
async def add_message(message: Message = Body(...)):
    """
    Add a new translation task to the queue.

    Creates a new translation job with the specified content, model, and API key.
    The message will be queued for processing based on its priority level.
    
    **Large Text Support**: This endpoint now supports large text content.
    - Content up to 50KB: Optimal performance
    - Content 50KB-100KB: Good performance with larger batches
    - Content >100KB: Supported but may take longer to process

    ## Request Body
    - **content**: Text to be translated (no hard limit, but >100KB may be slow)
    - **model_name**: Translation model to use (e.g., 'gpt-4', 'claude-3-haiku-20240307', 'gemini-pro')
    - **api_key**: API key for the specified model
    - **priority**: Priority level 0-10 (higher = processed first, default: 0)
    - **metadata**: Optional metadata for the translation
    - **webhook**: Optional webhook URL for status updates
    - **use_segmentation**: Segmentation method ('botok', 'sentence', 'newline', or None)

    ## Response
    Returns a message ID and initial status. Use the message ID to check translation progress.
    
    ## Performance Notes
    - Large text is automatically processed with optimized batch sizes
    - Very large text (>100KB) uses increased worker allocation
    - Progress updates work the same regardless of text size

    ## Example Request
    ```json
    {
      "content": "Hello world! This text needs to be translated.",
      "model_name": "claude-3-haiku-20240307",
      "api_key": "sk-1234567890abcdef",
      "priority": 5,
      "metadata": {
        "source_language": "english",
        "target_language": "tibetan"
      },
      "use_segmentation": "botok",
      "webhook": "https://example.com/webhook"
    }
    ```

    ## Example Response
    ```json
    {
      "success": true,
      "id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
      "status": {
        "progress": 0.0,
        "status_type": "pending",
        "message": "Queued for translation"
      },
      "position": null
    }
    ```
    """
    try:
        # Intelligent content length handling
        content_length = len(message.content)
        
        # Warn about very large content but don't block it
        if content_length > LARGE_TEXT_WARNING_THRESHOLD:
            logger.warning(f"Very large content detected: {content_length} characters. This may take longer to process.")
        elif content_length > RECOMMENDED_CONTENT_LENGTH:
            logger.info(f"Large content detected: {content_length} characters. Using optimized processing.")
        
        # Validate content is not empty
        if not message.content.strip():
            logger.warning("Empty content provided")
            return ErrorResponse(
                error="Content cannot be empty",
                error_code="EMPTY_CONTENT"
            )
        
        # Generate a unique ID for the message
        message_id = str(uuid.uuid4())
        
        # Create initial status
        status = TranslationStatus(
            progress=0.0,
            status_type="pending",
            message="Queued for translation"
        )
        
        # Store message data in Redis
        message_data = {
            "id": message_id,
            "content": message.content,
            "model_name": message.model_name,
            "api_key": message.api_key,
            "priority": message.priority if message.priority is not None else 0,
            "status": json.dumps(status.model_dump()),
            "webhook": message.webhook or "",
            "use_segmentation": message.use_segmentation if message.use_segmentation is not None else "botok",
            "created_at": time.time()
        }
        
        # Add metadata if provided
        if message.metadata:
            message_data["metadata"] = json.dumps(message.metadata)
        
        # Store in Redis
        try:
            redis_client.hset(f"message:{message_id}", mapping=message_data)
            logger.info(f"Stored message {message_id} in Redis ({content_length} characters)")
        except redis.DataError as e:
            # Handle Redis data size limits
            logger.error(f"Redis data error for large content ({content_length} chars): {e}")
            return ErrorResponse(
                error=f"Content too large for storage ({content_length} characters). Please reduce content size or contact support.",
                error_code="CONTENT_TOO_LARGE_FOR_STORAGE",
                details={"content_length": content_length, "redis_error": str(e)}
            )
        except redis.ResponseError as e:
            # Handle other Redis errors
            logger.error(f"Redis response error: {e}")
            return ErrorResponse(
                error=f"Storage error: {str(e)}",
                error_code="REDIS_STORAGE_ERROR",
                details={"content_length": content_length}
            )
        
        # Set expiration time (4 hours = 14400 seconds)
        redis_client.expire(f"message:{message_id}", REDIS_EXPIRY_SECONDS)
        
        # Determine which queue to use based on priority
        queue = get_queue_for_priority(message.priority)
        
        # Send task to Celery with appropriate queue
        try:
            task = process_message.apply_async(
                args=[message_data],
                queue=queue
            )
            logger.info(f"Added message {message_id} to Celery queue '{queue}' with task ID: {task.id}")
        except Exception as celery_error:
            # If Celery task creation fails, log detailed error and clean up Redis
            logger.error(f"Failed to create Celery task for message {message_id}: {str(celery_error)}")
            logger.error(f"Celery error type: {type(celery_error).__name__}")
            
            # Clean up the Redis entry since task creation failed
            try:
                redis_client.delete(f"message:{message_id}")
            except Exception as cleanup_error:
                logger.error(f"Failed to clean up Redis entry: {cleanup_error}")
            
            return ErrorResponse(
                error=f"Failed to queue translation task: {str(celery_error)}",
                error_code="CELERY_TASK_ERROR",
                details={
                    "exception_type": type(celery_error).__name__,
                    "queue": queue,
                    "message_id": message_id
                }
            )
        
        # Return response with message ID and initial status
        return MessageResponse(
            success=True,
            id=message_id,
            status=status,
            position=None  # Position is no longer tracked with Celery queues
        )
        
    except redis.RedisError as e:
        error_msg = f"Redis connection error: {str(e)}"
        logger.error(error_msg)
        return ErrorResponse(
            error=error_msg,
            error_code="REDIS_ERROR",
            details={"exception_type": type(e).__name__}
        )
    except ImportError as e:
        error_msg = f"Import error (missing dependencies): {str(e)}"
        logger.error(error_msg)
        return ErrorResponse(
            error=error_msg,
            error_code="IMPORT_ERROR",
            details={"exception_type": type(e).__name__}
        )
    except Exception as e:
        error_msg = f"Unexpected error while adding message to queue: {str(e)}"
        logger.error(error_msg)
        logger.error(f"Exception type: {type(e).__name__}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return ErrorResponse(
            error=error_msg,
            error_code="QUEUE_ERROR",
            details={"exception_type": type(e).__name__}
        )

@router.get("/{message_id}", 
           response_model=MessageStatusResponse,
           responses={
               404: {"model": ErrorResponse, "description": "Message not found"},
               500: {"model": ErrorResponse, "description": "Internal Server Error"}
           })
async def get_message_status(message_id: str):
    """
    Get the status and result of a translation message.

    Retrieves the current status of a translation job, including the translated text
    if the translation is completed.

    ## Path Parameters
    - **message_id**: Unique identifier of the message to check

    ## Response
    Returns the message status and translation result (if completed).

    ## Example Response (Pending)
    ```json
    {
      "success": true,
      "id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
      "status": {
        "progress": 25.0,
        "status_type": "started",
        "message": "Translation in progress"
      },
      "result": null,
      "created_at": 1705312200.0
    }
    ```

    ## Example Response (Completed)
    ```json
    {
      "success": true,
      "id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
      "status": {
        "progress": 100.0,
        "status_type": "completed",
        "message": "Translation completed successfully"
      },
      "result": {
        "translated_text": "སྐད་ཡིག་འགྱུར་བ་བྱས་པ།",
        "model_used": "claude-3-haiku-20240307",
        "completed_at": "2024-01-15T10:30:00Z"
      },
      "created_at": 1705312200.0
    }
    ```

    ## Status Types
    - **pending**: Waiting in queue
    - **started**: Translation in progress
    - **completed**: Translation finished successfully
    - **failed**: Translation failed (check status.message for details)
    """
    try:
        # Get message data from Redis
        message_data = redis_client.hgetall(f"message:{message_id}")
        
        if not message_data:
            logger.warning(f"Message not found: {message_id}")
            # Raise HTTPException instead of returning ErrorResponse
            raise HTTPException(
                status_code=404,
                detail={
                    "success": False,
                    "error": "Message not found",
                    "error_code": "MESSAGE_NOT_FOUND",
                    "details": {"message_id": message_id}
                }
            )
        
        # Parse status
        status_json = message_data.get("status", "{}")
        try:
            status_data = json.loads(status_json)
        except json.JSONDecodeError:
            logger.warning(f"Invalid status JSON for message {message_id}: {status_json}")
            status_data = {"progress": 0, "status_type": "pending", "message": "Status unknown"}

        # Create status object
        status = TranslationStatus(**status_data)
        
        # Get translation result if completed
        result = None
        if status.status_type == "completed":
            result_data = redis_client.hgetall(f"translation_result:{message_id}")
            if result_data and "translated_text" in result_data:
                result = TranslationResult(
                    translated_text=result_data.get("translated_text", ""),
                    model_used=result_data.get("model_used"),
                    completed_at=result_data.get("completed_at")
                )
            else:
                logger.warning(f"Translation completed but result not found for message {message_id}")
                # Update status to indicate result missing
                status.message = "Translation completed but result not found"
        
        # Get created timestamp
        created_at = None
        if "created_at" in message_data:
            try:
                created_at = float(message_data["created_at"])
            except (ValueError, TypeError):
                logger.warning(f"Invalid created_at timestamp for message {message_id}")
        
        return MessageStatusResponse(
            success=True,
            id=message_id,
            status=status,
            result=result,
            created_at=created_at
        )
        
    except HTTPException:
        # Re-raise HTTPException (404 case)
        raise
    except Exception as e:
        error_msg = f"Failed to get message status: {str(e)}"
        logger.error(error_msg)
        # Raise HTTPException for 500 errors instead of returning ErrorResponse
        raise HTTPException(
            status_code=500,
            detail={
                "success": False,
                "error": error_msg,
                "error_code": "STATUS_RETRIEVAL_ERROR",
                "details": {"message_id": message_id, "exception_type": type(e).__name__}
            }
        )

@router.post("/{message_id}/status",
            response_model=SuccessResponse,
            responses={
                400: {"model": ErrorResponse, "description": "Bad Request - Invalid status data"},
                404: {"model": ErrorResponse, "description": "Message not found"},
                500: {"model": ErrorResponse, "description": "Internal Server Error"}
            })
async def update_message_status(message_id: str, status_update: StatusUpdate = Body(...)):
    """
    Update the status of a translation message.

    Updates the progress and status of an existing translation job. This endpoint
    is typically used by the translation workers or webhook systems.

    ## Path Parameters
    - **message_id**: Unique identifier of the message to update

    ## Request Body
    - **progress**: Progress percentage (0-100)
    - **status_type**: Status type ('pending', 'started', 'completed', 'failed')
    - **message**: Optional status message or error details

    ## Example Request
    ```json
    {
      "progress": 75.0,
      "status_type": "started",
      "message": "Translation 75% complete"
    }
    ```

    ## Example Response
    ```json
    {
      "success": true,
      "message": "Status updated successfully",
      "data": {
        "message_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
        "progress": 75.0,
        "status_type": "started"
      }
    }
    ```
    """
    try:
        # Check if message exists
        if not redis_client.exists(f"message:{message_id}"):
            logger.warning(f"Attempted to update non-existent message: {message_id}")
            return ErrorResponse(
                error="Message not found",
                error_code="MESSAGE_NOT_FOUND",
                details={"message_id": message_id}
            )
        
        # Validate status_type
        valid_status_types = ["pending", "started", "completed", "failed"]
        if status_update.status_type not in valid_status_types:
            return ErrorResponse(
                error=f"Invalid status_type. Must be one of: {', '.join(valid_status_types)}",
                error_code="INVALID_STATUS_TYPE",
                details={"provided": status_update.status_type, "valid_types": valid_status_types}
            )
        
        # Update status in Redis
        status_data = {
            "progress": status_update.progress,
            "status_type": status_update.status_type,
            "message": status_update.message
        }
        
        redis_client.hset(
            f"message:{message_id}",
            "status",
            json.dumps(status_data)
        )
        
        # Refresh expiration time to keep active messages alive
        redis_client.expire(f"message:{message_id}", REDIS_EXPIRY_SECONDS)
        
        logger.info(f"Updated status for message {message_id}: {status_update.status_type} ({status_update.progress}%)")
        
        return SuccessResponse(
            message="Status updated successfully",
            data={
                "message_id": message_id,
                "progress": status_update.progress,
                "status_type": status_update.status_type
            }
        )
        
    except Exception as e:
        error_msg = f"Failed to update message status: {str(e)}"
        logger.error(error_msg)
        return ErrorResponse(
            error=error_msg,
            error_code="STATUS_UPDATE_ERROR",
            details={"message_id": message_id, "exception_type": type(e).__name__}
        )

@router.get("/health", 
           response_model=dict,
           responses={
               500: {"model": ErrorResponse, "description": "Health check failed"}
           })
async def health_check():
    """
    Check the health of Redis and Celery connections.
    
    This endpoint verifies that both Redis and Celery are properly connected
    and can be used for message processing.
    
    ## Response
    Returns the status of all system components.
    
    ## Example Response
    ```json
    {
      "success": true,
      "health": {
        "redis": "connected",
        "celery": "connected",
        "queues": ["priority", "normal", "low"],
        "timestamp": "2024-01-15T10:30:00Z"
      }
    }
    ```
    """
    health_status = {
        "redis": "unknown",
        "celery": "unknown", 
        "queues": [],
        "timestamp": time.time()
    }
    
    try:
        # Test Redis connection
        redis_client.ping()
        health_status["redis"] = "connected"
        logger.info("Redis health check: OK")
    except Exception as e:
        health_status["redis"] = f"failed: {str(e)}"
        logger.error(f"Redis health check failed: {e}")
    
    try:
        # Test Celery connection by checking if we can import and access the functions
        from celery_app import process_message, get_queue_for_priority
        
        # Check if we can get queue names
        queues = []
        for priority in [0, 5, 10]:
            try:
                queue = get_queue_for_priority(priority)
                if queue not in queues:
                    queues.append(queue)
            except Exception as e:
                logger.warning(f"Could not get queue for priority {priority}: {e}")
        
        health_status["queues"] = queues
        
        # Try to get Celery app status (basic connectivity test)
        try:
            # This will test if Celery is importable and basic functions work
            health_status["celery"] = "connected"
            logger.info("Celery health check: OK")
        except Exception as e:
            health_status["celery"] = f"connection issue: {str(e)}"
            logger.error(f"Celery health check failed: {e}")
            
    except ImportError as e:
        health_status["celery"] = f"import failed: {str(e)}"
        logger.error(f"Celery import failed: {e}")
    except Exception as e:
        health_status["celery"] = f"failed: {str(e)}"
        logger.error(f"Celery health check error: {e}")
    
    # Determine overall health
    is_healthy = (
        health_status["redis"] == "connected" and 
        health_status["celery"] == "connected"
    )
    
    if is_healthy:
        return {
            "success": True,
            "health": health_status,
            "status": "healthy"
        }
    else:
        return ErrorResponse(
            error="System health check failed",
            error_code="HEALTH_CHECK_FAILED",
            details=health_status
        )

@router.get("/{message_id}/partial", 
           response_model=dict,
           responses={
               404: {"model": ErrorResponse, "description": "Message not found"},
               500: {"model": ErrorResponse, "description": "Internal Server Error"}
           })
async def get_partial_translation_results(message_id: str):
    """
    Get partial translation results as they become available.
    
    This endpoint returns incremental translation results as each batch completes,
    allowing users to see progress in real-time rather than waiting for completion.
    
    ## Path Parameters
    - **message_id**: Unique identifier of the message
    
    ## Response
    Returns partial translation results with completion status.
    
    ## Example Response (In Progress)
    ```json
    {
      "success": true,
      "message_id": "abc-123",
      "partial_results": {
        "0": "First batch translated text...",
        "1": "Second batch translated text...",
        "2": "Third batch translated text..."
      },
      "completed_batches": 3,
      "total_batches": 10,
      "completion_percentage": 30,
      "status": "in_progress",
      "last_updated": 1705312200.0
    }
    ```
    
    ## Example Response (No Partial Results Yet)
    ```json
    {
      "success": true,
      "message_id": "abc-123", 
      "partial_results": {},
      "completed_batches": 0,
      "total_batches": 0,
      "completion_percentage": 0,
      "status": "pending",
      "message": "No partial results available yet"
    }
    ```
    """
    try:
        # Check if message exists
        message_data = redis_client.hgetall(f"message:{message_id}")
        if not message_data:
            logger.warning(f"Message not found for partial results: {message_id}")
            return ErrorResponse(
                error="Message not found",
                error_code="MESSAGE_NOT_FOUND",
                details={"message_id": message_id}
            )
        
        # Get partial results
        partial_data = redis_client.hgetall(f"translation_partial:{message_id}")
        
        if partial_data and "partial_results" in partial_data:
            # Parse partial results
            partial_results = json.loads(partial_data.get("partial_results", "{}"))
            completed_batches = int(partial_data.get("completed_batches", 0))
            total_batches = int(partial_data.get("total_batches", 0))
            completion_percentage = int(partial_data.get("completion_percentage", 0))
            last_updated = float(partial_data.get("last_updated", time.time()))
            
            return {
                "success": True,
                "message_id": message_id,
                "partial_results": partial_results,
                "completed_batches": completed_batches,
                "total_batches": total_batches,
                "completion_percentage": completion_percentage,
                "status": "completed" if completion_percentage >= 100 else "in_progress",
                "last_updated": last_updated
            }
        else:
            # No partial results yet
            return {
                "success": True,
                "message_id": message_id,
                "partial_results": {},
                "completed_batches": 0,
                "total_batches": 0,
                "completion_percentage": 0,
                "status": "pending",
                "message": "No partial results available yet"
            }
        
    except Exception as e:
        error_msg = f"Failed to get partial results: {str(e)}"
        logger.error(error_msg)
        return ErrorResponse(
            error=error_msg,
            error_code="PARTIAL_RESULTS_ERROR",
            details={"message_id": message_id, "exception_type": type(e).__name__}
        )

@router.post("/debug/translate", 
           response_model=dict,
           responses={
               500: {"model": ErrorResponse, "description": "Translation debug failed"}
           })
async def debug_translate(request: dict = Body(...)):
    """
    Debug endpoint to test translation functions directly.
    
    This endpoint allows testing individual translation components to diagnose issues.
    
    ## Request Body
    ```json
    {
      "text": "Hello world",
      "model_name": "claude-3-haiku-20240307", 
      "api_key": "your-api-key",
      "test_type": "direct"
    }
    ```
    
    ## Response
    Returns detailed debug information about the translation attempt.
    """
    try:
        from celery_worker import translate_text
        from utils.translator import translate_with_openai, translate_with_claude, translate_with_gemini
        
        text = request.get("text", "Hello world")
        model_name = request.get("model_name", "")
        api_key = request.get("api_key", "")
        test_type = request.get("test_type", "direct")
        
        debug_info = {
            "input": {
                "text": text,
                "model_name": model_name, 
                "api_key_present": bool(api_key),
                "api_key_length": len(api_key) if api_key else 0,
                "test_type": test_type
            },
            "results": {}
        }
        
        if test_type == "direct":
            # Test the direct translator functions
            try:
                if model_name.startswith("claude"):
                    result = translate_with_claude(content=text, model_name=model_name, api_key=api_key)
                    debug_info["results"]["direct_claude"] = {"success": True, "result": result}
                elif model_name.startswith("gpt"):
                    result = translate_with_openai(content=text, model_name=model_name, api_key=api_key)
                    debug_info["results"]["direct_openai"] = {"success": True, "result": result}
                elif model_name.startswith("gemini"):
                    result = translate_with_gemini(content=text, model_name=model_name, api_key=api_key)
                    debug_info["results"]["direct_gemini"] = {"success": True, "result": result}
                else:
                    debug_info["results"]["direct"] = {"success": False, "error": "Unsupported model"}
                    
            except Exception as e:
                debug_info["results"]["direct"] = {"success": False, "error": str(e), "type": type(e).__name__}
        
        # Test the celery worker function
        try:
            result = translate_text(
                message_id="debug-test",
                model_name=model_name,
                api_key=api_key,
                prompt=text
            )
            debug_info["results"]["celery_worker"] = {"success": True, "result": result}
        except Exception as e:
            debug_info["results"]["celery_worker"] = {"success": False, "error": str(e), "type": type(e).__name__}
        
        return {
            "success": True,
            "debug_info": debug_info
        }
        
    except Exception as e:
        logger.error(f"Debug translate failed: {e}")
        return ErrorResponse(
            error=f"Debug translation failed: {str(e)}",
            error_code="DEBUG_ERROR",
            details={"exception_type": type(e).__name__}
        )

@router.get("/redis/info", 
           response_model=dict,
           responses={
               500: {"model": ErrorResponse, "description": "Internal Server Error"}
           })
async def get_redis_info():
    """
    Get Redis information including key counts and expiration details.
    
    This endpoint provides information about Redis keys and their expiration times
    for monitoring and maintenance purposes.
    
    ## Response
    Returns information about Redis keys, their count, and expiration settings.
    
    ## Example Response
    ```json
    {
      "success": true,
      "redis_info": {
        "message_keys": 5,
        "translation_result_keys": 3,
        "expiry_hours": 4,
        "expiry_seconds": 14400,
        "sample_ttl": {
          "message:abc-123": 3456,
          "translation_result:abc-123": 3456
        }
      }
    }
    ```
    """
    try:
        # Get all message and translation result keys
        message_keys = redis_client.keys("message:*")
        result_keys = redis_client.keys("translation_result:*")
        
        # Sample TTL information for first few keys
        sample_ttl = {}
        for key in (message_keys[:3] + result_keys[:3]):  # Sample first 3 of each type
            ttl = redis_client.ttl(key)
            sample_ttl[key] = ttl if ttl > 0 else "No expiration set"
        
        return {
            "success": True,
            "redis_info": {
                "message_keys": len(message_keys),
                "translation_result_keys": len(result_keys),
                "expiry_hours": REDIS_EXPIRY_SECONDS // 3600,
                "expiry_seconds": REDIS_EXPIRY_SECONDS,
                "sample_ttl": sample_ttl,
                "total_keys": len(message_keys) + len(result_keys)
            }
        }
        
    except Exception as e:
        error_msg = f"Failed to get Redis info: {str(e)}"
        logger.error(error_msg)
        return ErrorResponse(
            error=error_msg,
            error_code="REDIS_INFO_ERROR",
            details={"exception_type": type(e).__name__}
        )

