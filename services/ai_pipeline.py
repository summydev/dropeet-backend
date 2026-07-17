import os
import json
import logging
from typing import Optional, List
from openai import OpenAI
from pydantic import ValidationError
from schemas.opportunity import OpportunityList

logger = logging.getLogger(__name__)

def extract_opportunity_details_deepseek(cleaned_text: str) -> Optional[List[dict]]:
    """
    Passes scraped text to DeepSeek to extract structured JSON data matching OpportunityList.
    Always returns a list of opportunities (even if it contains only one item).
    """
    if not cleaned_text:
        logger.warning("⚠️ No text provided to AI pipeline. Aborting extraction.")
        return None

    logger.info("🧠 Passing raw data to DeepSeek...")
    
    # 1. Grab your DeepSeek key from the environment variables
    deepseek_key = os.getenv("DEEPSEEK_API_KEY")
    
    if not deepseek_key:
        logger.error("❌ DEEPSEEK_API_KEY is missing from environment variables.")
        return None

    # 2. Explicitly pass the key to the client
    client = OpenAI(
        base_url="https://api.deepseek.com/v1",
        api_key=deepseek_key
    )
    
    system_prompt = (
        "You are an expert data extraction assistant for a career tracking tool. "
        "Analyze the unstructured text and extract every opportunity mentioned into a JSON object "
        "with an 'opportunities' key containing an array of opportunity objects. "
        "CRITICAL RULES TO PREVENT HALLUCINATIONS:\n"
        "1. DO NOT GUESS OR INVENT DATA. Treat the scraped text as absolute law.\n"
        "2. If the application deadline is not explicitly stated, you MUST set 'deadline' to null. "
        "Do not guess based on the posting date or standard timeframes.\n"
        "3. If the organization name is not clear, set it to 'Unknown'.\n"
        "REQUIRED DOCUMENTS:\n"
        "Scan the text for what the applicant needs to submit. Return this as a 'required_documents' "
        "key containing an array of strings (e.g., ['Resume', 'Cover Letter', 'Transcript']). "
        "If none are mentioned, return an empty array [].\n"
        "Output ONLY valid JSON with no markdown formatting elements or extra conversational tokens."
    )
    
    user_content = f"Extract the core opportunity details from this data:\n\n{cleaned_text}"
    preferred_models = ["deepseek-chat"]
    
    for model_name in preferred_models:
        try:
            logger.info(f"🔄 Attempting extraction with {model_name}...")
            
            response = client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content}
                ],
                response_format={"type": "json_object"},
                temperature=0.1
            )
            
            raw_json_string = response.choices[0].message.content
            parsed_data = json.loads(raw_json_string)
            
            # Use our unified container validation wrapper
            try:
                validated_container = OpportunityList(**parsed_data)
                return [opp.model_dump() for opp in validated_container.opportunities]
            except ValidationError as ve:
                logger.error(f"❌ Structural validation mismatch against OpportunityList schema: {ve}")
                # Fallback extraction parsing step if deepseek returns a direct array configuration object
                if isinstance(parsed_data, dict) and "opportunities" in parsed_data:
                    return parsed_data["opportunities"]
                return [parsed_data] if isinstance(parsed_data, dict) else None
            
        except Exception as e:
            if "429" in str(e) or "503" in str(e) or "502" in str(e):
                logger.warning(f"⚠️ {model_name} is currently throttled or busy. Retrying/Falling back...")
                continue
            else:
                logger.error(f"❌ Critical AI processing exception: {e}")
                return None
                
    logger.error("❌ All targeted DeepSeek models failed or timed out.")
    return None