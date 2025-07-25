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
from utils.translator import translate_with_openai, translate_with_claude,translate_with_gemini
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

@shared_task(name="celery_worker.translate_text")
def translate_text(message_id, model_name, api_key, prompt=""):
    """
    Translate text using either OpenAI, Claude, or Gemini AI based on the model name
    
    Args:
        message_id (str): Unique identifier for the translation job
        content (str): Text content to translate
        model_name (str): Model to use for translation (e.g., 'gpt-4', 'claude-3-opus', 'gemini-pro')
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
            # Translation completed - no need to update progress here as it's handled by the caller
        elif model_name.startswith("claude"):
            # Use Claude prompt
            translation = translate_with_claude(content =prompt, model_name=model_name, api_key=api_key)
            # Translation completed - no need to update progress here as it's handled by the caller
        elif model_name.startswith("gemini"):
            # Use Gemini
            translation = translate_with_gemini(content=prompt, model_name=model_name, api_key=api_key)
            # Translation completed - no need to update progress here as it's handled by the caller
        else:
            raise ValueError(f"Unsupported model: {model_name}. Please use a model name starting with 'gpt', 'claude', or 'gemini'.")
        
        
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
        logger.error(f"Exception type: {type(e).__name__}")
        logger.error(f"Model name: {model_name}")
        logger.error(f"API key present: {'Yes' if api_key else 'No'}")
        logger.error(f"Prompt length: {len(prompt) if prompt else 0}")
        
        # Add stack trace for debugging
        import traceback
        logger.error(f"Stack trace: {traceback.format_exc()}")
        
        # Return a failed status instead of re-raising the exception
        # This ensures the error is properly handled and marked as failed
        return {
            "status": "failed",
            "message_id": message_id,
            "error": str(e),
            "model_used": model_name,
            "error_type": type(e).__name__
        }



if __name__ == "__main__":
    # This file is used to start the Celery worker
    # Run with: celery -A celery_worker worker --loglevel=info
    # Or with beat for scheduled tasks: celery -A celery_worker worker --beat --loglevel=info
    pass
