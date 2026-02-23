from datetime import datetime
from scraper_utils import safe_get_json

def _is_bot_author(author: str) -> bool:
    if not author:
        return True
    a = author.strip().lower()
    if a == "automoderator":
        return True
    return a.endswith("bot") or a.startswith("bot_") or a.startswith("bot-")


def fetch_comments(subreddit, post_id, limit=3):
    """Fetch top comments for a post."""
    fetch_limit = max(25, limit * 8)
    url = f"https://www.reddit.com/r/{subreddit}/comments/{post_id}.json?sort=top&limit={fetch_limit}"
    try:
        data = safe_get_json(url)
    except Exception as e:
        print(f"Reddit API error for comments: {e}")
        return []

    comments = []
    if len(data) > 1:
        for comment in data[1]["data"]["children"]: 
            if comment["kind"] == "t1":
                c = comment["data"]
                author = c.get("author")
                if _is_bot_author(author):
                    continue
                comment_doc = {
                    "id": c.get("id"),
                    "author": author,
                    "body": c.get("body"),
                    "ups": c.get("ups"),
                    "url": f"https://www.reddit.com{c.get('permalink')}",
                    "created_utc": datetime.utcfromtimestamp(c.get("created_utc")),
                }
                comments.append(comment_doc)

    comments.sort(key=lambda x: x.get("ups", 0), reverse=True)
    comments = comments[:limit]

    return comments
