# services/ai_pipeline.py

import os
import json
import logging
from typing import Optional, List
from openai import OpenAI
from pydantic import ValidationError
from schemas.opportunity import CandidateExtractionList, CandidateOpportunity
from services.local_extractor import extract_local
from config.settings import settings

logger = logging.getLogger(__name__)

LOCAL_CONFIDENCE_THRESHOLD = 0.75 

def extract_opportunity_details_deepseek(cleaned_text: str, html: str = "", url: str = "") -> Optional[List[CandidateOpportunity]]:
    if not cleaned_text:
        logger.warning("No text provided.")
        return None

    # --- STEP 1: Local extraction ---
    if html:
        try:
            local_results = extract_local(html, url)
            if local_results and local_results[0].confidence_score >= LOCAL_CONFIDENCE_THRESHOLD:
                logger.info(f"✅ Local extraction succeeded with confidence {local_results[0].confidence_score}. Skipping DeepSeek.")
                return local_results
            else:
                logger.info("Local confidence too low, falling back to DeepSeek.")
        except Exception as e:
            logger.warning(f"Local extraction failed: {e}")

    # --- STEP 2: DeepSeek fallback ---
    logger.info("🧠 Passing raw data to DeepSeek...")
    deepseek_key = settings.DEEPSEEK_API_KEY
    if not deepseek_key:
        logger.error("❌ DEEPSEEK_API_KEY is missing.")
        return None

    client = OpenAI(base_url="https://api.deepseek.com/v1", api_key=deepseek_key)

    system_prompt = (
        "You are a strict data extraction system. Extract opportunities from the text into a JSON object "
        "with an 'opportunities' array. "
        "CRITICAL RULES TO PREVENT HALLUCINATIONS:\n"
        "1. DO NOT GUESS OR INVENT DATA. Treat the scraped text as absolute law.\n"
        "2. If the application deadline is not explicitly stated, set 'extracted_deadline' to null.\n"
        "3. 'extracted_deadline' MUST be the exact text found in the document (e.g., 'Friday 5PM'). Do not reformat it.\n"
        "4. You MUST provide an 'evidence' dictionary mapping the fields to the exact text snippets that prove them.\n"
        "5. Provide a 'confidence_score' between 0.0 and 1.0.\n"
        "Output ONLY valid JSON with no markdown formatting elements."
    )
    
    user_content = f"Extract details from this data:\n\n{cleaned_text}"
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
                # Validates against the UNTRUSTED candidate schema
                validated = CandidateExtractionList(**parsed)
                return validated.opportunities
            except ValidationError as ve:
                logger.error(f"Schema validation error: {ve}")
                return None

        except Exception as e:
            if any(str_code in str(e) for str_code in ["429", "503", "502"]):
                logger.warning(f"Model {model_name} throttled, trying next...")
                continue
            logger.error(f"DeepSeek critical error: {e}")
            return None

    logger.error("All DeepSeek models failed.")
    return None