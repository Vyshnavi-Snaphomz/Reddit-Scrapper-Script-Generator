import requests


def generate_text_with_gemini(api_key: str, prompt: str, model: str = "gemini-1.5-flash"):
    if not api_key.strip():
        raise ValueError("Missing GEMINI_API_KEY")

    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.6,
            "maxOutputTokens": 8192,
        },
    }

    def _normalize_model_name(m: str) -> str:
        m = (m or "").strip()
        return m.replace("models/", "")

    def _list_generate_models() -> list[str]:
        url = "https://generativelanguage.googleapis.com/v1beta/models"
        headers = {"x-goog-api-key": api_key}
        resp = requests.get(url, headers=headers, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        models = []
        for item in data.get("models", []):
            methods = item.get("supportedGenerationMethods", []) or []
            if "generateContent" in methods:
                name = item.get("name", "")
                if name.startswith("models/"):
                    name = name.split("/", 1)[1]
                if name:
                    models.append(name)
        return models

    # Try user model first, then modern known models, then discovered models.
    fallback_models = [
        "gemini-2.5-flash",
        "gemini-2.0-flash",
        "gemini-1.5-flash",
        "gemini-1.5-pro",
    ]
    discovered = []
    try:
        discovered = _list_generate_models()
    except Exception:
        discovered = []

    models_to_try = []
    for m in [_normalize_model_name(model)] + fallback_models + discovered:
        m = _normalize_model_name(m)
        if m and m not in models_to_try:
            models_to_try.append(m)

    last_error = None
    for m in models_to_try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent"
        headers = {"x-goog-api-key": api_key, "Content-Type": "application/json"}
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=120)
            resp.raise_for_status()
            data = resp.json()
            candidates = data.get("candidates", [])
            if not candidates:
                return ""
            parts = candidates[0].get("content", {}).get("parts", [])
            return "".join(p.get("text", "") for p in parts if p.get("text"))
        except requests.HTTPError as e:
            last_error = e
            # 404 often means invalid/unsupported model; try next model.
            if getattr(e.response, "status_code", None) == 404:
                continue
            raise

    raise RuntimeError(
        f"No valid Gemini model found. Tried: {', '.join(models_to_try)}. Last error: {last_error}"
    )
