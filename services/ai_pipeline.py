import json
import logging
from typing import Optional
from google import genai
from google.genai import types
from schemas.opportunity import OpportunityData

logger = logging.getLogger(__name__)

def extract_opportunity_details(cleaned_text: str, image_bytes: bytes = None, image_mime: str = None) -> Optional[dict]:
    """
    Passes scraped text and images to Gemini to extract structured JSON data.
    Implements a multi-tier fallback loop to handle rate limits.
    """
    if not cleaned_text:
        logger.warning("⚠️ No text provided to AI pipeline. Aborting extraction.")
        return None

    logger.info("🧠 Passing raw data to Gemini...")
    client = genai.Client()
    contents = [f"Extract the core opportunity details from this data:\n\n{cleaned_text}"]
    
    if image_bytes and image_mime:
        contents.append(types.Part.from_bytes(data=image_bytes, mime_type=image_mime))
    
    # ---------------------------------------------------------
    # MULTI-TIER FALLBACK LOOP
    # ---------------------------------------------------------
    preferred_models = ["gemini-2.5-flash-lite", "gemini-1.5-flash"]
    
    for model_name in preferred_models:
        try:
            logger.info(f"🔄 Attempting extraction with {model_name}...")
            response = client.models.generate_content(
                model=model_name,
                contents=contents,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=OpportunityData,
                    temperature=0.1 
                ),
            )
            
            # Gemini returns a JSON string based on our schema, parse it into a dict
            return json.loads(response.text)
            
        except Exception as e:
            # Catch both 503 Unavailable and 429 Too Many Requests
            if "503" in str(e) or "UNAVAILABLE" in str(e) or "429" in str(e):
                logger.warning(f"⚠️ {model_name} is busy or rate-limited. Falling back...")
                continue
            else:
                logger.error(f"❌ Critical AI error: {e}")
                return None
                
    logger.error("❌ All AI models failed or timed out.")
    return None