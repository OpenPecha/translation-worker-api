"""
Message routes for the FastAPI application
"""
import json
import uuid
import time
import logging
from fastapi import APIRouter, HTTPException, Body
from typing import Optional
from pydantic import BaseModel, Field
import redis

from models.message import Message, MessageResponse, MessageStatus, StatusUpdate, TranslationStatus
from celery_app import process_message, get_queue_for_priority, update_status

# Configure logging
logger = logging.getLogger("message-routes")

# Create router
router = APIRouter( tags=["messages"])

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

@router.post("", response_model=MessageResponse, status_code=201)
async def add_message(message: Message = Body(...)):
    """
    Add a new translation task to the queue.

    Adds a new translation task with the specified content, model, and API key.

    ### Request Example

    ```json
    {
      "content": "ཉེ་ཆར་ཇག་ ...",
      "metadata": {
        "source_language": "tibetan",
        "target_language": "english"
      },
      "model_name": "claude-3-haiku-20240307",
      "priority": 5,
      "api_key": "model api key",
      "use_segmentation": None || "botok",
      "webhook": ""
    }
    ```

    ### Response Example

    ```json
    {
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
            "webhook": message.webhook,
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
            id=message_id,
            status=status,
            position=None  # Position is no longer tracked with Celery queues
        )
        
    except Exception as e:
        logger.error(f"Error adding message to queue: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to add message to queue: {str(e)}")

@router.get("/{message_id}", response_model=dict)
async def get_message_status(message_id: str):
    """Get the status of a translation message in the queue"""
    try:
        # Get message data from Redis
        message_data = redis_client.hgetall(f"message:{message_id}")
        
        if not message_data:
            raise HTTPException(status_code=404, detail="Message not found")
        
        # Parse status
        status_json = message_data.get("status", "{}")
        try:
            status_data = json.loads(status_json)
        except json.JSONDecodeError:
            status_data = {"progress": 0, "status_type": "pending", "message": None}
        
        # Create base response with id and status
        response = {
            "id": message_id,
            "status": status_data,
        }
        
        # If the message is completed, add the translation result
        result_data = redis_client.hgetall(f"translation_result:{message_id}")
            
        if result_data and "translated_text" in result_data:
                response["translated_text"] = result_data.get("translated_text")
                response["model_used"] = result_data.get("model_used")
                response["completed_at"] = result_data.get("completed_at")
        else:
                response["message"] = "Translation completed but result not found"
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get message status: {str(e)}")

@router.post("/{message_id}/status")
async def update_message_status(message_id: str, status_update: dict = Body(...)):
    """Update the status of a translation message"""
    try:
        # Check if message exists
        if not redis_client.exists(f"message:{message_id}"):
            raise HTTPException(status_code=404, detail="Message not found")
        
        # Extract status data from the request body
        # This handles both direct JSON and StatusUpdate model instances
        progress = status_update.get("progress", 0)
        status_type = status_update.get("status_type", "pending")
        message = status_update.get("message", None)
        
        # Update status in Redis
        status_data = {
            "progress": progress,
            "status_type": status_type,
            "message": message
        }
        
        redis_client.hset(
            f"message:{message_id}",
            "status",
            json.dumps(status_data)
        )
        
        logger.info(f"Updated status for message {message_id}: {status_type} ({progress}%)")
        return {"status": "updated", "message_id": message_id}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update status for message {message_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to update message status: {str(e)}")

