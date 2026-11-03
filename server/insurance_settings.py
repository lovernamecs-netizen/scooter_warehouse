"""보험증권 CoolSMS 설정: 업무 데이터와 분리된 로컬 설정 + OS 비밀 저장소."""
from __future__ import annotations
import json
import os
import re
import tempfile
from pathlib import Path

from .insurance_documents import InsuranceDocumentError

DEFAULT_MSG = (
    "[안내] {차량번호} 관련 고지문입니다.\n\n"
    "※ 유상종합 요청 관련 필수 고지사항\n"
    "- 신중하게 선택 부탁드립니다.\n"
    "- 보험해지는 불가합니다.\n"
    "- 고객 사유로 중도해지 시 남은 구독료의 20% 위약금이 발생합니다. (전계약)"
)
SERVICE = "ScooterWarehouse.Insurance.CoolSMS"
LOCAL_KEYS = ("api_key", "api_secret")

def _path() -> Path:
    base = os.environ.get("INSURANCE_CONFIG_DIR")
    if not base:
        base = os.environ.get("APPDATA") or os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
        base = str(Path(base) / "ScooterWarehouse")
    return Path(base).expanduser() / "insurance-mms.json"

def _load_public() -> dict:
    try:
        obj = json.loads(_path().read_text(encoding="utf-8"))
        return obj if isinstance(obj, dict) else {}
    except (FileNotFoundError, ValueError, OSError):
        return {}

def _write_public(meta: dict) -> None:
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    # 자격 증명은 절대 파일에 저장하지 않습니다.
    allowed = {"sender_phone": str(meta.get("sender_phone", "")),
               "msg_template": str(meta.get("msg_template", DEFAULT_MSG))}
    fd, tmp = tempfile.mkstemp(prefix=".insurance-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            json.dump(allowed, out, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
        if os.name != "nt":
            os.chmod(path, 0o600)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)

def _keyring():
    try:
        import keyring
        return keyring
    except ImportError:
        raise InsuranceDocumentError("보안 저장소(keyring)가 설치되지 않았습니다. 서버 관리자에게 문의하세요.")

def _secret(name: str) -> str:
    env_name = "COOLSMS_" + name.upper()
    if os.environ.get(env_name):
        return os.environ[env_name]
    try:
        return _keyring().get_password(SERVICE, name) or ""
    except Exception:
        return ""

def public_settings() -> dict:
    meta = _load_public()
    return {
        "sender_phone": meta.get("sender_phone") or os.environ.get("COOLSMS_SENDER_PHONE", ""),
        "msg_template": meta.get("msg_template", DEFAULT_MSG),
        "api_key_configured": bool(_secret("api_key")),
        "api_secret_configured": bool(_secret("api_secret")),
    }

def credentials() -> tuple[str, str, str]:
    meta = _load_public()
    key, secret = _secret("api_key"), _secret("api_secret")
    sender = re.sub(r"\D", "", str(meta.get("sender_phone") or os.environ.get("COOLSMS_SENDER_PHONE", "")))
    if not (key and secret and re.fullmatch(r"0\d{8,10}", sender)):
        raise InsuranceDocumentError("CoolSMS 설정이 완료되지 않았습니다. API 계정과 등록된 발신번호를 확인해 주세요.")
    return key, secret, sender

def save_account(data: dict) -> dict:
    meta = _load_public()
    phone = re.sub(r"\D", "", str(data.get("sender_phone", meta.get("sender_phone", ""))))
    if not re.fullmatch(r"0\d{8,10}", phone):
        raise InsuranceDocumentError("발신번호는 숫자 9~11자리로 입력해 주세요.")
    # 빈 값은 기존 비밀 값을 보존합니다.
    key = str(data.get("api_key", "")).strip()
    secret = str(data.get("api_secret", "")).strip()
    if len(key) > 200 or len(secret) > 300:
        raise InsuranceDocumentError("API 계정 설정 길이가 올바르지 않습니다.")
    if key or secret:
        try:
            vault = _keyring()
            if key:
                vault.set_password(SERVICE, "api_key", key)
            if secret:
                vault.set_password(SERVICE, "api_secret", secret)
        except Exception as exc:
            raise InsuranceDocumentError("운영체제 보안 저장소에 API 정보를 저장하지 못했습니다.") from exc
    meta["sender_phone"] = phone
    _write_public(meta)
    return public_settings()

def save_template(message: str) -> dict:
    text = str(message or "").strip()
    if not text or len(text.encode("utf-8")) > 2000:
        raise InsuranceDocumentError("MMS 문구를 입력해 주세요. UTF-8 기준 2,000바이트 이하여야 합니다.")
    meta = _load_public()
    meta["msg_template"] = text
    _write_public(meta)
    return public_settings()
