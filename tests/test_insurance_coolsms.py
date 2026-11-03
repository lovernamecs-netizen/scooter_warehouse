"""보험증권 + CoolSMS 전체 기능의 합성·모의 발송 테스트 (실제 문자 발송 없음)."""
import base64
import io
import json
import uuid
from pathlib import Path

import pytest

from server import insurance_coolsms
from server import insurance_settings
from server.insurance_documents import InsuranceDocumentError


@pytest.fixture
def sample_jpeg():
    from PIL import Image
    buffer = io.BytesIO()
    Image.new("RGB", (200, 220), (255, 255, 255)).save(buffer, "JPEG")
    return base64.b64encode(buffer.getvalue()).decode("ascii")


@pytest.fixture
def request_data(sample_jpeg):
    return {
        "request_id": str(uuid.uuid4()),
        "plate": "경기수원너4265",
        "phone": "01012345678",
        "jpeg_base64": sample_jpeg,
        "text": "[안내] {차량번호} 관련 보험증권 고지문입니다.",
    }


def test_send_success_preserves_original_coolsms_fields_and_template(monkeypatch, request_data):
    monkeypatch.setattr(insurance_coolsms, "credentials", lambda: ("test-key", "test-secret", "01011112222"))
    seen = []
    def mocked_sender(path, key, secret, sender, to, msg):
        seen.append((key, secret, sender, to, msg, path.read_bytes()))
        assert path.exists()
        return {"state": "accepted", "group_id": "synthetic-test-group"}
    response = insurance_coolsms.send_one(request_data, provider=mocked_sender)
    assert response["state"] == "accepted"
    assert response["delivery_confirmed"] is False
    assert len(seen) == 1
    assert seen[0][:4] == ("test-key", "test-secret", "01011112222", "01012345678")
    assert "경기수원너4265" in seen[0][4]
    assert seen[0][5].startswith(b"\xff\xd8\xff")
    # 재요청이 동일 idempotency key면 통신사 중복 발송하지 않음.
    repeated = insurance_coolsms.send_one(request_data, provider=mocked_sender)
    assert repeated["repeated_request"] is True
    assert len(seen) == 1


def test_send_failure_maps_to_natural_language(monkeypatch, request_data):
    monkeypatch.setattr(insurance_coolsms, "credentials", lambda: ("test-key", "test-secret", "01011112222"))
    response = insurance_coolsms.send_one(
        request_data,
        provider=lambda *a: {"state": "failed", "code": "1030", "detail": "잔액이 부족합니다."},
    )
    assert response["state"] == "failed"
    assert "잔액" in response["title"]
    assert response["technical"]["code"] == "1030"


def test_send_rejects_broken_jpeg_and_invalid_phone(sample_jpeg, request_data):
    request_data["jpeg_base64"] = base64.b64encode(b"not a jpeg").decode()
    with pytest.raises(InsuranceDocumentError, match="JPG"):
        insurance_coolsms._validate(request_data)
    request_data["jpeg_base64"] = sample_jpeg
    request_data["phone"] = "123"
    with pytest.raises(InsuranceDocumentError, match="휴대전화"):
        insurance_coolsms._validate(request_data)


def test_send_rejects_oversized_jpeg(request_data):
    # 이 테스트는 실제 이미지 디코딩 전에 용량 방어 로직이 동작해야 합니다.
    request_data["jpeg_base64"] = base64.b64encode(b"\xff\xd8\xff" + b"a" * 199001 + b"\xff\xd9").decode()
    with pytest.raises(InsuranceDocumentError, match="199KB"):
        insurance_coolsms._validate(request_data)


def test_send_unknown_state_disables_blind_retry(monkeypatch, request_data):
    monkeypatch.setattr(insurance_coolsms, "credentials", lambda: ("test-key", "test-secret", "01011112222"))
    attempts = []
    def timeout_sender(*args):
        attempts.append(True)
        raise TimeoutError("timeout while sending MMS")
    result = insurance_coolsms.send_one(request_data, provider=timeout_sender)
    assert result["state"] == "unknown"
    assert "확인" in result["title"]
    repeated = insurance_coolsms.send_one(request_data, provider=timeout_sender)
    assert repeated["repeated_request"]
    assert len(attempts) == 1


def test_settings_persist_template_and_do_not_write_secrets(tmp_path, monkeypatch):
    monkeypatch.setenv("INSURANCE_CONFIG_DIR", str(tmp_path))
    monkeypatch.delenv("COOLSMS_API_KEY", raising=False)
    monkeypatch.delenv("COOLSMS_API_SECRET", raising=False)
    class FakeVault:
        values = {}
        def set_password(self, service, name, value):
            self.values[name] = value
        def get_password(self, service, name):
            return self.values.get(name)
    vault = FakeVault()
    monkeypatch.setattr(insurance_settings, "_keyring", lambda: vault)
    state = insurance_settings.save_account({
        "sender_phone": "010-1111-2222",
        "api_key": "private-demo-key",
        "api_secret": "private-demo-secret",
    })
    assert state["api_key_configured"]
    assert state["api_secret_configured"]
    assert state["sender_phone"] == "01011112222"
    insurance_settings.save_template("보험증권 {차량번호} 안내")
    assert insurance_settings.credentials() == ("private-demo-key", "private-demo-secret", "01011112222")
    config_file = (tmp_path / "insurance-mms.json")
    raw = config_file.read_text(encoding="utf-8")
    assert "private-demo-key" not in raw
    assert "private-demo-secret" not in raw
    assert json.loads(raw)["msg_template"] == "보험증권 {차량번호} 안내"


def test_defaults_preserve_original_legal_notification():
    text = insurance_settings.DEFAULT_MSG
    assert "보험해지는 불가합니다." in text
    assert "20% 위약금" in text
    assert "{차량번호}" in text


def test_unconfigured_account_is_blocked(tmp_path, monkeypatch):
    monkeypatch.setenv("INSURANCE_CONFIG_DIR", str(tmp_path))
    monkeypatch.delenv("COOLSMS_API_KEY", raising=False)
    monkeypatch.delenv("COOLSMS_API_SECRET", raising=False)
    monkeypatch.setattr(insurance_settings, "_secret", lambda name: "")
    with pytest.raises(InsuranceDocumentError, match="설정"):
        insurance_settings.credentials()
