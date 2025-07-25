"""
Celery configuration for the translation queue worker

This module configures Celery with multiple queues for priority handling
and automatic retry mechanisms for failed tasks.
"""
import os
from celery import Celery, signals
from dotenv import load_dotenv
import logging
from kombu import Queue
import redis

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("celery-app")

# Configure Redis connection constants
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_DB = int(os.getenv("REDIS_DB", 0))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", None)

def get_redis_client():
    """Get a Redis client connection with consistent configuration"""
    return redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        db=REDIS_DB,
        password=REDIS_PASSWORD,
        decode_responses=True
    )

# Configure Celery using environment variables if available
BROKER_URL = os.getenv("CELERY_BROKER_URL")
RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND")

# If environment variables aren't set, construct URLs from Redis settings
if not BROKER_URL:
    BROKER_URL = f"redis://{':' + REDIS_PASSWORD + '@' if REDIS_PASSWORD else ''}{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}"
if not RESULT_BACKEND:
    RESULT_BACKEND = BROKER_URL

# Create Celery app with configured broker and backend
celery_app = Celery('translation_tasks', broker=BROKER_URL, backend=RESULT_BACKEND)

# Configure Celery for better visibility and stability
celery_app.conf.update(
    worker_send_task_events=True,
    task_send_sent_event=True,
    task_track_started=True,
    worker_hijack_root_logger=False,
    broker_connection_retry=True,
    broker_connection_retry_on_startup=True,
    broker_connection_max_retries=10,
    broker_connection_timeout=30,
    result_expires=3600,  # Results expire after 1 hour
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
)

# Define queue names as constants
QUEUE_HIGH_PRIORITY = 'high_priority'
QUEUE_DEFAULT = 'default'

# Configure Celery queues
celery_app.conf.task_queues = [
    Queue(QUEUE_HIGH_PRIORITY),
    Queue(QUEUE_DEFAULT),
]

celery_app.conf.task_default_queue = QUEUE_DEFAULT

celery_app.conf.task_routes = {
    'tasks.high_priority_translation': {'queue': QUEUE_HIGH_PRIORITY},
    'tasks.default_translation': {'queue': QUEUE_DEFAULT},
    'translate Job': {'queue': QUEUE_DEFAULT},
}

# Add signal handler for task revocation/termination
@signals.task_revoked.connect
def task_revoked_handler(request, terminated, signum, **kwargs):
    """Handle task revocation/termination by updating the message status"""
    try:
        task_id = request.id
        task_name = request.task
        logger.info(f"Task {task_id} ({task_name}) was revoked/terminated")
        
        # Try to extract message_id from task args if it's a translation task
        if task_name == "translate Job" and request.args:
            try:
                message_data = request.args[0]
                message_id = message_data.get('id')
                
                if message_id:
                    # Update the status to terminated
                    update_status(
                        message_id=message_id,
                        progress=0,
                        status_type="terminated",
                        message="Translation task was terminated manually"
                    )
            except Exception as e:
                logger.error(f"Failed to update status for terminated task: {str(e)}")
    except Exception as e:
        logger.error(f"Error in task_revoked_handler: {str(e)}")

# Define the main translation task with automatic retry
@celery_app.task(
    name="translate Job",
    bind=True,
    acks_late=True,         # Acknowledge after task completes
    time_limit=6000,         # 10 minutes (6000 seconds) time limit
    soft_time_limit=270     # Soft time limit (4.5 minutes) to allow for graceful shutdown
)
def process_message(self, message_data):
    
    """
    Process a translation message with automatic retry on failure
    
    Args:
        message_data (dict): The message data containing translation details
        
    Returns:
        dict: Result of the translation process
    """
    import json
    import time
    import redis
    from celery.exceptions import MaxRetriesExceededError, SoftTimeLimitExceeded
    from utils.text_segmentation import segment_text, translate_segments
    
    message_id = message_data.get('id')
    
    try:
        # Extract message details
        content = message_data.get('content')
        model_name = message_data.get('model_name')
        api_key = message_data.get('api_key')
        webhook = message_data.get('webhook')  # Get webhook URL if provided
        
        # Get the segmentation method to use
        use_segmentation = message_data.get('use_segmentation', 'botok')
        
        
        # Validate segmentation method
        valid_segmentation_methods = [None, 'botok', 'sentence', 'newline']
        if use_segmentation not in valid_segmentation_methods:
            logger.warning(f"Invalid segmentation method: {use_segmentation}. Using 'botok' as default.")
            use_segmentation = 'botok'
        
        
        # Store the task ID in Redis for later termination if needed
        task_id = self.request.id
        redis_client = get_redis_client()
        redis_client.hset(f"message:{message_id}", "task_id", task_id)
        
        # Extract metadata if available
        metadata = message_data.get('metadata', {})
        if isinstance(metadata, str):
            try:
                metadata = json.loads(metadata)
            except json.JSONDecodeError:
                metadata = {}
        
        # Get source and target languages from metadata if available
        source_lang = metadata.get('source_language')
        target_lang = metadata.get('target_language')
        
        # Update status to started
        update_status(
            message_id=message_id,
            progress=0,
            status_type="started",
            message=f"Translation started (attempt {self.request.retries + 1})",
            webhook_url=webhook,
            model_name=model_name,
            metadata=metadata
        )
        
        # Step 1: Segment the text into smaller chunks
        update_status(
            message_id=message_id,
            progress=1,
            status_type="started",
            message="Segmenting text for translation",
            webhook_url=webhook,
            model_name=model_name,
            metadata=metadata
        )
        
        # Use segmentation based on the use_segmentation parameter
        segments = segment_text(content, language=source_lang, use_segmentation=use_segmentation)
        segment_count = len(segments)
        
        # Log segmentation method used
        if use_segmentation=='botok': 
            logger.info(f"Used advanced text segmentation for message {message_id}. Created {segment_count} segments.")
        else:
            logger.info(f"Used simple newline-based segmentation for message {message_id}. Created {segment_count} segments.")
        
        # Step 2: Import the translation function
        from celery_worker import translate_text as translate_func
        
        # Step 3: Process segments in batches with the translation function
        update_status(
            message_id=message_id,
            progress=10,
            status_type="started",
            message=f"Starting batch translation with {segment_count} segments",
            webhook_url=webhook,
            model_name=model_name,
            metadata=metadata
        )
   
        # Get batch size from environment or use default
        import os
        batch_size = int(os.getenv("SEGMENT_BATCH_SIZE", 10))
        max_workers = int(os.getenv("MAX_TRANSLATION_WORKERS", 4))
        
        # Translate segments in batches
        import asyncio
        result = asyncio.run(translate_segments(
            segments=segments,
            translate_func=translate_func,
            message_id=message_id,
            model_name=model_name,
            api_key=api_key,
            source_lang=source_lang,
            target_lang=target_lang,
            update_status_func=update_status,
            batch_size=batch_size,
            max_workers=max_workers
        ))
        
        # Step 4: Save the translated text to Redis
        if result and 'translated_text' in result:
            # Connect to Redis
            redis_client = get_redis_client()
            
            # Store the translation result in a separate Redis key
            redis_client.hset(
                f"translation_result:{message_id}",
                mapping={
                    "translated_text": result["translated_text"],
                    "model_used": model_name,
                    "completed_at": time.time()
                }
            )
            
            # Set expiration time (7 days)
            redis_client.expire(f"translation_result:{message_id}", 60 * 60 * 24 * 7)
            
            # Also update the message status with the translated text
            # Get the current message data
            message_data = redis_client.hgetall(f"message:{message_id}")
            if message_data and "status" in message_data:
                try:
                    # Parse the current status
                    status_data = json.loads(message_data["status"])
                    
                    # Add the translated text to the status
                    status_data["translated_text"] = result["translated_text"]
                    
                    # Update the message status with the translated text
                    redis_client.hset(
                        f"message:{message_id}",
                        "status",
                        json.dumps(status_data)
                    )
                    
                except Exception as e:
                    logger.warning(f"Could not update message status with translated text: {str(e)}")
            
            # Update status to completed and send webhook with translated text
            update_status(
                message_id=message_id,
                progress=100,
                status_type="completed",
                message=f"Translation completed successfully. Length: {len(result['translated_text'])} characters.",
                webhook_url=webhook,
                translated_text=result["translated_text"],
                model_name=model_name,
                metadata=metadata
            )
            
            
            
            
            
            
            return {
                "status": "completed",
                "message_id": message_id,
                "translated_text": result["translated_text"]
            }
        else:
            raise Exception("Translation failed: No translated text returned")
        
    except SoftTimeLimitExceeded:
        # Handle soft time limit exceeded - we're approaching the 5 minute limit
        logger.warning(f"Soft time limit exceeded for message {message_id}. Task will be terminated soon.")
        
        # Update status to reflect timeout
        update_status(
            message_id=message_id,
            progress=50,  # Use a mid-point progress value
            status_type="failed",  # Changed from "timeout" to "failed" for consistency
            message="Translation failed: Task timed out after 4.5 minutes. The task will be terminated.",
            webhook_url=webhook if 'webhook' in locals() else None,
            model_name=model_name if 'model_name' in locals() else None,
            metadata=metadata if 'metadata' in locals() else None
        )
        
        # Return partial result if available
        if 'result' in locals() and result and 'translated_text' in result:
            return {
                "status": "failed",  # Changed from "timeout" to "failed" for consistency
                "message_id": message_id,
                "translated_text": result["translated_text"],
                "message": "Translation failed: Task timed out but partial results are available"
            }
        else:
            return {
                "status": "failed",  # Changed from "timeout" to "failed" for consistency
                "message_id": message_id,
                "message": "Translation failed: Task timed out before any results were available"
            }
    except Exception as exc:
        # Get a detailed error message
        error_message = f"Translation failed: {str(exc)}"
        
        # Update status to failed with the specific error message
        update_status(
            message_id=message_id,
            progress=0,
            status_type="failed",
            message=error_message,
            webhook_url=webhook if 'webhook' in locals() else None,
            model_name=model_name if 'model_name' in locals() else None,
            metadata=metadata if 'metadata' in locals() else None
        )
        
        # Log the error with traceback for better debugging
        logger.error(f"Translation failed for message {message_id}: {error_message}")
        logger.exception(exc)  # This logs the full traceback
        
        # Return error information
        return {
            "status": "failed",
            "message_id": message_id,
            "error": error_message
        }

@celery_app.task(name="update_status")
def update_status(message_id, progress, status_type, message=None, webhook_url=None, translated_text=None, model_name=None, metadata=None):
    """
    Update the status of a translation job and send webhook notification if webhook_url is provided
    
    Args:
        message_id (str): Unique identifier for the translation job
        progress (float): Progress percentage (0-100)
        status_type (str): Status type (pending, started, completed, failed)
        message (str, optional): Status message or error details
        webhook_url (str, optional): URL to send webhook notifications to
        translated_text (str, optional): Translated text (only sent when progress is 100%)
        model_name (str, optional): Model used for translation
        metadata (dict, optional): Additional metadata to include in webhook
    
    Returns:
        bool: True if status was updated successfully, False otherwise
    """
    import redis
    import json
    
    try:
        # Connect to Redis
        redis_client = get_redis_client()
        
        # Create status data
        status_data = {
            "progress": progress,
            "status_type": status_type,
            "message": message
        }
        
        # Update status in Redis
        redis_client.hset(
            f"message:{message_id}",
            "status",
            json.dumps(status_data)
        )
        
        # Send webhook notification if webhook_url is provided
        if webhook_url:
            send_webhook_notification(
                message_id=message_id,
                progress=progress,
                status_type=status_type,
                message=message,
                translated_text=translated_text if progress == 100 else None,
                model_name=model_name,
                metadata=metadata,
                webhook_url=webhook_url
            )
        
        return True
    except redis.RedisError as e:
        logger.error(f"Redis error when updating status for message {message_id}: {str(e)}")
        return False
    except (ValueError, TypeError) as e:
        logger.error(f"Data error when updating status for message {message_id}: {str(e)}")
        return False

def send_webhook_notification(message_id, progress, status_type, message=None, translated_text=None, model_name=None, metadata=None, webhook_url=None):
    """
    Send a webhook notification with the current status of a translation job
    
    Args:
        message_id (str): Unique identifier for the translation job
        progress (float): Progress percentage (0-100)
        status_type (str): Status type (pending, started, completed, failed)
        message (str, optional): Status message or error details
        translated_text (str, optional): The translated text (only sent when progress is 100%)
        model_name (str, optional): The model used for translation
        metadata (dict, optional): Additional metadata to include in the webhook
        webhook_url (str, optional): The webhook URL to send the notification to
        
    Returns:
        bool: True if webhook was sent successfully, False otherwise
    """
    if not webhook_url:
        return False
        
    try:
        import requests
        import time
        
        # Prepare webhook payload
        webhook_payload = {
            "message_id": message_id,
            "status": status_type,
            "progress": progress,
            "message": message
        }
        
        # Only include the translated content when progress is 100%
        if progress == 100 and translated_text:
            webhook_payload["content"] = translated_text
            
        # Add model information if available
        if model_name:
            webhook_payload["model_used"] = model_name
            
        # Add timestamp
        webhook_payload["timestamp"] = time.time()
        
        # Add metadata if available
        if metadata:
            webhook_payload["metadata"] = metadata
        
        # Send webhook notification
        logger.info(f"Sending webhook notification to {webhook_url} (progress: {progress}%)")
        webhook_response = requests.post(
            webhook_url,
            json=webhook_payload,
            headers={"Content-Type": "application/json"},
            timeout=10  # Set a reasonable timeout
        )
        
        # Log webhook response
        if webhook_response.status_code >= 200 and webhook_response.status_code < 300:
            logger.info(f"Webhook notification sent successfully to {webhook_url}")
            return True
        else:
            logger.warning(f"Webhook notification failed with status code {webhook_response.status_code}: {webhook_response.text}")
            return False
    except Exception as webhook_error:
        # Log webhook error but don't fail the task
        logger.error(f"Failed to send webhook notification: {str(webhook_error)}")
        return False

# Helper function to determine which queue to use based on priority
def get_queue_for_priority(priority):
    """
    Determine which queue to use based on priority level
    
    Args:
        priority (int): Priority level (higher = more important)
        
    Returns:
        str: Queue name to use
    """
    if priority and priority >= 5:
        return QUEUE_HIGH_PRIORITY
    return QUEUE_DEFAULT
