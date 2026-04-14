"""Module for loading a flattened odds DataFrame into a native BigQuery table."""

import logging

import pandas as pd
from google.cloud import bigquery
from google.cloud.exceptions import NotFound

logger = logging.getLogger(__name__)

# BigQuery schema matching the 16-column flattened structure
_BQ_SCHEMA = [
    bigquery.SchemaField("event_id", "STRING", mode="NULLABLE"),
    bigquery.SchemaField("sport_key", "STRING", mode="NULLABLE"),
    bigquery.SchemaField("sport_title", "STRING", mode="NULLABLE"),
    bigquery.SchemaField("home_team", "STRING", mode="NULLABLE"),
    bigquery.SchemaField("away_team", "STRING", mode="NULLABLE"),
    bigquery.SchemaField("commence_time", "TIMESTAMP", mode="NULLABLE"),
    bigquery.SchemaField("bookmaker_key", "STRING", mode="NULLABLE"),
    bigquery.SchemaField("bookmaker_title", "STRING", mode="NULLABLE"),
    bigquery.SchemaField("bookmaker_last_update", "TIMESTAMP", mode="NULLABLE"),
    bigquery.SchemaField("market_key", "STRING", mode="NULLABLE"),
    bigquery.SchemaField("market_last_update", "TIMESTAMP", mode="NULLABLE"),
    bigquery.SchemaField("outcome_name", "STRING", mode="NULLABLE"),
    bigquery.SchemaField("price", "FLOAT64", mode="NULLABLE"),
    bigquery.SchemaField("raw_implied", "FLOAT64", mode="NULLABLE"),
    bigquery.SchemaField("true_implied", "FLOAT64", mode="NULLABLE"),
    bigquery.SchemaField("ingested_at", "TIMESTAMP", mode="NULLABLE"),
]


def _ensure_dataset(client: bigquery.Client, dataset_id: str, location: str) -> None:
    """Create the BigQuery dataset if it does not already exist.

    Args:
        client: An authenticated BigQuery client.
        dataset_id: Fully-qualified dataset ID (``project.dataset``).
        location: GCP region for the dataset (e.g. ``"US"``).
    """
    try:
        client.get_dataset(dataset_id)
        logger.info("Dataset '%s' already exists.", dataset_id)
    except NotFound:
        dataset = bigquery.Dataset(dataset_id)
        dataset.location = location
        client.create_dataset(dataset, timeout=30)
        logger.info("Created dataset '%s' in location '%s'.", dataset_id, location)


def load_to_bigquery(
    df: pd.DataFrame,
    project_id: str,
    dataset_name: str,
    table_name: str,
    location: str = "US",
) -> None:
    """Load a flattened odds DataFrame into a native BigQuery table.

    Creates the dataset and table if they do not already exist, then
    appends the DataFrame rows using ``WRITE_APPEND``. The table is
    partitioned by ``ingested_at`` for efficient time-range queries.

    Args:
        df: Flattened DataFrame produced by ``transform.flatten_odds``.
        project_id: GCP project ID (e.g. ``"my-gcp-project"``).
        dataset_name: BigQuery dataset name (e.g. ``"tennis_data"``).
        table_name: BigQuery table name (e.g. ``"raw_odds"``).
        location: GCP region for the dataset. Defaults to ``"US"``.

    Raises:
        google.cloud.exceptions.GoogleCloudError: On any BigQuery API failure.
    """
    client = bigquery.Client(project=project_id)
    dataset_id = f"{project_id}.{dataset_name}"
    table_id = f"{dataset_id}.{table_name}"

    # Step 1 — ensure dataset exists
    _ensure_dataset(client, dataset_id, location)

    # Step 2 — ensure table exists with partitioning on ingested_at
    try:
        client.get_table(table_id)
        logger.info("Table '%s' already exists.", table_id)
    except NotFound:
        table = bigquery.Table(table_id, schema=_BQ_SCHEMA)
        table.time_partitioning = bigquery.TimePartitioning(
            type_=bigquery.TimePartitioningType.DAY,
            field="ingested_at",
        )
        client.create_table(table)
        logger.info("Created table '%s' with DAY partitioning on 'ingested_at'.", table_id)

    # Step 3 — append rows
    job_config = bigquery.LoadJobConfig(
        schema=_BQ_SCHEMA,
        write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
    )

    job = client.load_table_from_dataframe(df, table_id, job_config=job_config)
    job.result()  # wait for completion

    logger.info(
        "Loaded %d rows into '%s'. BQ job ID: %s",
        len(df),
        table_id,
        job.job_id,
    )
