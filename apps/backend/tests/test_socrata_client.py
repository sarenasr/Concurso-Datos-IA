"""Focused tests for actionable Socrata HTTP errors."""

from __future__ import annotations

from unittest.mock import Mock

import httpx
import pytest

from app.socrata.client import SocrataClient


def test_client_error_includes_socrata_response_body() -> None:
    client = SocrataClient("datos.gov.co")
    request = httpx.Request("GET", "https://datos.gov.co/resource/test.json")
    response = httpx.Response(
        400,
        request=request,
        json={"message": "Query coordinator error: No such column"},
    )
    client.client.get = Mock(return_value=response)

    with pytest.raises(httpx.HTTPStatusError, match="No such column"):
        client._request_with_retry("/resource/test.json")
