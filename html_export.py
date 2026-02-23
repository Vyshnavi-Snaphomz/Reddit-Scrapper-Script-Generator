import os
import html as html_lib
import time
import tempfile
import io
from contextlib import redirect_stdout, redirect_stderr
from datetime import datetime, timezone
from typing import Dict, Iterable, List, Optional


def _to_unix_seconds(value: Optional[datetime]) -> int:
    if not value:
        return 0
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    else:
        value = value.astimezone(timezone.utc)
    return int(value.timestamp())


def format_time_ago(created_utc_seconds: int) -> str:
    if not created_utc_seconds:
        return ""
    seconds = int(time.time()) - int(created_utc_seconds)
    if seconds < 3600:
        return f"{max(1, seconds // 60)}m ago"
    if seconds < 86400:
        return f"{seconds // 3600}h ago"
    if seconds < 86400 * 30:
        return f"{seconds // 86400}d ago"
    if seconds < 86400 * 365:
        return f"{seconds // (86400 * 30)}mo ago"
    return f"{seconds // (86400 * 365)}yr ago"


def format_number(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


_AVATAR_COLOURS = [
    "#FF4500",
    "#FF6534",
    "#46D160",
    "#0DD3BB",
    "#0079D3",
    "#FFB000",
    "#FF585B",
    "#7193FF",
    "#25B79F",
    "#DB0064",
    "#A06EFF",
    "#ED9C00",
]


def avatar_color(username: str) -> str:
    return _AVATAR_COLOURS[sum(ord(c) for c in username) % len(_AVATAR_COLOURS)]


_SNOO = """
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 40 40" width="36" height="36">
  <circle cx="20" cy="20" r="20" fill="#FF4500"/>
  <ellipse cx="20" cy="25" rx="13" ry="10" fill="white"/>
  <ellipse cx="7.5" cy="22" rx="3.5" ry="4.5" fill="white"/>
  <ellipse cx="32.5" cy="22" rx="3.5" ry="4.5" fill="white"/>
  <circle cx="15" cy="22.5" r="3" fill="#FF4500"/>
  <circle cx="15.9" cy="21.6" r="1.1" fill="white"/>
  <circle cx="25" cy="22.5" r="3" fill="#FF4500"/>
  <circle cx="25.9" cy="21.6" r="1.1" fill="white"/>
  <path d="M14 28.5 Q20 32.5 26 28.5" stroke="#FF4500" stroke-width="1.8"
        fill="none" stroke-linecap="round"/>
  <line x1="20" y1="15" x2="26.5" y2="7" stroke="white"
        stroke-width="2" stroke-linecap="round"/>
  <circle cx="27.5" cy="6" r="3.2" fill="white"/>
</svg>
"""


def build_card_html(post: Dict, comments: Iterable[Dict], sub_name: str) -> str:
    title = html_lib.escape(post.get("title", ""))
    author = html_lib.escape(post.get("author", "Unknown"))
    ups = int(post.get("ups", 0) or 0)
    num_comments = int(post.get("num_comments", 0) or 0)
    created_utc = _to_unix_seconds(post.get("created_utc"))
    flair_text = post.get("link_flair_text", "") or ""

    time_ago = format_time_ago(created_utc)
    ups_str = format_number(ups)
    cmt_str = format_number(num_comments)

    raw_body = post.get("selftext", "") or ""
    body_escaped = html_lib.escape(raw_body)
    if len(body_escaped) > 2000:
        body_escaped = body_escaped[:2000] + "..."
    body_html_inner = body_escaped.replace("\n\n", "</p><p>").replace("\n", "<br>")
    body_section = (
        f'<div class="post-body"><p>{body_html_inner}</p></div>' if body_escaped.strip() else ""
    )
    flair_section = (
        f'<span class="flair">{html_lib.escape(flair_text)}</span>' if flair_text else ""
    )

    comment_blocks: List[str] = []
    for c in comments:
        c_author_raw = c.get("author") or "Unknown"
        c_author = html_lib.escape(c_author_raw)
        c_initial = c_author_raw[0].upper() if c_author_raw else "?"
        c_color = avatar_color(c_author_raw)
        c_score = format_number(int(c.get("ups", c.get("score", 0)) or 0))
        c_time = format_time_ago(_to_unix_seconds(c.get("created_utc")))
        c_time_str = (
            f'<span class="c-dot">&#8226;</span><span class="c-time">{c_time}</span>' if c_time else ""
        )
        raw_c = html_lib.escape(c.get("body", "") or "")
        if len(raw_c) > 600:
            raw_c = raw_c[:600] + "..."
        c_body_html = raw_c.replace("\n", " ")
        comment_blocks.append(
            f"""
        <div class="comment">
          <div class="avatar" style="background:{c_color};">{c_initial}</div>
          <div class="c-right">
            <div class="c-header">
              <span class="c-author">{c_author}</span>
              {c_time_str}
            </div>
            <p class="c-body">{c_body_html}</p>
            <div class="c-actions">
              <div class="c-vote">
                <span class="up-arrow">&#8593;</span>
                <span class="c-score">{c_score}</span>
                <span class="dn-arrow">&#8595;</span>
              </div>
              <span class="c-btn">Reply</span>
              <span class="c-btn">Award</span>
              <span class="c-btn">Share</span>
              <span class="c-btn">&#183;&#183;&#183;</span>
            </div>
          </div>
        </div>"""
        )
    comments_html = "\n".join(comment_blocks) if comment_blocks else (
        '<div class="no-comments">No comments retrieved</div>'
    )

    return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
               "Helvetica Neue", Arial, sans-serif;
  background: #dae0e6;
  width: 800px;
}}
.card {{ background: #fff; width: 100%; }}
.top-nav {{
  display: flex; align-items: center; padding: 14px 16px; gap: 12px;
  background: #fff; border-bottom: 1px solid #edeff1;
}}
.back-btn {{ font-size: 22px; color: #1c1c1c; flex-shrink: 0; line-height: 1; }}
.snoo-wrap {{ flex-shrink: 0; }}
.sub-info  {{ flex: 1; min-width: 0; }}
.sub-line  {{
  font-size: 14px; font-weight: 700; color: #1c1c1c;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}}
.author-line {{ font-size: 12px; color: #878a8c; margin-top: 1px; }}
.more-btn {{ font-size: 20px; color: #878a8c; letter-spacing: 3px; flex-shrink: 0; }}
.post-content {{ padding: 16px 16px 0; }}
.post-title {{ font-size: 20px; font-weight: 700; color: #1c1c1c; line-height: 1.35; margin-bottom: 10px; }}
.flair {{
  display: inline-block; background: #f6f7f8; border: 1px solid #edeff1;
  color: #1c1c1c; font-size: 12px; font-weight: 500; padding: 3px 10px;
  border-radius: 12px; margin-bottom: 12px;
}}
.post-body {{ font-size: 14px; color: #1c1c1c; line-height: 1.75; padding-bottom: 14px; }}
.post-body p {{ margin-bottom: 10px; }}
.post-body p:last-child {{ margin-bottom: 0; }}
.action-bar {{
  display: flex; align-items: center; padding: 10px 16px; gap: 8px;
  border-top: 1px solid #edeff1; flex-wrap: wrap;
}}
.vote-pill {{
  display: flex; align-items: center; background: #f6f7f8;
  border-radius: 20px; padding: 6px 14px; gap: 8px;
}}
.vote-pill .up {{ color: #ff4500; font-size: 18px; font-weight: 900; }}
.vote-pill .cnt {{ font-size: 14px; font-weight: 700; color: #1c1c1c; }}
.vote-pill .down {{ color: #878a8c; font-size: 18px; }}
.act-pill {{
  display: flex; align-items: center; gap: 6px; background: #f6f7f8;
  border-radius: 20px; padding: 6px 14px; font-size: 14px;
  color: #878a8c; font-weight: 500;
}}
.join-conv {{
  display: flex; justify-content: space-between; align-items: center;
  margin: 12px 16px 4px; padding: 11px 18px; background: #f6f7f8;
  border: 1px solid #edeff1; border-radius: 24px; color: #878a8c; font-size: 14px;
}}
.join-arrows {{ display: flex; flex-direction: column; line-height: 1.1; font-size: 10px; color: #878a8c; }}
.sort-bar {{
  display: flex; align-items: center; padding: 10px 16px; gap: 12px;
  border-top: 1px solid #edeff1; border-bottom: 1px solid #edeff1; margin-top: 12px;
}}
.sort-label {{ font-size: 14px; color: #1c1c1c; }}
.sort-label strong {{ font-weight: 700; }}
.search-pill {{
  display: flex; align-items: center; gap: 7px; background: #f6f7f8;
  border-radius: 20px; padding: 6px 14px; font-size: 14px; color: #878a8c;
}}
.comment {{ display: flex; gap: 10px; padding: 14px 16px; border-bottom: 1px solid #f0f2f5; }}
.comment:last-child {{ border-bottom: none; }}
.avatar {{
  width: 34px; height: 34px; min-width: 34px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  font-size: 15px; font-weight: 700; color: #fff;
}}
.c-right {{ flex: 1; min-width: 0; }}
.c-header {{ display: flex; align-items: center; gap: 5px; margin-bottom: 5px; flex-wrap: wrap; }}
.c-author {{ font-size: 13px; font-weight: 700; color: #1c1c1c; }}
.c-dot {{ color: #878a8c; font-size: 11px; }}
.c-time {{ font-size: 12px; color: #878a8c; }}
.c-body {{ font-size: 14px; color: #1c1c1c; line-height: 1.6; margin-bottom: 8px; word-break: break-word; }}
.c-actions {{ display: flex; align-items: center; gap: 14px; flex-wrap: wrap; }}
.c-vote {{ display: flex; align-items: center; gap: 6px; }}
.up-arrow {{ color: #ff4500; font-size: 15px; font-weight: 700; }}
.c-score {{ font-size: 13px; font-weight: 700; color: #1c1c1c; }}
.dn-arrow {{ color: #878a8c; font-size: 15px; }}
.c-btn {{ font-size: 13px; color: #878a8c; font-weight: 600; }}
.no-comments {{ padding: 20px 16px; color: #878a8c; font-size: 14px; font-style: italic; }}
</style></head><body>
<div class="card">
  <div class="top-nav">
    <div class="back-btn">&#8592;</div>
    <div class="snoo-wrap">{_SNOO}</div>
    <div class="sub-info">
      <div class="sub-line">r/{html_lib.escape(sub_name)}&nbsp;&bull;&nbsp;{time_ago}</div>
      <div class="author-line">{author}</div>
    </div>
    <div class="more-btn">&#8230;</div>
  </div>
  <div class="post-content">
    <h1 class="post-title">{title}</h1>
    {flair_section}
    {body_section}
  </div>
  <div class="action-bar">
    <div class="vote-pill">
      <span class="up">&#8679;</span>
      <span class="cnt">{ups_str}</span>
      <span class="down">&#8681;</span>
    </div>
    <div class="act-pill">&#128172;&nbsp;{cmt_str}</div>
    <div class="act-pill">&#127942;&nbsp;Award</div>
    <div class="act-pill">&#8599;&nbsp;Share</div>
  </div>
  <div class="join-conv">
    <span>Join the conversation</span>
    <div class="join-arrows"><span>&#9650;</span><span>&#9660;</span></div>
  </div>
  <div class="sort-bar">
    <div class="sort-label">Sort by:&nbsp;<strong>Best</strong>&nbsp;&#9660;</div>
    <div class="search-pill">&#128269;&nbsp;Search Comments</div>
  </div>
  <div class="comments-wrap">
    {comments_html}
  </div>
</div>
</body></html>"""


def _safe_name(s: str) -> str:
    return "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in s)


def export_post_assets(post: Dict, comments: Iterable[Dict], output_dir: Optional[str] = None) -> Dict[str, Optional[str]]:
    target_dir = output_dir or tempfile.gettempdir()
    os.makedirs(target_dir, exist_ok=True)
    subreddit = _safe_name(post.get("subreddit") or "subreddit")
    post_id = _safe_name(post.get("id") or "post")
    post_rank = post.get("post_rank") or 0
    base = f"{subreddit}_post{post_rank}_{post_id}"

    html_path = os.path.join(target_dir, f"{base}.html")
    html_text = build_card_html(post, comments, subreddit)
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_text)

    image_path = None
    try:
        from html2image import Html2Image

        hti = Html2Image(output_path=target_dir)
        image_name = f"{base}.png"
        # Suppress html2image/chrome stdout like "xxxx bytes written to file ..."
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            hti.screenshot(html_str=html_text, save_as=image_name, size=(800, 3000))
        image_path = os.path.join(target_dir, image_name)
    except Exception as e:
        print(f"Image render skipped for post {post_id}: {e}")

    return {"html_path": html_path, "image_path": image_path}
