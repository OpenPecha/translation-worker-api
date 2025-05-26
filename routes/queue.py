"""
Queue routes for the FastAPI application
"""
import json
import logging
import time
from fastapi import APIRouter, HTTPException

# Configure logging
logger = logging.getLogger("queue-routes")

# Create router
router = APIRouter(tags=["queue"])

# Connect to Redis directly to avoid circular imports
import os
import redis
from dotenv import load_dotenv

# Import celery_app for task termination
from celery_app import celery_app

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

# Define constants
MESSAGE_KEY_PREFIX = "message:*"
TRANSLATION_RESULT_KEY_PREFIX = "translation_result:*"

@router.get("/stats")
async def get_queue_stats():
    """Get statistics about the queue"""
    try:
        # Get all message keys
        all_messages = redis_client.keys(MESSAGE_KEY_PREFIX)
        total_messages = len(all_messages)
        
        # Count by status
        status_counts = {"pending": 0, "started": 0, "completed": 0, "failed": 0}
        
        for msg_key in all_messages:
            status_json = redis_client.hget(msg_key, "status")
            if status_json:
                try:
                    status_data = json.loads(status_json)
                    status_type = status_data.get("status_type")
                    if status_type in status_counts:
                        status_counts[status_type] += 1
                except json.JSONDecodeError:
                    pass
        
        # Get Celery queue information (this is not directly accessible)
        # We'll just report the counts by status instead
        
        return {
            "total_messages": total_messages,
            "status_counts": status_counts,
            "note": "Queue sizes are no longer directly available with Celery. Status counts reflect the current state of all messages."
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get queue stats: {str(e)}")

@router.get("/next")
async def get_next_message():
    """Get the next message from the queue without removing it"""
    try:
        # Get all message keys and sort by creation time (newest first)
        all_messages = redis_client.keys("message:*")
        
        if not all_messages:
            return {"status": "empty"}
            
        # Find the most recently created message with pending status
        newest_message = None
        newest_time = 0
        
        for msg_key in all_messages:
            message_id = msg_key.split(":")[1]  # Extract message ID from key
            message_data = redis_client.hgetall(msg_key)
            
            if not message_data:
                continue
                
            # Parse status
            status_json = message_data.get("status", "{}")
            try:
                status_data = json.loads(status_json)
            except json.JSONDecodeError:
                status_data = {"progress": 0, "status_type": "pending", "message": None}
                
            # Only consider pending messages
            if status_data.get("status_type") == "pending":
                created_at = float(message_data.get("created_at", 0))
                if created_at > newest_time:
                    newest_time = created_at
                    newest_message = {
                        "id": message_id,
                        "content": message_data.get("content"),
                        "model_name": message_data.get("model_name"),
                        "priority": int(message_data.get("priority", 0)),
                        "status": status_data,
                        "queue": "celery"  # Now using Celery queues
                    }
        
        if newest_message:
            return newest_message
        else:
            return {"status": "empty"}
    
    except Exception as e:
        logger.error(f"Error getting next message: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get next message: {str(e)}")

@router.post("/process")
async def process_next_message():
    """Process (remove) the next message from the queue using Celery worker"""
    try:
        # Get all message keys and sort by creation time (newest first)
        all_messages = redis_client.keys("message:*")
        
        if not all_messages:
            return {"status": "empty"}
            
        # Find the most recently created message with pending status
        newest_message = None
        newest_time = 0
        newest_id = None
        
        for msg_key in all_messages:
            message_id = msg_key.split(":")[1]  # Extract message ID from key
            message_data = redis_client.hgetall(msg_key)
            
            if not message_data:
                continue
                
            # Parse status
            status_json = message_data.get("status", "{}")
            try:
                status_data = json.loads(status_json)
            except json.JSONDecodeError:
                status_data = {"progress": 0, "status_type": "pending", "message": None}
                
            # Only consider pending messages
            if status_data.get("status_type") == "pending":
                created_at = float(message_data.get("created_at", 0))
                if created_at > newest_time:
                    newest_time = created_at
                    newest_id = message_id
                    newest_message = message_data
                    newest_status = status_data
        
        if newest_message:
            # Import here to avoid circular imports
            from celery_app import process_message, get_queue_for_priority
            
            # Determine which queue to use based on priority
            priority = int(newest_message.get("priority", 0))
            queue = get_queue_for_priority(priority)
            
            # Send task to Celery with appropriate queue
            task = process_message.apply_async(
                args=[newest_message],
                queue=queue
            )
            
            logger.info(f"Manually processing message {newest_id} with task ID: {task.id}")
            
            return {
                "status": "processing",
                "message_id": newest_id,
                "queue": queue,
                "task_id": task.id,
                "message_status": newest_status
            }
        else:
            return {"status": "empty"}
    
    except Exception as e:
        logger.error(f"Error processing next message: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to process next message: {str(e)}")

@router.post("/reset")
async def reset_queue():
    """Reset the Redis queue by deleting all message and translation result keys"""
    try:
        # Get all message keys
        message_keys = redis_client.keys(MESSAGE_KEY_PREFIX)
        translation_keys = redis_client.keys(TRANSLATION_RESULT_KEY_PREFIX)
        
        # Count keys to be deleted
        message_count = len(message_keys)
        translation_count = len(translation_keys)
        
        # Delete all message keys
        if message_keys:
            redis_client.delete(*message_keys)
            
        # Delete all translation result keys
        if translation_keys:
            redis_client.delete(*translation_keys)
        
        logger.info(f"Reset queue: deleted {message_count} messages and {translation_count} translation results")
        
        return {
            "status": "success",
            "message": f"Queue reset successful. Deleted {message_count} messages and {translation_count} translation results."
        }
        
    except Exception as e:
        logger.error(f"Failed to reset queue: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to reset queue: {str(e)}")

@router.post("/reset-tasks")
async def reset_tasks():
    """Reset all Celery tasks and purge the task queue"""
    try:
        # Purge all queues in Celery
        celery_app.control.purge()
        
        # Try to delete Flower database file if it exists
        flower_db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "flower.db")
        if os.path.exists(flower_db_path):
            try:
                os.remove(flower_db_path)
                logger.info(f"Deleted Flower database file: {flower_db_path}")
            except Exception as e:
                logger.warning(f"Could not delete Flower database file: {str(e)}")
        
        # Inspect active tasks (for logging purposes)
        inspector = celery_app.control.inspect()
        active_tasks = inspector.active() or {}
        scheduled_tasks = inspector.scheduled() or {}
        reserved_tasks = inspector.reserved() or {}
        
        # Count total tasks
        active_count = sum(len(tasks) for tasks in active_tasks.values())
        scheduled_count = sum(len(tasks) for tasks in scheduled_tasks.values())
        reserved_count = sum(len(tasks) for tasks in reserved_tasks.values())
        total_count = active_count + scheduled_count + reserved_count
        
        logger.info(f"Reset tasks: purged all Celery queues with {total_count} tasks")
        
        return {
            "status": "success",
            "message": f"Task reset successful. Purged all Celery queues with {total_count} tasks.",
            "details": {
                "active_tasks": active_count,
                "scheduled_tasks": scheduled_count,
                "reserved_tasks": reserved_count
            }
        }
        
    except Exception as e:
        logger.error(f"Failed to reset tasks: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to reset tasks: {str(e)}")

@router.post("/reset-all")
async def reset_all():
    """Reset both the Redis queue and all Celery tasks"""
    try:
        # Reset the Redis queue
        queue_result = await reset_queue()
        
        # Reset the Celery tasks
        tasks_result = await reset_tasks()
        
        return {
            "status": "success",
            "message": "Complete system reset successful.",
            "queue_reset": queue_result,
            "tasks_reset": tasks_result
        }
        
    except Exception as e:
        logger.error(f"Failed to perform complete reset: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to perform complete reset: {str(e)}")


@router.post("/terminate/{message_id}")
async def terminate_task(message_id: str):
    """Terminate a running translation task by message ID"""
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
        
        # Check if the message is already completed or terminated
        current_status = status_data.get("status_type")
        if current_status in ["completed", "terminated", "failed"]:
            return {"status": "success", "message": f"Message {message_id} already in final state: {current_status}"}
        
        # Get task ID from Redis if available
        task_id = message_data.get("task_id")
        
        # If no task ID found, try to find active tasks for this message
        if not task_id:
            # Inspect active tasks
            inspector = celery_app.control.inspect()
            active_tasks = inspector.active() or {}
            reserved_tasks = inspector.reserved() or {}
            scheduled_tasks = inspector.scheduled() or {}
            
            # Search for tasks with this message ID in their arguments
            for worker, tasks in active_tasks.items():
                for task in tasks:
                    if task.get('args') and message_id in str(task.get('args')):
                        task_id = task.get('id')
                        break
            
            # If still not found, check reserved tasks
            if not task_id:
                for worker, tasks in reserved_tasks.items():
                    for task in tasks:
                        if task.get('args') and message_id in str(task.get('args')):
                            task_id = task.get('id')
                            break
            
            # If still not found, check scheduled tasks
            if not task_id:
                for worker, tasks in scheduled_tasks.items():
                    for task in tasks:
                        if task.get('args') and message_id in str(task.get('args')):
                            task_id = task.get('id')
                            break
        
        # If task ID found, revoke/terminate the task
        if task_id:
            # Revoke the task with terminate=True to force termination
            celery_app.control.revoke(task_id, terminate=True, signal='SIGTERM')
            logger.info(f"Terminated task {task_id} for message {message_id}")
            
            # Update status to terminated directly in Redis
            status_data = {
                "progress": 0,
                "status_type": "terminated",
                "message": "Translation task was terminated manually"
            }
            
            redis_client.hset(
                f"message:{message_id}",
                "status",
                json.dumps(status_data)
            )
            
            return {
                "status": "success", 
                "message": f"Task for message {message_id} has been terminated",
                "task_id": task_id
            }
        else:
            # If no task ID found, just update the status
            status_data = {
                "progress": 0,
                "status_type": "terminated",
                "message": "Translation task was terminated (no active task found)"
            }
            
            redis_client.hset(
                f"message:{message_id}",
                "status",
                json.dumps(status_data)
            )
            
            return {
                "status": "success", 
                "message": f"No active task found for message {message_id}, status updated to terminated"
            }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error terminating task for message {message_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to terminate task: {str(e)}")

@router.post("/complete/{message_id}")
async def mark_message_complete(message_id: str):
    """Mark a message as completed in the queue"""
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
        
        # Check if the message is already completed
        if status_data.get("status_type") == "completed":
            return {"status": "success", "message": f"Message {message_id} already marked as completed"}
        
        # Get model name for logging
        model_name = message_data.get("model_name", "unknown")
        
        # Import here to avoid circular imports
        from celery_app import update_status, celery_app
        from celery.result import AsyncResult
        
        # Update status to completed using Celery task
        update_status.delay(
            message_id=message_id,
            progress=100.0,
            status_type="completed",
            message="Translation completed successfully"
        )
        
        # Update completion timestamp
        redis_client.hset(f"message:{message_id}", "completed_at", time.time())
        
        # Log completion
        logger.info(f"Translation COMPLETED for message {message_id} using model {model_name}")
        
        return {"status": "success", "message": f"Message {message_id} marked as completed"}
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to mark message as completed: {str(e)}")

