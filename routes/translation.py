"""
Translation routes for the FastAPI application
"""
import json
import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

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

# Pydantic models for the test endpoint
class TranslationTestRequest(BaseModel):
    text: str
    translator_type: str  # "openai" or "claude"
    model_name: str
    api_key: str

class TranslationTestResponse(BaseModel):
    success: bool
    translated_text: Optional[str] = None
    error: Optional[str] = None
    translator_used: str
    model_used: str

@router.get("/test")
async def get_test_info():
    """
    Get information about how to test the translator functions
    
    Returns example request format and available options
    """
    return {
        "message": "Use POST /translation/test to test translator functions",
        "example_request": {
            "text": "Hello, how are you?",
            "translator_type": "openai",  # or "claude"
            "model_name": "gpt-3.5-turbo",  # or "claude-3-sonnet-20240229"
            "api_key": "your-api-key-here"
        },
        "available_translators": {
            "openai": {
                "description": "OpenAI GPT models for translation",
                "example_models": ["gpt-3.5-turbo", "gpt-4", "gpt-4-turbo"]
            },
            "claude": {
                "description": "Anthropic Claude models for translation",
                "example_models": ["claude-3-sonnet-20240229", "claude-3-haiku-20240307"]
            }
        },
        "response_format": {
            "success": "boolean indicating if translation was successful",
            "translated_text": "the translated text (if successful)",
            "error": "error message (if failed)",
            "translator_used": "which translator was used",
            "model_used": "which model was used"
        }
    }

@router.post("/test", response_model=TranslationTestResponse)
async def test_translator(request: TranslationTestRequest):
    """
    Test the translator functions with sample text
    
    This endpoint allows you to test both OpenAI and Claude translators
    without going through the full queue system.
    """
    try:
        # Import the translator functions
        from utils.translator import translate_with_openai, translate_with_claude, translate_with_gemini
        
        if request.translator_type.lower() == "openai":
            # Test OpenAI translator
            translated_text = translate_with_openai(
                content=request.text,
                model_name=request.model_name,
                api_key=request.api_key
            )
            
            return TranslationTestResponse(
                success=True,
                translated_text=translated_text,
                translator_used="openai",
                model_used=request.model_name
            )
            
        elif request.translator_type.lower() == "claude":
            # Test Claude translator
            result = translate_with_claude(
                content=request.text,
                model_name=request.model_name,
                api_key=request.api_key
            )
            
            return TranslationTestResponse(
                success=True,
                translated_text=result.get("translated_text"),
                translator_used="claude",
                model_used=request.model_name
            )
        elif request.translator_type.lower() == "gemini":
            # Test Gemini translator
            result = translate_with_gemini(
                content=request.text,
                model_name=request.model_name,
                api_key=request.api_key
            )
            
            return TranslationTestResponse(
                success=True,
                translated_text=result.get("translated_text"),
                translator_used="gemini",
                model_used=request.model_name
            )
        else:
            raise HTTPException(
                status_code=400, 
                detail="translator_type must be either 'openai' or 'claude'"
            )
            
    except Exception as e:
        logger.error(f"Translation test failed: {str(e)}")
        return TranslationTestResponse(
            success=False,
            error=str(e),
            translator_used=request.translator_type,
            model_used=request.model_name
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
