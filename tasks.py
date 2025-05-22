"""
Celery tasks for the translation queue worker
"""
import os
import time
import json
import logging
import random
import requests
from celery import shared_task
import redis
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("celery-worker.log")
    ]
)
logger = logging.getLogger("celery-worker")

# Configure Redis connection
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_DB = int(os.getenv("REDIS_DB", 0))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", None)

# Queue names
MESSAGE_QUEUE_PRIORITY = "message_queue:priority"  # Sorted set for priority queue
MESSAGE_QUEUE_REGULAR = "message_queue:regular"  # List for regular queue

# API configuration
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")

# Connect to Redis
redis_client = redis.Redis(
    host=REDIS_HOST,
    port=REDIS_PORT,
    db=REDIS_DB,
    password=REDIS_PASSWORD,
    decode_responses=True
)

@shared_task(name="tasks.update_translation_status")
def update_translation_status(message_id, progress, status_type, message=None):
    """
    Update the status of a translation job in the queue
    """
    try:
        status_data = {
            "progress": progress,
            "status_type": status_type,
            "message": message
        }
        
        response = requests.post(
            f"{API_BASE_URL}/messages/{message_id}/status",
            json=status_data
        )
        response.raise_for_status()
        logger.info(f"Updated status for message {message_id}: {status_type} ({progress}%)")
        return True
    except Exception as e:
        logger.error(f"Failed to update status for message {message_id}: {str(e)}")
        return False

@shared_task(name="tasks.process_translation")
def process_translation(message_id, content, model_name, api_key, metadata=None):
    """
    Process a translation message from the queue
    """
    try:
        
        # Validate API key
        if not api_key:
            raise ValueError("Missing API key for translation service")
        
        # Mark as started
        update_translation_status(message_id, 0, "started", "Translation in progress")
        
        # Calculate steps based on content length
        content_length = len(content)
        base_steps = 5
        additional_steps = min(15, content_length // 100)
        steps = base_steps + additional_steps
        
        # Simulate translation process
        print(f"\033[1;33m🔄 Starting translation job {message_id} with model {model_name}\033[0m")
        
        # Simulate progress updates
        for i in range(1, steps + 1):
            progress = (i / steps) * 100
            
            # Add some randomness to make it look more realistic
            sleep_time = (10 / steps) * (0.5 + random.random())
            time.sleep(sleep_time)
            
            # Create a progress message
            if content_length > 500:
                estimated_chars = int((progress / 100) * content_length)
                progress_msg = f"Translation {progress:.1f}% complete ({estimated_chars}/{content_length} characters)"
            else:
                progress_msg = f"Translation {progress:.1f}% complete"
                
            # Update status
            update_translation_status(message_id, progress, "started", progress_msg)
        
        # In a real implementation, you would call the actual translation API here
        # For now, we'll just simulate successful completion
        update_translation_status(message_id, 100, "completed", "Translation completed successfully")
        
        logger.info(f"Successfully processed translation job: {message_id}")
        return {"status": "completed", "message_id": message_id}
    
    except Exception as e:
        logger.error(f"Error processing translation: {str(e)}")
        # Update status to failed
        try:
            update_translation_status(message_id, 0, "failed", f"Translation failed: {str(e)}")
        except Exception as update_error:
            logger.error(f"Failed to update error status: {str(update_error)}")
        return {"status": "failed", "message_id": message_id, "error": str(e)}

@shared_task(name="tasks.check_empty_queue")
def check_empty_queue():
    """
    Check if the queue is empty and trigger processing of any pending messages
    """
    try:
        # Check priority queue first
        priority_items = redis_client.zrange(MESSAGE_QUEUE_PRIORITY, 0, 0)
        if priority_items:
            message_id = priority_items[0]
            # Remove from priority queue
            redis_client.zrem(MESSAGE_QUEUE_PRIORITY, message_id)
            
            # Get message data
            message_data = redis_client.hgetall(f"message:{message_id}")
            if message_data:
                # Check if message is already completed
                if "status" in message_data:
                    try:
                        status_data = json.loads(message_data["status"])
                        if status_data.get("status_type") == "completed":
                            logger.info(f"Skipping already completed message {message_id} from priority queue")
                            return {"status": "skipped", "message_id": message_id, "reason": "already_completed"}
                    except Exception as e:
                        logger.warning(f"Could not parse status data for message {message_id}: {str(e)}")
                
                # Process the message
                process_translation.delay(
                    message_id=message_id,
                    content=message_data.get("content", ""),
                    model_name=message_data.get("model_name", "unknown"),
                    api_key=message_data.get("api_key", ""),
                    metadata=json.loads(message_data.get("metadata", "{}"))
                )
                return {"status": "processing", "message_id": message_id, "queue": "priority"}
        
        # If no priority items, check regular queue
        regular_item = redis_client.lpop(MESSAGE_QUEUE_REGULAR)
        if regular_item:
            message_id = regular_item
            
            # Get message data
            message_data = redis_client.hgetall(f"message:{message_id}")
            if message_data:
                # Check if message is already completed
                if "status" in message_data:
                    try:
                        status_data = json.loads(message_data["status"])
                        if status_data.get("status_type") == "completed":
                            logger.info(f"Skipping already completed message {message_id} from regular queue")
                            return {"status": "skipped", "message_id": message_id, "reason": "already_completed"}
                    except Exception as e:
                        logger.warning(f"Could not parse status data for message {message_id}: {str(e)}")
                
                # Process the message
                process_translation.delay(
                    message_id=message_id,
                    content=message_data.get("content", ""),
                    model_name=message_data.get("model_name", "unknown"),
                    api_key=message_data.get("api_key", ""),
                    metadata=json.loads(message_data.get("metadata", "{}"))
                )
                return {"status": "processing", "message_id": message_id, "queue": "regular"}
        
        # If we get here, both queues are empty
        logger.debug("Both queues are empty, nothing to process")
        return {"status": "empty"}
    
    except Exception as e:
        logger.error(f"Error checking queue: {str(e)}")
        return {"status": "error", "error": str(e)}
