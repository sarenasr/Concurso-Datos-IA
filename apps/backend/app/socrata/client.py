"""Socrata API client for datos.gov.co.

Handles catalog pagination (DDA catalog v1), views metadata, SoQL resource queries,
and distinct-value sampling (used to validate proposed graph JOIN edges).
"""
from __future__ import annotations

from typing import Iterator

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type


class SocrataRetryableError(Exception):
    """Raised on 429 / 5xx so tenacity can retry."""


class SocrataClient:
    """Thin wrapper around a Socrata domain's REST API.

    All requests carry the `X-App-Token` header (raises rate limits when present).
    Network/429/5xx errors are retried with exponential backoff via tenacity.
    """

    def __init__(self, domain: str, app_token: str = "", *, timeout: float = 30.0) -> None:
        self.domain = domain
        self.base_url = f"https://{domain}"
        headers = {"User-Agent": "DATIA/0.1"}
        if app_token:
            headers["X-App-Token"] = app_token
        self.client = httpx.Client(base_url=self.base_url, headers=headers, timeout=timeout)

    # -- internal helpers -------------------------------------------------

    def _get(self, path: str, params: dict | None = None) -> list | dict:
        resp = self._request_with_retry(path, params=params)
        return resp.json()

    def _request_with_retry(self, path: str, params: dict | None = None) -> httpx.Response:
        @retry(
            stop=stop_after_attempt(5),
            wait=wait_exponential(multiplier=1, min=1, max=20),
            retry=retry_if_exception_type(SocrataRetryableError),
            reraise=True,
        )
        def _do() -> httpx.Response:
            r = self.client.get(path, params=params)
            if r.status_code == 429 or r.status_code >= 500:
                raise SocrataRetryableError(f"{r.status_code} {r.text[:200]}")
            r.raise_for_status()
            return r

        return _do()

    # -- catalog ----------------------------------------------------------

    def iter_catalog(self, limit: int | None = None) -> Iterator[dict]:
        """Iterate every catalog entry for this domain.

        Paginates `/api/catalog/v1?domains={domain}&limit=100&offset=...`.
        When `limit` is None, exhaust the catalog until a page returns fewer than
        `page_size` results. Each yielded item is the raw result dict (which contains
        a `resource` sub-dict plus classification/metadata).
        """
        page_size = 100
        offset = 0
        yielded = 0
        while True:
            params = {"domains": self.domain, "limit": page_size, "offset": offset}
            data = self._get("/api/catalog/v1", params=params)
            results = data.get("results", []) if isinstance(data, dict) else []
            if not results:
                break
            for item in results:
                yield item
                yielded += 1
                if limit is not None and yielded >= limit:
                    return
            if len(results) < page_size:
                break
            offset += page_size

    # -- views metadata ---------------------------------------------------

    def get_views(self, id: str) -> dict:
        """Return the full views metadata for a dataset id (`/api/views/{id}.json`).

        Contains columns (name, fieldName, datatype), row count, attribution, etc.
        """
        return self._get(f"/api/views/{id}.json")

    # -- SoQL queries -----------------------------------------------------

    def query(self, id: str, soql: str) -> list[dict]:
        """Run a SoQL query against a resource.

        `soql` is a raw SoQL fragment such as
        `$select=...&$where=...&$group=...&$limit=...`. It is appended to
        `/resource/{id}.json` as URL params.
        """
        # soql already starts with "$..." params; strip a leading '?' if present
        path = f"/resource/{id}.json"
        params: dict = {}
        if soql:
            frag = soql.lstrip("?")
            for pair in frag.split("&"):
                if not pair:
                    continue
                if "=" in pair:
                    key, val = pair.split("=", 1)
                    params[key] = val
                else:
                    params[pair] = ""
        return self._get(path, params=params)  # type: ignore[return-value]

    def distinct_values(self, id: str, field: str, limit: int = 50) -> list:
        """Return distinct values of `field` for join validation.

        Implemented as `SELECT field, count GROUP BY field LIMIT n` so we both get
        the value set and a rough sense of cardinality.
        """
        soql = f"$select={field}&$group={field}&$limit={limit}"
        rows = self.query(id, soql)
        return [row.get(field) for row in rows if row.get(field) is not None]
