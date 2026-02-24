import os
import random
import time
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import requests


_FETCH_TRACE = []


def _request_headers() -> dict:
    # Build headers at call time so deployed secrets/env updates are always respected.
    return {
        "User-Agent": os.getenv("REDDIT_USER_AGENT", "snapreddit-bot/1.0 (contact: admin@example.com)"),
        "Accept": "application/json",
    }


def _sleep_between_requests() -> None:
    min_delay = float(os.getenv("SCRAPE_MIN_DELAY_SEC", "1.2"))
    max_delay = float(os.getenv("SCRAPE_MAX_DELAY_SEC", "2.8"))
    if max_delay < min_delay:
        max_delay = min_delay
    time.sleep(random.uniform(min_delay, max_delay))


def _ensure_query_params(url: str, params: dict) -> str:
    parsed = urlparse(url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    for k, v in params.items():
        query.setdefault(k, str(v))
    return urlunparse(parsed._replace(query=urlencode(query)))


def _reddit_variants(url: str) -> list:
    """
    Reddit can intermittently block one hostname in cloud environments.
    Try equivalent host variants before failing.
    """
    if "reddit.com" not in url:
        return [url]

    with_raw = _ensure_query_params(url, {"raw_json": 1})
    parsed = urlparse(with_raw)
    hosts = ["www.reddit.com", "reddit.com", "old.reddit.com"]
    out = []
    for host in hosts:
        out.append(urlunparse(parsed._replace(netloc=host)))
    # Preserve order while removing duplicates.
    return list(dict.fromkeys(out))


def _trace(msg: str) -> None:
    _FETCH_TRACE.append(msg)
    # Keep bounded memory for long-running Streamlit sessions.
    if len(_FETCH_TRACE) > 200:
        del _FETCH_TRACE[:100]


def get_fetch_trace(clear: bool = False) -> list:
    data = list(_FETCH_TRACE)
    if clear:
        _FETCH_TRACE.clear()
    return data


def safe_get_json(url: str, timeout: int = 25) -> Any:
    """
    Request JSON with rate limiting, retry, and exponential backoff.
    This lowers block risk but does not guarantee zero blocking.
    """
    retries = int(os.getenv("SCRAPE_MAX_RETRIES", "4"))
    backoff = float(os.getenv("SCRAPE_BACKOFF_BASE_SEC", "1.5"))
    candidate_urls = _reddit_variants(url)
    _trace(f"safe_get_json start: {url}")

    last_error = None
    for attempt in range(retries):
        _sleep_between_requests()
        should_backoff = False
        for candidate in candidate_urls:
            try:
                response = requests.get(candidate, headers=_request_headers(), timeout=timeout)
                if response.status_code == 200:
                    _trace(f"attempt {attempt+1}: 200 {candidate}")
                    return response.json()
                if response.status_code in (403, 429, 500, 502, 503, 504):
                    should_backoff = True
                    _trace(f"attempt {attempt+1}: {response.status_code} {candidate}")
                    last_error = RuntimeError(f"HTTP {response.status_code} for {candidate}")
                    continue
                _trace(f"attempt {attempt+1}: {response.status_code} {candidate}")
                response.raise_for_status()
            except Exception as exc:
                _trace(f"attempt {attempt+1}: error {candidate} -> {exc}")
                last_error = exc
                continue
        if should_backoff and attempt < retries - 1:
            time.sleep(backoff * (2 ** attempt))

    if last_error:
        raise last_error
    raise RuntimeError("Failed to fetch JSON.")
