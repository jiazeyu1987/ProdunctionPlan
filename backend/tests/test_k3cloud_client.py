import json
import unittest
from dataclasses import replace

from backend.app.config import get_settings
from backend.app.errors import AppError
from backend.app.gateway.k3cloud_client import K3CloudClient


class _FakeResponse:
    def __init__(self, text: str, status_code: int = 200) -> None:
        self.text = text
        self.status_code = status_code


class _FakeSession:
    def __init__(self, response_text: str, status_code: int = 200) -> None:
        self._response = _FakeResponse(response_text, status_code=status_code)
        self.calls: list[dict[str, object]] = []

    def post(  # noqa: D401 - signature matches requests.Session.post
        self,
        url: str,
        *,
        data: dict[str, object] | None = None,
        timeout: float | None = None,
        verify: bool | None = None,
    ) -> _FakeResponse:
        self.calls.append({"url": url, "data": data, "timeout": timeout, "verify": verify})
        return self._response


class K3CloudClientExecuteBillQueryTestCase(unittest.TestCase):
    def test_execute_bill_query_raises_when_k3cloud_returns_wrapped_error_payload(self) -> None:
        settings = replace(
            get_settings(),
            erp_k3cloud_base_url="http://example.test",
            erp_k3cloud_verify_ssl=False,
            erp_timeout_seconds=1.0,
        )
        client = K3CloudClient(settings)

        error_result = {
            "ResponseStatus": {
                "ErrorCode": 500,
                "IsSuccess": False,
                "Errors": [{"Message": "元数据中标识为FBizStatus的字段不存在"}],
            }
        }
        response_text = json.dumps([[{"Result": error_result}]], ensure_ascii=False)
        session = _FakeSession(response_text)

        with self.assertRaises(AppError) as cm:
            client.execute_bill_query(
                session,  # type: ignore[arg-type]
                form_id="PRD_MO",
                field_keys="FID,FBillNo,FBizStatus",
                limit=1,
            )

        self.assertEqual(cm.exception.code, "K3CLOUD_EXECUTE_BILL_QUERY_FAILED")
        self.assertIn("FBizStatus", cm.exception.message)
        self.assertEqual((cm.exception.details or {}).get("result"), error_result)

