import json
import logging
from typing import Optional, List
from openai import OpenAI
from pydantic import ValidationError
from schemas.opportunity import OpportunityData

logger = logging.getLogger(__name__)

def extract_opportunity_details_deepseek(cleaned_text: str) -> Optional[dict]:
    """
    Passes scraped text to DeepSeek to extract structured JSON data.
    Implements a fallback loop across preferred DeepSeek tier endpoints.
    Note: Image parameters removed as DeepSeek API is text-only.
    """
    if not cleaned_text:
        logger.warning("⚠️ No text provided to AI pipeline. Aborting extraction.")
        return None

    logger.info("🧠 Passing raw data to DeepSeek...")
    
    # Initialize OpenAI client with DeepSeek credentials
    # Ensure DEEPSEEK_API_KEY is configured in your environmental variables (.env)
    client = OpenAI(
        base_url="https://api.deepseek.com/v1",
    )
    
    # Build prompt instructions forcing JSON Array structure based on your schemas
    system_prompt = (
        "You are an expert data extraction assistant. Analyze the provided unstructured text "
        "and extract all relevant opportunity configurations (titles, application links, deadlines). "
        "You must output valid JSON matching the expected keys strictly. Do not include markdown blocks."
    )
    
    user_content = f"Extract the core opportunity details from this data:\n\n{cleaned_text}"

    # ---------------------------------------------------------
    # DEEPSEEK MODEL FALLBACK LOOP
    # ---------------------------------------------------------
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
                # Enforce JSON formatting structure natively
                response_format={"type": "json_object"},
                temperature=0.1
            )
            
            raw_json_string = response.choices[0].message.content
            parsed_data = json.loads(raw_json_string)
            
            # Explicitly validate the structure against your Pydantic schema
            try:
                validated_data = OpportunityData(**parsed_data)
                return validated_data.model_dump()
            except ValidationError as ve:
                logger.error(f"❌ Structural validation mismatch against OpportunityData schema: {ve}")
                # Fallback path if deepseek structure missed a key parameter validation 
                return parsed_data
            
        except Exception as e:
            if "429" in str(e) or "503" in str(e) or "502" in str(e):
                logger.warning(f"⚠️ {model_name} is currently throttled or busy. Retrying/Falling back...")
                continue
            else:
                logger.error(f"❌ Critical AI processing exception: {e}")
                return None
                
    logger.error("❌ All targeted DeepSeek models failed or timed out.")
    return None