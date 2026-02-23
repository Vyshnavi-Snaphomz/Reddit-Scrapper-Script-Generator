import logging
import requests
# import subprocess

from fastapi import FastAPI, Form, BackgroundTasks
from fastapi.responses import JSONResponse
from db import db
from match_feature import find_top_k_features
from datetime import datetime, timedelta

logging.basicConfig(level=logging.INFO)
app = FastAPI()
ISSUES_COLL = db["issues"]

def process_slack_command(token, user_id, channel_id, command, text, response_url):
    logging.info("Background task started for Slack command")
    try:
        text = text.lower().strip()
        blocks = []
        
        # if "updates" in text:
        #     week_ago = datetime.utcnow() - timedelta(days=7)
        #     issues = list(
        #         ISSUES_COLL.find({"post_created_utc": {"$gte": week_ago}})
        #         .sort("post_created_utc", -1)
        #         .limit(10)
        #         )
        #     reply_text = f"Here are the top {len(issues)} issues from this week:" if issues else "No updates found this week."

        if "updates" in text:
            # subprocess.Popen(["python3", "main.py"])

            week_ago = datetime.utcnow() - timedelta(days=7)
            issues = list(
                ISSUES_COLL.find({"post_created_utc": {"$gte": week_ago}})
                .sort("post_created_utc", -1)
                .limit(10)
            )

            reply_text = (
                f"Here are the top {len(issues)} issues from this week:"
                if issues else "No updates found this week."
            )

        elif "issues" in text:
            issues = list(ISSUES_COLL.find().sort("post_created_utc", -1).limit(5))
            reply_text = "Here are the 5 most recent issues:" if issues else "No issues found."
        elif "help" in text:
            issues = []
            reply_text = "*/snapreddit issues* - Top 5 most recent issues and SnapHomz features\n\n*/snapreddit updates* - past 1 week updates"
        else:
            issues = []
            reply_text = "Command not recognized."

        for i, issue in enumerate(issues, start=1):
            issues_array = issue.get("issues", [])
            issue_text = "\n".join(f"- {item}" for item in issues_array) if issues_array else "No issues listed."
            
            matched_features = find_top_k_features(issue_text, k=1)
            feature_name = matched_features[0]["text"] if matched_features else "N/A"
            
            date = issue.get("post_created_utc", "N/A")
            url = issue.get("post_url", "N/A")
            
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*{i}.* *Snaphomz * {feature_name} {url}\n\n *Date:* {date}\n\n*Issues:*\n{issue_text}\n\n"
                }
            })

        payload = {"response_type": "in_channel", "text": reply_text, "blocks": blocks}
        response = requests.post(response_url, json=payload)
        logging.info(f"Posted message to Slack, status {response.status_code}")
        response.raise_for_status()
    except Exception as e:
        logging.error(f"Error sending message to Slack: {e}")

@app.post("/slack/command")
async def handle_slash_command(
    background_tasks: BackgroundTasks,
    token: str = Form(...),
    user_id: str = Form(...),
    channel_id: str = Form(...),
    command: str = Form(...),
    text: str = Form(...),
    response_url: str = Form(...)
):
    background_tasks.add_task(process_slack_command, token, user_id, channel_id, command, text, response_url)
    return JSONResponse(content={"response_type": "ephemeral", "text": "Request received, processing..."})