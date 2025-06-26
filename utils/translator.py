

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
    
     
        
   
