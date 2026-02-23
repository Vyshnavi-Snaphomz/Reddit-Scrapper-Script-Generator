from db import posts_collection, db
from rag_generation import extract_issues_from_texts
from match_feature import find_top_k_features

def collect_posts_comments():
    items = []

    # Fetch posts + embedded comments with metadata
    for post in posts_collection.find(
        {},
        {
            "title": 1,
            "selftext": 1,
            "comments": 1,
            "author_fullname": 1,
            "url": 1,
            "score": 1,
            "created_utc": 1,
            "subreddit": 1,
        },
    ):
        # Post metadata
        post_meta = {
            "post_title": post.get("title"),
            "post_selftext": post.get("selftext"),
            "post_author": post.get("author_fullname"),
            "post_url": post.get("url"),
            "post_upvotes": post.get("score"),
            "post_created_utc": post.get("created_utc"),
            "subreddit": post.get("subreddit"),
        }

        # Post text
        if post.get("title") and post.get("selftext"):
            items.append(
                {
                    "text": post["title"] + " " + post["selftext"],
                    **post_meta,
                    "source": "post",
                }
            )

        # Embedded comments
        for comment in post.get("comments", []):
            if comment.get("body"):
                items.append(
                    {
                        "text": comment["body"],
                        "comment_author": comment.get("author"),
                        "comment_url": f"https://reddit.com{comment.get('permalink')}",
                        "comment_upvotes": comment.get("ups"),
                        "comment_created_utc": comment.get("created_utc"),
                        **post_meta,
                        "source": "comment",
                    }
                )

    print(f"Total texts to process: {len(items)}")

    issues_list = extract_issues_from_texts(items)

    issues_collection = db["issues"]
    inserted_count = 0

    for issue in issues_list:
        top_features = find_top_k_features(issue["text"], k=1)
        matched_feature = top_features[0] if top_features else None

        #attach matched feature to issue
        issue["matched_feature"] = matched_feature

        unique_filter = {
            "text": issue["text"],
            "post_url": issue.get("post_url"),
            "comment_url": issue.get("comment_url"),
        }

        result = issues_collection.update_one(
            unique_filter,
            {"$set": issue},
            upsert=True,
        )

        if result.upserted_id:  #count only new inserts
            inserted_count += 1

    if inserted_count > 0:
        print(f"Extracted {inserted_count} new issues stored in DB (with matched features)")
    else:
        print("No new issues extracted")

# if __name__ == "__main__":
#     collect_posts_comments()
