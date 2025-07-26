"""
PARALLEL OPTIMIZED CELERY APP
=============================

This version uses the parallel text segmentation module for 3-10x faster translation speed.
Key optimizations:
1. Parallel batch processing using ThreadPoolExecutor
2. Optimized batch sizing based on content length  
3. Real-time progress updates during parallel execution
4. Better resource utilization and throughput
"""

import os
import sys
import json
import asyncio
import logging
from datetime import datetime
from celery import Celery
from typing import Optional, Callable

# Add the current directory to Python path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import optimized parallel segmentation
from utils.text_segmentation_parallel import segment_text, translate_segments_parallel
from utils.translator import translate_with_openai, translate_with_claude, translate_with_gemini
from const import (
    REDIS_HOST, REDIS_PORT, REDIS_DB, 
    QUEUE_HIGH_PRIORITY, QUEUE_LOW_PRIORITY,
    REDIS_EXPIRY_SECONDS
)

# Configure logging for better debugging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("celery-worker.log")
    ]
)
logger = logging.getLogger("celery-parallel")

# Create Celery app with optimized settings for parallel processing
celery_app = Celery(
    'translation_worker_parallel',
    broker=f'redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}',
    backend=f'redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}',
    include=['celery_app_parallel']
)

# Optimized Celery configuration for parallel processing
celery_app.conf.update(
    # Task routing - force high priority for immediate processing
    task_routes={
        'celery_app_parallel.process_message': {'queue': QUEUE_HIGH_PRIORITY},
        'translate Job': {'queue': QUEUE_HIGH_PRIORITY},
    },
    
    # Performance optimizations
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    
    # Parallel processing optimizations
    worker_concurrency=8,  # Increased for better parallel handling
    worker_prefetch_multiplier=2,  # Reduced to prevent memory issues
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    
    # High priority queue as default
    task_default_queue=QUEUE_HIGH_PRIORITY,
    
    # Connection settings optimized for parallel workload
    broker_connection_retry_on_startup=True,
    broker_connection_retry=True,
    
    # Result backend settings
    result_expires=3600,  # 1 hour
    result_backend_transport_options={
        'master_name': 'mymaster'
    } if os.getenv('REDIS_SENTINEL') else {}
)

# Auto-discover tasks
celery_app.autodiscover_tasks(['celery_app_parallel'])

def get_redis_client():
    """Get Redis client with connection pooling for parallel operations"""
    import redis
    
    return redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT, 
        db=REDIS_DB,
        decode_responses=True,
        socket_connect_timeout=5,
        socket_timeout=5,
        retry_on_timeout=True,
        connection_pool=redis.ConnectionPool(
            host=REDIS_HOST,
            port=REDIS_PORT,
            db=REDIS_DB,
            max_connections=50,  # Increased for parallel operations
            retry_on_timeout=True
        )
    )

def update_status_direct(message_id: str, progress: int, status_type: str, message: str = ""):
    """
    Direct synchronous Redis status update optimized for parallel processing.
    """
    try:
        redis_client = get_redis_client()
        
        status_data = {
            "id": message_id,
            "progress": progress,
            "status_type": status_type,
            "message": message,
            "updated_at": datetime.now().isoformat(),
            "parallel_mode": True  # Flag to indicate parallel processing
        }
        
        # Store with optimized expiration
        redis_client.setex(
            f"message:{message_id}", 
            REDIS_EXPIRY_SECONDS, 
            json.dumps(status_data)
        )
        
        logger.debug(f"[{message_id}] Status updated: {progress}% - {message}")
        
    except Exception as e:
        logger.error(f"[{message_id}] Failed to update status: {str(e)}")

async def update_status_direct_async(message_id: str, progress: int, status_type: str, message: str = ""):
    """Async wrapper for status updates during parallel processing"""
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, update_status_direct, message_id, progress, status_type, message)

async def update_partial_result_async(message_id: str, batch_index: int, translated_text: str, total_batches: int):
    """
    Store partial translation results for real-time updates during parallel processing.
    """
    try:
        redis_client = get_redis_client()
        
        partial_data = {
            "batch_index": batch_index,
            "translated_text": translated_text,
            "total_batches": total_batches,
            "completed_at": datetime.now().isoformat(),
            "parallel_mode": True
        }
        
        # Store partial result with expiration
        redis_client.setex(
            f"translation_result:{message_id}:batch:{batch_index}",
            REDIS_EXPIRY_SECONDS,
            json.dumps(partial_data)
        )
        
        # Update overall partial result summary
        try:
            existing_summary = redis_client.get(f"translation_result:{message_id}")
            if existing_summary:
                summary = json.loads(existing_summary)
                summary["completed_batches"] = summary.get("completed_batches", 0) + 1
                summary["last_batch_completed"] = batch_index
                summary["progress_percentage"] = min(95, int((summary["completed_batches"] / total_batches) * 85) + 10)
            else:
                summary = {
                    "message_id": message_id,
                    "completed_batches": 1,
                    "total_batches": total_batches,
                    "last_batch_completed": batch_index,
                    "progress_percentage": min(95, int((1 / total_batches) * 85) + 10),
                    "parallel_mode": True,
                    "partial_results": []
                }
            
            # Add this batch to partial results
            summary["partial_results"].append({
                "batch_index": batch_index,
                "length": len(translated_text),
                "completed_at": datetime.now().isoformat()
            })
            
            redis_client.setex(
                f"translation_result:{message_id}",
                REDIS_EXPIRY_SECONDS,
                json.dumps(summary)
            )
            
        except Exception as summary_error:
            logger.warning(f"[{message_id}] Failed to update partial summary: {summary_error}")
            
    except Exception as e:
        logger.error(f"[{message_id}] Failed to store partial result: {str(e)}")

def get_queue_for_priority(priority: int) -> str:
    """Always return high priority queue for immediate processing"""
    return QUEUE_HIGH_PRIORITY

def get_translation_function(model_name: str):
    """Get the appropriate translation function based on model name"""
    if model_name.startswith("gpt") or model_name.startswith("text-davinci"):
        return translate_with_openai
    elif model_name.startswith("claude"):
        return translate_with_claude  
    elif model_name.startswith("gemini"):
        return translate_with_gemini
    else:
        raise ValueError(f"Unsupported model: {model_name}")

@celery_app.task(name='celery_app_parallel.process_message')
def process_message(message_id: str, content: str, model_name: str, api_key: str, 
                   source_lang: str = "bo", target_lang: str = "en", priority: int = 5):
    """
    Process translation message with PARALLEL OPTIMIZATION for maximum speed.
    
    This version uses:
    - Parallel batch processing with ThreadPoolExecutor
    - Optimized batch sizing based on content length
    - Real-time progress updates during parallel execution
    - Better resource utilization and 3-10x speed improvement
    """
    
    logger.info(f"[{message_id}] 🚀 PARALLEL PROCESSING STARTED")
    logger.info(f"[{message_id}] Content length: {len(content):,} chars")
    logger.info(f"[{message_id}] Model: {model_name}, Target: {target_lang}")
    
    try:
        # Initial status update
        update_status_direct(message_id, 5, "started", "Initializing parallel translation engine...")
        
        # Get translation function
        translate_func = get_translation_function(model_name)
        logger.info(f"[{message_id}] Using translation function: {translate_func.__name__}")
        
        # Segment text (quick operation)
        update_status_direct(message_id, 8, "started", "Segmenting text for parallel processing...")
        segments = segment_text(content, language=source_lang)
        logger.info(f"[{message_id}] Segmented into {len(segments)} segments")
        
        # Set up async event loop for parallel processing
        update_status_direct(message_id, 10, "started", "Starting parallel translation batches...")
        
        # Run the parallel translation
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            result = loop.run_until_complete(
                translate_segments_parallel(
                    segments=segments,
                    translate_func=translate_func,
                    message_id=message_id,
                    model_name=model_name,
                    api_key=api_key,
                    source_lang=source_lang,
                    target_lang=target_lang,
                    update_status_func=update_status_direct_async,
                    update_partial_result_func=update_partial_result_async
                )
            )
        finally:
            loop.close()
        
        # Handle result
        if result.get("status") == "completed":
            translated_text = result["translated_text"]
            performance = result.get("performance", {})
            
            # Store final result in Redis with performance metrics
            redis_client = get_redis_client()
            final_result = {
                "message_id": message_id,
                "content": content,
                "translated_text": translated_text,
                "model_name": model_name,
                "source_lang": source_lang,
                "target_lang": target_lang,
                "status": "completed",
                "completed_at": datetime.now().isoformat(),
                "parallel_mode": True,
                "performance": performance
            }
            
            redis_client.setex(
                f"translation_result:{message_id}",
                REDIS_EXPIRY_SECONDS,
                json.dumps(final_result)
            )
            
            # Final status update with performance info
            speed_info = ""
            if performance.get("chars_per_second"):
                speed_info = f" (~{performance['chars_per_second']:.0f} chars/sec)"
            
            update_status_direct(
                message_id, 
                100, 
                "completed", 
                f"Parallel translation completed in {performance.get('total_time', 0):.1f}s{speed_info}"
            )
            
            logger.info(f"[{message_id}] 🎉 PARALLEL TRANSLATION SUCCESS")
            logger.info(f"[{message_id}] Performance: {performance}")
            
            return {
                "status": "completed",
                "message_id": message_id,
                "translated_text": translated_text,
                "performance": performance
            }
            
        else:
            # Handle failure
            error_message = result.get("error", "Unknown parallel translation error")
            logger.error(f"[{message_id}] Parallel translation failed: {error_message}")
            
            update_status_direct(message_id, 0, "failed", f"Parallel translation failed: {error_message}")
            
            return {
                "status": "failed",
                "message_id": message_id,
                "error": error_message
            }
            
    except Exception as e:
        error_message = f"Parallel processing error: {str(e)}"
        logger.error(f"[{message_id}] {error_message}")
        
        # Add detailed error logging
        import traceback
        logger.error(f"[{message_id}] Stack trace: {traceback.format_exc()}")
        
        update_status_direct(message_id, 0, "failed", error_message)
        
        return {
            "status": "failed", 
            "message_id": message_id,
            "error": error_message
        }

# Export the app for worker startup
app = celery_app 