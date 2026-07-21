# services/tasks.py

import os
import logging
import asyncio
from datetime import datetime, timezone
from database.session import SessionLocal
from database.models import Opportunity, OpportunityStatus, User
from services.scraper import scrape_url_self_built
from services.ai_pipeline import extract_opportunity_details_deepseek
from services.google_calendar import sync_to_google_calendar

logger = logging.getLogger(__name__)
scraping_semaphore = asyncio.Semaphore(1)

async def process_link_task(url: str, user_id: int, auto_sync: bool):
    async with scraping_semaphore:
        logger.info(f"🚦 Processing: {url}")

        # 1. Get the user's saved LinkedIn cookies (if any)
        db = SessionLocal()
        try:
            user = db.query(User).filter(User.id == user_id).first()
            linkedin_cookies = user.linkedin_cookies if user else None
        finally:
            db.close()

        # 2. Configure proxy (optional – if you have one)
        proxy = None
        if os.getenv("RESIDENTIAL_PROXY_HOST"):
            proxy = {
                "server": os.getenv("RESIDENTIAL_PROXY_HOST"),
                "username": os.getenv("RESIDENTIAL_PROXY_USER"),
                "password": os.getenv("RESIDENTIAL_PROXY_PASS"),
            }

        # 3. Scrape using self‑built stack
        cleaned_text, _, _, raw_html = await scrape_url_self_built(
            url,
            user_cookies=linkedin_cookies,
            proxy=proxy
        )

        if not cleaned_text:
            logger.error(f"❌ No content extracted from {url}")
            return

        # 4. Hybrid AI extraction (local first, then DeepSeek fallback)
        extracted = extract_opportunity_details_deepseek(
            cleaned_text,
            html=raw_html,        # pass raw HTML for local extraction
            url=url
        )
        if not extracted:
            logger.error("❌ All extraction methods failed")
            return

        # 5. Save to DB and optionally sync (same as before)
        db = SessionLocal()
        try:
            for opp_data in extracted:
                parsed_deadline = None
                if opp_data.get("deadline"):
                    try:
                        parsed_deadline = datetime.strptime(
                            opp_data["deadline"], "%Y-%m-%d"
                        ).replace(tzinfo=timezone.utc)
                    except ValueError:
                        logger.warning(
                            f"Invalid deadline string: {opp_data.get('deadline')}"
                        )

                new_opp = Opportunity(
                    user_id=user_id,
                    title=opp_data.get("title", "Unknown Opportunity"),
                    organization=opp_data.get("organization"),
                    deadline=parsed_deadline,
                    summary=opp_data.get("summary"),
                    source_url=url,
                    status=OpportunityStatus.PENDING,
                    required_documents=opp_data.get("required_documents", []),
                )
                db.add(new_opp)
                db.commit()
                db.refresh(new_opp)

                if auto_sync and new_opp.deadline:
                    try:
                        sync_to_google_calendar(new_opp, db)
                        new_opp.status = OpportunityStatus.ACTIONED
                        db.commit()
                    except Exception as e:
                        logger.error(f"Calendar sync error: {e}")
        finally:
            db.close()