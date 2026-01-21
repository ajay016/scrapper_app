# parser/tasks.py
import time
import json
import redis
import threading
import requests

from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed, wait, FIRST_COMPLETED
from urllib.parse import urlparse, urljoin

from bs4 import BeautifulSoup
from celery import shared_task
from django.conf import settings
import logging








logger = logging.getLogger(__name__)



def normalize_domain(netloc: str) -> str:
    netloc = (netloc or "").lower().strip()

    # remove port if any (example: imdb.com:443)
    if ":" in netloc:
        netloc = netloc.split(":")[0]

    # strip www.
    if netloc.startswith("www."):
        netloc = netloc[4:]

    return netloc


class FastURLCrawler:
    """
    Celery-safe crawler:
    ✅ Runs fully inside Celery worker
    ✅ Uses Redis for status/results/stats
    ✅ pause/resume/stop works using Redis status key
    ✅ Emits 'complete' event payload exactly like your current frontend expects
    """

    def __init__(self, session_id, base_url, max_depth=2, filters=None, max_workers=5):
        self.session_id = session_id
        self.base_url = base_url
        self.max_depth = self.normalize_max_depth(max_depth)
        
        # ✅ ADD HERE
        self.start_ts = time.time()
        self.max_runtime_seconds = 8 * 60 * 60  # 8 hours
        
        # heartbeat variables
        self.heartbeat_key = f"crawler:last_seen:{self.session_id}"
        self.heartbeat_timeout = 40  # seconds
        self._last_heartbeat_check = 0

        # --- Redis ---
        redis_url = getattr(settings, "REDIS_URL", "redis://localhost:6379/0")
        self.r = redis.from_url(redis_url, decode_responses=True)

        # --- State ---
        self.visited_urls = set()
        self.all_unique_urls = set()
        self.found_links = []

        self.is_running = True
        self._stopped_by_user = False
        self._stop_executed = False

        self.base_domain = normalize_domain(urlparse(base_url).netloc)
        self.filters = filters or {}

        # Executor
        self.max_workers = max_workers
        self.executor = ThreadPoolExecutor(max_workers=self.max_workers)

        # Locks
        self.url_lock = threading.RLock()
        self._buffer_lock = threading.Lock()
        self._thread_local = threading.local()

        # Result buffering -> Redis (fast)
        self._result_buffer = []
        self._last_result_flush = time.time()
        self._result_flush_size = 50
        self._result_flush_interval = 0.5

        # Networking
        self.session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=max_workers,
            pool_maxsize=max_workers * 2
        )
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        })

        # Queue
        self.queue = deque([(self.base_url, 0)])

        # Rate limit
        self.last_request_time = 0
        self.min_request_interval = 0.05

        # Init Redis keys (keep same format)
        self._redis_init()
        
        logger.warning(
            f"[INIT] session={self.session_id} base_url={self.base_url} "
            f"base_domain={self.base_domain} max_depth={self.max_depth} workers={self.max_workers}"
        )
        
    @staticmethod
    def normalize_max_depth(max_depth):
        """
        0 / "0" / "" / None => unlimited (None)
        positive int => that depth
        """
        if max_depth is None:
            return None

        # string cleanup
        if isinstance(max_depth, str):
            max_depth = max_depth.strip()
            if max_depth == "" or max_depth.lower() in ("none", "null"):
                return None

        # numeric conversion
        try:
            max_depth_int = int(max_depth)
            if max_depth_int <= 0:
                return None
            return max_depth_int
        except Exception:
            return None

    def _redis_init(self):
        ttl = 86400

        self.r.set(f"crawler:status:{self.session_id}", "running", ex=ttl)

        self.r.set(
            f"crawler:stats:{self.session_id}",
            json.dumps({
                "total_found": 0,
                "pages_crawled": 0,
                "errors": 0,
                "filtered_links": 0,
                "beautifulsoup_success": 0,
                "selenium_fallback": 0,
                "duplicates_skipped": 0,
                "parallel_workers": self.max_workers,
            }),
            ex=ttl
        )

        # ✅ ADD THESE (FAST COUNTERS)
        self.r.set(f"crawler:total_found:{self.session_id}", 0, ex=ttl)
        self.r.set(f"crawler:pages_crawled:{self.session_id}", 0, ex=ttl)
        
    def get_thread_session(self):
        if not hasattr(self._thread_local, "session"):
            s = requests.Session()
            adapter = requests.adapters.HTTPAdapter(
                pool_connections=1,
                pool_maxsize=2,
            )
            s.mount("http://", adapter)
            s.mount("https://", adapter)
            s.headers.update(self.session.headers)  # copy your headers
            self._thread_local.session = s
        return self._thread_local.session

    def rate_limit(self):
        current_time = time.time()
        elapsed = current_time - self.last_request_time
        if elapsed < self.min_request_interval:
            time.sleep(self.min_request_interval - elapsed) 
        self.last_request_time = time.time()

    def should_follow_link(self, link):
        """Your same filtering logic (kept as-is)."""
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

            # Always block external first
            if not is_internal:
                return False

            check_url = url if case_sensitive else url.lower()

            # URL CONTAINS
            url_contains_raw = self.filters.get("urlContains") or self.filters.get("url_contains")
            if url_contains_raw:
                if isinstance(url_contains_raw, list):
                    keywords = [str(k).strip() for k in url_contains_raw if str(k).strip()]
                else:
                    keywords = [k.strip() for k in str(url_contains_raw).split(",") if k.strip()]

                if keywords:
                    match_found = any(
                        (k if case_sensitive else k.lower()) in check_url
                        for k in keywords
                    )
                    if not match_found:
                        return False

            # URL EXCLUDES
            url_excludes_raw = self.filters.get("urlExcludes") or self.filters.get("url_excludes")
            if url_excludes_raw:
                if isinstance(url_excludes_raw, list):
                    excludes = [str(ex).strip() for ex in url_excludes_raw if str(ex).strip()]
                else:
                    excludes = [ex.strip() for ex in str(url_excludes_raw).split(",") if ex.strip()]

                for exclude in excludes:
                    check_exclude = exclude if case_sensitive else exclude.lower()
                    if check_exclude in check_url:
                        return False

            # TEXT CONTAINS
            text_contains_raw = self.filters.get("textContains") or self.filters.get("text_contains")
            if text_contains_raw:
                text = link.get("text", "")
                check_text = text if case_sensitive else text.lower()

                if isinstance(text_contains_raw, list):
                    text_keywords = [str(tk).strip() for tk in text_contains_raw if str(tk).strip()]
                else:
                    text_keywords = [tk.strip() for tk in str(text_contains_raw).split(",") if tk.strip()]

                if text_keywords:
                    text_match = any(
                        (tk if case_sensitive else tk.lower()) in check_text
                        for tk in text_keywords
                    )
                    if not text_match:
                        return False

            return True

        except Exception as e:
            logger.error(f"Filter Error on {link.get('url')}: {e}")
            return False

    def check_pause(self):
        while True:
            if not self.check_heartbeat():
                return False
        
            status = self.r.get(f"crawler:status:{self.session_id}")

            if status == "stopped":
                self.is_running = False
                self._stopped_by_user = True
                return False

            if status == "paused":
                time.sleep(0.5)
                continue

            return True

    def get_stats(self):
        stats_raw = self.r.get(f"crawler:stats:{self.session_id}")
        return json.loads(stats_raw) if stats_raw else {}

    def set_stats(self, stats: dict):
        # Always keep TTL
        self.r.set(f"crawler:stats:{self.session_id}", json.dumps(stats), ex=86400)

    def incr_stat(self, key, inc=1):
        """Thread-safe stats increment stored in Redis JSON."""
        with self.url_lock:
            stats = self.get_stats()
            stats[key] = stats.get(key, 0) + inc
            self.set_stats(stats)
            return stats

    def add_result(self, result: dict):
        if self._stopped_by_user:
            return
        if not self.session_id:
            return

        now = time.time()

        # ✅ fast stop detection (won't slow crawling)
        if not hasattr(self, "_last_status_check"):
            self._last_status_check = 0

        if (now - self._last_status_check) > 0.2:
            self._last_status_check = now
            try:
                status = self.r.get(f"crawler:status:{self.session_id}")
                if status == "stopped":
                    self.is_running = False
                    self._stopped_by_user = True
                    return
            except Exception:
                pass

        with self._buffer_lock:
            self._result_buffer.append(result)

            should_flush = (
                len(self._result_buffer) >= self._result_flush_size
                or (now - self._last_result_flush) >= self._result_flush_interval
            )

            if should_flush:
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

    def flush_results(self):
        """Flush buffered results safely."""
        with self._buffer_lock:
            if not self._result_buffer:
                return
            try:
                pipe = self.r.pipeline()
                for res in self._result_buffer:
                    pipe.rpush(f"crawler:results:{self.session_id}", json.dumps(res))
                pipe.execute()
            except Exception as e:
                logger.error(f"Failed to flush final buffer: {e}")
            finally:
                self._result_buffer = []
                self._last_result_flush = time.time()

    def fast_extract_links(self, soup, base_url):
        links = []
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

                link_domain = normalize_domain(parsed_url.netloc)
                base_domain = self.base_domain

                is_internal = (
                    link_domain == base_domain
                    or link_domain.endswith("." + base_domain)
                    or base_domain.endswith("." + link_domain)
                )

                link_text = a_tag.get_text(strip=True)[:150] or a_tag.get("title", "")[:150]

                links.append({
                    "url": normalized_url,
                    "text": link_text,
                    "is_internal": is_internal,
                    "is_external": (not is_internal and is_http),
                    "is_contact": is_contact,
                    "crawlable": is_http,
                    "source_url": base_url,
                    "domain": parsed_url.netloc,
                })

            except Exception:
                continue

        return links

    def fast_process_with_beautifulsoup(self, url, depth):
        try:
            logger.info(f"[CRAWL] Fetching: {url}")
            
            session = self.get_thread_session()
            response = session.get(url, timeout=(10, 20), allow_redirects=True)

            final_url = response.url  # ✅ THIS IS THE REAL URL AFTER REDIRECT
            logger.info(f"[CRAWL] Status {response.status_code}: {final_url}")

            response.raise_for_status()

            content_type = response.headers.get("content-type", "")
            if "text/html" not in content_type:
                logger.warning(f"Skipping non-HTML content: {content_type}")
                return []

            soup = BeautifulSoup(response.content, "html.parser")

            # ✅ Use final_url so urljoin() works correctly
            links = self.fast_extract_links(soup, final_url)
            logger.warning(f"[BS4] depth={depth} page={final_url} extracted_links={len(links)}")

            self.incr_stat("beautifulsoup_success", 1)
            return links

        except Exception as e:
            logger.error(f"FAILED on {url}: {str(e)}")
            self.incr_stat("errors", 1)
            return []

    def process_single_page(self, url, depth):
        """Process one page (kept behavior)."""
        if not self.check_pause():
            return []

        self.rate_limit()

        # stats: pages_crawled
        self.r.incr(f"crawler:pages_crawled:{self.session_id}")
        
        logger.warning(f"[PAGE START] depth={depth} url={url}")

        links = self.fast_process_with_beautifulsoup(url, depth)
        
        
        total_extracted = len(links)
        internal_count = sum(1 for l in links if l.get("is_internal"))
        crawlable_count = sum(1 for l in links if l.get("crawlable", True))
        logger.warning(
            f"[DEBUG] depth={depth} page={url} extracted={total_extracted} internal={internal_count} crawlable={crawlable_count}"
        )

        if not self.is_running:
            return []

        filtered_links = []

        for link in links:
            if not self.check_pause():
                break
            if not self.is_running:
                break

            if not self.should_follow_link(link):
                self.incr_stat("filtered_links", 1)
                continue

            # ✅ only lock for checking + adding
            with self.url_lock:
                already_seen = link["url"] in self.all_unique_urls
                if not already_seen:
                    self.all_unique_urls.add(link["url"])

            # ✅ count duplicates outside lock
            if already_seen:
                self.incr_stat("duplicates_skipped", 1)
                continue

            # ✅ atomic redis counter (safe without lock)
            current_total = self.r.incr(f"crawler:total_found:{self.session_id}")

            link["depth"] = depth + 1
            link["found_at"] = time.time()
            filtered_links.append(link)

            self.add_result({
                "type": "link_found",
                "link": link,
                "total_found": current_total,
                "total_visited": len(self.visited_urls) + 1
            })

        self.found_links.extend(filtered_links)
        
        # ✅ Update JSON stats ONCE per page (not per link)
        try:
            stats = self.get_stats()
            stats["total_found"] = int(self.r.get(f"crawler:total_found:{self.session_id}") or 0)
            stats["pages_crawled"] = int(self.r.get(f"crawler:pages_crawled:{self.session_id}") or 0)
            self.set_stats(stats)
        except Exception:
            pass
        
        logger.warning(f"[PAGE END] depth={depth} url={url} kept={len(filtered_links)}")
        
        return filtered_links

    def process_batch_parallel(self, batch):
        all_new_links = []

        # Mark visited so we don't duplicate inside same run
        with self.url_lock:
            for url, _depth in batch:
                self.visited_urls.add(url)

        future_map = {
            self.executor.submit(self.process_single_page, url, depth): (url, depth)
            for url, depth in batch
        }

        # ✅ DO NOT USE wait(timeout=30) + cancel()
        # ✅ Just collect futures as they complete
        for future in as_completed(future_map):
            url, depth = future_map[future]
            try:
                new_links = future.result()  # requests has timeout already (10,20)
                if self.is_running:
                    all_new_links.extend(new_links)
            except Exception as e:
                logger.warning(f"[FUTURE ERROR] url={url} depth={depth} err={e}")
                self.incr_stat("errors", 1)

        logger.warning(f"[BATCH PARALLEL END] returned_links={len(all_new_links)}")
        return all_new_links

    def crawl(self):
        batch_size = 10

        logger.warning(
            f"[CRAWL START] session={self.session_id} queue={len(self.queue)} visited={len(self.visited_urls)}"
        )

        prev_queue_len = -1
        prev_total_found = -1
        stagnant_rounds = 0
        batch_number = 0

        try:
            while self.queue and self.is_running:
                if not self.check_heartbeat():
                    break
                
                batch_number += 1

                logger.warning(
                    f"[LOOP] batch={batch_number} queue_before={len(self.queue)} visited={len(self.visited_urls)}"
                )

                if not self.check_pause():
                    logger.warning(f"[LOOP EXIT] batch={batch_number} reason=paused_or_stopped")
                    break
                if not self.is_running:
                    logger.warning(f"[LOOP EXIT] batch={batch_number} reason=is_running_false")
                    break
                
                if self.max_runtime_seconds is not None:
                    if (time.time() - self.start_ts) > self.max_runtime_seconds:
                        logger.error(f"[RUNTIME STOP] session={self.session_id} exceeded max runtime")
                        self.r.set(f"crawler:status:{self.session_id}", "stopped", ex=86400)
                        self.is_running = False
                        self._stopped_by_user = True
                        break

                current_batch = []

                # Build batch
                while self.queue and len(current_batch) < batch_size:
                    url, depth = self.queue.popleft()

                    if url not in self.visited_urls and (self.max_depth is None or depth < self.max_depth):
                        current_batch.append((url, depth))

                logger.warning(
                    f"[BATCH BUILD] batch={batch_number} picked={len(current_batch)} queue_after_pick={len(self.queue)}"
                )
                
                logger.warning(
                    f"[BATCH URLS] batch={batch_number} urls={[u for u, d in current_batch]} depths={[d for u, d in current_batch]}"
                )

                if not current_batch:
                    logger.warning(f"[EMPTY BATCH] batch={batch_number} continuing...")
                    continue

                new_links = self.process_batch_parallel(current_batch)

                logger.warning(
                    f"[BATCH RESULT] batch={batch_number} new_links_returned={len(new_links)}"
                )

                # Queue next
                added_to_queue = 0
                skipped_depth = 0
                skipped_visited = 0
                skipped_external = 0

                for link in new_links:
                    next_depth = link.get("depth", 0)

                    if link["url"] in self.visited_urls:
                        skipped_visited += 1
                        continue

                    if not (self.max_depth is None or next_depth < self.max_depth):
                        skipped_depth += 1
                        continue

                    if not link.get("crawlable", True) or not link.get("is_internal"):
                        skipped_external += 1
                        continue

                    self.queue.append((link["url"], next_depth))
                    added_to_queue += 1

                logger.warning(
                    f"[QUEUE UPDATE] batch={batch_number} added={added_to_queue} "
                    f"skipped_visited={skipped_visited} skipped_depth={skipped_depth} skipped_external={skipped_external} "
                    f"queue_now={len(self.queue)} visited={len(self.visited_urls)}"
                )

                # STUCK detector
                stats = self.get_stats()
                total_found = stats.get("total_found", 0)
                current_queue_len = len(self.queue)

                if current_queue_len == prev_queue_len and total_found == prev_total_found:
                    stagnant_rounds += 1
                else:
                    stagnant_rounds = 0

                prev_queue_len = current_queue_len
                prev_total_found = total_found

                if stagnant_rounds >= 10:
                    logger.error(
                        f"[STUCK WARNING] batch={batch_number} no progress for {stagnant_rounds} loops | "
                        f"visited={len(self.visited_urls)} queue={current_queue_len} total_found={total_found}"
                    )
                    stagnant_rounds = 0

                # Progress event
                if len(self.visited_urls) > 0 and len(self.visited_urls) % 100 == 0:
                    self.add_result({
                        "type": "progress",
                        "visited": len(self.visited_urls),
                        "found": total_found,
                        "queued": len(self.queue),
                        "filtered": stats.get("filtered_links", 0),
                        "message": f"Progress: {len(self.visited_urls)} pages, {total_found} links, {len(self.queue)} queued"
                    })

            # ✅ finished normally
            final_status = self.r.get(f"crawler:status:{self.session_id}")
            logger.warning(
                f"[CRAWL END] session={self.session_id} final_status={final_status} "
                f"stopped_by_user={self._stopped_by_user} visited={len(self.visited_urls)} "
                f"queue={len(self.queue)} total_found={self.get_stats().get('total_found', 0)}"
            )

        except Exception as e:
            if self.is_running:
                logger.error(f"[CRAWL ERROR] {e}", exc_info=True)
                self.add_result({
                    "type": "error",
                    "message": f"Crawling error: {str(e)}"
                })
        finally:
            logger.warning(
                f"[CRAWL FINISHED LOOP] session={self.session_id} queue_empty={len(self.queue)==0} "
                f"is_running={self.is_running} stopped_by_user={self._stopped_by_user} "
                f"visited={len(self.visited_urls)} total_found={self.get_stats().get('total_found', 0)}"
            )
            self.stop()

    def stop(self):
        """
        ✅ Finalization rules preserved:
        - if stopped_by_user: set status=stopped, NO complete event, NO flushing after stop
        - else: set status=completed + push complete payload
        """
        logger.warning(
            f"[STOP CALLED] session={self.session_id} stopped_by_user={self._stopped_by_user} "
            f"queue={len(self.queue)} visited={len(self.visited_urls)}"
        )
        
        if self._stop_executed:
            return
        self._stop_executed = True

        self.is_running = False

        # If stopped by user: no more results
        if self._stopped_by_user:
            try:
                self.r.set(f"crawler:status:{self.session_id}", "stopped", ex=86400)
            except Exception:
                pass

            try:
                self.executor.shutdown(wait=False, cancel_futures=True)
            except Exception:
                pass
            return

        # Normal completion path
        try:
            self.flush_results()
        except Exception:
            pass

        stats = self.get_stats()
        complete_payload = {
            "type": "complete",
            "message": f"🎉 Crawl finished. Visited {stats.get('pages_crawled', 0)} pages.",
            "total_links": stats.get("total_found", 0),
            "total_pages": stats.get("pages_crawled", 0),
        }

        # ✅ Push complete FIRST
        try:
            self.r.rpush(f"crawler:results:{self.session_id}", json.dumps(complete_payload))
        except Exception:
            pass

        # ✅ Then set completed
        try:
            self.r.set(f"crawler:status:{self.session_id}", "completed", ex=86400)
        except Exception:
            pass
        
    
    def check_heartbeat(self):
        """
        Stops crawl automatically if Electron heartbeat disappears.
        """
        now = time.time()

        # don’t check too frequently
        if (now - self._last_heartbeat_check) < 3:
            return True

        self._last_heartbeat_check = now

        try:
            last_seen = self.r.get(self.heartbeat_key)
            if not last_seen:
                # No heartbeat ever sent
                self.is_running = False
                self._stopped_by_user = True
                self.r.set(f"crawler:status:{self.session_id}", "stopped", ex=86400)
                logger.warning(f"[HEARTBEAT STOP] No heartbeat key found. session={self.session_id}")
                return False

            last_seen = float(last_seen)
            if (now - last_seen) > self.heartbeat_timeout:
                # heartbeat expired
                self.is_running = False
                self._stopped_by_user = True
                self.r.set(f"crawler:status:{self.session_id}", "stopped", ex=86400)
                logger.warning(
                    f"[HEARTBEAT STOP] Heartbeat expired. session={self.session_id} "
                    f"last_seen={last_seen} now={now}"
                )
                return False

        except Exception as e:
            logger.error(f"[HEARTBEAT CHECK ERROR] {e}")

        return True


@shared_task(bind=True, name="parser.run_url_crawl")
def run_url_crawl(self, session_id, url, max_depth, filters, max_workers):
    """
    Celery task:
    ✅ runs crawl fully outside gunicorn
    ✅ uses Redis for status / results / stats
    ✅ pause/resume/stop compatible with your frontend
    """
    logger.info(f"[CELERY] Starting crawl session={session_id} url={url} max_depth={max_depth}")

    crawler = FastURLCrawler(
        session_id=session_id,
        base_url=url,
        max_depth=FastURLCrawler.normalize_max_depth(max_depth),
        filters=filters or {},
        max_workers=int(max_workers or 5),
    )

    crawler.crawl()
    
    final_status = crawler.r.get(f"crawler:status:{session_id}")
    logger.warning(
        f"[CELERY END] session={session_id} status={final_status} "
        f"visited={len(crawler.visited_urls)} queue={len(crawler.queue)} "
        f"total_found={crawler.get_stats().get('total_found', 0)}"
    )

    return {"session_id": session_id, "status": crawler.r.get(f"crawler:status:{session_id}") or "unknown"}
