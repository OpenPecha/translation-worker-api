

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
        print(e)
        raise


def translate_with_claude(content, model_name, api_key):
    """
    Translate text using Anthropic's Claude AI (with robust error handling)
    """
    from langchain_anthropic import ChatAnthropic
    from typing import List
    from pydantic import BaseModel, Field
    import json
    
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
                
                # Try to parse the content as JSON
                try:
                    if hasattr(regular_output, 'content'):
                        content_text = regular_output.content
                    else:
                        content_text = str(regular_output)
                    
                    # Try to extract JSON from the response
                    if '{' in content_text and '}' in content_text:
                        json_start = content_text.find('{')
                        json_end = content_text.rfind('}') + 1
                        json_text = content_text[json_start:json_end]
                        parsed_json = json.loads(json_text)
                        
                        if 'translation' in parsed_json:
                            return Translation(translation=parsed_json['translation'])
                    
                    # If no JSON, treat the whole response as a single translation
                    lines = content_text.strip().split('\n')
                    # Filter out empty lines and clean up
                    translations = [line.strip() for line in lines if line.strip()]
                    return Translation(translation=translations)
                    
                except Exception as parse_error:
                    print(f"Failed to parse Claude response: {parse_error}")
                    # Last resort: return the raw content as a single translation
                    raw_content = str(regular_output)
                    return Translation(translation=[raw_content])
                    
        except Exception as e:
            print(f"Claude translation error: {e}")
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
        output = llm.with_structured_output(Translation).invoke(data)
        return output
    
    try:
        translated_text = translate_text(content)
        print("translated_text: ",translated_text.translation)
        return {"translated_text": "\n".join(translated_text.translation)}
    except Exception as e:
        print(e)
        raise
    
     
        
   
