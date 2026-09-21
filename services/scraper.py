# services/scraper.py

import os
import logging
import socket
import ipaddress
from urllib.parse import urlparse
from typing import Tuple, Optional
from curl_cffi import requests as cffi_requests
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
import httpx

logger = logging.getLogger(__name__)

def _validate_url_security(url: str):
    """Prevents SSRF by blocking internal network access."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("Only HTTP/HTTPS allowed.")
    
    try:
        ip_addr = socket.gethostbyname(parsed.hostname)
        ip = ipaddress.ip_address(ip_addr)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast:
            raise ValueError(f"Blocked SSRF attempt to internal IP: {ip}")
    except socket.gaierror:
        raise ValueError(f"Could not resolve hostname: {parsed.hostname}")
    except ValueError:
        raise ValueError("Invalid IP address resolved.")

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

async def fetch_via_httpx(url: str) -> Optional[str]:
    """Lightweight fallback scraper that uses very little RAM."""
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=15.0) as client:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
            }
            response = await client.get(url, headers=headers)
            if response.status_code == 200 and len(response.text) > 200:
                return response.text
    except Exception as e:
        logger.warning(f"httpx fallback failed for {url}: {e}")
    return None

async def playwright_fetch(
    url: str,
    cookies: Optional[dict] = None,
    proxy: Optional[dict] = None
) -> Tuple[Optional[str], Optional[bytes], Optional[str], Optional[str]]:
    # [KEPT FOR FUTURE USE IF YOU UPGRADE SERVER RAM]
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

async def scrape_url_self_built(
    url: str,
    user_cookies: Optional[dict] = None,
    proxy: Optional[dict] = None
) -> Tuple[str, Optional[bytes], Optional[str], str]:
    
    # SECURITY GATE: Enforce SSRF rules
    try:
        _validate_url_security(url)
    except ValueError as e:
        logger.error(f"Security validation failed for {url}: {e}")
        return "", None, None, ""

    # Step 1: Fast curl_cffi (Lightweight - Safe for Render)
    raw_html = await fetch_via_curl_cffi(url)
    if raw_html:
        soup = BeautifulSoup(raw_html, "html.parser")
        cleaned_text = soup.get_text(separator="\n", strip=True)
        return cleaned_text, None, None, raw_html

    # Step 2: httpx fallback (Lightweight - Safe for Render)
    logger.info(f"curl_cffi missed, trying httpx fallback for {url}")
    raw_html = await fetch_via_httpx(url)
    if raw_html:
        soup = BeautifulSoup(raw_html, "html.parser")
        cleaned_text = soup.get_text(separator="\n", strip=True)
        return cleaned_text, None, None, raw_html

    # --- PLAYWRIGHT BYPASSED FOR RENDER FREE TIER ---
    # cookies_to_use = None
    # if "linkedin.com" in url:
    #     cookies_to_use = user_cookies
    #     if not cookies_to_use:
    #         logger.warning("No LinkedIn cookies provided – scraping may fail.")
    #
    # text, img_bytes, img_mime, raw_html = await playwright_fetch(
    #     url, cookies=cookies_to_use, proxy=proxy
    # )
    # if text:
    #     return text, img_bytes, img_mime, raw_html

    logger.error(f"All lightweight methods exhausted for {url}. Playwright disabled.")
    return "", None, None, ""