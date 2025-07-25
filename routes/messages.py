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
from const import MAX_CONTENT_LENGTH

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

    ## Request Body
    - **content**: Text to be translated (1-30,000 characters)
    - **model_name**: Translation model to use (e.g., 'gpt-4', 'claude-3-haiku-20240307', 'gemini-pro')
    - **api_key**: API key for the specified model
    - **priority**: Priority level 0-10 (higher = processed first, default: 0)
    - **metadata**: Optional metadata for the translation
    - **webhook**: Optional webhook URL for status updates
    - **use_segmentation**: Segmentation method ('botok', 'sentence', 'newline', or None)

    ## Response
    Returns a message ID and initial status. Use the message ID to check translation progress.

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
        # Validate content length
        if len(message.content) > MAX_CONTENT_LENGTH:
            logger.warning(f"Content too long: {len(message.content)} characters")
            return ErrorResponse(
                error=f"Content is too long. Maximum allowed: {MAX_CONTENT_LENGTH} characters, received: {len(message.content)} characters",
                error_code="CONTENT_TOO_LONG",
                details={"max_length": MAX_CONTENT_LENGTH, "actual_length": len(message.content)}
            )
        
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
        redis_client.hset(f"message:{message_id}", mapping=message_data)
        
        # Determine which queue to use based on priority
        queue = get_queue_for_priority(message.priority)
        
        # Send task to Celery with appropriate queue
        task = process_message.apply_async(
            args=[message_data],
            queue=queue
        )
        
        logger.info(f"Added message {message_id} to Celery queue '{queue}' with task ID: {task.id}")
        
        # Return response with message ID and initial status
        return MessageResponse(
            success=True,
            id=message_id,
            status=status,
            position=None  # Position is no longer tracked with Celery queues
        )
        
    except Exception as e:
        error_msg = f"Failed to add message to queue: {str(e)}"
        logger.error(error_msg)
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
            return ErrorResponse(
                error="Message not found",
                error_code="MESSAGE_NOT_FOUND",
                details={"message_id": message_id}
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
        
    except Exception as e:
        error_msg = f"Failed to get message status: {str(e)}"
        logger.error(error_msg)
        return ErrorResponse(
            error=error_msg,
            error_code="STATUS_RETRIEVAL_ERROR",
            details={"message_id": message_id, "exception_type": type(e).__name__}
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

