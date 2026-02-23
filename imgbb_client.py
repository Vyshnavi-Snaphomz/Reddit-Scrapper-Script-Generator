import base64
from typing import Optional

import requests


def upload_image_to_imgbb(image_path: str, api_key: str, timeout: int = 45) -> Optional[str]:
    with open(image_path, "rb") as f:
        image_b64 = base64.b64encode(f.read()).decode("utf-8")

    url = "https://api.imgbb.com/1/upload"
    response = requests.post(
        url,
        data={"key": api_key, "image": image_b64},
        timeout=timeout,
    )
    response.raise_for_status()
    payload = response.json()
    if not payload.get("success"):
        return None
    return payload.get("data", {}).get("url")
