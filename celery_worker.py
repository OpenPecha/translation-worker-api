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
        
        logger.info(f"Updated status for message {message_id}: {status_type} ({progress}%)")
        return True
    except Exception as e:
        logger.error(f"Failed to update status for message {message_id}: {str(e)}")
        return False

@shared_task(name="celery_worker.translate_text")
def translate_text(message_id, content, model_name, api_key, source_lang=None, target_lang=None):
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
    update_translation_status(message_id, 0, "started", "Translation in progress")
    
    try:
        # Determine which AI service to use based on model name
        if model_name.startswith("gpt") or model_name.startswith("text-davinci"):
            # Use OpenAI
            translation = translate_with_openai(content, model_name, api_key, source_lang, target_lang)
            # Update progress after successful API call
            update_translation_status(message_id, 50, "started", "OpenAI translation in progress")
        elif model_name.startswith("claude"):
            # Use Claude AI
            translation = translate_with_claude(content, model_name, api_key, source_lang, target_lang)
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
        logger.error(f"Translation error with {model_name}: {str(e)}")
        update_translation_status(message_id, 0, "failed", f"Translation failed: {str(e)}")
        raise

def translate_with_openai(content, model_name, api_key, source_lang=None, target_lang=None):
    """
    Translate text using OpenAI's API
    """
    from openai import OpenAI
    print("started translation via openai")
    # Configure OpenAI client with the provided API key using the new v1.0.0+ style
    client = OpenAI(api_key=api_key)
    
    # Prepare the system prompt based on source and target languages
    system_prompt = "You are a professional translator."
    if source_lang and target_lang:
        system_prompt += f" Translate the following text from {source_lang} to {target_lang}."
    elif target_lang:
        system_prompt += f" Translate the following text to {target_lang}."
    else:
        system_prompt += " Translate the following text to English."
    
    try:
        # Call the OpenAI API for translation using the new v1.0.0+ style
        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": system_prompt},
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


def translate_with_claude(content, model_name, api_key, source_lang=None, target_lang="English"):
    """
    Translate text using Anthropic's Claude AI (with input validation)
    """
    from anthropic import Anthropic
    import logging
    import time
    
    logger = logging.getLogger(__name__)
    
    # Log input parameters
    content_length = len(content) if isinstance(content, str) else "non-string"
    logger.info(f"Starting Claude translation - Content length: {content_length}, Model: {model_name}, Source: {source_lang}, Target: {target_lang}")
    
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
            logger.warning(f"Converting dict to string: {content[:100]}...")
    elif not isinstance(content, str):
        # Convert other types to string
        content = str(content)
        logger.warning(f"Converting {type(content)} to string: {content[:100]}...")
    
    # Validate content is not empty
    if not content or not content.strip():
        logger.error("Content is empty or contains only whitespace")
        raise ValueError("Content is empty or contains only whitespace")
    
    # Log content length after conversion
    logger.info(f"Content after conversion - Length: {len(content)} chars")
    if len(content) > 1000:
        logger.debug(f"Content preview: {content[:200]}...{content[-200:]}")
    
    # Configure Anthropic client with the provided API key
    client = Anthropic(api_key=api_key)
    
    # Prepare the prompt based on source and target languages
    prompt = "You are a professional translator that translates text accurately and preserves the original meaning and please dont include `Here is the translation to English` this kind of description in the response"
    prompt += "\n\nTranslate the following text TO " + target_lang + ":\n\n" + content
    
    try:
        # Log API call start time
        start_time = time.time()
        
        # Call the Claude API for translation using the modern SDK format
        response = client.messages.create(
            model=model_name,
            max_tokens=4000,
            temperature=0.3,  # Lower temperature for more accurate translations
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        )
        
        # Calculate and log API call duration
        elapsed_time = time.time() - start_time
        logger.info(f"Claude API call completed in {elapsed_time:.2f} seconds")
        
        # Extract the translated text from the response
        translated_text = response.content[0].text
        
        # Log translation result statistics
        translation_length = len(translated_text)
        logger.info(f"Translation successful - Result length: {translation_length} chars")
     
        # Calculate and log expansion/compression ratio
        ratio = translation_length / len(content)
        logger.info(f"Translation ratio (output/input): {ratio:.2f}")
        print("prompt:", prompt[:200] + "..." if len(prompt) > 200 else prompt)
        print("translated text:", translated_text[:200] + "..." if len(translated_text) > 200 else translated_text)
        return {"translated_text": translated_text}
        
    except Exception as e:
        logger.error(f"Claude AI translation error: {str(e)}")
        logger.error(f"Content type: {type(content)}, Content length: {len(content) if isinstance(content, str) else 'N/A'}")
        logger.exception(e)  # Log full stack trace
        raise


@shared_task(name="celery_worker.process_message")
def process_message(message):
    """
    Process a translation message from the queue.
    """
    import time
    import sys
    
    # Start timing the entire process
    process_start_time = time.time()
    
    # Log memory usage at start
    memory_info = sys.getsizeof(message) if message else 0
    logger.info(f"Starting message processing - Memory size of message: {memory_info} bytes")
    
    try:
        message_id = message['id']
        content = message['content']
        model_name = message['model_name']
        api_key = message['api_key']
        webhook = message.get('webhook')  # Get webhook URL if provided
        
        # Log message details
        content_length = len(content) if isinstance(content, str) else "non-string"
        logger.info(f"[{message_id}] Message details - Content length: {content_length}, Model: {model_name}")
        
        # Store task ID in Redis for later reference (e.g., for task termination)
        task_id = current_task.request.id
        logger.info(f"[{message_id}] Associated with Celery task ID: {task_id}")
        
        # Validate API key (this would be implemented based on your authentication system)
        if not api_key:
            logger.error(f"[{message_id}] Missing API key for translation service")
            raise ValueError("Missing API key for translation service")
        
        # Extract metadata if available
        metadata = {}
        metadata_start = time.time()
        if 'metadata' in message and message['metadata']:
            try:
                if isinstance(message['metadata'], str):
                    import json
                    metadata = json.loads(message['metadata'])
                    logger.info(f"[{message_id}] Parsed metadata from JSON string")
                else:
                    metadata = message['metadata']
                    logger.info(f"[{message_id}] Using metadata from dictionary")
                
                logger.info(f"[{message_id}] Metadata: {metadata}")
            except Exception as e:
                logger.warning(f"[{message_id}] Could not parse metadata: {str(e)}")
        else:
            logger.info(f"[{message_id}] No metadata provided")
        
        metadata_time = time.time() - metadata_start
        logger.debug(f"[{message_id}] Metadata processing took {metadata_time:.2f} seconds")
        
        # Extract source and target languages from metadata if available
        source_lang = metadata.get('source_language')
        target_lang = metadata.get('target_language')
        logger.info(f"[{message_id}] Language settings - Source: {source_lang}, Target: {target_lang}")
        
        try:
            # Import text segmentation utilities
            from utils.text_segmentation import segment_text, translate_segments
            
            # Segment the text based on source language
            segmentation_start = time.time()
            logger.info(f"[{message_id}] Starting text segmentation for content of length {content_length}")
            
            segments = segment_text(content, language=source_lang)
            
            segmentation_time = time.time() - segmentation_start
            logger.info(f"[{message_id}] Text segmentation completed in {segmentation_time:.2f} seconds")
            logger.info(f"[{message_id}] Created {len(segments)} segments")
            
            # Log segment lengths for debugging
            segment_lengths = [len(s) for s in segments]
            logger.info(f"[{message_id}] Segment lengths: {segment_lengths}")
            if segments:
                logger.info(f"[{message_id}] Largest segment: {max(segment_lengths)} chars, Smallest: {min(segment_lengths)} chars")
            
            # Update status to indicate segmentation is complete
            update_translation_status(
                message_id=message_id,
                progress=10,
                status_type="started",
                message=f"Text segmented into {len(segments)} parts. Starting translation..."
            )
            
            # Determine which translation function to use based on model name
            # Check if model_name is actually an API key (starts with 'sk-')
            if model_name and model_name.startswith('sk-'):
                logger.warning(f"[{message_id}] Model name appears to be an API key. Using default Claude model instead.")
                # Use a default Claude model
                model_name = "claude-3-opus-20240229"
                
            # Now determine which translation function to use
            # We should use translate_text which handles the message_id parameter
            # Instead of using translate_with_claude or translate_with_openai directly
            translation_func = translate_text
            logger.info(f"[{message_id}] Using translate_text function with model {model_name}")
            
            # Log the model type for debugging
            if model_name.startswith("gpt") or model_name.startswith("text-davinci"):
                logger.info(f"[{message_id}] Model type: OpenAI")
            elif model_name.startswith("claude"):
                logger.info(f"[{message_id}] Model type: Claude AI")
            else:
                logger.warning(f"[{message_id}] Unknown model type: {model_name}. Will be handled by translate_text.")
            
            # Process the translation using the segmentation utility
            translation_start = time.time()
            logger.info(f"[{message_id}] Starting translation of {len(segments)} segments")
            
            # Get batch size from environment variable
            batch_size = int(os.getenv("SEGMENT_BATCH_SIZE", 10))
            logger.info(f"[{message_id}] Using batch size: {batch_size}")
            
            result = translate_segments(
                segments=segments,
                translate_func=translation_func,
                message_id=message_id,
                model_name=model_name,
                api_key=api_key,
                source_lang=source_lang,
                target_lang=target_lang,
                update_status_func=update_translation_status,
                batch_size=batch_size
            )
            
            translation_time = time.time() - translation_start
            logger.info(f"[{message_id}] Translation completed in {translation_time:.2f} seconds")
            
            # Store the translated content in Redis for later retrieval
            redis_start = time.time()
            if 'translated_text' in result:
                translated_text = result["translated_text"]
                translated_length = len(translated_text) if translated_text else 0
                
                # Log translation statistics
                if content_length != "non-string" and translated_length > 0:
                    ratio = translated_length / int(content_length)
                    logger.info(f"[{message_id}] Translation statistics - Input: {content_length} chars, Output: {translated_length} chars, Ratio: {ratio:.2f}")
                
                redis_client = redis.Redis(
                    host=os.getenv("REDIS_HOST", "localhost"),
                    port=int(os.getenv("REDIS_PORT", 6379)),
                    db=int(os.getenv("REDIS_DB", 0)),
                    password=os.getenv("REDIS_PASSWORD", None),
                    decode_responses=True
                )
                
                logger.info(f"[{message_id}] Storing translation result in Redis")
                
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
                logger.info(f"[{message_id}] Set expiration for translation result (7 days)")
                
                # Also store the translated text in the message status
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
                        logger.info(f"[{message_id}] Updated message status with translated text")
                        
                    except Exception as e:
                        logger.warning(f"[{message_id}] Could not update message status with translated text: {str(e)}")
                        logger.exception(e)
                else:
                    logger.warning(f"[{message_id}] Could not find message data or status for {message_id}")
                
                redis_time = time.time() - redis_start
                logger.info(f"[{message_id}] Redis operations completed in {redis_time:.2f} seconds")
                
                # Send webhook notification if webhook URL is provided
                if 'webhook' in message_data and message_data['webhook']:
                    webhook_url = message_data['webhook']
                    logger.info(f"[{message_id}] Sending webhook notification to {webhook_url}")
                    
                    try:
                        webhook_payload = {
                            "content": result["translated_text"],
                            "message_id": message_id,
                            "status": "completed",
                            "model_used": model_name
                        }
                        
                        # Add metadata to webhook payload if available
                        if 'metadata' in message_data and message_data['metadata']:
                            try:
                                webhook_payload["metadata"] = json.loads(message_data['metadata'])
                            except:
                                # If metadata can't be parsed as JSON, use it as is
                                webhook_payload["metadata"] = message_data['metadata']
                        
                        # Send the webhook POST request
                        webhook_start = time.time()
                        webhook_response = requests.post(
                            webhook_url,
                            json=webhook_payload,
                            headers={"Content-Type": "application/json"},
                            timeout=10  # 10 second timeout
                        )
                        
                        webhook_time = time.time() - webhook_start
                        
                        # Log webhook response
                        if webhook_response.status_code >= 200 and webhook_response.status_code < 300:
                            logger.info(f"[{message_id}] Webhook notification sent successfully in {webhook_time:.2f} seconds. Status: {webhook_response.status_code}")
                        else:
                            logger.warning(f"[{message_id}] Webhook notification failed. Status: {webhook_response.status_code}, Response: {webhook_response.text}")
                    
                    except Exception as webhook_error:
                        logger.error(f"[{message_id}] Error sending webhook notification: {str(webhook_error)}")
                        logger.exception(webhook_error)
                else:
                    logger.info(f"[{message_id}] No webhook URL provided, skipping notification")
                    
                # Status is already updated in Redis directly, no need for another API call
                logger.info(f"[{message_id}] Translation completed. Length: {len(result['translated_text'])} characters.")
            else:
                logger.warning(f"[{message_id}] No translated_text in result: {result}")
            
            # Calculate and log total processing time
            total_time = time.time() - process_start_time
            logger.info(f"[{message_id}] Total processing time: {total_time:.2f} seconds")
            
            return {"status": "completed", "message_id": message_id, "processing_time": total_time}
            
        except Exception as e:
            # Log the error with full details
            logger.error(f"[{message_id}] Error during translation: {str(e)}")
            logger.exception(e)  # This logs the full stack trace
            
            # Calculate how long we ran before the error
            error_time = time.time() - process_start_time
            logger.error(f"[{message_id}] Translation failed after running for {error_time:.2f} seconds")
            
            # Make sure to mark as failed if there's an error
            update_translation_status(message_id, 0, "failed", f"Translation failed: {str(e)}")
            return {"status": "failed", "message_id": message_id, "error": str(e), "error_time": error_time}
    except Exception as e:
        # For errors outside the main try block, we might not have message_id
        logger.error(f"Error processing translation: {str(e)}")
        logger.exception(e)
        
        # Calculate how long we ran before the error
        error_time = time.time() - process_start_time
        logger.error(f"Processing failed after running for {error_time:.2f} seconds")
        
        # Try to update status if we have a message_id
        try:
            if 'id' in message:
                message_id = message['id']
                update_translation_status(message_id, 0, "failed", f"Translation failed: {str(e)}")
        except Exception as update_error:
            logger.error(f"Failed to update error status: {str(update_error)}")
        return False

if __name__ == "__main__":
    # This file is used to start the Celery worker
    # Run with: celery -A celery_worker worker --loglevel=info
    # Or with beat for scheduled tasks: celery -A celery_worker worker --beat --loglevel=info
    pass
