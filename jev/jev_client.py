"""Minimal client for TypeSafe's Jev (POST https://api.typesafe.ai/v1/systemone).

Jev is a classifier, not a generator: it gets a `state` (text) and named questions and returns, for a `noul` question, the probability
of "yes". The key lives in .env as TYPESAFE_API_KEY (never in the repo).
"""

import os
import time

import requests

URL = "https://api.typesafe.ai/v1/systemone"
MODEL = "jev-latest"


def ask(state: str | dict, questions: dict, model: str = MODEL, long_context: bool = True, retries: int = 3) -> dict:
    """Return the parsed response ({model, answers, usage}). Raises RuntimeError with the API detail on failure."""
    key = os.environ.get("TYPESAFE_API_KEY")
    if not key:
        raise RuntimeError("TYPESAFE_API_KEY is not set")
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    if long_context:
        headers["TypeSafe-Danger-Zone-Long-Context"] = "true"
    body = {"model": model, "state": state, "questions": questions}
    last = ""
    for attempt in range(retries):
        try:
            r = requests.post(URL, headers=headers, json=body, timeout=180)
        except requests.RequestException as exc:
            last = str(exc)
        else:
            if r.status_code == 200:
                return r.json()
            last = f"{r.status_code} {r.text[:400]}"
            if r.status_code < 500 and r.status_code != 429:
                break
        time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"Jev request failed: {last}")


def probabilities(state: str | dict, questions: dict, model: str = MODEL) -> tuple[dict[str, float], dict]:
    """noul questions only -> ({name: P(yes)}, usage)."""
    res = ask(state, questions, model)
    return {k: float(v["noul"]) for k, v in res["answers"].items()}, res.get("usage", {})
