from __future__ import annotations

import json
from typing import Any

import requests

from ..config import Settings
from ..errors import server_error


def parse_json(text: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def service_urls(base_url: str, service_name: str) -> list[str]:
    base = str(base_url or "").rstrip("/")
    return [
        f"{base}/K3Cloud/{service_name}",
        f"{base}/k3cloud/{service_name}",
        f"{base}/{service_name}",
    ]


def _extract_k3cloud_result(payload: object) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    direct = payload.get("Result")
    if isinstance(direct, dict):
        return direct
    if len(payload) == 1:
        wrapped = next(iter(payload.values()))
        if isinstance(wrapped, dict):
            wrapped_result = wrapped.get("Result")
            if isinstance(wrapped_result, dict):
                return wrapped_result
    for value in payload.values():
        if not isinstance(value, dict):
            continue
        nested = value.get("Result")
        if isinstance(nested, dict) and isinstance(nested.get("ResponseStatus"), dict):
            return nested
    return None


def _extract_k3cloud_error_messages(result: object) -> list[str]:
    if not isinstance(result, dict):
        return []
    status = result.get("ResponseStatus")
    if not isinstance(status, dict):
        return []
    errors = status.get("Errors") or []
    if not isinstance(errors, list):
        return []
    messages: list[str] = []
    for item in errors:
        if not isinstance(item, dict):
            continue
        message = item.get("Message")
        if message:
            messages.append(str(message))
    return messages


class K3CloudClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def validate_base_settings(self) -> None:
        required = {
            "PRODUCTION_PLAN_ERP_K3CLOUD_BASE_URL": self.settings.erp_k3cloud_base_url,
            "PRODUCTION_PLAN_ERP_K3CLOUD_ACCT_ID": self.settings.erp_k3cloud_acct_id,
            "PRODUCTION_PLAN_ERP_K3CLOUD_USERNAME": self.settings.erp_k3cloud_username,
            "PRODUCTION_PLAN_ERP_K3CLOUD_PASSWORD": self.settings.erp_k3cloud_password,
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise server_error(
                code="K3CLOUD_CONFIG_MISSING",
                message="K3Cloud ERP access is not fully configured.",
                details={"missing_env": missing},
            )

    def create_session(self) -> requests.Session:
        self.validate_base_settings()
        session = requests.Session()
        self.login(session)
        return session

    def login(self, session: requests.Session) -> None:
        service_name = (
            "Kingdee.BOS.WebApi.ServicesStub.AuthService.ValidateUser.common.kdsvc"
        )
        last_error = "Unknown K3Cloud login error."
        for url in service_urls(str(self.settings.erp_k3cloud_base_url), service_name):
            for payload in (
                {
                    "acctID": self.settings.erp_k3cloud_acct_id,
                    "username": self.settings.erp_k3cloud_username,
                    "password": self.settings.erp_k3cloud_password,
                    "lcid": self.settings.erp_k3cloud_lcid,
                },
                {
                    "AcctID": self.settings.erp_k3cloud_acct_id,
                    "UserName": self.settings.erp_k3cloud_username,
                    "Password": self.settings.erp_k3cloud_password,
                    "Lcid": self.settings.erp_k3cloud_lcid,
                },
            ):
                response = session.post(
                    url,
                    data=payload,
                    timeout=self.settings.erp_timeout_seconds,
                    verify=self.settings.erp_k3cloud_verify_ssl,
                )
                parsed = parse_json(response.text)
                if isinstance(parsed, dict) and (
                    parsed.get("LoginResultType") == 1
                    or parsed.get("IsSuccessByAPI") is True
                ):
                    return
                last_error = (
                    f"url={url} HTTP {response.status_code}: "
                    f"response={parsed!r}"
                )
        raise server_error(
            code="K3CLOUD_LOGIN_FAILED",
            message="K3Cloud login failed.",
            details={"error": last_error},
        )

    def execute_bill_query(
        self,
        session: requests.Session,
        *,
        form_id: str,
        field_keys: str,
        filter_string: str | None = None,
        order_string: str | None = None,
        start_row: int = 0,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        service_name = (
            "Kingdee.BOS.WebApi.ServicesStub.DynamicFormService.ExecuteBillQuery.common.kdsvc"
        )
        query_obj: dict[str, Any] = {
            "FormId": form_id,
            "FieldKeys": field_keys,
            "StartRow": start_row,
            "Limit": limit,
        }
        if order_string:
            query_obj["OrderString"] = order_string
        if filter_string:
            query_obj["FilterString"] = filter_string

        last_error = "Unknown K3Cloud ExecuteBillQuery error."
        for url in service_urls(str(self.settings.erp_k3cloud_base_url), service_name):
            response = session.post(
                url,
                data={"data": json.dumps(query_obj, ensure_ascii=False)},
                timeout=self.settings.erp_timeout_seconds,
                verify=self.settings.erp_k3cloud_verify_ssl,
            )
            parsed = parse_json(response.text)
            if isinstance(parsed, list):
                if parsed and isinstance(parsed[0], list):
                    if parsed[0] and isinstance(parsed[0][0], dict):
                        result = _extract_k3cloud_result(parsed[0][0])
                        if result is not None:
                            messages = _extract_k3cloud_error_messages(result)
                            message = "K3Cloud ExecuteBillQuery 返回错误。"
                            if messages:
                                message = f"K3Cloud ExecuteBillQuery 返回错误：{'；'.join(messages)}"
                            raise server_error(
                                code="K3CLOUD_EXECUTE_BILL_QUERY_FAILED",
                                message=message,
                                details={"result": result, "query": query_obj},
                            )
                    field_names = [field.strip() for field in field_keys.split(",") if field.strip()]
                    return [dict(zip(field_names, row)) for row in parsed]
                if parsed and isinstance(parsed[0], dict):
                    result = _extract_k3cloud_result(parsed[0])
                    if result is not None:
                        messages = _extract_k3cloud_error_messages(result)
                        message = "K3Cloud ExecuteBillQuery 返回错误。"
                        if messages:
                            message = f"K3Cloud ExecuteBillQuery 返回错误：{'；'.join(messages)}"
                        raise server_error(
                            code="K3CLOUD_EXECUTE_BILL_QUERY_FAILED",
                            message=message,
                            details={"result": result, "query": query_obj},
                        )
                if parsed and isinstance(parsed[0], dict):
                    return parsed
                return []
            last_error = f"url={url} HTTP {response.status_code}: response={parsed!r}"
        raise server_error(
            code="K3CLOUD_EXECUTE_BILL_QUERY_FAILED",
            message="K3Cloud ExecuteBillQuery failed.",
            details={"error": last_error, "query": query_obj},
        )

    def view_by_number(
        self,
        session: requests.Session,
        *,
        form_id: str,
        number: str,
    ) -> dict[str, Any]:
        service_name = "Kingdee.BOS.WebApi.ServicesStub.DynamicFormService.View.common.kdsvc"
        last_error = "Unknown K3Cloud View error."
        payload = {"formid": form_id, "data": json.dumps({"Number": number}, ensure_ascii=False)}
        for url in service_urls(str(self.settings.erp_k3cloud_base_url), service_name):
            response = session.post(
                url,
                data=payload,
                timeout=self.settings.erp_timeout_seconds,
                verify=self.settings.erp_k3cloud_verify_ssl,
            )
            parsed = parse_json(response.text)
            if isinstance(parsed, dict):
                result = parsed.get("Result", {})
                status = result.get("ResponseStatus", {})
                if status.get("IsSuccess") is True:
                    body = result.get("Result")
                    if isinstance(body, dict):
                        return body
                    raise server_error(
                        code="K3CLOUD_VIEW_INVALID_PAYLOAD",
                        message="K3Cloud View returned invalid result payload.",
                        details={"form_id": form_id, "number": number},
                    )
                last_error = f"url={url} response={parsed!r}"
                continue
            last_error = f"url={url} HTTP {response.status_code}: response={parsed!r}"
        raise server_error(
            code="K3CLOUD_VIEW_FAILED",
            message="K3Cloud View failed.",
            details={"error": last_error, "form_id": form_id, "number": number},
        )
