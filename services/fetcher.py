import socket
import ipaddress
from urllib.parse import urlparse
import requests

class FetchError(Exception):
    """Base exception for fetcher failures."""
    pass

class SecurityError(FetchError):
    """Raised when a URL violates security policies."""
    pass

class ContentFetcher:
    MAX_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB limit (prevents memory exhaustion)
    TIMEOUT = 10  # 10 seconds max connection/read time

    @staticmethod
    def _is_safe_url(url: str) -> bool:
        """
        DNS resolution and IP checking to prevent SSRF attacks.
        Ensures the URL points to a public, external server.
        """
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            raise SecurityError("Only HTTP and HTTPS protocols are allowed.")
        
        hostname = parsed.hostname
        if not hostname:
            raise SecurityError("Invalid URL format.")

        try:
            # Resolve the IP address behind the hostname
            ip_addr = socket.gethostbyname(hostname)
            ip = ipaddress.ip_address(ip_addr)
        except socket.gaierror:
            raise FetchError(f"Could not resolve hostname: {hostname}")
        except ValueError:
            raise SecurityError("Invalid IP address resolved.")

        # Reject private, loopback, link-local, and reserved IPs
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast:
            raise SecurityError(f"Access to internal IP {ip} is blocked.")
        
        return True

    @classmethod
    def fetch_text(cls, url: str) -> str:
        """
        Safely fetches the text content of a URL.
        """
        # 1. Run the security checks before connecting
        cls._is_safe_url(url)
        
        # 2. Use a session to securely limit redirects
        session = requests.Session()
        session.max_redirects = 3
        
        # 3. Disguise as a standard browser to avoid basic bot blocks
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml"
        }

        try:
            # 4. Use stream=True to prevent loading massive files into memory at once
            response = session.get(url, headers=headers, timeout=cls.TIMEOUT, stream=True)
            response.raise_for_status()

            content = b""
            for chunk in response.iter_content(chunk_size=8192):
                content += chunk
                # 5. Enforce the 5MB size limit mid-download
                if len(content) > cls.MAX_SIZE_BYTES:
                    raise SecurityError("Response payload exceeded the 5MB size limit.")
            
            # Decode the safely downloaded bytes into a string
            return content.decode(response.encoding or 'utf-8', errors='ignore')

        except requests.exceptions.TooManyRedirects:
            raise FetchError("Too many redirects. The URL might be stuck in a loop.")
        except requests.exceptions.RequestException as e:
            raise FetchError(f"Failed to fetch URL: {str(e)}")