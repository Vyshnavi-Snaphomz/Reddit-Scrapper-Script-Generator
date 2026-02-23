import os

from excel_storage import append_post_comment_block
from fetch_comments import fetch_comments
from fetch_post_url import fetch_post_from_url
from fetch_posts import fetch_posts
from fetch_subreddits import get_related_subreddits, get_subreddits_from_excel
from html_export import export_post_assets
from imgbb_client import upload_image_to_imgbb


def _store_post_and_upload(post, comments, show_subreddit, imgbb_api_key):
    assets = export_post_assets(post, comments)
    html_path = assets.get("html_path")
    image_path = assets.get("image_path")

    if imgbb_api_key.strip() and image_path and os.path.exists(image_path):
        try:
            post["imgbb_link"] = upload_image_to_imgbb(image_path, imgbb_api_key.strip())
            print(f"   -> ImgBB: {post['imgbb_link']}")
        except Exception as e:
            post["imgbb_link"] = None
            print(f"   -> ImgBB upload failed: {e}")
    else:
        post["imgbb_link"] = None

    # Temporary artifacts are deleted after upload.
    try:
        if image_path and os.path.exists(image_path):
            os.remove(image_path)
        if html_path and os.path.exists(html_path):
            os.remove(html_path)
    except Exception:
        pass

    append_post_comment_block(post, comments, show_subreddit=show_subreddit)
    return post


def fetch_for_subreddits(
    subreddits,
    posts_per_subreddit=5,
    comments_per_post=3,
    imgbb_api_key="",
):
    """Fetch exactly N top posts per subreddit and M top comments per post."""
    collected = []
    for subreddit in subreddits:
        print(f"\nFetching from r/{subreddit} ...")
        posts = fetch_posts(subreddit, limit=posts_per_subreddit)
        print(f"Fetched {len(posts)} posts from r/{subreddit}")

        for post_idx, post in enumerate(posts, start=1):
            post["post_rank"] = post_idx
            print(f"Inserted Post: {post['title']}")
            comments = fetch_comments(subreddit, post["id"], limit=comments_per_post)
            stored = _store_post_and_upload(
                post=post,
                comments=comments,
                show_subreddit=(post_idx == 1),
                imgbb_api_key=imgbb_api_key,
            )
            collected.append({"post": stored, "comments": comments})
            print(f"   -> {len(comments)} comments fetched for post {post['id']}")
    return collected


def fetch_for_post_urls(post_urls, comments_per_post=3, imgbb_api_key=""):
    """Fetch from direct Reddit post links and store output in Excel."""
    collected = []
    for idx, post_url in enumerate(post_urls, start=1):
        post = fetch_post_from_url(post_url)
        if not post:
            print(f"Skipped URL (invalid/excluded/not found): {post_url}")
            continue
        post["post_rank"] = idx
        comments = fetch_comments(post["subreddit"], post["id"], limit=comments_per_post)
        stored = _store_post_and_upload(
            post=post,
            comments=comments,
            show_subreddit=True,
            imgbb_api_key=imgbb_api_key,
        )
        collected.append({"post": stored, "comments": comments, "post_url": post_url})
    return collected


def run_pipeline(subreddits=None, posts_per_subreddit=5, comments_per_post=3):
    if subreddits:
        related_subreddits = [s.strip() for s in subreddits if s and s.strip()]
    else:
        get_related_subreddits()
        related_subreddits = get_subreddits_from_excel()
    print("Loaded subreddits:", related_subreddits)

    fetch_for_subreddits(
        related_subreddits,
        posts_per_subreddit=posts_per_subreddit,
        comments_per_post=comments_per_post,
    )
    print("\nPipeline complete! Scraped data is stored in Excel.")


if __name__ == "__main__":
    run_pipeline()
