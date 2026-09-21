# services/scraper.py

import os
import logging
import socket
import ipaddress
from urllib.parse import urlparse
from typing import Tuple, Optional
from curl_cffi import requests as cffi_requests
from bs4 import BeautifulSoup
import httpx

logger = logging.getLogger(__name__)

# Memory safeguard: Max 2MB per page to prevent OOM (Out of Memory) crashes
MAX_PAGE_SIZE = 2 * 1024 * 1024  

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

async def fetch_lean(url: str, cookies: Optional[dict] = None) -> Optional[str]:
    """
    Uses curl_cffi to spoof a real browser's TLS signature without the massive RAM overhead of Playwright.
    Now properly injects session cookies to bypass LinkedIn login walls.
    """
    try:
        # Context manager ensures connections close instantly when done
        with cffi_requests.Session(impersonate="chrome124") as session:
            resp = session.get(
                url,
                headers={
                    "Accept-Language": "en-US,en;q=0.9",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9",
                },
                cookies=cookies, # Inject LinkedIn cookies here
                timeout=10,      # Strict timeout prevents hanging worker threads
                stream=True      # Stream prevents loading massive files into RAM all at once
            )
            
            if resp.status_code != 200:
                logger.warning(f"URL {url} returned status {resp.status_code}")
                # LinkedIn often returns 999 for bot detection.
                return None

            content = b""
            for chunk in resp.iter_content(chunk_size=8192):
                content += chunk
                if len(content) > MAX_PAGE_SIZE:
                    logger.warning(f"Page exceeded 2MB limit. Truncating {url}")
                    break # Protects server RAM by stopping the download

            return content.decode(resp.encoding or 'utf-8', errors='ignore')
            
    except Exception as e:
        logger.error(f"Lean fetch failed for {url}: {e}")
        return None

async def scrape_url_self_built(
    url: str,
    user_cookies: Optional[dict] = None,
    proxy: Optional[dict] = None # Left in for future proxy support
) -> Tuple[str, Optional[bytes], Optional[str], str]:
    
    # 1. SECURITY GATE: Run validation before ANY outbound request
    try:
        _validate_url_security(url)
    except ValueError as e:
        logger.error(f"Security validation failed for {url}: {e}")
        return "", None, None, ""

    # 2. Fetch the raw HTML using our lean, low-RAM client
    # We pass the LinkedIn cookies straight into the fetcher
    cookies_to_use = user_cookies if "linkedin.com" in url else None
    if "linkedin.com" in url and not cookies_to_use:
        logger.warning("No LinkedIn cookies provided – scraping may fail or hit a login wall.")

    raw_html = await fetch_lean(url, cookies=cookies_to_use)
    
    if not raw_html:
        logger.error(f"Failed to fetch HTML for {url}")
        return "", None, None, ""

    soup = BeautifulSoup(raw_html, "html.parser")
    
    # 3. Optional: Grab OpenGraph image for the UI card
    img_bytes, img_mime = None, None
    og_image = soup.find("meta", property="og:image")
    if og_image and og_image.get("content"):
        img_url = og_image["content"]
        if img_url.startswith("http"):
            try:
                async with httpx.AsyncClient() as client:
                    img_resp = await client.get(img_url, timeout=5)
                    if img_resp.status_code == 200:
                        img_bytes = img_resp.content
                        img_mime = "image/jpeg" if "jpg" in img_url.lower() else "image/png"
            except Exception as e:
                logger.warning(f"Could not fetch OG image: {e}")

    # 4. Strip out heavy, useless tags to save tokens when passed to the LLM
    for script_tag in soup(["style", "nav", "footer", "aside"]):
        script_tag.decompose()

    cleaned_text = soup.get_text(separator="\n", strip=True)
    
    return cleaned_text, img_bytes, img_mime, raw_html