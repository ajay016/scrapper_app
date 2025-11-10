import requests
from bs4 import BeautifulSoup
from urllib.parse import urlencode
import logging
from urllib.parse import urlparse, parse_qs, unquote
import base64
from urllib.parse import urljoin
from playwright.sync_api import sync_playwright
from .playwright_wrapper import playwright_browser
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import asyncio
from playwright.async_api import async_playwright
import random
from math import ceil
import re
from typing import List, Optional
from django.conf import settings







def resolve_bing_ck_url(href):
    try:
        parsed = urlparse(href)
        qs = parse_qs(parsed.query)
        u_vals = qs.get("u", [])
        if u_vals:
            u_raw = u_vals[0]
            import re
            m = re.search(r"(aHR0[0-9A-Za-z_\-=%]+)", u_raw)
            candidate = m.group(1) if m else u_raw
            candidate = candidate.split("&")[0].replace("%3D", "=")
            padding = -len(candidate) % 4
            try:
                decoded = base64.urlsafe_b64decode(candidate + "=" * padding).decode("utf-8", "ignore")
                if decoded.startswith("http"):
                    return decoded
            except Exception:
                pass
    except Exception:
        pass
    return href

# def scrape_bing_results(query, num_results=None):
#     collected = set()

#     with sync_playwright() as p:
#         browser = p.chromium.launch(headless=False)
#         context = browser.new_context(
#             viewport={"width": 1280, "height": 800},
#             user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36",
#             locale="en-US",
#             timezone_id="America/New_York",
#             java_script_enabled=True
#         )
#         page = context.new_page()

#         # Stealth patch (minimal manual)
#         page.add_init_script("""
#             Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
#             Object.defineProperty(navigator, 'languages', {get: () => ['en-US','en']});
#             Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});
#         """)

#         page.goto(f"https://www.bing.com/search?q={query}")
#         time.sleep(random.uniform(2, 4))

#         while True:
#             content = page.content()
#             if "unusual traffic" in content.lower() or "verify your identity" in content.lower():
#                 print("⚠️ CAPTCHA detected! Manual solve or fallback required.")
#                 break

#             try:
#                 page.wait_for_selector("li.b_algo", timeout=15000, state="attached")
#             except:
#                 print("⚠️ No results found or page blocked")
#                 break

#             # Scroll like human
#             for _ in range(random.randint(2, 5)):
#                 page.mouse.wheel(0, random.randint(100, 300))
#                 time.sleep(random.uniform(0.3, 0.8))

#             links = page.query_selector_all("li.b_algo h2 a")
#             new_links = 0
#             for a in links:
#                 href = a.get_attribute("href")
#                 resolved = resolve_bing_ck_url(href) if "bing.com/ck/a" in href else href
#                 if resolved.startswith("http") and resolved not in collected:
#                     collected.add(resolved)
#                     new_links += 1
#                     yield resolved
#                     if num_results and len(collected) >= num_results:
#                         browser.close()
#                         return

#             if new_links == 0:
#                 break

#             # Next page click with human-like movement
#             next_button = page.query_selector("a.sb_pagN")
#             if not next_button:
#                 break
#             box = next_button.bounding_box()
#             if box:
#                 page.mouse.move(box["x"] + box["width"]/2, box["y"] + box["height"]/2, steps=random.randint(5,15))
#                 time.sleep(random.uniform(0.2, 0.5))
#                 next_button.click()
#                 page.wait_for_load_state("networkidle")
#                 time.sleep(random.uniform(1.5, 3.0))

#         browser.close()



async def scrape_bing_results(query, num_results=None):
    collected = set()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36",
            locale="en-US",
            timezone_id="America/New_York",
            java_script_enabled=True
        )
        page = await context.new_page()

        # Stealth patch (minimal manual)
        await page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            Object.defineProperty(navigator, 'languages', {get: () => ['en-US','en']});
            Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});
        """)

        await page.goto(f"https://www.bing.com/search?q={query}")
        await asyncio.sleep(random.uniform(2, 4))

        while True:
            content = await page.content()
            if "unusual traffic" in content.lower() or "verify your identity" in content.lower():
                print("⚠️ CAPTCHA detected! Manual solve or fallback required.")
                break

            try:
                await page.wait_for_selector("li.b_algo", timeout=15000, state="attached")
            except:
                print("⚠️ No results found or page blocked")
                break

            # Scroll like human
            for _ in range(random.randint(2, 5)):
                await page.mouse.wheel(0, random.randint(100, 300))
                await asyncio.sleep(random.uniform(0.3, 0.8))

            links = await page.query_selector_all("li.b_algo h2 a")
            new_links = 0
            for a in links:
                href = await a.get_attribute("href")
                resolved = resolve_bing_ck_url(href) if "bing.com/ck/a" in href else href
                if resolved.startswith("http") and resolved not in collected:
                    collected.add(resolved)
                    new_links += 1
                    yield resolved
                    if num_results and len(collected) >= num_results:
                        await browser.close()
                        return

            if new_links == 0:
                break

            # Next page click with human-like movement
            next_button = await page.query_selector("a.sb_pagN")
            if not next_button:
                break
            box = await next_button.bounding_box()
            if box:
                await page.mouse.move(box["x"] + box["width"]/2, box["y"] + box["height"]/2, steps=random.randint(5,15))
                await asyncio.sleep(random.uniform(0.2, 0.5))
                await next_button.click()
                await page.wait_for_load_state("networkidle")
                await asyncio.sleep(random.uniform(1.5, 3.0))

        await browser.close()


def scrape_duckduckgo_results(query, num_results=None, stop_flag=None):
    from playwright.sync_api import sync_playwright
    import time

    p = sync_playwright().start()
    browser = p.chromium.launch(headless=False)
    context = browser.new_context(
        viewport={"width": 1280, "height": 800},
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
        )
    )
    page = context.new_page()

    try:
        page.goto(f"https://duckduckgo.com/?q={query}&ia=web", timeout=60000)
        page.wait_for_selector("a[data-testid='result-title-a']", timeout=15000)

        collected = set()
        processed_count = 0

        while True:
            if stop_flag and stop_flag.is_set():
                print("⛔ Stop flag detected — closing browser now.")
                return

            all_hrefs = page.eval_on_selector_all(
                "a[data-testid='result-title-a']",
                "elements => elements.map(el => el.href)"
            )
            new_hrefs = all_hrefs[processed_count:]

            if not new_hrefs:
                if stop_flag and stop_flag.is_set():
                    print("⛔ Stop flag detected before loading more results.")
                    return

                # Attempt to click More Results up to 3 times
                clicked = False
                for _ in range(3):
                    more_btn = page.locator("#r1-0 + div a[data-testid='more-results'], #more-results").first
                    if more_btn.count() > 0:
                        try:
                            more_btn.scroll_into_view_if_needed(timeout=3000)
                            more_btn.click()
                            page.wait_for_load_state("networkidle")
                            clicked = True
                            break
                        except Exception:
                            time.sleep(0.5)  # retry
                    else:
                        break

                if clicked:
                    continue  # retry fetching new links

                # Fallback: scroll to bottom to trigger lazy load
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_load_state("networkidle")
                new_count = page.eval_on_selector_all(
                    "a[data-testid='result-title-a']",
                    "elements => elements.map(el => el.href)"
                )
                if len(new_count) == processed_count:
                    break
                else:
                    continue

            for href in new_hrefs:
                if stop_flag and stop_flag.is_set():
                    print("⛔ Stop flag detected inside loop — closing browser now.")
                    return

                if href and href not in collected:
                    collected.add(href)
                    yield href
                    if num_results and len(collected) >= num_results:
                        return

            processed_count = len(all_hrefs)

    except Exception as e:
        print("DuckDuckGo scrape error:", e)
    finally:
        try:
            browser.close()
        except:
            pass
        try:
            p.stop()
        except:
            pass
