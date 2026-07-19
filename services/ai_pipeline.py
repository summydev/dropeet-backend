# services/ai_pipeline.py

import os
import json
import logging
from typing import Optional, List
from openai import OpenAI
from pydantic import ValidationError
from schemas.opportunity import OpportunityList
from services.local_extractor import extract_local   # <--- new import

logger = logging.getLogger(__name__)

LOCAL_CONFIDENCE_THRESHOLD = 0.75  # above this, skip DeepSeek

def extract_opportunity_details_deepseek(cleaned_text: str, html: str = "", url: str = "") -> Optional[List[dict]]:
    """
    Hybrid extraction: tries local extraction first. If confidence is high, returns that.
    Otherwise, falls back to DeepSeek.
    """
    if not cleaned_text:
        logger.warning("No text provided.")
        return None

    # --- STEP 1: Local extraction (if HTML is available) ---
    if html:
        try:
            local_results = extract_local(html, url)
            if local_results and local_results[0].get("_confidence", 0) >= LOCAL_CONFIDENCE_THRESHOLD:
                logger.info(f"✅ Local extraction succeeded with confidence {local_results[0]['_confidence']}. Skipping DeepSeek.")
                # Clean up internal fields before returning
                return [_clean_local_opp(o) for o in local_results]
            else:
                logger.info("Local confidence too low, falling back to DeepSeek.")
        except Exception as e:
            logger.warning(f"Local extraction failed: {e}")

    # --- STEP 2: DeepSeek fallback (unchanged logic) ---
    logger.info("🧠 Passing raw data to DeepSeek...")
    deepseek_key = os.getenv("DEEPSEEK_API_KEY")
    if not deepseek_key:
        logger.error("❌ DEEPSEEK_API_KEY is missing.")
        return None

    client = OpenAI(base_url="https://api.deepseek.com/v1", api_key=deepseek_key)

    system_prompt = (
        "You are an expert data extraction assistant for a career tracking tool. "
        "Analyze the unstructured text and extract every opportunity mentioned into a JSON object "
        "with an 'opportunities' key containing an array of opportunity objects. "
        "CRITICAL RULES TO PREVENT HALLUCINATIONS:\n"
        "1. DO NOT GUESS OR INVENT DATA. Treat the scraped text as absolute law.\n"
        "2. If the application deadline is not explicitly stated, set 'deadline' to null.\n"
        "3. If the organization name is not clear, set it to 'Unknown'.\n"
        "REQUIRED DOCUMENTS: Scan the text for what the applicant needs to submit and return as a 'required_documents' array.\n"
        "Output ONLY valid JSON with no markdown formatting elements or extra tokens."
    )
    user_content = f"Extract the core opportunity details from this data:\n\n{cleaned_text}"

    preferred_models = ["deepseek-chat"]
    for model_name in preferred_models:
        try:
            response = client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content}
                ],
                response_format={"type": "json_object"},
                temperature=0.1
            )
            raw_json = response.choices[0].message.content
            parsed = json.loads(raw_json)

            try:
                validated = OpportunityList(**parsed)
                return [opp.model_dump() for opp in validated.opportunities]
            except ValidationError as ve:
                logger.error(f"Schema validation error: {ve}")
                if isinstance(parsed, dict) and "opportunities" in parsed:
                    return parsed["opportunities"]
                return [parsed] if isinstance(parsed, dict) else None

        except Exception as e:
            if any(str_code in str(e) for str_code in ["429", "503", "502"]):
                logger.warning(f"Model {model_name} throttled, trying next...")
                continue
            logger.error(f"DeepSeek critical error: {e}")
            return None

    logger.error("All DeepSeek models failed.")
    return None

def _clean_local_opp(opp: dict) -> dict:
    """Remove internal keys before returning to the caller."""
    opp.pop("_confidence", None)
    opp.pop("_method", None)
    return opp