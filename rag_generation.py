import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None


def is_realestate_us(text, model="gpt-4o-mini"):
    """
    Check if the text is related to real estate AND location is United States of America - US.
    Returns True if relevant, else False.
    """
    prompt = f"""
    Determine if the following text is about *real estate* (housing, buying/selling,
    renting, mortgages, property issues, etc.) AND related to the *United States*.

    Text:
    "{text}"

    Respond with only 'YES' or 'NO'.
    """
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are a strict classifier. Reply only 'YES' or 'NO'."},
                {"role": "user", "content": prompt}
            ],
            temperature=0,
            max_tokens=2
        )

        decision = response.choices[0].message.content.strip().upper() if response.choices else "NO"
        return decision == "YES"
    except Exception as e:
        print(f"Error in classifier: {e}")
        return False


def extract_issues_from_texts(items, model="gpt-4o-mini"):
    """
    Given a list of items (posts or comments with metadata),
    extract issues/pain points mentioned in each text.
    Skip items not related to US real estate or without clear issues.
    """
    results = []

    for item in items:
        text = item.get("text", "").strip()
        if not text:
            continue

        # Relevance check
        if not is_realestate_us(text, model=model):
            continue

        # Issue extraction
        prompt = f"""
        Extract the specific issues, problems, or pain points described in the following text:
        "{text}"

        Respond with a clear bullet list of issues only.
        If there are no issues, just respond with "None".
        """
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are an assistant that extracts pain points and issues from real estate text. "
                                   "If no issues are present, respond with 'None'."
                    },
                    {"role": "user", "content": prompt}
                ],
                temperature=0,
                max_tokens=300
            )

            issues_text = response.choices[0].message.content.strip() if response.choices else ""

            # Skip if no issues found and normalize to list
            if not issues_text or issues_text.lower() in ["none", "no issues", "n/a", "-"]:
                continue

            issues_list = [i.strip("-• \n") for i in issues_text.split("\n") if i.strip()]

            # Store metadata
            result_doc = {
                "text": text,
                "issues_raw": issues_text,
                "issues": issues_list,
                "source": item.get("source"),
                # Post metadata
                "post_title": item.get("post_title"),
                "post_selftext": item.get("post_selftext"),
                "post_author": item.get("post_author"),
                "post_url": item.get("post_url"),
                "post_upvotes": item.get("post_upvotes"),
                "post_created_utc": item.get("post_created_utc"),
                "subreddit": item.get("subreddit"),
                # Comment metadata
                "comment_author": item.get("comment_author"),
                "comment_url": item.get("comment_url"),
                "comment_upvotes": item.get("comment_upvotes"),
                "comment_created_utc": item.get("comment_created_utc")
            }

            results.append(result_doc)

        except Exception as e:
            print(f"Error processing text: {e}")

    return results
    if client is None:
        return False

    if client is None:
        print("OPENAI_API_KEY not set; skipping issue extraction.")
        return []
