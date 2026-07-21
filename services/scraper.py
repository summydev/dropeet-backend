# services/scraper.py

import os
import logging
from typing import Tuple, Optional
from curl_cffi import requests as cffi_requests
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
import httpx

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------
# 1. Lightweight first attempt (TLS fingerprint spoofing)
# --------------------------------------------------------------------
async def fetch_via_curl_cffi(url: str) -> Optional[str]:
    try:
        resp = cffi_requests.get(
            url,
            impersonate="chrome124",
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                "Accept-Language": "en-US,en;q=0.9",
            },
            timeout=15,
        )
        if resp.status_code == 200 and len(resp.text) > 200:
            return resp.text
    except Exception:
        pass
    return None

# --------------------------------------------------------------------
# 2. Playwright fallback (supports cookies & optional proxy)
# --------------------------------------------------------------------
async def playwright_fetch(
    url: str,
    cookies: Optional[dict] = None,
    proxy: Optional[dict] = None
) -> Tuple[Optional[str], Optional[bytes], Optional[str], Optional[str]]:
    """
    Returns (cleaned_text, image_bytes, image_mime, raw_html).
    """
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=["--disable-blink-features=AutomationControlled"]
            )
            context_options = {
                "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            }
            if proxy:
                context_options["proxy"] = proxy

            context = await browser.new_context(**context_options)

            # Inject cookies (e.g., LinkedIn session)
            if cookies:
                domain = ".linkedin.com" if "linkedin.com" in url else None
                if domain:
                    cookie_list = [{"name": k, "value": v, "domain": domain, "path": "/"} for k, v in cookies.items()]
                    await context.add_cookies(cookie_list)

            page = await context.new_page()
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(4000)

            raw_html = await page.content()
            soup = BeautifulSoup(raw_html, "html.parser")
            cleaned_text = soup.get_text(separator="\n", strip=True)

            # Optional image extraction
            img_bytes = None
            img_mime = None
            og_image = await page.query_selector("meta[property='og:image']")
            if og_image:
                img_url = await og_image.get_attribute("content")
                if img_url and img_url.startswith("http"):
                    async with httpx.AsyncClient() as client:
                        resp = await client.get(img_url, timeout=10)
                        if resp.status_code == 200:
                            img_bytes = resp.content
                            img_mime = "image/jpeg" if "jpg" in img_url else "image/png"

            await browser.close()
            return cleaned_text, img_bytes, img_mime, raw_html
    except Exception as e:
        logger.error(f"Playwright fallback failed: {e}")
        return None, None, None, None

# --------------------------------------------------------------------
# 3. Main scraper – returns (cleaned_text, image_bytes, image_mime, raw_html)
# --------------------------------------------------------------------
async def scrape_url_self_built(
    url: str,
    user_cookies: Optional[dict] = None,
    proxy: Optional[dict] = None
) -> Tuple[str, Optional[bytes], Optional[str], str]:
    """
    Self‑built scraper that returns cleaned text, optional image, and the raw HTML
    for use in the local extraction pipeline.
    """
    # Step 1: try fast curl_cffi (works for many static sites)
    raw_html = await fetch_via_curl_cffi(url)
    if raw_html:
        soup = BeautifulSoup(raw_html, "html.parser")
        cleaned_text = soup.get_text(separator="\n", strip=True)
        return cleaned_text, None, None, raw_html

    # Step 2: Playwright with cookies (LinkedIn/Instagram) or without
    cookies_to_use = None
    if "linkedin.com" in url:
        cookies_to_use = user_cookies
        if not cookies_to_use:
            logger.warning("No LinkedIn cookies provided – scraping may fail.")

    text, img_bytes, img_mime, raw_html = await playwright_fetch(
        url, cookies=cookies_to_use, proxy=proxy
    )
    if text:
        return text, img_bytes, img_mime, raw_html

    # Step 3: if everything fails
    logger.error(f"All self‑built methods exhausted for {url}")
    return "", None, None, ""