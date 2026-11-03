"""관리·도구 전체 웹 API 흐름 검증: 임시 SQLite + 합성 문서 + 모의 MMS."""
import io
import uuid

import pytest
from fastapi.testclient import TestClient

from server.db import Database
from server.app import create_app
from server.models import User
from server.security import hash_password
from server import insurance_settings, insurance_coolsms


@pytest.fixture
def app_client(tmp_path, monkeypatch):
    monkeypatch.setenv("INSURANCE_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.delenv("COOLSMS_API_KEY", raising=False)
    monkeypatch.delenv("COOLSMS_API_SECRET", raising=False)
    class Vault:
        def __init__(self):
            self.store = {}
        def get_password(self, service, name):
            return self.store.get(name, "")
        def set_password(self, service, name, value):
            self.store[name] = value
    monkeypatch.setattr(insurance_settings, "_keyring", lambda: VaultInstance)
    VaultInstance = Vault()
    db = Database("sqlite:///" + str(tmp_path / "smoke.db"))
    db.init(seed_catalog=False)
    with db.transaction() as session:
        session.add(User(username="insurance-admin", password=hash_password("test-password-123"), role="admin"))
        session.add(User(username="insurance-worker", password=hash_password("test-password-123"), role="worker"))
    with TestClient(create_app(db)) as client:
        admin = client.post("/api/login", json={"username": "insurance-admin", "password": "test-password-123"})
        worker = client.post("/api/login", json={"username": "insurance-worker", "password": "test-password-123"})
        assert admin.status_code == worker.status_code == 200
        yield client, {"Authorization": "Bearer " + admin.json()["token"]}, {"Authorization": "Bearer " + worker.json()["token"]}


def test_end_to_end_pdf_contacts_settings_and_mock_mms(app_client, monkeypatch):
    import fitz
    client, admin, worker = app_client
    assert client.get("/api/insurance/mms/settings").status_code == 401

    config = client.put("/api/insurance/mms/settings", headers=admin, json={
        "sender_phone": "010-1111-2222", "api_key": "fake", "api_secret": "fake-secret"
    })
    assert config.status_code == 200, config.text
    assert config.json()["api_key_configured"]
    assert "api_key" not in config.json()
    assert client.put("/api/insurance/mms/settings", headers=worker, json={
        "sender_phone": "010-1111-2222"
    }).status_code == 403
    changed = client.put("/api/insurance/mms/template", headers=worker, json={
        "msg_template": "보험증권 {차량번호} 발송 안내"
    })
    assert changed.status_code == 200, changed.text

    doc = fitz.open()
    page = doc.new_page(width=600, height=850)
    page.draw_rect(fitz.Rect(350, 404, 410, 430), fill=(1, 0, 0))
    pdf = doc.tobytes()
    doc.close()
    output = client.post("/api/insurance/convert", headers=worker,
                         files={"file": ("insurance.pdf", pdf, "application/pdf")})
    assert output.status_code == 200, output.text
    transformed = output.json()["pages"][0]
    assert transformed["size_bytes"] <= 199000
    assert transformed["within_limit"] is True
    assert transformed["plate"] == ""  # 원본에 차량번호가 없어 반드시 사람 검증

    rows = "차량번호,전화번호\n123가4567,010-1234-5678\n".encode("utf-8-sig")
    contacts = client.post("/api/insurance/contacts", headers=worker,
                           files={"file": ("contacts.csv", rows, "text/csv")})
    assert contacts.status_code == 200, contacts.text
    assert contacts.json()["contacts"]["123가4567"] == "01012345678"

    seen = []
    def mocked_send(path, key, secret, sender, phone, message):
        seen.append((key, secret, sender, phone, message, path.exists()))
        return {"state": "accepted", "group_id": "test-group-123"}
    monkeypatch.setattr(insurance_coolsms, "_send_with_provider", mocked_send)
    body = {"request_id": str(uuid.uuid4()), "plate": "123가4567",
            "phone": "01012345678", "text": changed.json()["msg_template"],
            "jpeg_base64": transformed["jpeg_base64"]}
    result = client.post("/api/insurance/mms/send", headers=worker, json=body)
    assert result.status_code == 200, result.text
    assert result.json()["state"] == "accepted"
    assert "123가4567" in seen[0][4]
    assert seen[0][0:4] == ("fake", "fake-secret", "01011112222", "01012345678")
    assert seen[0][5] is True
    duplicate = client.post("/api/insurance/mms/send", headers=worker, json=body)
    assert duplicate.status_code == 200
    assert duplicate.json()["repeated_request"] is True
    assert len(seen) == 1


def test_mms_invalid_document_is_refused_without_calling_provider(app_client, monkeypatch):
    client, admin, worker = app_client
    assert client.put("/api/insurance/mms/settings", headers=admin, json={
        "sender_phone": "01011112222", "api_key": "demo-key", "api_secret": "demo-secret"
    }).status_code == 200
    monkeypatch.setattr(insurance_coolsms, "_send_with_provider",
                        lambda *args: (_ for _ in ()).throw(AssertionError("should not send")))
    response = client.post("/api/insurance/mms/send", headers=worker, json={
        "request_id": str(uuid.uuid4()), "plate": "not_a_plate",
        "phone": "01012345678", "text": "보험 안내",
        "jpeg_base64": "!"
    })
    assert response.status_code == 422
    assert "차량번호" in response.json()["detail"]
