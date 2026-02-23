import os

from rag_generation import is_realestate_us
from scraper_utils import safe_get_json
from excel_storage import append_subreddits, get_subreddits

def _basic_realestate_filter(text: str) -> bool:
    text_l = (text or "").lower()
    keywords = [
        "real estate",
        "realestate",
        "housing",
        "mortgage",
        "rent",
        "landlord",
        "tenant",
        "home buying",
        "property",
        "realtor",
    ]
    return any(k in text_l for k in keywords)


def get_related_subreddits(query="realestate", limit=11, save_to_excel=True):
    """Fetch related subreddits and store only US real-estate ones in Excel."""
    url = f"https://www.reddit.com/subreddits/search.json?q={query}&limit={limit}"
    try:
        data = safe_get_json(url)
    except Exception as e:
        print(f"Reddit API error for subreddits: {e}")
        return []

    subreddits = []
    subreddit_records = []
    use_openai_filter = bool(os.getenv("OPENAI_API_KEY"))
    for sub in data["data"]["children"]:
        name = sub["data"]["display_name"]
        title = sub["data"].get("title", "")
        description = sub["data"].get("public_description", "")

        text_to_check = f"{name} {title} {description}"
        is_match = is_realestate_us(text_to_check) if use_openai_filter else _basic_realestate_filter(text_to_check)
        if is_match:
            subreddits.append(name)
            subreddit_records.append(
                {
                    "name": name,
                    "query": query,
                    "title": title,
                    "description": description,
                }
            )

    if save_to_excel and subreddit_records:
        append_subreddits(subreddit_records)

    return subreddits


def get_subreddits_from_excel(query=None):
    """Fetch stored subreddits from Excel."""
    return get_subreddits(query=query)


# Backward compatible alias for existing imports.
def get_subreddits_from_db(query=None):
    return get_subreddits_from_excel(query=query)


if __name__ == "__main__":
    related = get_related_subreddits("realestate", limit=20)
    print("Stored US Real Estate Subreddits:", related)
