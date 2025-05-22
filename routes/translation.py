"""
Translation routes for the FastAPI application
"""
import json
import logging
from fastapi import APIRouter, HTTPException

# Configure logging
logger = logging.getLogger("translation-routes")

# Create router
router = APIRouter(prefix="/translation", tags=["translation"])

# Connect to Redis directly to avoid circular imports
import os
import redis
from dotenv import load_dotenv

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

@router.get("/{message_id}")
async def get_translation_result(message_id: str):
    """Get the translation result for a completed message"""
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
        
        # Check if the message is completed
        if status_data.get("status_type") != "completed":
            return {
                "id": message_id,
                "status": status_data,
                "message": "Translation not yet completed"
            }
        
        # Get translation result
        result_data = redis_client.hgetall(f"translation_result:{message_id}")
        
        if not result_data or "translated_text" not in result_data:
            return {
                "id": message_id,
                "status": status_data,
                "message": "Translation result not found"
            }
        
        # Return the translation result
        return {
            "id": message_id,
            "status": status_data,
            "translated_text": result_data.get("translated_text"),
            "model_used": result_data.get("model_used"),
            "completed_at": result_data.get("completed_at")
        }
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get translation result: {str(e)}")
