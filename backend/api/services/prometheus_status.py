"""
Service for syncing intern statuses from Prometheus external API.

Handles:
- Bulk status fetching via POST /api/external/interns/statuses
- Single status fetching via GET /api/external/interns/status
- Mapping Prometheus status codes to HR canonical statuses
- Auto-export to Contacts on "Принят" status

All Prometheus calls are server-to-server (secrets never exposed to client).
"""

import logging
from typing import List, Optional

from api.config import settings
from api.utils.http_client import get_http_client

logger = logging.getLogger("hr-analyzer.prometheus-status")

# ── Prometheus status code → HR canonical status ──
STATUS_CODE_MAP = {
    "TRAINING": "Обучается",
    "ACCEPTED": "Принят",
    "REJECTED": "Отклонен",
}

# Backwards compat: "Недопущен" → "Отклонен"
LEGACY_STATUS_COMPAT = {
    "Недопущен": "Отклонен",
}


def map_prometheus_status(code: str) -> str:
    """Map Prometheus status.code to HR canonical status string."""
    return STATUS_CODE_MAP.get(code, code)


def normalize_hr_status(label: str) -> str:
    """Normalize legacy HR status labels to canonical ones."""
    return LEGACY_STATUS_COMPAT.get(label, label)


def _get_credentials() -> tuple:
    """Return (base_url, api_key) or raise if not configured."""
    base_url = settings.prometheus_base_url
    api_key = settings.communication_api_key
    if not base_url or not api_key:
        missing = []
        if not base_url:
            missing.append("PROMETHEUS_BASE_URL")
        if not api_key:
            missing.append("COMMUNICATION_API_KEY")
        raise PrometheusNotConfiguredError(
            f"Prometheus not configured (missing: {', '.join(missing)})"
        )
    return base_url.rstrip("/"), api_key


class PrometheusNotConfiguredError(Exception):
    pass


class PrometheusAPIError(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"Prometheus API error {status_code}: {detail}")


async def fetch_status_single(
    *, email: Optional[str] = None, intern_id: Optional[str] = None
) -> dict:
    """
    GET /api/external/interns/status?email=...  or ?internId=...

    Returns raw JSON from Prometheus:
      { found: bool, intern?: {...}, status?: {code, label}, statusUpdatedAt?: ISO }
    """
    base_url, api_key = _get_credentials()

    params = {}
    if email:
        params["email"] = email.strip().lower()
    if intern_id:
        params["internId"] = intern_id

    if not params:
        raise ValueError("Either email or intern_id must be provided")

    client = get_http_client()
    url = f"{base_url}/api/external/interns/status"

    try:
        response = await client.get(
            url,
            headers={"Authorization": f"Bearer {api_key}"},
            params=params,
        )
    except Exception as exc:
        logger.error("Prometheus status request failed: %s", type(exc).__name__)
        raise PrometheusAPIError(502, "Failed to connect to Prometheus")

    if response.status_code == 400:
        return {"found": False, "error": "bad_request"}
    if response.status_code == 401:
        logger.error("Prometheus 401 on status endpoint")
        raise PrometheusAPIError(401, "Prometheus authentication failed")
    if response.status_code == 404:
        return {"found": False}
    if response.status_code != 200:
        logger.error("Prometheus status returned %d", response.status_code)
        raise PrometheusAPIError(response.status_code, f"Unexpected status {response.status_code}")

    return response.json()


async def fetch_statuses_bulk(emails: List[str]) -> List[dict]:
    """
    POST /api/external/interns/statuses  { emails: [...] }

    Handles chunking if len(emails) > 200.
    Returns flat list of results in order.
    """
    base_url, api_key = _get_credentials()

    if not emails:
        return []

    # Normalize emails
    normalized = [e.strip().lower() for e in emails if e and e.strip()]
    if not normalized:
        return []

    client = get_http_client()
    url = f"{base_url}/api/external/interns/statuses"
    all_results: List[dict] = []

    # Chunk by 200 (Prometheus limit)
    for i in range(0, len(normalized), 200):
        chunk = normalized[i : i + 200]

        try:
            response = await client.post(
                url,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={"emails": chunk},
            )
        except Exception as exc:
            logger.error("Prometheus bulk status request failed: %s", type(exc).__name__)
            # Return error entries for this chunk
            for email in chunk:
                all_results.append({
                    "email": email,
                    "found": False,
                    "error": "connection_failed",
                })
            continue

        if response.status_code == 401:
            logger.error("Prometheus 401 on bulk status endpoint")
            raise PrometheusAPIError(401, "Prometheus authentication failed")

        if response.status_code != 200:
            logger.error("Prometheus bulk status returned %d", response.status_code)
            for email in chunk:
                all_results.append({
                    "email": email,
                    "found": False,
                    "error": f"prometheus_error_{response.status_code}",
                })
            continue

        data = response.json()
        results = data.get("results") or []
        all_results.extend(results)

    return all_results
