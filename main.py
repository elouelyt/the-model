"""Entrypoint for Sprint 1: extract tennis odds and upload to GCS."""

from dotenv import load_dotenv

from src.config import load_config
from src.ingestion.extract_odds import fetch_odds, upload_to_gcs

load_dotenv()


def main() -> None:
    """Orchestrate odds extraction and GCS upload."""
    config = load_config()
    bucket_name = config["gcp"]["bucket_name"]

    data = fetch_odds()
    gcs_uri = upload_to_gcs(data, bucket_name)
    print(f"Done. Data available at: {gcs_uri}")


if __name__ == "__main__":
    main()

