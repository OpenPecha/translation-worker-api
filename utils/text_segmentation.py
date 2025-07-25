"""
Text segmentation utilities for the translation queue worker.

This module provides functions to segment text into sentences,
translate each segment individually, and then merge them back together.
"""

import re
import logging
import time
import asyncio
from typing import List, Dict, Any, Callable, Optional, Union, Tuple
import os
from const import SYSTEM_PROMPT

# Configure logging
logger = logging.getLogger("text-segmentation")

def segment_text(text: str, language: Optional[str] = None, use_segmentation: Optional[str] = "botok") -> List[str]:
    """
    Segment text into sentences.
    
    Args:
        text (str): The text to segment
        language (str, optional): Language code to use for segmentation
        use_segmentation (str, optional): Segmentation method to use:
            - 'botok': Use botok for Tibetan segmentation (if language is Tibetan)
            - 'sentence': Use sentence-based segmentation
            - 'newline': Use simple newline-based segmentation
            - None: No segmentation, treat the entire text as one segment
        
    Returns:
        List[str]: List of text segments
    """
    if not text or not text.strip():
        return []
        
    # Clean the text
    text = text.strip()
    
    
    # Handle newline-based segmentation
    if use_segmentation == "newline":
        segments = [s.strip() for s in text.split('\n') if s.strip()]
        
        # If there are no newlines or very few segments, split by maximum length to avoid too large segments
        if len(segments) <= 1 or any(len(s) > 1500 for s in segments):
            segments = split_by_length(text, max_length=1000)
        return segments
    
    # Handle Tibetan segmentation with botok
    if use_segmentation == "botok":
        try:
            return segment_tibetan_text(text)
        except Exception as e:
            logger.warning(f"Error segmenting Tibetan text with botok: {str(e)}. Falling back to default segmentation.")
    
    # Default sentence-based segmentation using regex
    else:
        # Fallback for any unrecognized segmentation method
        logger.warning(f"Unrecognized segmentation method: {use_segmentation}. Using sentence-based segmentation.")
        segments = re.split(r'(?<=[.!?])\s+', text)
        segments = [s.strip() for s in segments if s.strip()]
    
    return segments

def segment_tibetan_text(text: str) -> List[str]:
    import botok

    tok = botok.WordTokenizer()
    try:
        tokens = tok.tokenize(text)
        
        sentences = []
        current_sentence = ""
        
        for token in tokens:
            current_sentence += token.text
            
            # Check if token is a sentence boundary (shad or other punctuation)
            if token.text in ['།', '༎', '༑', '༈', '༏', '༐', '༔']:
                sentences.append(current_sentence.strip())
                current_sentence = ""
        
        # Add the last sentence if there's any content left
        if current_sentence.strip():
            sentences.append(current_sentence.strip())
        
        return sentences
    except ImportError:
        
        # Fallback method: split by Tibetan punctuation
        segments = re.split(r'([།༎༑༈༏༐༔])', text)
        
        # Recombine segments with their punctuation
        sentences = []
        for i in range(0, len(segments) - 1, 2):
            if i + 1 < len(segments):
                sentences.append(segments[i] + segments[i + 1])
            else:
                sentences.append(segments[i])
        
        return [s.strip() for s in sentences if s.strip()]

def split_by_length(text: str, max_length: int = 800) -> List[str]:
    """
    Split text into chunks of maximum length, trying to split at natural boundaries.
    
    Args:
        text (str): The text to split
        max_length (int): Maximum length of each chunk
        
    Returns:
        List[str]: List of text chunks
    """
    if len(text) <= max_length:
        return [text]
    
    chunks = []
    current_pos = 0
    
    while current_pos < len(text):
        # If we're near the end of the text
        if current_pos + max_length >= len(text):
            chunks.append(text[current_pos:])
            break
        
        # Find a good split point (space, newline, punctuation)
        end_pos = current_pos + max_length
        
        # Try to find a newline
        newline_pos = text.rfind('\n', current_pos, end_pos)
        if newline_pos > current_pos:
            end_pos = newline_pos + 1
        else:
            # Try to find a sentence boundary
            sentence_end = re.search(r'[.!?]\s+', text[current_pos:end_pos])
            if sentence_end:
                end_pos = current_pos + sentence_end.end()
            else:
                # Try to find a space
                space_pos = text.rfind(' ', current_pos, end_pos)
                if space_pos > current_pos:
                    end_pos = space_pos + 1
        
        chunks.append(text[current_pos:end_pos].strip())
        current_pos = end_pos
    
    return [c for c in chunks if c.strip()]

# Constant for maximum characters per batch
MAX_BATCH_CHARS = 6000

def batch_segments(segments: List[str], batch_size: int = int(os.getenv("SEGMENT_BATCH_SIZE", 10))) -> List[str]:
    """
    Combine segments into batches with a maximum of 1000 characters per batch.
    
    Args:
        segments (List[str]): List of text segments to batch
        batch_size (int): Maximum number of segments to combine in each batch (secondary constraint)
        
    Returns:
        List[str]: List of batched segments
    """
    if not segments:
        return []
    
    batched_segments = []
    current_batch = []
    current_length = 0
    for segment in segments:
        segment_length = len(segment)
        
        # If this segment alone exceeds the max character limit, we need to split it
        if segment_length > MAX_BATCH_CHARS:
            # If we have any segments in the current batch, add them as a batch first
            if current_batch:
                batched_segments.append("\n".join(current_batch))
                current_batch = []
                current_length = 0
            
            # Split the long segment and add each part as its own batch
            sub_segments = split_by_length(segment, MAX_BATCH_CHARS)
            for sub_segment in sub_segments:
                batched_segments.append(sub_segment)
            
            # Continue to the next segment
            continue
        
        # If adding this segment would exceed the character limit, start a new batch
        if current_length + segment_length > MAX_BATCH_CHARS and current_batch:
            batched_segments.append("\n".join(current_batch))
            current_batch = []
            current_length = 0
        
        # Add the segment to the current batch
        current_batch.append(segment)
        current_length += segment_length
        
        # If current batch has reached the maximum number of segments, start a new batch
        # This is a secondary constraint after the character limit
        if len(current_batch) >= batch_size:
            batched_segments.append("\n".join(current_batch))
            current_batch = []
            current_length = 0
    
    # Add the last batch if it's not empty
    if current_batch:
        batched_segments.append("\n".join(current_batch))
    
    return batched_segments

async def translate_batch(
    batch_index: int,
    batch: str,
    translate_func: Callable,
    message_id: str,
    model_name: str,
    api_key: str,
    source_lang: Optional[str] = None,
    target_lang: Optional[str] = None,
    update_status_func: Optional[Callable] = None,
    total_batches: int = 1
) -> Tuple[int, str]:
    """
    Translate a single batch with retry logic.
    
    Args:
        batch_index (int): Index of the batch (for ordering)
        batch (str): Text batch to translate
        translate_func (Callable): Function to use for translation
        message_id (str): Unique identifier for the translation job
        model_name (str): Model to use for translation
        api_key (str): API key for the translation service
        source_lang (str, optional): Source language code
        target_lang (str, optional): Target language code
        update_status_func (Callable, optional): Function to update translation status
        total_batches (int): Total number of batches
        
    Returns:
        Tuple[int, str]: Batch index and translated text
    """
    # Initialize retry counter
    retry_count = 0
    max_retries = 3
    success = False
    translated_text = ""
    
    while retry_count <= max_retries and not success:
        try:
            # Only log retries and failures to avoid spamming status updates
            if retry_count > 0:
                logger.info(f"[{message_id}] Retry {retry_count+1}/{max_retries} for batch {batch_index+1}/{total_batches}")
                
                # Only update status on retries to inform about issues
                if update_status_func:
                    # Check if the update function is async
                    if asyncio.iscoroutinefunction(update_status_func):
                        await update_status_func(
                            message_id=message_id, 
                            progress=max(10, int(((batch_index + 1) / total_batches) * 90) + 10), 
                            status_type="started", 
                            message=f"Retrying batch {batch_index+1}/{total_batches} (attempt {retry_count+1})"
                        )
                    else:
                        update_status_func(
                            message_id=message_id, 
                            progress=max(10, int(((batch_index + 1) / total_batches) * 90) + 10), 
                            status_type="started", 
                            message=f"Retrying batch {batch_index+1}/{total_batches} (attempt {retry_count+1})"
                        )
            
            # Call the translation function
            # Debug log all parameters to identify any issues
            # get array of strings
            source = batch.split('\n')
            length = len(source)
            PROMPT = (
                f"{SYSTEM_PROMPT}\n"
                f"[Translate the text to {target_lang} which is code for a language. the translations should be in an array of strings with the same length as the source text. that is {length} translations]\n"
                f"{source} "
            )
            # The error was that we're missing the message_id parameter
            # The translate_text function requires message_id as the first parameter
            result = translate_func(
                message_id=message_id,  # Add the message_id parameter
                model_name=model_name,
                api_key=api_key,
                prompt=PROMPT
            )
            # Extract the translated text
            if isinstance(result, dict):
                if result.get("status") == "completed" and "translated_text" in result:
                    # Successful translation
                    translated_text = result["translated_text"].replace('</br>', '\n')
                    success = True
                elif result.get("status") == "failed":
                    # Translation failed at AI service level
                    error_msg = result.get("error", "Unknown translation error")
                    logger.error(f"[{message_id}] AI translation failed for batch {batch_index+1}: {error_msg}")
                    raise Exception(f"AI translation failed: {error_msg}")
                elif "translated_text" in result:
                    # Legacy format (just translated_text)
                    translated_text = result["translated_text"].replace('</br>', '\n')
                    success = True
                else:
                    # Unexpected result format
                    logger.error(f"[{message_id}] Unexpected result format from translate_func: {result}")
                    raise Exception(f"Unexpected translation result format: {result}")
            else:
                # String result (legacy format)
                translated_text = str(result).replace('</br>', '\n')
                success = True
            
            # Log successful translation
            if success:
                logger.info(f"[{message_id}] Successfully translated batch {batch_index+1}/{total_batches}")
                
                # Update progress immediately after successful batch
                if update_status_func:
                    batch_progress = max(10, min(95, int(((batch_index + 1) / total_batches) * 85) + 10))  # 10-95% range
                    progress_message = f"Completed batch {batch_index+1}/{total_batches} ({batch_progress}%)"
                    
                    # Check if the update function is async
                    if asyncio.iscoroutinefunction(update_status_func):
                        await update_status_func(
                            message_id=message_id,
                            progress=batch_progress,
                            status_type="started",
                            message=progress_message
                        )
                    else:
                        update_status_func(
                            message_id=message_id,
                            progress=batch_progress,
                            status_type="started",
                            message=progress_message
                        )
                
                # Update partial results in Redis
                try:
                    from celery_app import update_partial_result_async
                    await update_partial_result_async(
                        message_id=message_id,
                        batch_index=batch_index,
                        batch_result=translated_text,
                        total_batches=total_batches
                    )
                except Exception as e:
                    logger.warning(f"[{message_id}] Failed to update partial result for batch {batch_index+1}: {e}")
            
            # If we got here, the translation was successful
            # We no longer update status here to avoid redundant updates
            # The translate_segments function will handle all status updates
            
        except Exception as e:
            retry_count += 1
            error_msg = str(e)
            logger.error(f"[{message_id}] Error translating batch {batch_index+1} (attempt {retry_count}/{max_retries}): {error_msg}")
            
            if retry_count < max_retries:
                # Wait for 1 minute before retrying
                wait_time = 60  # seconds
                
                if update_status_func:
                    # Check if the update function is async
                    if asyncio.iscoroutinefunction(update_status_func):
                        await update_status_func(
                            message_id=message_id, 
                            progress=max(10, int(((batch_index + 1) / total_batches) * 90) + 10), 
                            status_type="started", 
                            message=f"Translation failed, waiting {wait_time} seconds before retry {retry_count+1}/{max_retries}"
                        )
                    else:
                        update_status_func(
                            message_id=message_id, 
                            progress=max(10, int(((batch_index + 1) / total_batches) * 90) + 10), 
                            status_type="started", 
                            message=f"Translation failed, waiting {wait_time} seconds before retry {retry_count+1}/{max_retries}"
                        )
                
                await asyncio.sleep(wait_time)
            else:
                # After 3 failed attempts, update status to failed and use placeholder text
                error_message = f"Failed to translate batch {batch_index+1} after {max_retries} attempts: {error_msg}"
                
                if update_status_func:
                    # Check if the update function is async
                    if asyncio.iscoroutinefunction(update_status_func):
                        await update_status_func(
                            message_id=message_id, 
                            progress=max(10, int(((batch_index + 1) / total_batches) * 90) + 10), 
                            status_type="failed", 
                            message=f"Translation failed: {error_message}"
                        )
                    else:
                        update_status_func(
                            message_id=message_id, 
                            progress=max(10, int(((batch_index + 1) / total_batches) * 90) + 10), 
                            status_type="failed", 
                            message=f"Translation failed: {error_message}"
                        )
                
                # After 3 failed attempts, use the source text as fallback
                translated_text = "<failed>"+batch+"</failed>"
                
                if update_status_func:
                    # Check if the update function is async
                    if asyncio.iscoroutinefunction(update_status_func):
                        await update_status_func(
                            message_id=message_id, 
                            progress=max(10, int(((batch_index + 1) / total_batches) * 90) + 10), 
                            status_type="started", 
                            message=f"Translation failed after {max_retries} attempts. Using source text for batch {batch_index+1}/{total_batches}."
                        )
                    else:
                        update_status_func(
                            message_id=message_id, 
                            progress=max(10, int(((batch_index + 1) / total_batches) * 90) + 10), 
                            status_type="started", 
                            message=f"Translation failed after {max_retries} attempts. Using source text for batch {batch_index+1}/{total_batches}."
                        )
    
    # Return the batch index along with the translated text to maintain order
    return (batch_index, translated_text)

async def translate_segments(
    segments: List[str],
    translate_func: Callable,
    message_id: str,
    model_name: str,
    api_key: str,
    source_lang: Optional[str] = None,
    target_lang: Optional[str] = None,
    update_status_func: Optional[Callable] = None,
    batch_size: int = 10,
    max_workers: int = 4
) -> Dict[str, Any]:
    """
    Translate a list of text segments in batches using multi-threading and track progress.
    
    Args:
        segments (List[str]): List of text segments to translate
        translate_func (Callable): Function to use for translation
        message_id (str): Unique identifier for the translation job
        model_name (str): Model to use for translation
        api_key (str): API key for the translation service
        source_lang (str, optional): Source language code
        target_lang (str, optional): Target language code
        update_status_func (Callable, optional): Function to update translation status
        batch_size (int): Number of segments to combine in each batch
        max_workers (int): Maximum number of concurrent translation threads
        
    Returns:
        Dict[str, Any]: Translation result with status and translated text
    """
    if not segments:
        return {
            "status": "completed",
            "message_id": message_id,
            "translated_text": "",
            "model_used": model_name
        }
    
    
    # Get max_workers from environment variable if available
    max_workers = int(os.getenv("MAX_TRANSLATION_WORKERS", max_workers))
    
    # Combine segments into batches
    batched_segments = batch_segments(segments, batch_size)
    
    # Log batch information
    
    total_batches = len(batched_segments)
    # Use a dictionary to store results in order
    translated_batches = {}
    
    # Create tasks for concurrent execution
    tasks = []
    for i, batch in enumerate(batched_segments):
        task = translate_batch(
            i,  # batch_index
            batch,
            translate_func,
            message_id,
            model_name,
            api_key,
            source_lang,
            target_lang,
            update_status_func,
            total_batches
        )
        tasks.append(task)
    
    # Execute all tasks concurrently using asyncio.gather
    try:
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process results and track progress more accurately
        completed = 0
        for i, result in enumerate(results):
            try:
                if isinstance(result, Exception):
                    error_message = f"Error processing batch {i+1}: {str(result)}"
                    logger.error(f"[{message_id}] {error_message}")
                    
                    # Update status to failed for this batch
                    if update_status_func:
                        # Check if the update function is async
                        if asyncio.iscoroutinefunction(update_status_func):
                            await update_status_func(
                                message_id=message_id,
                                progress=max(10, int(((completed + 1) / total_batches) * 90) + 10),  # 10-100% range
                                status_type="failed",
                                message=f"Translation failed: {error_message}"
                            )
                        else:
                            update_status_func(
                                message_id=message_id,
                                progress=max(10, int(((completed + 1) / total_batches) * 90) + 10),  # 10-100% range
                                status_type="failed",
                                message=f"Translation failed: {error_message}"
                            )
                    
                    # Use fallback text for failed batch
                    translated_batches[i] = f"<failed>Batch {i+1} translation failed</failed>"
                else:
                    batch_index, translated_text = result
                    translated_batches[batch_index] = translated_text
                
                # Update overall progress more accurately
                completed += 1
                # Progress from 10% to 100% (reserving 0-10% for segmentation)
                overall_progress = min(100, max(10, int((completed / total_batches) * 90) + 10))
                
                # Log progress at key milestones
                if completed % max(1, total_batches // 4) == 0 or completed == total_batches:
                    logger.info(f"[{message_id}] Completed {completed}/{total_batches} batches ({overall_progress}%)")
                
                # Only update status at major milestones to avoid spam (individual batches update themselves)
                if completed == total_batches:
                    # Final update when all batches are complete
                    if update_status_func:
                        status_message = "All batches completed, finalizing translation"
                        
                        # Check if the update function is async
                        if asyncio.iscoroutinefunction(update_status_func):
                            await update_status_func(
                                message_id,
                                95,  # 95% - final assembly pending
                                "started",
                                status_message
                            )
                        else:
                            update_status_func(
                                message_id,
                                95,  # 95% - final assembly pending
                                "started",
                                status_message
                            )
            except Exception as e:
                error_message = f"Error processing result for batch {i+1}: {str(e)}"
                logger.error(f"[{message_id}] {error_message}")
                completed += 1
    
    except Exception as e:
        error_msg = str(e)
        logger.error(f"[{message_id}] Critical error in asyncio.gather: {error_msg}")
        logger.error(f"[{message_id}] Exception type: {type(e).__name__}")
        
        # Add stack trace for debugging
        import traceback
        logger.error(f"[{message_id}] Stack trace: {traceback.format_exc()}")
        
        # If this is an asyncio-related error, we should not continue
        if "asyncio" in error_msg.lower() or "coroutine" in error_msg.lower():
            logger.error(f"[{message_id}] Asyncio error detected - this indicates a code issue, not a translation issue")
            raise Exception(f"Asyncio execution error: {error_msg}")
        
        # Handle the case where the entire gather fails
        logger.warning(f"[{message_id}] Creating fallback entries for all {total_batches} batches due to gather failure")
        for i in range(total_batches):
            if i not in translated_batches:
                translated_batches[i] = f"<failed>Batch {i+1} translation failed</failed>"
    
    # Check if we have all batches
    missing_batches = [i for i in range(total_batches) if i not in translated_batches]
    if missing_batches:
        logger.error(f"[{message_id}] Missing {len(missing_batches)} batches: {missing_batches}")
        # For missing batches, use placeholder
        for i in missing_batches:
            translated_batches[i] = f"<failed>Batch {i+1} translation failed</failed>"
    
    # Combine all translated batches in the correct order
    ordered_translations = [translated_batches[i] for i in range(total_batches)]
    
    # Combine all translated batches
    combined_translation = "\n".join(ordered_translations)
    
    return {
        "status": "completed",
        "message_id": message_id,
        "translated_text": combined_translation,
        "model_used": model_name
    }

def merge_translated_segments(segments: List[str], language: Optional[str] = None) -> str:
    """
    Merge translated segments back into a single text.
    
    Args:
        segments (List[str]): List of translated segments
        language (str, optional): Target language code
        
    Returns:
        str: Merged translated text
    """
    if not segments:
        return ""
    
    # For Tibetan, use a different joining approach
    if language and language.lower() in ['bo', 'tibetan']:
        # Join without spaces for Tibetan
        return "".join(segments)
    
    # Default: join with spaces
    return " ".join(segments)

def count_tokens(text: str) -> int:
    """
    Estimate the number of tokens in the text.
    This is a very rough estimate based on whitespace and punctuation.
    
    Args:
        text (str): Text to count tokens for
        
    Returns:
        int: Estimated token count
    """
    # Simple whitespace tokenization for rough estimate
    tokens = re.findall(r'\S+', text)
    return len(tokens)
