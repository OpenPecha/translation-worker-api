"""
Translation utilities for different AI models
Enhanced with parallel processing support while maintaining segment order
"""
import asyncio
import concurrent.futures
from typing import Dict, Any


def translate_with_openai(content, model_name, api_key):
    """
    Translate text using OpenAI's GPT models (synchronous)
    """
    import openai
    
    openai.api_key = api_key
    
    try:
        response = openai.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": "You are a professional translator. Translate the provided text accurately."},
                {"role": "user", "content": content}
            ],
            temperature=0.3,
            max_tokens=4000
        )
        
        translated_text = response.choices[0].message.content
        return {"translated_text": translated_text}
        
    except Exception as e:
        print(f"OpenAI translation error: {e}")
        return {"translated_text": f"[OpenAI translation error: {str(e)}]"}


def translate_with_claude(content, model_name, api_key):
    """
    Translate text using Anthropic's Claude AI (with robust error handling)
    """
    from langchain_anthropic import ChatAnthropic
    from typing import List
    from pydantic import BaseModel, Field
    import json
    import ast
    
    llm = ChatAnthropic(model=model_name, temperature=0, api_key=api_key)
    
    class Translation(BaseModel):
        translation: List[str] = Field(description="List of translations of the sourcetext")

    def translate_text(data):
        try:
            # Try structured output first
            output = llm.with_structured_output(Translation).invoke(data)
            if output and hasattr(output, 'translation') and output.translation:
                return output
            else:
                # If structured output fails or returns empty, fall back to regular output
                print(f"Structured output failed or empty, trying fallback for Claude")
                regular_output = llm.invoke(data)
                
                # Try to parse the content as various formats
                try:
                    if hasattr(regular_output, 'content'):
                        content_text = regular_output.content
                    else:
                        content_text = str(regular_output)
                    
                    print(f"Claude raw response: {content_text}")
                    
                    # Method 1: Try to extract JSON from the response
                    if '{' in content_text and '}' in content_text:
                        json_start = content_text.find('{')
                        json_end = content_text.rfind('}') + 1
                        json_text = content_text[json_start:json_end]
                        try:
                            parsed_json = json.loads(json_text)
                            if 'translation' in parsed_json:
                                return Translation(translation=parsed_json['translation'])
                        except json.JSONDecodeError:
                            print("Failed to parse as JSON")
                    
                    # Method 2: Try to parse as Python list literal (e.g., "['item1', 'item2']")
                    if content_text.strip().startswith('[') and content_text.strip().endswith(']'):
                        try:
                            parsed_list = ast.literal_eval(content_text.strip())
                            if isinstance(parsed_list, list):
                                return Translation(translation=parsed_list)
                        except (ValueError, SyntaxError) as e:
                            print(f"Failed to parse as Python list literal: {e}")
                    
                    # Method 3: Look for list-like pattern in text
                    import re
                    list_pattern = r'\[([^\]]+)\]'
                    list_matches = re.findall(list_pattern, content_text)
                    if list_matches:
                        try:
                            # Try to parse the content inside brackets
                            list_content = list_matches[0]
                            # Handle quoted strings
                            if "'" in list_content:
                                items = [item.strip().strip("'\"") for item in list_content.split("',")]
                                items = [item for item in items if item]  # Remove empty items
                                if items:
                                    return Translation(translation=items)
                        except Exception as e:
                            print(f"Failed to parse list pattern: {e}")
                    
                    # Method 4: If no JSON or list, treat the whole response as lines
                    lines = content_text.strip().split('\n')
                    # Filter out empty lines and clean up
                    translations = [line.strip() for line in lines if line.strip()]
                    if translations:
                        return Translation(translation=translations)
                    else:
                        # Fallback: single item list
                        return Translation(translation=[content_text.strip()])
                    
                except Exception as parse_error:
                    print(f"Failed to parse Claude response: {parse_error}")
                    # Last resort: return the raw content as a single translation
                    raw_content = str(regular_output)
                    return Translation(translation=[raw_content])
                    
        except Exception as e:
            print(f"Claude translation error: {e}")
            # Check if it's a Pydantic validation error with string input
            if "Input should be a valid list" in str(e):
                print("Detected Pydantic list validation error, attempting string parsing...")
                try:
                    # Extract the problematic input value from the error
                    error_str = str(e)
                    if 'input_value=' in error_str:
                        # Extract the input value
                        input_start = error_str.find('input_value=') + len('input_value=')
                        input_end = error_str.find(',', input_start)
                        if input_end == -1:
                            input_end = error_str.find(']', input_start) + 1
                        input_value = error_str[input_start:input_end].strip('"\'')
                        
                        print(f"Attempting to parse: {input_value}")
                        
                        # Try to parse this as a Python list
                        if input_value.startswith('[') and input_value.endswith(']'):
                            try:
                                parsed_list = ast.literal_eval(input_value)
                                if isinstance(parsed_list, list):
                                    return Translation(translation=parsed_list)
                            except:
                                pass
                        
                        # Fallback: treat as single item
                        return Translation(translation=[input_value])
                except:
                    pass
            
            # Return a fallback translation to prevent complete failure
            return Translation(translation=["[Translation failed - Claude error]"])

    try:
        translated_text = translate_text(content)
        
        # Ensure we have valid translation data
        if translated_text and hasattr(translated_text, 'translation') and translated_text.translation:
            return {"translated_text": "\n".join(translated_text.translation)}
        else:
            # Fallback if translation is still empty
            return {"translated_text": "[Translation unavailable - Claude returned empty response]"}
            
    except Exception as e:
        print(f"Claude function error: {e}")
        # Return error in the expected format instead of raising
        return {"translated_text": f"[Translation error: {str(e)}]"}


def translate_with_gemini(content, model_name, api_key):
    """
    Translate text using Google's Gemini AI (with input validation)
    """
    from langchain_google_genai import ChatGoogleGenerativeAI
    from typing import List
    from pydantic import BaseModel, Field
    
    llm = ChatGoogleGenerativeAI(model=model_name, temperature=0, google_api_key=api_key)
    
    class Translation(BaseModel):
        translation: List[str] = Field(description="List of translations of the sourcetext")

    def translate_text(data):
        try:
            output = llm.with_structured_output(Translation).invoke(data)
            return output
        except Exception as e:
            print(f"Gemini translation error: {e}")
            # Fallback for Gemini
            try:
                regular_output = llm.invoke(data)
                content_text = regular_output.content if hasattr(regular_output, 'content') else str(regular_output)
                lines = content_text.strip().split('\n')
                translations = [line.strip() for line in lines if line.strip()]
                return Translation(translation=translations)
            except Exception as fallback_error:
                print(f"Gemini fallback error: {fallback_error}")
                return Translation(translation=["[Translation failed - Gemini error]"])

    try:
        translated_text = translate_text(content)
        if translated_text and hasattr(translated_text, 'translation') and translated_text.translation:
            return {"translated_text": "\n".join(translated_text.translation)}
        else:
            return {"translated_text": "[Translation unavailable - Gemini returned empty response]"}
    except Exception as e:
        print(f"Gemini function error: {e}")
        return {"translated_text": f"[Translation error: {str(e)}]"}


# ========================================
# PARALLEL PROCESSING ASYNC WRAPPERS
# ========================================

async def translate_with_openai_async(content: str, model_name: str, api_key: str, executor: concurrent.futures.ThreadPoolExecutor) -> Dict[str, Any]:
    """
    Async wrapper for OpenAI translation using ThreadPoolExecutor for true parallelism
    """
    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(executor, translate_with_openai, content, model_name, api_key)
        return result
    except Exception as e:
        return {"translated_text": f"[Async OpenAI error: {str(e)}]"}


async def translate_with_claude_async(content: str, model_name: str, api_key: str, executor: concurrent.futures.ThreadPoolExecutor) -> Dict[str, Any]:
    """
    Async wrapper for Claude translation using ThreadPoolExecutor for true parallelism
    """
    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(executor, translate_with_claude, content, model_name, api_key)
        return result
    except Exception as e:
        return {"translated_text": f"[Async Claude error: {str(e)}]"}


async def translate_with_gemini_async(content: str, model_name: str, api_key: str, executor: concurrent.futures.ThreadPoolExecutor) -> Dict[str, Any]:
    """
    Async wrapper for Gemini translation using ThreadPoolExecutor for true parallelism
    """
    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(executor, translate_with_gemini, content, model_name, api_key)
        return result
    except Exception as e:
        return {"translated_text": f"[Async Gemini error: {str(e)}]"}


def get_async_translation_function(model_name: str):
    """
    Get the appropriate async translation function based on model name
    """
    if model_name.startswith("gpt") or model_name.startswith("text-davinci"):
        return translate_with_openai_async
    elif model_name.startswith("claude"):
        return translate_with_claude_async
    elif model_name.startswith("gemini"):
        return translate_with_gemini_async
    else:
        raise ValueError(f"Unsupported model: {model_name}")


# ========================================
# PARALLEL BATCH TRANSLATION
# ========================================

async def translate_batch_parallel_ordered(
    batch_index: int,
    batch_content: str,
    model_name: str,
    api_key: str,
    source_lang: str,
    target_lang: str,
    executor: concurrent.futures.ThreadPoolExecutor
) -> tuple[int, Dict[str, Any]]:
    """
    Translate a single batch in parallel while preserving order through batch_index
    
    Returns:
        tuple[batch_index, result] - batch_index ensures correct ordering
    """
    try:
        # Get the appropriate async translation function
        translate_func = get_async_translation_function(model_name)
        
        # Prepare the prompt for this batch
        source_lines = batch_content.split('\n')
        length = len(source_lines)
        
        from const import SYSTEM_PROMPT
        prompt = (
            f"{SYSTEM_PROMPT}\n"
            f"[Translate the text to {target_lang} which is code for a language. "
            f"the translations should be in an array of strings with the same length as the source text. "
            f"that is {length} translations]\n"
            f"{source_lines}"
        )
        
        # Execute translation in parallel
        result = await translate_func(prompt, model_name, api_key, executor)
        
        # Return with batch_index to maintain order
        return batch_index, {
            "status": "completed",
            "translated_text": result.get("translated_text", ""),
            "batch_index": batch_index
        }
        
    except Exception as e:
        # Return error with batch_index to maintain order
        return batch_index, {
            "status": "failed",
            "error": str(e),
            "batch_index": batch_index,
            "translated_text": f"[Batch {batch_index + 1} failed: {str(e)}]"
        }


async def translate_segments_parallel_ordered(
    segments: list[str],
    model_name: str,
    api_key: str,
    source_lang: str = "bo",
    target_lang: str = "en",
    batch_size: int = 10,
    max_workers: int = 15,
    progress_callback=None
) -> Dict[str, Any]:
    """
    Translate segments in parallel while maintaining exact order
    
    Args:
        segments: List of text segments to translate
        model_name: AI model to use
        api_key: API key for the service
        source_lang: Source language code
        target_lang: Target language code  
        batch_size: Number of segments per batch
        max_workers: Maximum parallel workers
        progress_callback: Optional callback for progress updates
        
    Returns:
        Dict with translated text in original order
    """
    if not segments:
        return {
            "status": "completed",
            "translated_text": "",
            "performance": {"total_time": 0, "parallel_workers": 0}
        }
    
    import time
    start_time = time.time()
    
    # Create batches while maintaining order
    batches = []
    current_batch = []
    
    for segment in segments:
        current_batch.append(segment)
        if len(current_batch) >= batch_size:
            batches.append("\n".join(current_batch))
            current_batch = []
    
    # Add final batch if not empty
    if current_batch:
        batches.append("\n".join(current_batch))
    
    total_batches = len(batches)
    
    # Progress update
    if progress_callback:
        await progress_callback(f"Starting parallel translation of {total_batches} batches with {max_workers} workers")
    
    # Create ThreadPoolExecutor for true parallelism
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Create parallel tasks with batch indices to maintain order
        tasks = []
        for batch_index, batch_content in enumerate(batches):
            task = translate_batch_parallel_ordered(
                batch_index=batch_index,
                batch_content=batch_content,
                model_name=model_name,
                api_key=api_key,
                source_lang=source_lang,
                target_lang=target_lang,
                executor=executor
            )
            tasks.append(task)
        
        # Execute all batches in TRUE PARALLEL
        try:
            # This now runs truly in parallel thanks to ThreadPoolExecutor
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Sort results by batch_index to maintain original order
            ordered_results = {}
            successful_batches = 0
            failed_batches = 0
            
            for result in results:
                if isinstance(result, Exception):
                    print(f"Task exception: {result}")
                    failed_batches += 1
                    continue
                
                batch_index, batch_result = result
                ordered_results[batch_index] = batch_result
                
                if batch_result.get("status") == "completed":
                    successful_batches += 1
                else:
                    failed_batches += 1
                
                # Progress update
                if progress_callback:
                    progress = int(((successful_batches + failed_batches) / total_batches) * 100)
                    await progress_callback(f"Completed batch {batch_index + 1}/{total_batches} ({progress}%)")
            
            # Assemble final translation in correct order
            final_translation_parts = []
            for i in range(total_batches):
                if i in ordered_results:
                    batch_result = ordered_results[i]
                    translated_text = batch_result.get("translated_text", f"[Missing batch {i + 1}]")
                    final_translation_parts.append(translated_text)
                else:
                    final_translation_parts.append(f"[Missing batch {i + 1}]")
            
            final_text = "\n".join(final_translation_parts)
            total_time = time.time() - start_time
            
            # Progress completion
            if progress_callback:
                await progress_callback(f"Parallel translation completed: {successful_batches}/{total_batches} batches in {total_time:.1f}s")
            
            return {
                "status": "completed",
                "translated_text": final_text,
                "performance": {
                    "total_time": total_time,
                    "batches_completed": successful_batches,
                    "batches_failed": failed_batches,
                    "parallel_workers": max_workers,
                    "batches_per_second": total_batches / total_time if total_time > 0 else 0
                }
            }
            
        except Exception as e:
            total_time = time.time() - start_time
            error_msg = f"Parallel translation failed: {str(e)}"
            
            if progress_callback:
                await progress_callback(error_msg)
            
            return {
                "status": "failed",
                "error": error_msg,
                "performance": {
                    "total_time": total_time,
                    "parallel_workers": max_workers
                }
            }
    
     
        
   
