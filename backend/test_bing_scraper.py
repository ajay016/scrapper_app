import os
import django
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import urllib.parse
import base64
import requests
import re

# If you want Django models available
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "scraper_backend.settings")
django.setup()


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/116.0.0.0 Safari/537.36"
    )
}


def decode_bing_redirect(url: str) -> str | None:
    """Extract the real URL from a Bing redirect link."""
    if not url:
        return None
    parsed = urllib.parse.urlparse(url)
    qs = urllib.parse.parse_qs(parsed.query)
    if "u" not in qs:
        return None
    u_val = qs["u"][0]

    # Remove any small prefix like 'a1'
    u_val = re.sub(r"^[a-zA-Z0-9]{0,2}", "", u_val)

    # Convert URL-safe base64 to standard base64
    u_val = u_val.replace("-", "+").replace("_", "/")

    # Pad string with '=' to correct length
    padding = 4 - len(u_val) % 4
    if padding < 4:
        u_val += "=" * padding

    try:
        decoded = base64.b64decode(u_val).decode("utf-8", errors="ignore")
        return decoded
    except Exception:
        return None


def scrape_search_results(query, num_results=50):
    """
    Scrape DuckDuckGo HTML search results with pagination.
    Returns a list of result URLs (up to num_results).
    """
    results = []
    base_url = "https://duckduckgo.com/html/"  # correct endpoint
    s = 0

    print("DuckDuckGo URL:", base_url)

    while len(results) < num_results:
        payload = {"q": query, "s": s}
        resp = requests.post(base_url, data=payload, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        links = [a["href"] for a in soup.select("a.result__a")]
        if not links:
            break  # no more results
        results.extend(links)
        s += 50  # DuckDuckGo increments offset by 50

    return results[:num_results]

if __name__ == "__main__":
    links = scrape_search_results("intel core i5", num_results=20)
    for i, link in enumerate(links, 1):
        print(i, link)
