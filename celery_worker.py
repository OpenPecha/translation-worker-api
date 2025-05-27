"""
Celery worker script for the translation queue worker

This file contains the Celery worker configuration and task definitions
for the translation queue system. It handles processing translation jobs
from the Redis queue.
"""
import os
import time
import json
import logging
import random
import requests
import redis
from celery import shared_task, current_task
from celery_app import celery_app

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
def translate_text(message_id, content, model_name, api_key, prompt=""):
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
    content_with_prompt = prompt+":"+content
    print(content_with_prompt)
    try:
        # Determine which AI service to use based on model name
        if model_name.startswith("gpt") or model_name.startswith("text-davinci"):
            # Use OpenAI
            translation = translate_with_openai(content=content_with_prompt, model_name=model_name, api_key=api_key)
            # Update progress after successful API call
            update_translation_status(message_id, 50, "started", "OpenAI translation in progress")
        elif model_name.startswith("claude"):
            # Use Claude AI
            translation = translate_with_claude(content =content_with_prompt, model_name=model_name, api_key=api_key)
            # Update progress after successful API call
            update_translation_status(message_id, 50, "started", "Claude AI translation in progress")
        else:
            raise ValueError(f"Unsupported model: {model_name}. Please use a model name starting with 'gpt' or 'claude'.")
        
        # Log completion but don't update status here to avoid redundant updates
        logger.info(f"Translation API call completed for message {message_id}")
        
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





def translate_with_openai(content, model_name, api_key):
    """
    Translate text using OpenAI's API
    """
    from openai import OpenAI
    print("started translation via openai")
    # Configure OpenAI client with the provided API key using the new v1.0.0+ style
    client = OpenAI(api_key=api_key)
    
    try:
        # Call the OpenAI API for translation using the new v1.0.0+ style
        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "user", "content": content}
            ],
            temperature=0.3,  # Lower temperature for more accurate translations
        )
        
        # Extract the translated text from the response using the new response format
        translated_text = response.choices[0].message.content
        print("translated: ",translated_text)
        return translated_text
        
    except Exception as e:
        logger.error(f"OpenAI translation error: {str(e)}")
        raise


def translate_with_claude(content, model_name, api_key):
    """
    Translate text using Anthropic's Claude AI (with input validation)
    """
    from anthropic import Anthropic
    import logging
    import time
    
    logger = logging.getLogger(__name__)
    # Validate and convert content to string
    if isinstance(content, dict):
        logger.warning(f"Content is a dict: {content}")
        # If it's a dict, try to extract text from common keys
        if 'text' in content:
            content = content['text']
        elif 'content' in content:
            content = content['content']
        elif 'message' in content:
            content = content['message']
        else:
            # Convert dict to string as fallback
            content = str(content)
    elif not isinstance(content, str):
        # Convert other types to string
        content = str(content)
    
    # Validate content is not empty
    if not content or not content.strip():
        logger.error("Content is empty or contains only whitespace")
        raise ValueError("Content is empty or contains only whitespace")
    
    # Configure Anthropic client with the provided API key
    client = Anthropic(api_key=api_key)
    
    print("content" ,content)
        # Call the Claude API for translation using the modern SDK format
    response = client.messages.create(
            model=model_name,
            max_tokens=4000,
            temperature=0.3,  # Lower temperature for more accurate translations
            messages=[
                {
                    "role": "user",
                    "content":content
                }
            ]
        )
    print(response)
        
        # Calculate and log API call duration
        
        # Extract the translated text from the response
    translated_text = response.content[0].text
        
        # Log translation result statistics
     
    return {"translated_text": translated_text}
        
    # except AttributeError as e:
    #     # Specific handling for API client attribute errors (e.g., 'Anthropic' object has no attribute 'messages')
    #     raise ValueError(f"API client configuration error: {str(e)}")
        
    # except ValueError as e:
    #     # Handle value errors, including API key issues
    #     raise
        
    # except Exception as e:
    #     # General error handling
    #     logger.error(f"Claude AI translation error: {str(e)}")
    #     logger.error(f"Content type: {type(content)}, Content length: {len(content) if isinstance(content, str) else 'N/A'}")
    #     raise



if __name__ == "__main__":
    # This file is used to start the Celery worker
    # Run with: celery -A celery_worker worker --loglevel=info
    # Or with beat for scheduled tasks: celery -A celery_worker worker --beat --loglevel=info
    pass
