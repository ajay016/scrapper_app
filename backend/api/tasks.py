from celery import shared_task
from django.conf import settings
import redis
import json
import logging
import time
from .crawler import FastURLCrawler












logger = logging.getLogger(__name__)


@shared_task(bind=True)
def run_crawler_task(self, session_id, url, max_depth, filters, max_workers):
    """
    Runs crawler in Celery worker.
    Pause/Resume/Stop controlled by Redis key: crawler:status:<session_id>
    """
    r = redis.from_url(settings.REDIS_URL, decode_responses=True)

    # Store celery task id (optional, useful for force-kill)
    r.set(f"crawler:task_id:{session_id}", self.request.id, ex=86400)

    try:
        crawler = FastURLCrawler(
            session_id=session_id,
            base_url=url,
            max_depth=max_depth,
            filters=filters,
            max_workers=max_workers
        )
        crawler.crawl()

    except Exception as e:
        logger.error(f"[CELERY] Crawler crashed for session {session_id}: {e}")

        try:
            r.set(f"crawler:status:{session_id}", "failed", ex=86400)
            r.rpush(
                f"crawler:results:{session_id}",
                json.dumps({"type": "error", "message": f"Crawler crashed: {str(e)}"})
            )
        except Exception:
            pass

    return "done"



@shared_task
def cleanup_zombie_sessions():
    r = redis.from_url(settings.REDIS_URL, decode_responses=True)
    now = time.time()

    # Use SCAN, not KEYS
    cursor = 0
    while True:
        cursor, keys = r.scan(cursor=cursor, match="crawler:status:*", count=200)

        for status_key in keys:
            session_id = status_key.split(":")[-1]
            status = r.get(status_key)

            # Only cleanup running/paused sessions
            if status not in ("running", "paused"):
                continue

            start_time = r.get(f"crawler:start_time:{session_id}")
            last_seen = r.get(f"crawler:last_seen:{session_id}")

            start_time = float(start_time) if start_time else 0
            last_seen = float(last_seen) if last_seen else 0

            # Zombie conditions
            too_old = start_time and (now - start_time > 21600)       # >2 hours
            tab_gone = last_seen and (now - last_seen > 60)          # >30 seconds no poll

            if too_old or tab_gone:
                logger.info(f"[CLEANUP] Stopping zombie session {session_id}")
                r.set(f"crawler:status:{session_id}", "stopped", ex=86400)

        if cursor == 0:
            break

