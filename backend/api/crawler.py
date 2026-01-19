import time
import json
import threading
import logging
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin, urlparse

import redis
import requests
from bs4 import BeautifulSoup
from django.conf import settings

logger = logging.getLogger(__name__)


class FastURLCrawler:
    def __init__(self, session_id, base_url, max_depth=2, filters=None, max_workers=5):
        self.session_id = session_id
        self.base_url = base_url
        self.max_depth = max_depth

        # 1) Redis
        redis_url = getattr(settings, "REDIS_URL", "redis://localhost:6379/0")
        self.r = redis.from_url(redis_url, decode_responses=True)
        
        self.root_domain = self._norm_domain(urlparse(base_url).netloc)

        # 2) State
        self.visited_urls = set()
        self.all_unique_urls = set()

        self.is_running = True
        self._stopped_by_user = False

        self.base_domain = urlparse(base_url).netloc
        self.filters = filters or {}

        self.max_workers = max_workers
        self.executor = ThreadPoolExecutor(max_workers=self.max_workers)
        self.url_lock = threading.Lock()

        self.found_links = []

        # Buffering for results (helps frontend)
        self._result_buffer = []
        self._last_result_flush = time.time()
        self._result_flush_size = 50
        self._result_flush_interval = 0.5

        # 3) Networking (requests + headers)
        self.session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=max_workers, pool_maxsize=max_workers * 2
        )
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
            }
        )

        # 4) Queue / Rate limit
        self.queue = deque([(self.base_url, 0)])
        self.last_request_time = 0
        self.min_request_interval = 0.05

        # 5) Initialize Redis keys
        self.r.set(f"crawler:status:{self.session_id}", "running", ex=86400)
        self.r.set(
            f"crawler:stats:{self.session_id}",
            json.dumps(
                {
                    "total_found": 0,
                    "pages_crawled": 0,
                    "errors": 0,
                    "filtered_links": 0,
                    "beautifulsoup_success": 0,
                    "selenium_fallback": 0,
                    "duplicates_skipped": 0,
                    "parallel_workers": self.max_workers,
                }
            ),
            ex=86400,
        )

    # -------------------------
    # Utilities
    # -------------------------

    def rate_limit(self):
        current_time = time.time()
        elapsed = current_time - self.last_request_time
        if elapsed < self.min_request_interval:
            time.sleep(self.min_request_interval - elapsed)
        self.last_request_time = time.time()

    def get_status(self):
        return self.r.get(f"crawler:status:{self.session_id}")
    
    
    def _norm_domain(self, netloc: str) -> str:
        netloc = (netloc or "").lower().strip()
        if netloc.startswith("www."):
            netloc = netloc[4:]
        return netloc

    def _is_internal_domain(self, netloc: str) -> bool:
        base = self.root_domain
        cur = self._norm_domain(netloc)

        if not base or not cur:
            return False

        # exact match
        if cur == base:
            return True

        # allow subdomains like m.imdb.com
        if cur.endswith("." + base):
            return True

        return False


    def check_pause(self):
        """
        Blocks when paused.
        Stops immediately when stopped.
        """
        while True:
            status = self.get_status()

            if status == "stopped":
                self.is_running = False
                self._stopped_by_user = True
                return False

            if status == "paused":
                time.sleep(1)
                continue

            return True

    def get_redis_stats(self):
        stats_raw = self.r.get(f"crawler:stats:{self.session_id}")
        return json.loads(stats_raw) if stats_raw else {}

    def update_redis_stats(self, key_name, increment=1):
        """
        Update stats JSON atomically-ish with lock.
        """
        with self.url_lock:
            stats = self.get_redis_stats()
            stats[key_name] = stats.get(key_name, 0) + increment
            self.r.set(f"crawler:stats:{self.session_id}", json.dumps(stats), ex=86400)
            return stats

    def should_follow_link(self, link):
        """
        Strict link filter (internal links only).
        """
        if not self.filters:
            return link.get("is_internal", False)

        try:
            url = link.get("url", "")
            is_internal = link.get("is_internal", False)

            case_sensitive = (
                self.filters.get("caseSensitive")
                or self.filters.get("case_sensitive")
                or False
            )

            # 1) block external
            if not is_internal:
                return False

            check_url = url if case_sensitive else url.lower()

            # 2) URL CONTAINS
            url_contains_raw = self.filters.get("urlContains") or self.filters.get(
                "url_contains"
            )
            if url_contains_raw:
                if isinstance(url_contains_raw, list):
                    keywords = [str(k).strip() for k in url_contains_raw if str(k).strip()]
                else:
                    keywords = [
                        k.strip() for k in str(url_contains_raw).split(",") if k.strip()
                    ]

                if keywords:
                    match_found = any(
                        (k if case_sensitive else k.lower()) in check_url for k in keywords
                    )
                    if not match_found:
                        return False

            # 3) URL EXCLUDES
            url_excludes_raw = self.filters.get("urlExcludes") or self.filters.get(
                "url_excludes"
            )
            if url_excludes_raw:
                if isinstance(url_excludes_raw, list):
                    excludes = [str(ex).strip() for ex in url_excludes_raw if str(ex).strip()]
                else:
                    excludes = [
                        ex.strip() for ex in str(url_excludes_raw).split(",") if ex.strip()
                    ]

                for exclude in excludes:
                    check_ex = exclude if case_sensitive else exclude.lower()
                    if check_ex in check_url:
                        return False

            # 4) TEXT CONTAINS
            text_contains_raw = self.filters.get("textContains") or self.filters.get(
                "text_contains"
            )
            if text_contains_raw:
                text = link.get("text", "")
                check_text = text if case_sensitive else text.lower()

                if isinstance(text_contains_raw, list):
                    tks = [str(t).strip() for t in text_contains_raw if str(t).strip()]
                else:
                    tks = [t.strip() for t in str(text_contains_raw).split(",") if t.strip()]

                if tks:
                    match_found = any(
                        (tk if case_sensitive else tk.lower()) in check_text for tk in tks
                    )
                    if not match_found:
                        return False

            return True

        except Exception as e:
            logger.error(f"Filter Error on {link.get('url')}: {e}")
            return False

    # -------------------------
    # Results buffer push
    # -------------------------

    def add_result(self, result):
        """
        Buffer results and flush in batches.
        If stopped_by_user: don't send anything anymore.
        """
        if self._stopped_by_user:
            return
        if not self.session_id:
            return

        self._result_buffer.append(result)
        now = time.time()

        if (
            len(self._result_buffer) >= self._result_flush_size
            or (now - self._last_result_flush) >= self._result_flush_interval
        ):
            try:
                pipe = self.r.pipeline()
                for res in self._result_buffer:
                    pipe.rpush(f"crawler:results:{self.session_id}", json.dumps(res))
                pipe.execute()
            except Exception as e:
                logger.error(f"Failed to flush result buffer: {e}")
            finally:
                self._result_buffer = []
                self._last_result_flush = time.time()

    def flush_buffer_now(self):
        """
        Force flush buffered results (for completion).
        """
        if self._stopped_by_user:
            return

        try:
            if self._result_buffer:
                pipe = self.r.pipeline()
                for res in self._result_buffer:
                    pipe.rpush(f"crawler:results:{self.session_id}", json.dumps(res))
                pipe.execute()
                self._result_buffer = []
        except Exception as e:
            logger.error(f"Force flush failed: {e}")

    # -------------------------
    # Crawl main
    # -------------------------

    def crawl(self):
        try:
            # Make sure executor is alive
            self.executor.submit(lambda: None)
        except Exception:
            self.executor = ThreadPoolExecutor(max_workers=self.max_workers)

        try:
            batch_size = 10

            while self.queue and self.is_running:
                self.check_pause()
                if not self.is_running:
                    break

                current_batch = []
                while self.queue and len(current_batch) < batch_size:
                    url, depth = self.queue.popleft()

                    if url not in self.visited_urls and (
                        self.max_depth is None or depth < self.max_depth
                    ):
                        current_batch.append((url, depth))

                if not current_batch:
                    continue

                new_links = self.process_batch_parallel(current_batch)

                # Add new links to queue
                for link in new_links:
                    if not self.is_running:
                        break

                    if link["url"] not in self.visited_urls and (
                        self.max_depth is None
                        or link.get("depth", 0) < self.max_depth
                    ):
                        if self.should_follow_link(link):
                            self.queue.append((link["url"], link.get("depth", 0)))
                        else:
                            self.update_redis_stats("filtered_links", 1)

                if len(self.visited_urls) % 100 == 0:
                    stats = self.get_redis_stats()
                    self.add_result(
                        {
                            "type": "progress",
                            "visited": len(self.visited_urls),
                            "found": stats.get("total_found", 0),
                            "queued": len(self.queue),
                            "filtered": stats.get("filtered_links", 0),
                            "message": f"Progress: {len(self.visited_urls)} pages, {stats.get('total_found', 0)} links, {len(self.queue)} queued",
                        }
                    )

        except Exception as e:
            if self.is_running:
                logger.error(f"Crawling error: {e}")
                self.add_result({"type": "error", "message": f"Crawling error: {str(e)}"})
        finally:
            self.stop()

    def process_batch_parallel(self, url_batch):
        all_new_links = []

        with self.url_lock:
            for url, _depth in url_batch:
                self.visited_urls.add(url)

        try:
            futures = {
                self.executor.submit(self.process_single_page, url, depth): (url, depth)
                for url, depth in url_batch
            }

            for future in as_completed(futures):
                if not self.is_running:
                    break

                url, depth = futures[future]
                try:
                    new_links = future.result(timeout=20)
                    if self.is_running:
                        all_new_links.extend(new_links)
                        with self.url_lock:
                            self.visited_urls.add(url)
                except Exception as e:
                    if self.is_running:
                        logger.warning(f"Failed to process {url}: {e}")
                        self.update_redis_stats("errors", 1)

        except RuntimeError:
            logger.info("Executor accessed during shutdown. Stopping batch.")

        return all_new_links

    def process_single_page(self, url, depth):
        self.check_pause()
        self.rate_limit()

        try:
            self.update_redis_stats("pages_crawled", 1)

            links = self.fast_process_with_beautifulsoup(url, depth)
            if not self.is_running:
                return []

            filtered_links = []

            for link in links:
                self.check_pause()
                if not self.is_running:
                    break

                if not self.should_follow_link(link):
                    self.update_redis_stats("filtered_links", 1)
                    continue

                with self.url_lock:
                    if link["url"] in self.all_unique_urls:
                        self.update_redis_stats("duplicates_skipped", 1)
                        continue

                    self.all_unique_urls.add(link["url"])

                stats = self.update_redis_stats("total_found", 1)
                current_total = stats.get("total_found", 0)

                link["depth"] = depth + 1
                link["found_at"] = time.time()

                filtered_links.append(link)

                self.add_result(
                    {
                        "type": "link_found",
                        "link": link,
                        "total_found": current_total,
                        "total_visited": len(self.visited_urls),
                    }
                )

            self.found_links.extend(filtered_links)
            return filtered_links

        except Exception as e:
            logger.error(f"Error processing page {url}: {e}")
            self.update_redis_stats("errors", 1)
            return []

    def fast_process_with_beautifulsoup(self, url, depth):
        try:
            logger.info(f"Attempting to fetch: {url}")

            response = self.session.get(url, timeout=20, allow_redirects=True)
            logger.info(f"Status Code for {url}: {response.status_code}")

            response.raise_for_status()

            content_type = response.headers.get("content-type", "")
            if "text/html" not in content_type:
                logger.warning(f"Skipping non-HTML content: {content_type}")
                return []

            soup = BeautifulSoup(response.content, "html.parser")
            links = self.fast_extract_links(soup, url)

            self.update_redis_stats("beautifulsoup_success", 1)
            return links

        except Exception as e:
            logger.error(f"FAILED on {url}: {str(e)}")
            self.update_redis_stats("errors", 1)
            return []

    def fast_extract_links(self, soup, base_url):
        links = []
        base_domain = self.base_domain
        seen_urls = set()

        for a_tag in soup.find_all("a", href=True):
            try:
                href = a_tag["href"].strip()

                if not href or href.startswith(("javascript:", "#")):
                    continue

                full_url = urljoin(base_url, href)
                parsed_url = urlparse(full_url)

                scheme = parsed_url.scheme.lower()
                is_http = scheme in ["http", "https"]
                is_contact = scheme in ["mailto", "tel"]

                if is_http:
                    normalized_url = f"{parsed_url.scheme}://{parsed_url.netloc}{parsed_url.path}"
                    if parsed_url.query:
                        normalized_url += f"?{parsed_url.query}"
                else:
                    normalized_url = full_url

                if normalized_url in seen_urls:
                    continue
                seen_urls.add(normalized_url)

                is_internal = self._is_internal_domain(parsed_url.netloc)
                link_text = a_tag.get_text(strip=True)[:150] or a_tag.get("title", "")[:150]

                links.append(
                    {
                        "url": normalized_url,
                        "text": link_text,
                        "is_internal": is_internal,
                        "is_external": (not is_internal and is_http),
                        "is_contact": is_contact,
                        "crawlable": is_http,
                        "source_url": base_url,
                        "domain": parsed_url.netloc,
                    }
                )

            except Exception:
                continue

        return links

    # -------------------------
    # Stop
    # -------------------------

    def stop(self):
        """
        Clean shutdown.
        - If stopped_by_user: do NOT flush buffer and do NOT push complete.
        - If natural completion: flush buffer + push complete event immediately.
        """
        if not hasattr(self, "is_running") or not self.is_running:
            return

        self.is_running = False

        # STOPPED BY USER => no more results pushed
        if self._stopped_by_user:
            try:
                self.r.set(f"crawler:status:{self.session_id}", "stopped", ex=86400)
            except Exception:
                pass

            try:
                if hasattr(self, "executor"):
                    self.executor.shutdown(wait=False, cancel_futures=True)
            except Exception:
                pass

            return

        # NATURAL COMPLETION => flush + completed + send complete event immediately
        try:
            self.flush_buffer_now()
        except Exception:
            pass

        try:
            self.r.set(f"crawler:status:{self.session_id}", "completed", ex=86400)
        except Exception:
            pass

        try:
            if hasattr(self, "executor"):
                self.executor.shutdown(wait=False, cancel_futures=True)
        except Exception:
            pass

        # ✅ Send completion event immediately (no buffering)
        try:
            stats = self.get_redis_stats()
            complete_payload = {
                "type": "complete",
                "message": f"🎉 Crawl finished. Visited {stats.get('pages_crawled', 0)} pages.",
                "total_links": stats.get("total_found", 0),
                "total_pages": stats.get("pages_crawled", 0),
            }
            self.r.rpush(f"crawler:results:{self.session_id}", json.dumps(complete_payload))
        except Exception:
            pass
