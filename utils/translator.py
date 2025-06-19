

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
        logger.error(f"OpenAI translation error: {str(e)}")
        raise


def translate_with_claude(content, model_name, api_key):
    """
    Translate text using Anthropic's Claude AI (with input validation)
    """
    from langchain_anthropic import ChatAnthropic
    from typing import TypedDict, List
    from pydantic import BaseModel, Field
    llm = ChatAnthropic(model=model_name, temperature=0,api_key=api_key)
    # Validate and convert content to string
    
    class Translation(BaseModel):
        translation: List[str] = Field(description="List of translations of the sourcetext")

    def translate_text(data):
        output = llm.with_structured_output(Translation).invoke(data)
        return output
    try:
        translated_text = translate_text(content)
        return {"translated_text": "\n".join(translated_text.translation)}
    except Exception as e:
        print(e)
        raise
    
     
        
    # except AttributeError as e:
    #     # Specific handling for API client attribute errors (e.g., 'Anthropic' object has no attribute 'messages')
    #     raise ValueError(f"API client configuration error: {str(e)}")
        
    # except ValueError as e:
    #     # Handle value errors, including API key issues
    #     raise
        
    # except Exception as e:
    #     # General error handling
    #     logger.error(f"Claude AI translation error: {str(e)}")
    #     logger.error(f"Content type: {type(content)}, Content length: {len(content) if isinstance(content, str) else 'N/A'}")
    #     raise
