from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import httpx
import os
import json
from typing import Optional, Dict, Any, Literal, AsyncGenerator

router = APIRouter()

class AIRequest(BaseModel):
    provider: Literal["openai", "anthropic"]
    model: str
    api_key: str
    prompt: str
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = 4096  # Make this configurable
    additional_params: Optional[Dict[str, Any]] = None

async def stream_openai_response(url: str, headers: Dict, payload: Dict) -> AsyncGenerator[str, None]:
    async with httpx.AsyncClient(timeout=60.0) as client:
        async with client.stream('POST', url, headers=headers, json=payload) as response:
            if response.status_code != 200:
                error_text = await response.aread()
                yield f"data: {json.dumps({'error': f'API Error: {response.status_code} - {error_text.decode()}'})}\n\n"
                return
                
            async for line in response.aiter_lines():
                if line.startswith('data: '):
                    line = line[6:]  # Remove 'data: ' prefix
                    if line.strip() == '[DONE]':
                        yield f"data: {json.dumps({'done': True})}\n\n"
                        break
                    try:
                        data = json.loads(line)
                        if 'choices' in data and len(data['choices']) > 0:
                            content = data['choices'][0].get('delta', {}).get('content', '')
                            if content:
                                yield f"data: {json.dumps({'content': content})}\n\n"
                    except json.JSONDecodeError:
                        continue

async def stream_anthropic_response(url: str, headers: Dict, payload: Dict) -> AsyncGenerator[str, None]:
    async with httpx.AsyncClient(timeout=60.0) as client:
        async with client.stream('POST', url, headers=headers, json=payload) as response:
            if response.status_code != 200:
                error_text = await response.aread()
                yield f"data: {json.dumps({'error': f'API Error: {response.status_code} - {error_text.decode()}'})}\n\n"
                return
                
            async for line in response.aiter_lines():
                if not line:
                    continue
                    
                # Anthropic sends different event types
                if line.startswith('event: '):
                    event_type = line[7:].strip()
                    continue
                elif line.startswith('data: '):
                    data_str = line[6:].strip()
                    
                    # Skip empty data lines
                    if not data_str:
                        continue
                        
                    try:
                        data = json.loads(data_str)
                        
                        # Handle different message types
                        if data.get('type') == 'content_block_delta':
                            # This is the actual text content
                            content = data.get('delta', {}).get('text', '')
                            if content:
                                yield f"data: {json.dumps({'content': content})}\n\n"
                        
                        elif data.get('type') == 'message_stop':
                            # Stream is complete
                            yield f"data: {json.dumps({'done': True})}\n\n"
                            break
                            
                        elif data.get('type') == 'error':
                            # Error occurred
                            error_msg = data.get('error', {}).get('message', 'Unknown error')
                            yield f"data: {json.dumps({'error': error_msg})}\n\n"
                            break
                            
                    except json.JSONDecodeError as e:
                        # Skip malformed JSON
                        continue

@router.post("/process")
async def process_ai_request(request: AIRequest):
    """
    Process an AI request with the specified model and parameters.
    Supports both OpenAI and Anthropic (Claude) models.
    """
    try:
        if request.provider == "openai":
            api_url = "https://api.openai.com/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {request.api_key}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": request.model,
                "messages": [{"role": "user", "content": request.prompt}],
                "temperature": request.temperature,
                **(request.additional_params or {})
            }
        elif request.provider == "anthropic":
            api_url = "https://api.anthropic.com/v1/messages"
            headers = {
                "x-api-key": request.api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json"
            }
            payload = {
                "model": request.model,
                "messages": [{"role": "user", "content": request.prompt}],
                "max_tokens": request.max_tokens or 4096,  # Required for Anthropic
                "temperature": request.temperature,
                **(request.additional_params or {})
            }
        else:
            raise HTTPException(status_code=400, detail="Unsupported provider")

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                api_url,
                headers=headers,
                json=payload
            )
            
            if response.status_code != 200:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"AI API error: {response.text}"
                )
            
            result = response.json()
            return {
                "status": "success",
                "result": result
            }
            
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error processing AI request: {str(e)}"
        )

@router.post("/stream")
async def stream_ai_response(request: AIRequest):
    """
    Stream an AI response with the specified model and parameters.
    Supports both OpenAI and Anthropic (Claude) models.
    """
    try:
        if request.provider == "openai":
            api_url = "https://api.openai.com/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {request.api_key}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": request.model,
                "messages": [{"role": "user", "content": request.prompt}],
                "temperature": request.temperature,
                "stream": True,
                **(request.additional_params or {})
            }
            stream_generator = stream_openai_response
            
        elif request.provider == "anthropic":
            api_url = "https://api.anthropic.com/v1/messages"
            headers = {
                "x-api-key": request.api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json"
            }
            payload = {
                "model": request.model,
                "messages": [{"role": "user", "content": request.prompt}],
                "max_tokens": request.max_tokens or 4096,  # Required for Anthropic
                "temperature": request.temperature,
                "stream": True,
                **(request.additional_params or {})
            }
            stream_generator = stream_anthropic_response
        else:
            raise HTTPException(status_code=400, detail="Unsupported provider")

        return StreamingResponse(
            stream_generator(api_url, headers, payload),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "Access-Control-Allow-Origin": "*",
            }
        )
            
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error streaming AI response: {str(e)}"
        )