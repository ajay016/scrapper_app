import requests
from bs4 import BeautifulSoup
import logging
import urllib.parse
from urllib.parse import urljoin
from playwright.sync_api import sync_playwright
import time
import random
from typing import List, Optional
from django.conf import settings



RESULT_LINK_SELECTOR = "a[data-testid='result-title-a']"

# possible "More results" selectors (cover variations)
MORE_SELECTORS = [
    "a.result--more__btn",     # expected
    "a.result--more",          # variant
    "a[data-testid='result-more']",  # hypothetical
    "div.result--more a",      # variant
    "a#rld-cta",               # possible id
    "a.load-more",             # fallback
]







logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)   # change to INFO in production

# HEADERS = {
#     "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
#                   "AppleWebKit/537.36 (KHTML, like Gecko) "
#                   "Chrome/116.0.0.0 Safari/537.36",
#     "Accept-Language": "en-US,en;q=0.9",
#     "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
#     "Referer": "https://www.bing.com/",
#     "Connection": "keep-alive",
# }

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/116.0.0.0 Safari/537.36"
    )
}


# def google_search(query, num_results=20):
#     """Fetch up to `num_results` links using Google Custom Search API with pagination"""
#     url = "https://www.googleapis.com/customsearch/v1"
#     results = []
#     start = 1

#     while len(results) < num_results:
#         params = {
#             "key": settings.GOOGLE_API_KEY,
#             "cx": settings.GOOGLE_SEARCH_ENGINE_ID,
#             "q": query,
#             "num": min(10, num_results - len(results)),  # API max 10
#             "start": start,
#         }
#         response = requests.get(url, params=params)
#         response.raise_for_status()
#         data = response.json()
#         items = data.get("items", [])
#         if not items:
#             break
#         results.extend(item["link"] for item in items)
#         start += 10
        
#     print('search results in google search: ', results)

#     return results[:num_results]


# def scrape_bing_results(query, num_results=50, pause=1.5, verbose=False):
#     """
#     Scrape Bing search results with pagination (first=1,11,21...).
#     Returns up to `num_results` cleaned absolute URLs.
#     """
#     results = []
#     base_url = "https://www.bing.com/search"
#     # Bing 'first' param expects values: 1 (page1), 11 (page2), 21 (page3)...
#     first = 1

#     while len(results) < num_results:
#         params = {"q": query, "first": first}
#         if verbose:
#             logger.debug("Requesting %s params=%s", base_url, params)

#         resp = requests.get(base_url, params=params, headers=HEADERS, timeout=15)
#         if verbose:
#             logger.debug("Status: %s", resp.status_code)

#         resp.raise_for_status()
#         text = resp.text

#         # quick checks for blocking / captcha / unusual traffic
#         blocking_signals = [
#             "Our systems have detected unusual traffic",
#             "To continue, please verify",
#             "detected unusual traffic from your",  # part-matches
#             "are you a human",
#             "Why did this happen?",
#         ]
#         lower = text.lower()
#         if any(sig.lower() in lower for sig in blocking_signals):
#             # Save sample HTML for debugging
#             with open("bing_blocked_sample.html", "w", encoding="utf-8") as f:
#                 f.write(text[:100000])  # save first 100k chars
#             raise RuntimeError("Bing blocked the request — captcha/unusual-traffic detected. "
#                                "Saved sample to bing_blocked_sample.html")

#         soup = BeautifulSoup(text, "html.parser")

#         # try a few selectors (bings DOM can vary)
#         candidate_selectors = [
#             "li.b_algo h2 a",   # most common
#             ".b_algo h2 a",
#             "h2 a",             # fallback
#             "a[href^='http']"   # last resort, might include many non-result links
#         ]

#         anchors = []
#         for sel in candidate_selectors:
#             anchors = soup.select(sel)
#             if anchors:
#                 if verbose:
#                     logger.debug("Selector matched: %s -> %d anchors", sel, len(anchors))
#                 break

#         # Optional debugging: if nothing matched, dump a small snippet for inspection
#         if not anchors:
#             if verbose:
#                 logger.debug("No anchors found with known selectors. Dumping <main> snippet for debug.")
#                 main = soup.find("main") or soup
#                 snippet = getattr(main, "prettify", lambda: str(main))()[:5000]
#                 with open("bing_no_anchors_snippet.html", "w", encoding="utf-8") as f:
#                     f.write(snippet)
#             break

#         # extract and normalize links
#         page_links = []
#         for a in anchors:
#             href = a.get("href")
#             if not href:
#                 continue
#             # normalize relative links
#             if href.startswith("/"):
#                 href = urljoin("https://www.bing.com", href)
#             # filter out some common non-content patterns
#             if href.startswith("http") and not href.lower().endswith((".jpg", ".png", ".gif", ".pdf", ".zip")):
#                 page_links.append(href)

#         if not page_links:
#             if verbose:
#                 logger.debug("No candidate page links found for page starting at %d", first)
#             break

#         # append and dedupe on-the-fly
#         for u in page_links:
#             if u not in results:
#                 results.append(u)
#             if len(results) >= num_results:
#                 break

#         if verbose:
#             logger.debug("Collected %d results (total)", len(results))

#         # increment to next results page
#         first += 10  # 1 -> 11 -> 21 ...
#         time.sleep(pause)

#     return results[:num_results]




# def scrape_google_search(query):
#     all_links = []
    
#     with sync_playwright() as p:
#         # Launch browser with stealthier settings
#         # Use --no-sandbox to avoid issues in some environments
#         browser = p.chromium.launch(headless=False, args=['--no-sandbox'])
        
#         # Create a new browser context with a realistic user-agent and viewport
#         context = browser.new_context(
#             user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36",
#             viewport={"width": 1280, "height": 720}
#         )
#         page = context.new_page()
        
#         # Inject JavaScript to hide automation properties
#         page.evaluate('''
#             Object.defineProperty(navigator, 'webdriver', {
#               get: () => undefined
#             })
#         ''')

#         start = 0
#         while True:
#             url = f"https://www.google.com/search?q={query}&start={start}"
            
#             try:
#                 # Use a more flexible wait condition
#                 page.goto(url, wait_until="domcontentloaded")
                
#                 # Check for a CAPTCHA element (common selectors for "I'm not a robot")
#                 if page.locator('div#recaptcha').is_visible() or page.locator('div#g-recaptcha').is_visible():
#                     print("CAPTCHA detected. Cannot proceed.")
#                     break
                
#                 # Check for a "Sorry" page message
#                 if "Sorry for the interruption" in page.content():
#                     print("Google is blocking access. Cannot proceed.")
#                     break

#                 # Wait for at least one result to appear. This is critical.
#                 page.wait_for_selector("div.g a:has(h3)", timeout=10000)
                
#                 # New, more reliable selector (as of late 2023) for organic links
#                 links_on_page = page.locator("div.g a:has(h3)").all()
                
#                 if not links_on_page:
#                     print("No more results found. Stopping.")
#                     break
                
#                 for link_element in links_on_page:
#                     href = link_element.get_attribute("href")
#                     if href:
#                         all_links.append(href)
                
#                 start += 10
#                 time.sleep(random.uniform(2, 5))
                
#             except Exception as e:
#                 print(f"An error occurred: {e}. It's possible the selector is outdated or you've been blocked.")
#                 break
        
#         browser.close()
    
#     return all_links


# def scrape_search_results(query, num_results=50):
#     results = []
#     base_url = "https://html.duckduckgo.com/html/"
#     s = 0

#     while len(results) < num_results:
#         payload = {"q": query, "s": s}
#         resp = requests.post(base_url, data=payload, headers=HEADERS, timeout=10)
#         resp.raise_for_status()

#         html = resp.text
#         print("DEBUG HTML snippet:", html[:20000])  # check what we actually got

#         soup = BeautifulSoup(html, "html.parser")
#         links = [a["href"] for a in soup.find_all("a", class_="result__a")]

#         print(f"Fetched {len(links)} links at offset {s}")

#         if not links:
#             break

#         results.extend(links)
#         s += 50

#     return results[:num_results]

# def scrape_search_results(query, num_results=50):
#     results = []
#     print(f"[DEBUG] Starting DuckDuckGo search for: {query}, limit={num_results}")

#     try:
#         with sync_playwright() as p:
#             print("[DEBUG] Launching Chromium browser...")
#             browser = p.chromium.launch(headless=False)
#             page = browser.new_page()
#             url = f"https://duckduckgo.com/?q={query}&ia=web"
#             print(f"[DEBUG] Navigating to: {url}")
#             page.goto(url, timeout=60000)

#             # Wait for initial results
#             page.wait_for_selector("a[data-testid='result-title-a']", timeout=15000)

#             while True:
#                 # Collect all current results
#                 links = page.locator("a[data-testid='result-title-a']")
#                 link_count = links.count()
#                 print(f"[DEBUG] Found {link_count} total links so far")

#                 for i in range(min(link_count, num_results)):
#                     href = links.nth(i).get_attribute("href")
#                     if href and href not in results:
#                         results.append(href)
#                         print(f"[DEBUG] Collected: {href}")

#                 # Stop if we already have enough
#                 if len(results) >= num_results:
#                     break

#                 # Check if "More results" button exists
#                 if page.locator("#more-results").is_visible():
#                     print("[DEBUG] Clicking 'More results'...")
#                     page.click("#more-results")
#                     page.wait_for_timeout(2000)  # wait for results to load
#                 else:
#                     print("[DEBUG] No more 'More results' button found")
#                     break

#             browser.close()
#             print("[DEBUG] Browser closed.")

#     except Exception as e:
#         print(f"[ERROR] Exception in scrape_search_results: {e}", flush=True)
#         import traceback
#         traceback.print_exc()

#     print(f"[DEBUG] Returning {len(results)} results.")
#     return results



def scrape_search_results(query, num_results=50):
    results = []
    print(f"[DEBUG] Starting DuckDuckGo search for: {query}, limit={num_results}")

    try:
        with sync_playwright() as p:
            print("[DEBUG] Launching Chromium browser (headless)...")
            browser = p.chromium.launch(
                headless=False,
                args=["--disable-blink-features=AutomationControlled"]
            )
            page = browser.new_page(viewport={"width": 1280, "height": 800})

            url = f"https://duckduckgo.com/?q={query}&ia=web"
            print(f"[DEBUG] Navigating to: {url}")
            page.goto(url, timeout=60000)

            # Wait for initial results
            page.wait_for_selector("a[data-testid='result-title-a']", timeout=15000)

            while True:
                # Collect all current results
                links = page.locator("a[data-testid='result-title-a']")
                link_count = links.count()
                print(f"[DEBUG] Found {link_count} links so far")

                for i in range(link_count):
                    href = links.nth(i).get_attribute("href")
                    if href and href not in results:
                        results.append(href)
                        print(f"[DEBUG] Collected: {href}")
                        if len(results) >= num_results:
                            break

                if len(results) >= num_results:
                    break

                # Check if "More results" button exists and is visible
                more_button = page.locator("#more-results")
                if more_button.count() > 0:
                    try:
                        more_button.scroll_into_view_if_needed()
                        more_button.click()
                        print("[DEBUG] Clicked 'More results', waiting for new results...")
                        page.wait_for_timeout(2000)  # wait for new results to load
                    except Exception as e:
                        print(f"[DEBUG] Could not click 'More results': {e}")
                        break
                else:
                    print("[DEBUG] No more 'More results' button found")
                    break

            browser.close()
            print("[DEBUG] Browser closed.")

    except Exception as e:
        print(f"[ERROR] Exception in scrape_search_results: {e}", flush=True)
        import traceback
        traceback.print_exc()

    print(f"[DEBUG] Returning {len(results)} results.")
    return results


# def scrape_search_results(query, num_results=50):
#     results = []
#     print(f"[DEBUG] Starting Google search for: {query}, limit={num_results}")

#     try:
#         with sync_playwright() as p:
#             print("[DEBUG] Launching Chromium browser...")
#             browser = p.chromium.launch(headless=False)
#             page = browser.new_page()
#             url = f"https://www.google.com/search?q={query}"
#             print(f"[DEBUG] Navigating to: {url}")
#             page.goto(url, timeout=60000)

#             while True:
#                 # Wait for search results to appear
#                 page.wait_for_selector("div#search a h3", timeout=15000)

#                 # Collect current links
#                 links = page.locator("div#search a h3")
#                 for i in range(links.count()):
#                     href = links.nth(i).evaluate("el => el.parentElement.href")
#                     if href and href not in results:
#                         results.append(href)
#                         print(f"[DEBUG] Collected: {href}")
#                     if len(results) >= num_results:
#                         break

#                 if len(results) >= num_results:
#                     break

#                 # Check for "Next" button
#                 next_button = page.locator("#pnnext")
#                 if next_button.is_visible():
#                     print("[DEBUG] Clicking 'Next'...")
#                     next_button.click()
#                     page.wait_for_timeout(2000)  # wait for next page
#                 else:
#                     print("[DEBUG] No more 'Next' button found")
#                     break

#             browser.close()
#             print("[DEBUG] Browser closed.")

#     except Exception as e:
#         print(f"[ERROR] Exception in scrape_google_search: {e}", flush=True)
#         import traceback
#         traceback.print_exc()

#     print(f"[DEBUG] Returning {len(results)} results.")
#     return results