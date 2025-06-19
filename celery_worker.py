"""
Celery worker script for the translation queue worker

This file contains the Celery worker configuration and task definitions
for the translation queue system. It handles processing translation jobs
from the Redis queue.
"""
import os
import json
import logging
import redis
from celery import shared_task
from utils.translator import translate_with_openai, translate_with_claude
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

# API configuration
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")

@shared_task(name="celery_worker.update_translation_status")
def update_translation_status(message_id, progress, status_type, message=None):
    """
    Update the status of a translation job directly in Redis
    
    Args:
        message_id (str): Unique identifier for the translation job
        progress (float): Progress percentage (0-100)
        status_type (str): Status type (pending, started, completed, failed)
        message (str, optional): Status message or error details
    """
    try:
        # Create status data
        status_data = {
            "progress": progress,
            "status_type": status_type,
            "message": message
        }
        
        # Connect to Redis
        redis_client = redis.Redis(
            host=os.getenv("REDIS_HOST", "localhost"),
            port=int(os.getenv("REDIS_PORT", 6379)),
            db=int(os.getenv("REDIS_DB", 0)),
            password=os.getenv("REDIS_PASSWORD", None),
            decode_responses=True
        )
        
        # Update status directly in Redis
        redis_client.hset(
            f"message:{message_id}",
            "status",
            json.dumps(status_data)
        )
        
        return True
    except Exception as e:
        logger.error(f"Failed to update status for message {message_id}: {str(e)}")
        return False

@shared_task(name="celery_worker.translate_text")
def translate_text(message_id, model_name, api_key, prompt=""):
    """
    Translate text using either OpenAI or Claude AI based on the model name
    
    Args:
        message_id (str): Unique identifier for the translation job
        content (str): Text content to translate
        model_name (str): Model to use for translation (e.g., 'gpt-4', 'claude-3-opus')
        api_key (str): API key for the selected service
        source_lang (str, optional): Source language code (e.g., 'en')
        target_lang (str, optional): Target language code (e.g., 'fr')
        
    Returns:
        dict: Translation result with status and translated text
    """
    try:
        # Determine which AI service to use based on model name
        if model_name.startswith("gpt") or model_name.startswith("text-davinci"):
            # Use OpenAI
            translation = translate_with_openai(content=prompt, model_name=model_name, api_key=api_key)
            # Update progress after successful API call
            update_translation_status(message_id, 50, "started", "OpenAI translation in progress")
        elif model_name.startswith("claude"):
            # Use Claude prompt
            translation = translate_with_claude(content =prompt, model_name=model_name, api_key=api_key)
            # Update progress after successful API call
            update_translation_status(message_id, 50, "started", "Claude AI translation in progress")
        else:
            raise ValueError(f"Unsupported model: {model_name}. Please use a model name starting with 'gpt' or 'claude'.")
        
        
        # Handle different return types from translation functions
        if isinstance(translation, dict) and "translated_text" in translation:
            # If translation is already a dict with translated_text key
            translated_text = translation["translated_text"]
        else:
            # If translation is a string or other format
            translated_text = str(translation)
        
        return {
            "status": "completed",
            "message_id": message_id,
            "translated_text": translated_text,
            "model_used": model_name
        }
        
    except Exception as e:
        error_message = f"Translation error with {model_name}: {str(e)}"
        logger.error(error_message)
        
        # Update status as failed
        update_translation_status(message_id, 0, "failed", f"Translation failed: {str(e)}")
        
        # Return a failed status instead of re-raising the exception
        # This ensures the error is properly handled and marked as failed
        return {
            "status": "failed",
            "message_id": message_id,
            "error": str(e),
            "model_used": model_name
        }



if __name__ == "__main__":
    # This file is used to start the Celery worker
    # Run with: celery -A celery_worker worker --loglevel=info
    # Or with beat for scheduled tasks: celery -A celery_worker worker --beat --loglevel=info
    pass
