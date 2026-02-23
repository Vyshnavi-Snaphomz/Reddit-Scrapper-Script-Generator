from datetime import datetime, timezone
from urllib.parse import urlparse

from scraper_utils import safe_get_json


def _is_bot_author(author: str) -> bool:
    if not author:
        return True
    a = author.strip().lower()
    if a == "automoderator":
        return True
    return a.endswith("bot") or a.startswith("bot_") or a.startswith("bot-")


def _is_excluded_post(data: dict) -> bool:
    title = (data.get("title") or "").strip().lower()
    return (
        data.get("promoted")
        or data.get("stickied")
        or data.get("pinned")
        or data.get("is_ad")
        or "community highlights" in title
        or ("promoted" in (data.get("domain") or "").lower())
        or _is_bot_author(data.get("author"))
    )


def parse_reddit_post_url(post_url: str):
    """
    Parse URLs like:
    https://www.reddit.com/r/<subreddit>/comments/<post_id>/<slug>/
    """
    parsed = urlparse((post_url or "").strip())
    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) < 4:
        return None, None
    if parts[0].lower() != "r" or parts[2].lower() != "comments":
        return None, None
    subreddit = parts[1]
    post_id = parts[3]
    return subreddit, post_id


def fetch_post_from_url(post_url: str):
    subreddit, post_id = parse_reddit_post_url(post_url)
    if not subreddit or not post_id:
        return None

    url = f"https://www.reddit.com/r/{subreddit}/comments/{post_id}.json?sort=top&limit=1"
    try:
        data = safe_get_json(url)
    except Exception as e:
        print(f"Reddit API error for single post URL: {e}")
        return None

    try:
        post_data = data[0]["data"]["children"][0]["data"]
    except Exception:
        return None

    if _is_excluded_post(post_data):
        return None

    created_ts = post_data.get("created_utc")
    created_dt = datetime.fromtimestamp(created_ts, tz=timezone.utc) if created_ts else None
    post_age_days = None
    if created_dt:
        post_age_days = max(0, int((datetime.now(timezone.utc) - created_dt).total_seconds() // 86400))

    return {
        "id": post_data.get("id"),
        "title": (post_data.get("title") or "").strip(),
        "selftext": post_data.get("selftext"),
        "author": post_data.get("author"),
        "author_fullname": post_data.get("author_fullname"),
        "link_flair_text": post_data.get("link_flair_text"),
        "url": post_data.get("url"),
        "ups": post_data.get("ups"),
        "score": post_data.get("score"),
        "upvote_ratio": post_data.get("upvote_ratio"),
        "num_comments": post_data.get("num_comments"),
        "created_utc": created_dt,
        "post_age_days": post_age_days,
        "subreddit": subreddit,
        "comments": [],
    }
