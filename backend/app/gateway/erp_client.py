from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from ..config import Settings, get_settings
from ..errors import server_error


class ERPClient:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def request_json(
        self,
        endpoint_path: str | None,
        *,
        method: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        base_url = self.settings.erp_base_url
        if not base_url:
            raise server_error(
                code="ERP_BASE_URL_MISSING",
                message="PRODUCTION_PLAN_ERP_BASE_URL is not configured.",
            )
        if not endpoint_path:
            raise server_error(
                code="ERP_ENDPOINT_MISSING",
                message="Required ERP endpoint path is not configured.",
            )

        url = urljoin(f"{base_url.rstrip('/')}/", endpoint_path.lstrip("/"))
        normalized_method = str(method or "POST").strip().upper() or "POST"
        body = None
        if normalized_method not in {"GET", "HEAD"}:
            body = json.dumps(payload or {}, ensure_ascii=False).encode("utf-8")
        request = Request(url, data=body, method=normalized_method)
        if body is not None:
            request.add_header("Content-Type", "application/json")
        request.add_header("Accept", "application/json")
        if self.settings.erp_authorization:
            request.add_header("Authorization", self.settings.erp_authorization)

        try:
            with urlopen(request, timeout=self.settings.erp_timeout_seconds) as response:
                raw = response.read().decode("utf-8")
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            raise server_error(
                code="ERP_HTTP_ERROR",
                message=f"ERP request failed with HTTP {exc.code}.",
                details={"url": url, "body": detail},
            ) from exc
        except URLError as exc:
            raise server_error(
                code="ERP_CONNECTION_ERROR",
                message="ERP request failed.",
                details={"url": url, "reason": str(exc.reason)},
            ) from exc

        try:
            payload_json = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise server_error(
                code="ERP_INVALID_JSON",
                message="ERP returned invalid JSON.",
                details={"url": url},
            ) from exc

        if not isinstance(payload_json, dict):
            raise server_error(
                code="ERP_INVALID_PAYLOAD",
                message="ERP payload must be a JSON object.",
                details={"url": url},
            )

        return payload_json

    def request_items(
        self,
        endpoint_path: str | None,
        *,
        method: str,
        payload: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        payload_json = self.request_json(endpoint_path, method=method, payload=payload)
        if not isinstance(payload_json.get("items"), list):
            raise server_error(
                code="ERP_INVALID_PAYLOAD",
                message="ERP payload must be an object with an items array.",
                details={"path": endpoint_path},
            )
        return payload_json["items"]

    def post_items(self, endpoint_path: str | None, payload: dict[str, Any]) -> list[dict[str, Any]]:
        return self.request_items(endpoint_path, method="POST", payload=payload)
