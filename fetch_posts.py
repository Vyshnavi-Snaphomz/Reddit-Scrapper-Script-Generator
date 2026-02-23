from datetime import datetime, timezone
from scraper_utils import safe_get_json

# from fetch_subreddits import get_subreddits_from_db, get_related_subreddits
# from fetch_comments import fetch_comments

def _is_bot_author(author: str) -> bool:
    if not author:
        return True
    a = author.strip().lower()
    if a == "automoderator":
        return True
    return a.endswith("bot") or a.startswith("bot_") or a.startswith("bot-")


def fetch_posts(subreddit, limit=5):
    """Fetch hot posts from a subreddit."""
    posts = []
    after = None
    page_size = min(100, max(25, limit * 5))
    max_pages = 5

    for _ in range(max_pages):
        url = f"https://www.reddit.com/r/{subreddit}/hot.json?limit={page_size}"
        if after:
            url += f"&after={after}"
        try:
            data = safe_get_json(url)
        except Exception as e:
            print(f"Reddit API error for posts: {e}")
            break

        children = data.get("data", {}).get("children", [])
        if not children:
            break

        for post in children:
            p = post["data"]
            title = (p.get("title") or "").strip()
            title_l = title.lower()
            author = p.get("author")

            # Skip sponsored/promoted/community-highlight style posts.
            if (
                p.get("promoted")
                or p.get("stickied")
                or p.get("pinned")
                or p.get("is_ad")
                or "community highlights" in title_l
                or ("promoted" in (p.get("domain") or "").lower())
                or _is_bot_author(author)
            ):
                continue

            created_ts = p.get("created_utc")
            created_dt = datetime.fromtimestamp(created_ts, tz=timezone.utc) if created_ts else None
            post_age_days = None
            if created_dt:
                post_age_days = max(0, int((datetime.now(timezone.utc) - created_dt).total_seconds() // 86400))

            post_doc = {
                "id": p.get("id"),
                "title": title,
                "selftext": p.get("selftext"),
                "author": author,
                "author_fullname": p.get("author_fullname"),
                "link_flair_text": p.get("link_flair_text"),
                "url": p.get("url"),
                "ups": p.get("ups"),
                "score": p.get("score"),
                "upvote_ratio": p.get("upvote_ratio"),
                "num_comments": p.get("num_comments"),
                "created_utc": created_dt,
                "post_age_days": post_age_days,
                "subreddit": subreddit,
                "comments": []
            }
            posts.append(post_doc)
            if len(posts) >= limit:
                return posts

        after = data.get("data", {}).get("after")
        if not after:
            break

    return posts

# if __name__ == "__main__":
#     get_related_subreddits()  # store related subreddits in DB
#     related_subreddits = get_subreddits_from_db()
#     print("Loaded subreddits from DB:", related_subreddits)

#     #Fetching Posts & Comments
#     for subreddit in related_subreddits:
#         print(f"\nFetching from r/{subreddit} ...")
#         posts = fetch_posts(subreddit)

#         for post in posts:
#             print(f"Inserted Post: {post['title']}")
#             comments = fetch_comments(subreddit, post["id"], limit=10)
#             print(f"   -> {len(comments)} comments fetched for post {post['id']}")
