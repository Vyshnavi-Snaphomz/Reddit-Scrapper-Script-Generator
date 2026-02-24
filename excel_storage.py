import json
import os
from datetime import datetime
from typing import Dict, Iterable, List, Optional

import gspread
from google.oauth2.service_account import Credentials


SHEET_ID = os.getenv("GOOGLE_SHEET_ID", "")
WORKSHEET_NAME = os.getenv("GOOGLE_WORKSHEET_NAME", "scraped_data")
# Kept name for compatibility with existing imports/usages in app UI.
EXCEL_PATH = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}" if SHEET_ID else "GOOGLE_SHEET_ID not set"

HEADERS = [
    "subreddit",
    "post",
    "posted on",
    "author",
    "likes",
    "Comments",
    "post_age_days",
    "post_flair",
    "post_id",
    "post_title",
    "post_selftext",
    "post_url",
    "post_upvote_ratio",
    "post_num_comments",
    "post_rank",
    "comment_id_array",
    "comment_author_array",
    "comment_body_array",
    "comment_ups_array",
    "comment_url_array",
    "comment_created_utc_array",
    "comments_array",
    "imgbb_link",
    "scraped_at_utc",
]


def _now_iso() -> str:
    return datetime.utcnow().isoformat()


def _dt_to_iso(val):
    return val.isoformat() if val else None


def _service_account_info() -> dict:
    raw = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    if not raw:
        raise RuntimeError("Missing GOOGLE_SERVICE_ACCOUNT_JSON in environment/secrets.")
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise RuntimeError("GOOGLE_SERVICE_ACCOUNT_JSON is not valid JSON.") from e


def _worksheet():
    if not SHEET_ID:
        raise RuntimeError("Missing GOOGLE_SHEET_ID in environment/secrets.")

    info = _service_account_info()
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_info(info, scopes=scopes)
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(SHEET_ID)
    try:
        ws = sh.worksheet(WORKSHEET_NAME)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=WORKSHEET_NAME, rows=1000, cols=len(HEADERS) + 5)
    _ensure_headers(ws)
    return ws


def _ensure_headers(ws):
    row1 = ws.row_values(1)
    if row1 != HEADERS:
        ws.update("A1", [HEADERS])


def _append_rows(rows: Iterable[List]):
    ws = _worksheet()
    rows = list(rows)
    if not rows:
        return
    normalized = []
    width = len(HEADERS)
    for r in rows:
        if len(r) < width:
            r = r + [None] * (width - len(r))
        elif len(r) > width:
            r = r[:width]
        normalized.append(r)
    ws.append_rows(normalized, value_input_option="USER_ENTERED")


def append_rows(rows: Iterable[Dict]) -> None:
    rows = list(rows or [])
    if not rows:
        return
    as_lists = []
    for row in rows:
        as_lists.append([row.get(h) for h in HEADERS])
    _append_rows(as_lists)


def append_subreddit_block(
    subreddit: str,
    query: Optional[str] = None,
    title: Optional[str] = None,
    description: Optional[str] = None,
) -> None:
    row = [
        subreddit,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        _now_iso(),
    ]
    _append_rows([row])


def append_post_comment_block(post: Dict, comments: Iterable[Dict], show_subreddit: bool) -> None:
    post_rank = post.get("post_rank")
    post_label = f"post{post_rank}" if post_rank else "post"
    comment_rows = list(comments) if comments else []
    comments_array = [
        {
            "comment_id": c.get("id"),
            "author": c.get("author"),
            "body": c.get("body"),
            "ups": c.get("ups"),
            "url": c.get("url"),
            "created_utc": _dt_to_iso(c.get("created_utc")),
        }
        for c in comment_rows
    ]
    comment_id_array = [c.get("comment_id") for c in comments_array]
    comment_author_array = [c.get("author") for c in comments_array]
    comment_body_array = [c.get("body") for c in comments_array]
    comment_ups_array = [c.get("ups") for c in comments_array]
    comment_url_array = [c.get("url") for c in comments_array]
    comment_created_utc_array = [c.get("created_utc") for c in comments_array]

    row = [
        post.get("subreddit") if show_subreddit else None,
        post_label,
        _dt_to_iso(post.get("created_utc")),
        post.get("author"),
        post.get("ups"),
        len(comment_rows),
        post.get("post_age_days"),
        post.get("link_flair_text"),
        post.get("id"),
        post.get("title"),
        post.get("selftext"),
        post.get("url"),
        post.get("upvote_ratio"),
        post.get("num_comments"),
        post_rank,
        json.dumps(comment_id_array, ensure_ascii=False),
        json.dumps(comment_author_array, ensure_ascii=False),
        json.dumps(comment_body_array, ensure_ascii=False),
        json.dumps(comment_ups_array, ensure_ascii=False),
        json.dumps(comment_url_array, ensure_ascii=False),
        json.dumps(comment_created_utc_array, ensure_ascii=False),
        json.dumps(comments_array, ensure_ascii=False),
        post.get("imgbb_link"),
        _now_iso(),
    ]
    _append_rows([row])


def append_post_row(post: Dict, post_rank: int) -> None:
    return None


def append_comment_rows(subreddit: str, post: Dict, comments: Iterable[Dict]) -> None:
    append_post_comment_block(post, comments, show_subreddit=False)


def append_subreddits(records: Iterable[Dict]) -> None:
    for rec in records:
        append_subreddit_block(
            subreddit=rec.get("name"),
            query=rec.get("query"),
            title=rec.get("title"),
            description=rec.get("description"),
        )


def append_posts(records: Iterable[Dict]) -> None:
    return None


def append_comments(subreddit: str, post_id: str, comments: Iterable[Dict]) -> None:
    return None


def _all_rows() -> List[Dict]:
    ws = _worksheet()
    values = ws.get_all_values()
    if not values:
        return []
    headers = values[0]
    rows = []
    for raw in values[1:]:
        if not any((cell or "").strip() for cell in raw):
            continue
        if len(raw) < len(headers):
            raw = raw + [""] * (len(headers) - len(raw))
        row = {headers[i]: raw[i] for i in range(len(headers))}
        rows.append(row)
    return rows


def get_subreddits(query: Optional[str] = None) -> List[str]:
    rows = _all_rows()
    seen = set()
    out = []
    for row in rows:
        subreddit = row.get("subreddit")
        if not subreddit or subreddit in seen:
            continue
        seen.add(subreddit)
        out.append(subreddit)
    return out


def counts() -> Dict[str, int]:
    rows = _all_rows()
    total_comments = 0
    for r in rows:
        try:
            arr = json.loads(r.get("comments_array") or "[]")
            total_comments += len(arr) if isinstance(arr, list) else 0
        except Exception:
            continue
    return {
        "rows": len(rows),
        "subreddits": len({r.get("subreddit") for r in rows if r.get("subreddit")}),
        "posts": len({r.get("post_id") for r in rows if r.get("post_id")}),
        "comments": total_comments,
    }


def get_recent_rows(limit: int = 50) -> List[Dict]:
    rows = _all_rows()
    if limit <= 0:
        return rows
    return rows[-limit:]


def get_all_rows() -> List[Dict]:
    return _all_rows()
