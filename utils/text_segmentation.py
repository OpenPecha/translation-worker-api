"""
Text segmentation utilities for the translation queue worker.

This module provides functions to segment text into sentences,
translate each segment individually, and then merge them back together.
"""

import re
import logging
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any, Callable, Optional, Union, Tuple
import os

# Configure logging
logger = logging.getLogger("text-segmentation")

def segment_text(text: str, language: Optional[str] = None, use_segmentation: bool = True) -> List[str]:
    """
    Segment text into sentences.
    
    Args:
        text (str): The text to segment
        language (str, optional): Language code to use for segmentation
        use_segmentation (bool, optional): Whether to use advanced segmentation (True) or simple newline-based segmentation (False)
        
    Returns:
        List[str]: List of text segments
    """
    if not text or not text.strip():
        return []
        
    # Clean the text
    text = text.strip()
    
    # If use_segmentation is False, simply split by newlines
    if not use_segmentation:
        logger.info("Using simple newline-based segmentation as requested")
        segments = [s.strip() for s in text.split('\n') if s.strip()]
        
        # If there are no newlines or very few segments, split by maximum length to avoid too large segments
        if len(segments) <= 1 or any(len(s) > 1500 for s in segments):
            logger.info("Text has few or no newlines, applying length-based splitting")
            segments = split_by_length(text, max_length=1000)
            
        return segments
    
    # For Tibetan text, use a different segmentation approach
    if language and language.lower() in ['bo', 'tibetan']:
        try:
            return segment_tibetan_text(text)
        except Exception as e:
            logger.warning(f"Error segmenting Tibetan text: {str(e)}. Falling back to default segmentation.")
    
    # Default segmentation using regex
    # This pattern matches sentence boundaries:
    # - End with period, question mark, or exclamation followed by space or end of string
    # - Handle abbreviations, quotes, and parentheses
    segments = re.split(r'(?<=[.!?])\s+', text)
    
    # Filter out empty segments
    segments = [s.strip() for s in segments if s.strip()]
    
    # If the text is very long but no sentence boundaries were found,
    # fall back to splitting by newlines or a maximum length
    if len(segments) <= 1 and len(text) > 1000:
        # Try splitting by newlines first
        segments = [s.strip() for s in text.split('\n') if s.strip()]
        
        # If still too long or still just one segment, split by maximum length
        if len(segments) <= 1 or any(len(s) > 1000 for s in segments):
            segments = split_by_length(text, max_length=800)
    
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
MAX_BATCH_CHARS = 1000

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
            logger.warning(f"Segment exceeds maximum character limit ({segment_length} > {MAX_BATCH_CHARS}). Splitting segment.")
            # If we have any segments in the current batch, add them as a batch first
            if current_batch:
                batched_segments.append("\n\n".join(current_batch))
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
            batched_segments.append("\n\n".join(current_batch))
            current_batch = []
            current_length = 0
        
        # Add the segment to the current batch
        current_batch.append(segment)
        current_length += segment_length
        
        # If current batch has reached the maximum number of segments, start a new batch
        # This is a secondary constraint after the character limit
        if len(current_batch) >= batch_size:
            batched_segments.append("\n\n".join(current_batch))
            current_batch = []
            current_length = 0
    
    # Add the last batch if it's not empty
    if current_batch:
        batched_segments.append("\n\n".join(current_batch))
    
    return batched_segments

def translate_batch(
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
    
    # Log batch details
    logger.info(f"[{message_id}] Starting batch {batch_index+1}/{total_batches}, length: {len(batch)} chars")
    if len(batch) > 500:
        logger.info(f"[{message_id}] Batch {batch_index+1} preview: {batch[:100]}...{batch[-100:]}")
    else:
        logger.info(f"[{message_id}] Batch {batch_index+1} content: {batch}")
    
    # Thread-safe progress update
    progress_lock = threading.Lock()
    
    while retry_count < max_retries and not success:
        try:
            # Update progress
            progress = int((batch_index / total_batches) * 100)
            retry_msg = f" (Retry {retry_count+1}/{max_retries})" if retry_count > 0 else ""
            
            with progress_lock:
                if update_status_func:
                    update_status_func(
                        message_id, 
                        progress, 
                        "started", 
                        f"Translating batch {batch_index+1}/{total_batches} ({progress}%){retry_msg}"
                    )
            
            # Only log on first attempt (no retry)
            if retry_count == 0:
                logger.info(f"[{message_id}] Translating batch {batch_index+1}/{total_batches}, model: {model_name}, target_lang: {target_lang}")
            else:
                logger.info(f"[{message_id}] Retry {retry_count+1}/{max_retries} for batch {batch_index+1}/{total_batches}")
            
            start_time = time.time()
            
            # Call the translation function
            # Debug log all parameters to identify any issues
            logger.info(f"[{message_id}] Translation parameters - Model: {model_name}, API key: {api_key[:10]}..., Source: {source_lang}, Target: {target_lang}")
            
            # The error was that we're missing the message_id parameter
            # The translate_text function requires message_id as the first parameter
            result = translate_func(
                message_id=message_id,  # Add the message_id parameter
                content=batch,
                model_name=model_name,
                api_key=api_key,
                source_lang=source_lang,
                target_lang=target_lang
            )
            
            elapsed_time = time.time() - start_time
            logger.info(f"[{message_id}] Translation API call for batch {batch_index+1} took {elapsed_time:.2f} seconds")
            
            # Extract the translated text
            if isinstance(result, dict) and "translated_text" in result:
                translated_text = result["translated_text"]
                logger.info(f"[{message_id}] Batch {batch_index+1} translated successfully, output length: {len(translated_text)} chars")
                if len(translated_text) > 500:
                    logger.debug(f"[{message_id}] Batch {batch_index+1} result preview: {translated_text[:100]}...{translated_text[-100:]}")
            else:
                translated_text = str(result)
                logger.warning(f"[{message_id}] Batch {batch_index+1} returned unexpected format, converted to string, length: {len(translated_text)} chars")
            
            # If we got here, the translation was successful
            success = True
            
            # We no longer update status here to avoid redundant updates
            # The translate_segments function will handle all status updates
            
        except Exception as e:
            retry_count += 1
            error_msg = str(e)
            logger.error(f"[{message_id}] Error translating batch {batch_index+1} (attempt {retry_count}/{max_retries}): {error_msg}")
            logger.exception(e)
            
            if retry_count < max_retries:
                # Wait for 1 minute before retrying
                wait_time = 60  # seconds
                
                with progress_lock:
                    if update_status_func:
                        update_status_func(
                            message_id, 
                            progress, 
                            "started", 
                            f"Translation failed, waiting {wait_time} seconds before retry {retry_count+1}/{max_retries}"
                        )
                
                logger.info(f"[{message_id}] Waiting {wait_time} seconds before retry {retry_count+1}/{max_retries} for batch {batch_index+1}")
                time.sleep(wait_time)
            else:
                # After 3 failed attempts, use the source text as fallback
                logger.warning(f"[{message_id}] Batch {batch_index+1}: Using source text after {max_retries} failed attempts.")
                translated_text = "<failed>"+batch+"</failed>"
                
                with progress_lock:
                    if update_status_func:
                        update_status_func(
                            message_id, 
                            progress, 
                            "started", 
                            f"Translation failed after {max_retries} attempts. Using source text for batch {batch_index+1}/{total_batches}."
                        )
    
    # Return the batch index along with the translated text to maintain order
    return (batch_index, translated_text)

def translate_segments(
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
        logger.warning(f"No segments to translate for message_id: {message_id}")
        return {
            "status": "completed",
            "message_id": message_id,
            "translated_text": "",
            "model_used": model_name
        }
    
    # Log the number and size of segments
    total_chars = sum(len(s) for s in segments)
    logger.info(f"[{message_id}] Starting translation of {len(segments)} segments, total chars: {total_chars}, target_lang: {target_lang}")
    logger.info(f"[{message_id}] Segment lengths: {[len(s) for s in segments]}")
    
    # Get max_workers from environment variable if available
    max_workers = int(os.getenv("MAX_TRANSLATION_WORKERS", max_workers))
    
    # Combine segments into batches
    batched_segments = batch_segments(segments, batch_size)
    
    # Log batch information
    batch_lengths = [len(batch) for batch in batched_segments]
    logger.info(f"[{message_id}] Created {len(batched_segments)} batches with batch_size={batch_size}")
    logger.info(f"[{message_id}] Largest batch: {max(batch_lengths)} chars, Smallest batch: {min(batch_lengths)} chars")
    
    total_batches = len(batched_segments)
    logger.info(f"===== STARTING PARALLEL TRANSLATION: {total_batches} batches with {max_workers} workers =====")
    
    # Use a dictionary to store results in order
    translated_batches = {}
    
    # Use ThreadPoolExecutor to process batches concurrently
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all translation tasks
        future_to_batch = {}
        
        # Submit all tasks to the thread pool
        for i, batch in enumerate(batched_segments):
            logger.info(f"[{message_id}] Submitting batch {i+1}/{total_batches} for translation, length: {len(batch)} chars")
            
            future = executor.submit(
                translate_batch,
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
            future_to_batch[future] = i
            
            # No delay needed
        
        # Process results as they complete (but we'll store them in order)
        completed = 0
        
        for future in as_completed(future_to_batch):
            try:
                batch_index, translated_text = future.result()
                batch_length = len(batched_segments[batch_index])
                translated_length = len(translated_text)
                
                logger.info(f"[{message_id}] Completed batch {batch_index+1}/{total_batches}, " +
                           f"input: {batch_length} chars, output: {translated_length} chars, " +
                           f"ratio: {translated_length/batch_length:.2f}")
                
                translated_batches[batch_index] = translated_text
                
                # Update overall progress
                completed += 1
                overall_progress = int((completed / total_batches) * 100)
                
                # Log progress at certain intervals to avoid log spam
                if completed == 1 or completed == total_batches or completed % 5 == 0:
                    logger.info(f"Progress: {completed}/{total_batches} batches ({overall_progress}%)")
                
                # Always update status after each batch is completed
                if update_status_func:
                    update_status_func(
                        message_id,
                        overall_progress,
                        "started",
                        f"Completed {completed}/{total_batches} batches ({overall_progress}%)"
                    )
            except Exception as e:
                logger.error(f"[{message_id}] Error processing batch {future_to_batch[future]+1}: {str(e)}")
                logger.exception(e)
                # Still need to count this batch as completed even if it failed
                completed += 1
    
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
    combined_translation = "\n\n".join(ordered_translations)
    
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
