import os
import streamlit as st
import json
import io
import csv
from pathlib import Path
from dotenv import load_dotenv

from gemini_client import generate_text_with_gemini
from main import fetch_for_post_urls, fetch_for_subreddits

load_dotenv()


def _get_secret(name: str, default: str = "") -> str:
    # Streamlit Cloud secrets take priority; fallback to process env/.env.
    # Avoid noisy local warnings when secrets.toml is not present.
    secrets_candidates = [
        Path.home() / ".streamlit" / "secrets.toml",
        Path.cwd() / ".streamlit" / "secrets.toml",
    ]
    should_try_streamlit_secrets = any(p.exists() for p in secrets_candidates) or bool(
        os.getenv("STREAMLIT_CLOUD")
    )
    if should_try_streamlit_secrets:
        try:
            val = st.secrets.get(name, None)
            if val is not None and str(val).strip():
                return str(val).strip()
        except Exception:
            pass
    return os.getenv(name, default).strip()

st.set_page_config(page_title="Reddit Pipeline", layout="wide")
st.title("Reddit Pipeline Runner")
st.caption("Scrape Reddit data, upload rendered cards to ImgBB, and download CSV after each retrieval.")

with st.sidebar:
    st.subheader("Scraping Safety Controls")
    st.code(
        "\n".join(
            [
                "REDDIT_USER_AGENT=snapreddit-bot/1.0",
                "SCRAPE_MIN_DELAY_SEC=1.2",
                "SCRAPE_MAX_DELAY_SEC=2.8",
                "SCRAPE_MAX_RETRIES=4",
                "SCRAPE_BACKOFF_BASE_SEC=1.5",
            ]
        ),
        language="bash",
    )
    st.warning("No scraper can guarantee zero blocking. Use conservative request rates.")

imgbb_api_key = _get_secret("IMGBB_API_KEY")
gemini_api_key = _get_secret("GEMINI_API_KEY")
gemini_model = _get_secret("GEMINI_MODEL", "gemini-1.5-flash")

if "last_results" not in st.session_state:
    st.session_state["last_results"] = []
if "generated_scripts" not in st.session_state:
    st.session_state["generated_scripts"] = ""
if "script_source_links" not in st.session_state:
    st.session_state["script_source_links"] = []
if "generated_by_post" not in st.session_state:
    st.session_state["generated_by_post"] = []
if "last_csv_data" not in st.session_state:
    st.session_state["last_csv_data"] = ""
if "stored_rows" not in st.session_state:
    st.session_state["stored_rows"] = []


def _results_to_rows(results):
    rows = []
    for item in results or []:
        post = item.get("post", {}) or {}
        comments = item.get("comments", []) or []
        comments_array = [
            {
                "comment_id": c.get("id"),
                "author": c.get("author"),
                "body": c.get("body"),
                "ups": c.get("ups"),
                "url": c.get("url"),
                "created_utc": str(c.get("created_utc")) if c.get("created_utc") else None,
            }
            for c in comments
        ]
        row = {
            "subreddit": post.get("subreddit"),
            "post": f"post{post.get('post_rank')}" if post.get("post_rank") else "post",
            "posted on": str(post.get("created_utc")) if post.get("created_utc") else None,
            "author": post.get("author"),
            "likes": post.get("ups"),
            "Comments": len(comments),
            "post_age_days": post.get("post_age_days"),
            "post_flair": post.get("link_flair_text"),
            "post_id": post.get("id"),
            "post_title": post.get("title"),
            "post_selftext": post.get("selftext"),
            "post_url": item.get("post_url")
            or (f"https://www.reddit.com/r/{post.get('subreddit')}/comments/{post.get('id')}/" if post.get("subreddit") and post.get("id") else None),
            "post_upvote_ratio": post.get("upvote_ratio"),
            "post_num_comments": post.get("num_comments"),
            "post_rank": post.get("post_rank"),
            "comment_id_array": json.dumps([c.get("comment_id") for c in comments_array], ensure_ascii=False),
            "comment_author_array": json.dumps([c.get("author") for c in comments_array], ensure_ascii=False),
            "comment_body_array": json.dumps([c.get("body") for c in comments_array], ensure_ascii=False),
            "comment_ups_array": json.dumps([c.get("ups") for c in comments_array], ensure_ascii=False),
            "comment_url_array": json.dumps([c.get("url") for c in comments_array], ensure_ascii=False),
            "comment_created_utc_array": json.dumps([c.get("created_utc") for c in comments_array], ensure_ascii=False),
            "comments_array": json.dumps(comments_array, ensure_ascii=False),
            "imgbb_link": post.get("imgbb_link"),
            "scraped_at_utc": post.get("scraped_at_utc"),
        }
        rows.append(row)
    return rows


def _rows_to_csv(rows):
    if not rows:
        return ""
    headers = list(rows[0].keys())
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=headers)
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue()

limits_col1, limits_col2 = st.columns(2)
with limits_col1:
    posts_per_subreddit = st.number_input(
        "Posts per subreddit",
        min_value=1,
        max_value=25,
        value=5,
        step=1,
    )
with limits_col2:
    comments_per_post = st.number_input(
        "Comments per post",
        min_value=1,
        max_value=20,
        value=3,
        step=1,
    )

tab_subs, tab_urls, tab_script = st.tabs(["Subreddit List", "Post URL", "Generate Script"])

with tab_subs:
    default_subreddits = "\n".join(
        ["REBubble", "BayAreaRealEstate", "FirstTimeHomeBuyer", "RealEstate", "realtors"]
    )
    manual_subreddits = st.text_area(
        "Subreddits (one per line)",
        value=default_subreddits,
        height=140,
    )

    if st.button("Fetch from Subreddits", use_container_width=True):
        subs = [s.strip() for s in manual_subreddits.replace(",", "\n").splitlines() if s.strip()]
        if not subs:
            st.error("Provide at least one subreddit.")
        elif not imgbb_api_key.strip():
            st.error("Missing `IMGBB_API_KEY`. Set it in `.env` (local) or `st.secrets` / Streamlit Cloud Secrets.")
        else:
            with st.spinner("Fetching posts/comments from subreddit list..."):
                results = fetch_for_subreddits(
                    subs,
                    posts_per_subreddit=int(posts_per_subreddit),
                    comments_per_post=int(comments_per_post),
                    imgbb_api_key=imgbb_api_key,
                )
            st.session_state["last_results"] = results
            rows = _results_to_rows(results)
            st.session_state["stored_rows"].extend(rows)
            st.session_state["last_csv_data"] = _rows_to_csv(rows)
            st.success(f"Completed. Retrieved {len(results)} posts.")
            if st.session_state["last_csv_data"]:
                st.download_button(
                    "Download Retrieved CSV",
                    data=st.session_state["last_csv_data"],
                    file_name="retrieved_posts_subreddits.csv",
                    mime="text/csv",
                    use_container_width=True,
                    key="download_csv_subs",
                )

with tab_urls:
    post_urls_text = st.text_area(
        "Post links (one per line)",
        value="https://www.reddit.com/r/RealEstate/comments/1rc6cty/advice_regarding_a_realtor/",
        height=140,
    )
    if st.button("Fetch from Post URLs", use_container_width=True):
        post_urls = [u.strip() for u in post_urls_text.splitlines() if u.strip()]
        if not post_urls:
            st.error("Provide at least one Reddit post URL.")
        elif not imgbb_api_key.strip():
            st.error("Missing `IMGBB_API_KEY`. Set it in `.env` (local) or `st.secrets` / Streamlit Cloud Secrets.")
        else:
            with st.spinner("Fetching post details from URL list..."):
                results = fetch_for_post_urls(
                    post_urls=post_urls,
                    comments_per_post=int(comments_per_post),
                    imgbb_api_key=imgbb_api_key,
                )
            st.session_state["last_results"] = results
            rows = _results_to_rows(results)
            st.session_state["stored_rows"].extend(rows)
            st.session_state["last_csv_data"] = _rows_to_csv(rows)
            st.success(f"Completed. Retrieved {len(results)} posts.")
            if st.session_state["last_csv_data"]:
                st.download_button(
                    "Download Retrieved CSV",
                    data=st.session_state["last_csv_data"],
                    file_name="retrieved_posts_urls.csv",
                    mime="text/csv",
                    use_container_width=True,
                    key="download_csv_urls",
                )

with tab_script:
    st.subheader("Script Generator (Gemini)")
    default_prompt = """You are my Snaphomz CMO + Apple-level Creative Director + Short-form Scriptwriter.

Generate Instagram Reel scripts from ONLY this data:
- post_title
- post_selftext
- Comments
- comments_array

OUTPUT REQUIREMENTS (VERY STRICT)
1) Return ONLY the scripts. No analysis. No explanation. No bullet-point notes. No tables.
2) Do NOT include timestamps.
3) Do NOT include headings/labels like “Hook,” “Problem,” “Analysis,” “Solution,” “Outro,” “Section 1,” etc.
4) Each script must still follow this narrative flow internally:
   - Start with a high-retention hook
   - State the real problem viewers are feeling
   - Give a clear, logical analysis that cuts through confusion
   - End with an actionable solution + a clean outro
   Write it as one continuous, natural script with paragraph breaks only.
SCRIPT COUNT + LENGTH
6) Write 6 scripts total.
7) Each script must be 50–60 seconds (Reel-friendly, dense with value).

APPLE-LEVEL STYLE (MUST)
8) The scripts must feel “Apple-level”:
   - Minimal, crisp, premium.
   - Short sentences. Clear logic.
   - Calm confidence. Emotionally intelligent.
   - No cringe. No hype. No emojis. No excessive slang.
   - No filler like “In today’s video,” “like and subscribe,” etc.
   - Avoid “guru” energy. Sound like a trusted product team explaining clearly.

REDDIT VOICE-OF-CUSTOMER (MUST)
9) Use Reddit comments to capture real voice-of-customer:
   - Pull the fears, objections, debates, and hot takes people are actually having.
   - Paraphrase. Do NOT quote long lines verbatim.
   - Do NOT reveal usernames or personal info.

USE THE PROVIDED FIELDS INTELLIGENTLY (MUST)
10) Use the fields as signals to choose and shape content:
   - Prioritize higher "post_rank" and higher "comment_rank" first.
   - Use "post_flair" to ensure variety across topics.
   - Use "post_upvote_ratio", "likes", "comment_ups" to detect what resonates or is controversial.
   - Use "post_age_days" / "posted on" to bias toward recent topics (but evergreen angles are allowed).
   - Use "post_num_comments" to spot high-discussion threads.
   - If "imgbb_link" exists, assume there may be an image/screenshot referenced; describe it generically (do not mention imgbb).

SAFETY + ACCURACY (MUST)
11) No legal/financial advice.
    - Use safe language: “generally,” “often,” “a good starting point,” “depends,” “for your situation.”
    - If the CSV doesn’t support a claim, don’t invent it. Keep it general and say what to check next.
12) Privacy:
    - Never include "author" or "comment_author" names.
    - Never include direct links in the script (no "post_url" or "comment_url" spoken aloud).
    - Do not read out IDs.

BRAND INTEGRATION (LIGHT)
13) Mention “Snaphomz” at most once per script, only near the end, as a soft option.
    - No hard selling. No promises. Keep it calm and premium.

CONTENT MIX (ENSURE VARIETY ACROSS 6)
Across the 6 scripts, cover:
- First-time buyer confusion (rates, down payment myths, closing costs, inspections)
- Offers/negotiation reality (contingencies, timelines, seller credits, bidding wars)
- Renting vs buying decision psychology (fear, uncertainty, decision fatigue)
- “Reddit advice vs reality” (myth vs reality, respectfully)

CLARITY FORMULA (USE OFTEN)
- Contrast: “People say X. Reality is Y.”
- Turn chaos into a simple decision rule or checklist.
- Give 3–5 concrete steps (not generic motivation).

Output:
SCRIPT 1:
[hook]
[body]
"""

    prompt_text = st.text_area("Prompt", value=default_prompt, height=220, key="prompt_text")
    scripts_per_post = st.number_input(
        "Scripts per post",
        min_value=1,
        max_value=12,
        value=6,
        step=1,
        help="Generate this many scripts for each selected post.",
    )

    all_rows = st.session_state.get("stored_rows", [])
    valid_rows = [
        r for r in all_rows
        if r.get("post_id") and (
            (r.get("post_title") or "").strip()
            or (r.get("post_selftext") or "").strip()
            or (r.get("comments_array") or "").strip()
        )
    ]
    st.caption(f"Valid content rows available: {len(valid_rows)}")

    mode = st.radio(
        "Selection Mode",
        ["Single Row", "Row Range"],
        horizontal=True,
    )

    selected_rows = []
    if mode == "Single Row":
        target_row_number = st.number_input(
            "Content row number (1-based)",
            min_value=1,
            max_value=max(1, len(valid_rows)),
            value=min(15, max(1, len(valid_rows))),
            step=1,
        )
        if valid_rows:
            selected_rows = [valid_rows[int(target_row_number) - 1]]
    else:
        c1, c2 = st.columns(2)
        with c1:
            start_row = st.number_input(
                "Start row",
                min_value=1,
                max_value=max(1, len(valid_rows)),
                value=1,
                step=1,
            )
        with c2:
            end_row = st.number_input(
                "End row",
                min_value=1,
                max_value=max(1, len(valid_rows)),
                value=min(10, max(1, len(valid_rows))),
                step=1,
            )
        if valid_rows:
            s = min(int(start_row), int(end_row))
            e = max(int(start_row), int(end_row))
            selected_rows = valid_rows[s - 1 : e]

    # Keep only required fields for Gemini input.
    llm_rows = [
        {
            "post_title": r.get("post_title"),
            "post_selftext": r.get("post_selftext"),
            "Comments": r.get("Comments"),
            "comments_array": r.get("comments_array"),
        }
        for r in selected_rows
    ]

    if llm_rows:
        st.markdown("**Selected Data Preview**")
        st.dataframe(llm_rows[:5], use_container_width=True)

    if st.button("Generate Scripts", use_container_width=True, key="generate_scripts"):
        if not gemini_api_key.strip():
            st.error("Missing `GEMINI_API_KEY` in environment (`.env`).")
        elif not llm_rows:
            st.error("No valid rows selected.")
        else:
            generated_blocks = []
            progress = st.progress(0, text="Generating scripts...")
            total = len(selected_rows)

            for i, row in enumerate(selected_rows, start=1):
                llm_row = {
                    "post_title": row.get("post_title"),
                    "post_selftext": row.get("post_selftext"),
                    "Comments": row.get("Comments"),
                    "comments_array": row.get("comments_array"),
                }
                row_prompt = (
                    f"{prompt_text}\n\n"
                    f"Generate exactly {int(scripts_per_post)} scripts for this post.\n\n"
                    "DATASET (JSON):\n"
                    f"{json.dumps([llm_row], ensure_ascii=False, indent=2)}\n\n"
                    "Now generate scripts."
                )
                try:
                    scripts = generate_text_with_gemini(
                        api_key=gemini_api_key,
                        prompt=row_prompt,
                        model=gemini_model,
                    )
                except Exception as e:
                    scripts = f"Generation failed for post_id {row.get('post_id')}: {e}"

                reddit_link = row.get("post_url")
                if not reddit_link and row.get("subreddit") and row.get("post_id"):
                    reddit_link = f"https://www.reddit.com/r/{row.get('subreddit')}/comments/{row.get('post_id')}/"

                generated_blocks.append(
                    {
                        "post_id": row.get("post_id"),
                        "post_title": row.get("post_title"),
                        "subreddit": row.get("subreddit"),
                        "post_url": reddit_link,
                        "scripts": scripts,
                    }
                )
                progress.progress(int(i * 100 / total), text=f"Generated {i}/{total} posts")

            st.session_state["generated_by_post"] = generated_blocks
            progress.empty()

    generated_by_post = st.session_state.get("generated_by_post", [])
    if generated_by_post:
        st.markdown("### Generated Scripts (Per Post)")
        for idx, block in enumerate(generated_by_post, start=1):
            header_cols = st.columns([3, 1])
            with header_cols[0]:
                st.markdown(f"#### Post {idx}: {block.get('post_title') or 'Untitled'}")
                st.caption(f"r/{block.get('subreddit') or ''} | post_id: {block.get('post_id')}")
                if block.get("post_url"):
                    st.markdown(f"[Open Reddit Post]({block.get('post_url')})")
            with header_cols[1]:
                st.download_button(
                    "Download",
                    data=block.get("scripts", ""),
                    file_name=f"scripts_post_{idx}_{block.get('post_id') or 'unknown'}.txt",
                    mime="text/plain",
                    use_container_width=True,
                    key=f"download_scripts_{idx}",
                )

            with st.expander(f"View Scripts for Post {idx}", expanded=(idx == 1)):
                st.text_area(
                    f"Scripts Output {idx}",
                    value=block.get("scripts", ""),
                    height=360,
                    key=f"scripts_output_{idx}",
                )

st.divider()
st.subheader("Latest Retrieved Data")

results = st.session_state.get("last_results", [])
if results:
    for item in results:
        post = item.get("post", {})
        comments = item.get("comments", [])

        meta = st.columns([3, 2])
        with meta[0]:
            st.markdown(f"### {post.get('title', 'Untitled')}")
            st.caption(
                f"r/{post.get('subreddit', '')} | u/{post.get('author', 'unknown')} | "
                f"ups: {post.get('ups', 0)} | comments: {post.get('num_comments', 0)}"
            )
            reddit_link = item.get("post_url")
            if not reddit_link:
                subreddit = post.get("subreddit")
                post_id = post.get("id")
                if subreddit and post_id:
                    reddit_link = f"https://www.reddit.com/r/{subreddit}/comments/{post_id}/"
            if reddit_link:
                st.markdown(f"[Open Reddit Post]({reddit_link})")
            if post.get("link_flair_text"):
                st.markdown(f"`{post.get('link_flair_text')}`")
            if post.get("selftext"):
                st.write(post.get("selftext")[:600] + ("..." if len(post.get("selftext", "")) > 600 else ""))
            with st.expander(f"Top retrieved comments ({len(comments)})"):
                for idx, c in enumerate(comments, start=1):
                    st.markdown(f"**{idx}. u/{c.get('author','unknown')}** ({c.get('ups',0)} ups)")
                    st.write(c.get("body", ""))
                    st.markdown("---")
        with meta[1]:
            if post.get("imgbb_link"):
                st.image(post.get("imgbb_link"), use_column_width=True)
                st.markdown(f"[Open ImgBB Link]({post.get('imgbb_link')})")
            else:
                st.info("No ImgBB link available for this post.")
        st.markdown("---")
else:
    st.info("No data fetched in this session yet.")

st.subheader("Session Snapshot")
stored_rows = st.session_state.get("stored_rows", [])
total_comments = 0
for r in stored_rows:
    try:
        arr = json.loads(r.get("comments_array") or "[]")
        total_comments += len(arr) if isinstance(arr, list) else 0
    except Exception:
        pass
metrics = st.columns(4)
metrics[0].metric("rows", len(stored_rows))
metrics[1].metric("subreddits", len({r.get("subreddit") for r in stored_rows if r.get("subreddit")}))
metrics[2].metric("posts", len({r.get("post_id") for r in stored_rows if r.get("post_id")}))
metrics[3].metric("comments", total_comments)

if stored_rows:
    st.subheader("Recently Retrieved Rows")
    st.dataframe(stored_rows[-30:], use_container_width=True)
    st.download_button(
        "Download All Retrieved CSV (Session)",
        data=_rows_to_csv(stored_rows),
        file_name="retrieved_posts_session.csv",
        mime="text/csv",
        use_container_width=True,
        key="download_csv_session_all",
    )
