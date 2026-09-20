# services/tasks.py

import os
import logging
import asyncio
from sqlalchemy.exc import IntegrityError
from database.session import SessionLocal
from database.models import Opportunity, OpportunityStatus, User
from services.scraper import scrape_url_self_built
from services.ai_pipeline import extract_opportunity_details_deepseek
from services.validator import OpportunityValidator 
from config.settings import settings

logger = logging.getLogger(__name__)
scraping_semaphore = asyncio.Semaphore(1)

async def process_link_task(url: str, user_id: int):
    async with scraping_semaphore:
        logger.info(f"🚦 Processing: {url}")

        db = SessionLocal()
        try:
            user = db.query(User).filter(User.id == user_id).first()
            linkedin_cookies = user.linkedin_cookies if user else None

            proxy = None
            if settings.RESIDENTIAL_PROXY_HOST:
                proxy = {
                    "server": settings.RESIDENTIAL_PROXY_HOST,
                    "username": settings.RESIDENTIAL_PROXY_USER,
                    "password": settings.RESIDENTIAL_PROXY_PASS,
                }

            # 1. Secure Fetch
            cleaned_text, _, _, raw_html = await scrape_url_self_built(
                url, user_cookies=linkedin_cookies, proxy=proxy
            )

            if not cleaned_text:
                logger.error(f"❌ No content extracted from {url}")
                return

            # 2. Extract Untrusted Candidates
            candidates = extract_opportunity_details_deepseek(
                cleaned_text, html=raw_html, url=url
            )
            
            if not candidates:
                logger.error("❌ All extraction methods failed")
                return

            # 3. Validate and Save
            for candidate in candidates:
                # Deterministic parse of the untrusted LLM output
                validated = OpportunityValidator.validate(candidate, url)

                # Prevent duplicates via idempotency key
                existing = db.query(Opportunity).filter(
                    Opportunity.idempotency_key == validated.idempotency_key
                ).first()
                
                if existing:
                    logger.info(f"Duplicate prevented for: {validated.title}")
                    continue

                new_opp = Opportunity(
                    user_id=user_id,
                    title=validated.title,
                    organization=validated.organization,
                    summary=validated.summary,
                    source_url=validated.source_url,
                    deadline=validated.deadline,
                    timezone=validated.timezone,
                    location=validated.location,
                    idempotency_key=validated.idempotency_key,
                    confidence=validated.confidence,
                    evidence=validated.evidence,
                    status=OpportunityStatus.PENDING, # Forces user interaction
                    required_documents=validated.required_documents,
                )
                
                db.add(new_opp)
                try:
                    db.commit()
                except IntegrityError:
                    db.rollback()
                    logger.warning(f"Race condition caught on idempotency key for {url}")
        finally:
            db.close()