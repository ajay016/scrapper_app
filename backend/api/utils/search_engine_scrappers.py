import requests
from bs4 import BeautifulSoup
from urllib.parse import urlencode
import logging
import urllib.parse
from urllib.parse import urljoin
from playwright.sync_api import sync_playwright
import time
import random
from typing import List, Optional
from django.conf import settings



# ---------- Scraper: Bing with graceful fallback detection ----------
def scrape_bing_results(query, num_results=100):
    base_url = "https://www.bing.com/search"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    collected = set()
    offset = 0
    failure_count = 0

    while True:
        params = {"q": query, "first": offset}
        url = f"{base_url}?{urlencode(params)}"

        try:
            r = requests.get(url, headers=headers, timeout=15)
            if r.status_code != 200:
                print("Bing HTTP", r.status_code)
                break

            # detect human verification page
            if "Our systems have detected unusual traffic" in r.text or "verify your identity" in r.text:
                print("⚠️ Bing hit human verification challenge.")
                break

            soup = BeautifulSoup(r.text, "html.parser")
            results = soup.select("li.b_algo h2 a")

            if not results:
                failure_count += 1
                if failure_count >= 2:  # stop after 2 consecutive failures
                    break
                time.sleep(1)
                continue

            new_links = []
            for link in results:
                href = link.get("href")
                if href and href.startswith("http") and href not in collected:
                    collected.add(href)
                    new_links.append(href)
                    yield href
                    if num_results and len(collected) >= num_results:
                        return

            if not new_links:
                break

            offset += len(new_links)
            time.sleep(0.6)

        except Exception as e:
            print("Bing scrape error:", e)
            break


# ---------- Scraper: DuckDuckGo (Playwright fallback) ----------
def scrape_duckduckgo_results(query, num_results=50):
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled"])
            page = browser.new_page(viewport={"width": 1280, "height": 800})
            url = f"https://duckduckgo.com/?q={query}&ia=web"
            page.goto(url, timeout=60000)
            page.wait_for_selector("a[data-testid='result-title-a']", timeout=15000)

            collected = set()
            while True:
                links = page.locator("a[data-testid='result-title-a']")
                count = links.count()
                for i in range(count):
                    href = links.nth(i).get_attribute("href")
                    if href and href not in collected:
                        collected.add(href)
                        yield href
                        if len(collected) >= num_results:
                            break
                if len(collected) >= num_results:
                    break

                more_button = page.locator("#more-results")
                if more_button.count() > 0:
                    try:
                        more_button.scroll_into_view_if_needed()
                        more_button.click()
                        page.wait_for_timeout(1000)
                    except Exception:
                        break
                else:
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    page.wait_for_timeout(1000)
                    new_count = page.locator("a[data-testid='result-title-a']").count()
                    if new_count <= count:
                        break

            browser.close()
    except Exception as e:
        print("DuckDuckGo scrape error:", e)