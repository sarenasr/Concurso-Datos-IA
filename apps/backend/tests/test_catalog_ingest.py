"""Tests for catalog ingestion and schema guards."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.agents.tools import get_schema
from app.rag.catalog import ingest_catalog


def test_get_schema_returns_none_for_chart_asset() -> None:
    """Chart/map/story assets have no columns and must be rejected by get_schema."""
    mock_client = MagicMock()
    mock_client.get_views.return_value = {
        "id": "ghsz-zbhz",
        "name": "Cantidad de suicidios en Antioquia, 2007-2021",
        "columns": [],
    }

    with patch("app.agents.tools._socrata", return_value=mock_client):
        result = get_schema("ghsz-zbhz")

    assert result is None


def test_ingest_catalog_skips_non_dataset_assets() -> None:
    """Only tabular datasets should be indexed; charts and maps are skipped."""
    mock_socrata_client = MagicMock()
    mock_socrata_client.iter_catalog.return_value = [
        {
            "resource": {
                "id": "db67-sbus",
                "name": "Suicidios Antioquia",
                "type": "dataset",
            }
        },
        {
            "resource": {
                "id": "ghsz-zbhz",
                "name": "Cantidad de suicidios en Antioquia, 2007-2021",
                "type": "chart",
            }
        },
    ]

    mock_table = MagicMock()
    mock_table.upsert.return_value.execute.return_value.data = []
    mock_sb = MagicMock()
    mock_sb.table.return_value = mock_table

    with (
        patch("app.rag.catalog.SocrataClient", return_value=mock_socrata_client),
        patch("app.rag.catalog._supabase", return_value=mock_sb),
    ):
        ingest_catalog()

    # ingest_catalog batches and upserts once for a 2-item input
    call_args = mock_table.upsert.call_args
    assert call_args is not None
    batch = call_args[0][0]
    assert len(batch) == 1
    assert batch[0]["id"] == "db67-sbus"
    assert batch[0]["type"] == "dataset"
