import os
import random
import time
from typing import Any

import requests


DEFAULT_HEADERS = {
    "User-Agent": os.getenv("REDDIT_USER_AGENT", "snapreddit-bot/1.0 (contact: admin@example.com)"),
    "Accept": "application/json",
}


def _sleep_between_requests() -> None:
    min_delay = float(os.getenv("SCRAPE_MIN_DELAY_SEC", "1.2"))
    max_delay = float(os.getenv("SCRAPE_MAX_DELAY_SEC", "2.8"))
    if max_delay < min_delay:
        max_delay = min_delay
    time.sleep(random.uniform(min_delay, max_delay))


def safe_get_json(url: str, timeout: int = 25) -> Any:
    """
    Request JSON with rate limiting, retry, and exponential backoff.
    This lowers block risk but does not guarantee zero blocking.
    """
    retries = int(os.getenv("SCRAPE_MAX_RETRIES", "4"))
    backoff = float(os.getenv("SCRAPE_BACKOFF_BASE_SEC", "1.5"))

    last_error = None
    for attempt in range(retries):
        _sleep_between_requests()
        try:
            response = requests.get(url, headers=DEFAULT_HEADERS, timeout=timeout)
            if response.status_code == 200:
                return response.json()
            if response.status_code in (429, 500, 502, 503, 504):
                wait_time = backoff * (2 ** attempt)
                time.sleep(wait_time)
                continue
            response.raise_for_status()
        except Exception as exc:
            last_error = exc
            if attempt < retries - 1:
                time.sleep(backoff * (2 ** attempt))
            continue

    if last_error:
        raise last_error
    raise RuntimeError("Failed to fetch JSON.")
