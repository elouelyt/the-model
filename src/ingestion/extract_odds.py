"""Module for extracting tennis odds from The-Odds-API and uploading to GCS or saving locally."""

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s — %(levelname)s — %(message)s")
logger = logging.getLogger(__name__)

_BASE_URL = "https://api.the-odds-api.com/v4/sports"
_ATP_KEY_PREFIX = "tennis_atp_"
_REGIONS = "us"
_MARKETS = "h2h"


def fetch_active_atp_sport_keys(api_key: str) -> list[str]:
    """Fetch all currently active ATP singles tournament sport keys from The-Odds-API.

    Queries the /v4/sports/ endpoint and filters for keys prefixed with
    'tennis_atp_', which covers all active ATP singles tournaments. This
    avoids hardcoding tournament names since tournaments are ephemeral
    (typically 1-2 weeks long).

    Args:
        api_key: The-Odds-API authentication key.

    Returns:
        A list of active ATP sport key strings (e.g. ['tennis_atp_monte_carlo']).
        Returns an empty list if no ATP tournaments are currently active.

    Raises:
        requests.HTTPError: If the API returns a non-200 status code.
    """
    url = f"{_BASE_URL}/"
    response = requests.get(url, params={"apiKey": api_key}, timeout=30)
    response.raise_for_status()

    all_sports: list[dict] = response.json()
    atp_keys = [
        sport["key"]
        for sport in all_sports
        if sport["key"].startswith(_ATP_KEY_PREFIX) and sport.get("active", False)
    ]

    logger.info("Found %d active ATP tournament(s): %s", len(atp_keys), atp_keys)
    return atp_keys


def fetch_odds() -> list[dict]:
    """Fetch upcoming H2H odds for all active ATP tournaments from The-Odds-API.

    Dynamically discovers active ATP sport keys so no tournament name is
    ever hardcoded. Returns an empty list if no ATP tournaments are active,
    which the UI should surface as 'no upcoming matches'.

    Returns:
        A combined list of event dicts across all active ATP tournaments.
        Empty list if no active tournaments are found.

    Raises:
        EnvironmentError: If THE_ODDS_API_KEY is not set.
        requests.HTTPError: If any API call returns a non-200 status code.
    """
    api_key = os.getenv("THE_ODDS_API_KEY")
    if not api_key:
        raise EnvironmentError("THE_ODDS_API_KEY is not set in the environment.")

    sport_keys = fetch_active_atp_sport_keys(api_key)

    if not sport_keys:
        logger.warning("No active ATP tournaments found. Returning empty event list.")
        return []

    all_events: list[dict] = []
    params = {
        "apiKey": api_key,
        "regions": _REGIONS,
        "markets": _MARKETS,
    }

    for sport_key in sport_keys:
        url = f"{_BASE_URL}/{sport_key}/odds/"
        logger.info("Fetching odds for %s (regions=%s, markets=%s)...", sport_key, _REGIONS, _MARKETS)
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()

        events: list[dict] = response.json()
        logger.info("Fetched %d events for %s.", len(events), sport_key)
        all_events.extend(events)

    logger.info("Total events fetched across all ATP tournaments: %d", len(all_events))
    return all_events


def save_locally(data: list[dict], output_dir: str = "data/raw") -> Path:
    """Serialize data as JSON and save it to a local directory for sandbox exploration.

    Args:
        data: The list of event dicts to save.
        output_dir: Relative path to the local output directory.

    Returns:
        The Path of the saved file.
    """
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_path = Path(output_dir) / f"tennis_odds_{timestamp}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    logger.info("Saved %d events locally to %s", len(data), out_path)
    return out_path


def upload_to_gcs(data: list[dict], bucket_name: str) -> str:
    """Serialize data as JSON and upload it to a GCS bucket.

    Authentication uses Application Default Credentials (ADC). Run
    ``gcloud auth application-default login`` locally, or attach a
    service account when deploying to GCP.

    Args:
        data: The list of event dicts to upload.
        bucket_name: Target GCS bucket name (without ``gs://`` prefix).

    Returns:
        The full GCS URI of the uploaded object (e.g. ``gs://bucket/raw/...``).

    Raises:
        google.cloud.exceptions.GoogleCloudError: On any GCS failure.
    """
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    blob_name = f"raw/tennis_odds_{timestamp}.json"

    from google.cloud import storage  # noqa: PLC0415 — lazy import, not needed without GCP
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_name)

    blob.upload_from_string(
        data=json.dumps(data, indent=2),
        content_type="application/json",
    )

    gcs_uri = f"gs://{bucket_name}/{blob_name}"
    logger.info("Uploaded %d events to %s", len(data), gcs_uri)
    return gcs_uri


if __name__ == "__main__":
    # Sprint 3 sandbox mode: fetch all active ATP tournaments dynamically.
    # Returns empty list if no tournaments are active — UI handles this case.
    odds_data = fetch_odds()
    if not odds_data:
        print("No upcoming ATP matches found. Try again when a tournament is active.")
    else:
        local_path = save_locally(odds_data)
        print(f"Success! {len(odds_data)} events saved locally to: {local_path}")
