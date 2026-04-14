"""Orchestrator: reads the latest raw odds JSON from GCS and loads it into BigQuery."""

import json
import logging

from dotenv import load_dotenv
from google.cloud import storage

from src.config import load_config
from src.processing.transform import flatten_odds
from src.processing.load_bq import load_to_bigquery

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s — %(levelname)s — %(message)s")
logger = logging.getLogger(__name__)

_DATASET_NAME = "tennis_data"
_TABLE_NAME = "raw_odds"
_GCS_PREFIX = "raw/"


def _get_latest_blob(bucket: storage.Bucket, prefix: str) -> storage.Blob:
    """Return the most recently created blob under the given GCS prefix.

    Args:
        bucket: An authenticated GCS Bucket object.
        prefix: The GCS object prefix to filter by (e.g. ``"raw/"``).

    Returns:
        The most recently created ``storage.Blob``.

    Raises:
        FileNotFoundError: If no blobs are found under the prefix.
    """
    blobs = sorted(
        bucket.list_blobs(prefix=prefix),
        key=lambda b: b.time_created,
        reverse=True,
    )
    if not blobs:
        raise FileNotFoundError(f"No files found in GCS under prefix '{prefix}'.")
    return blobs[0]


def run_etl() -> None:
    """Execute the full ETL pipeline: GCS → transform → BigQuery.

    Reads required configuration from environment variables:
        - ``GCP_BUCKET_NAME``: Source GCS bucket.
        - ``GCP_PROJECT_ID``: Target GCP project for BigQuery.

    Raises:
        EnvironmentError: If required environment variables are not set.
        FileNotFoundError: If no raw files exist in the GCS bucket.
        ValueError: If the downloaded JSON is empty or malformed.
        google.cloud.exceptions.GoogleCloudError: On any GCP API failure.
    """
    config = load_config()
    bucket_name = config["gcp"]["bucket_name"]
    project_id = config["gcp"]["project_id"]

    # --- Extract ---
    logger.info("Connecting to GCS bucket '%s'...", bucket_name)
    gcs_client = storage.Client()
    bucket = gcs_client.bucket(bucket_name)

    latest_blob = _get_latest_blob(bucket, _GCS_PREFIX)
    logger.info("Reading file: gs://%s/%s", bucket_name, latest_blob.name)

    raw_json = latest_blob.download_as_text()
    data: list[dict] = json.loads(raw_json)
    logger.info("Downloaded %d events from GCS.", len(data))

    # --- Transform ---
    df = flatten_odds(data)
    logger.info("Transform complete. DataFrame shape: %s", df.shape)

    # --- Load ---
    load_to_bigquery(
        df=df,
        project_id=project_id,
        dataset_name=_DATASET_NAME,
        table_name=_TABLE_NAME,
    )

    logger.info("ETL pipeline complete.")


if __name__ == "__main__":
    run_etl()
