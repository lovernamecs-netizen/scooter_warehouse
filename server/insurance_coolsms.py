"""원본 CoolSMS MMS 기능을 재고관리 웹 앱에 이식한 독립 발송 어댑터.

지원이 종료된 sdk.api.message 인터페이스를 우선 사용(설치되어 있을 경우),
없으면 공식 SOLAPI Python SDK로 같은 CoolSMS 계정의 MMS를 발송합니다.
이 모듈의 실제 전송 함수는 사용자가 명시적으로 발송할 때만 호출합니다.
"""
from __future__ import annotations

import base64
import binascii
import io
import re
import tempfile
import threading
import time
import uuid
from pathlib import Path

from .insurance_documents import InsuranceDocumentError, MAX_JPEG_BYTES, normalize_plate
from .insurance_mms import explain_failure
from .insurance_settings import credentials

_idempotency_lock = threading.Lock()
_idempotency: dict[str, tuple[float, dict]] = {}
MAX_MESSAGE_BYTES = 2000

def _validate(data: dict) -> tuple[str, str, bytes, str]:
    recipient = re.sub(r"\D", "", str(data.get("phone", "")))
    if not re.fullmatch(r"01[016789]\d{7,8}", recipient):
        raise InsuranceDocumentError("받는 사람의 휴대전화 번호를 확인해 주세요.")
    plate = normalize_plate(data.get("plate", ""))
    if not re.fullmatch(r"[가-힣0-9]{5,20}", plate):
        raise InsuranceDocumentError("차량번호를 확인해 주세요.")
    message = str(data.get("text", "")).strip()
    if "{차량번호}" in message:
        message = message.replace("{차량번호}", plate)
    if not message or len(message.encode("utf-8")) > MAX_MESSAGE_BYTES:
        raise InsuranceDocumentError("MMS 문구는 2,000바이트 이하여야 합니다.")
    raw = str(data.get("jpeg_base64", ""))
    if len(raw) > MAX_JPEG_BYTES * 2:
        raise InsuranceDocumentError("JPG 파일의 용량이 199KB를 초과했습니다.")
    try:
        image = base64.b64decode(raw, validate=True)
    except (binascii.Error, ValueError):
        raise InsuranceDocumentError("JPG 이미지 데이터가 손상되었습니다.")
    if not (image[:3] == b"\xff\xd8\xff" and image[-2:] == b"\xff\xd9"):
        raise InsuranceDocumentError("JPG 형식의 이미지 파일만 발송할 수 있습니다.")
    if len(image) > MAX_JPEG_BYTES:
        raise InsuranceDocumentError("JPG 이미지가 199KB를 초과했습니다. 가독성을 확인하고 다시 변환해 주세요.")
    try:
        from PIL import Image
        with Image.open(io.BytesIO(image)) as jpg:
            jpg.verify()
        with Image.open(io.BytesIO(image)) as jpg:
            if jpg.width > 1500 or jpg.height > 1440:
                raise InsuranceDocumentError("MMS 이미지 크기는 최대 1500×1440픽셀이어야 합니다.")
    except InsuranceDocumentError:
        raise
    except Exception as exc:
        raise InsuranceDocumentError("JPG 파일의 내용을 확인할 수 없습니다.") from exc
    return recipient, plate, image, message

def _send_with_provider(path: Path, key: str, secret: str, sender: str, to: str, message: str) -> dict:
    """기존 SDK 또는 공식 SOLAPI SDK 결과를 접수 상태로 정규화."""
    try:
        from sdk.api.message import Message
    except ImportError:
        Message = None

    if Message is not None:
        cool = Message(key, secret)
        result = cool.send({
            "type": "mms", "to": to, "from": sender,
            "text": message, "image": str(path),
        })
        if not isinstance(result, dict):
            return {"state": "unknown", "code": "", "detail": "서비스 응답 형식을 확인하지 못했습니다.", "group_id": ""}
        errors = result.get("error_list") or []
        if errors or int(result.get("error_count", 0) or 0):
            err = errors[0] if errors else {}
            if not isinstance(err, dict):
                err = {"message": str(err)}
            return {"state": "failed", "code": str(err.get("code", "")),
                    "detail": str(err.get("message", err.get("msg", "CoolSMS 접수 실패"))),
                    "group_id": str(result.get("group_id") or "")}
        if result.get("success_count") is not None and int(result.get("success_count") or 0) < 1:
            return {"state": "failed", "code": "", "detail": "접수 성공 건수가 0건입니다.", "group_id": ""}
        return {"state": "accepted", "group_id": str(result.get("group_id") or ""), "provider": "CoolSMS"}
    # 공식 지원되는 SOLAPI SDK fallback
    try:
        from solapi import SolapiMessageService
        from solapi.model import RequestMessage
        from solapi.model.request.storage import FileTypeEnum
    except ImportError as exc:
        raise InsuranceDocumentError("CoolSMS 발송 모듈을 찾지 못했습니다. 서버에 SOLAPI SDK를 설치해 주세요.") from exc
    service = SolapiMessageService(api_key=key, api_secret=secret)
    uploaded = service.upload_file(file_path=str(path), upload_type=FileTypeEnum.MMS)
    response = service.send(RequestMessage(from_=sender, to=to, text=message, image_id=uploaded.file_id))
    info = getattr(response, "group_info", None)
    count = getattr(info, "count", None)
    successes = getattr(count, "registered_success", None)
    failures = getattr(count, "registered_failed", None)
    group_id = str(getattr(info, "group_id", "") or "")
    if (successes is not None and int(successes) < 1) or (failures is not None and int(failures) > 0):
        return {"state": "failed", "code": "", "detail": "MMS 접수에 실패했습니다.", "group_id": group_id}
    if successes is None and not group_id:
        return {"state": "unknown", "code": "", "detail": "서비스 응답에서 접수 여부를 확인하지 못했습니다.", "group_id": ""}
    return {"state": "accepted", "group_id": group_id, "provider": "SOLAPI"}

def send_one(data: dict, provider=None) -> dict:
    recipient, plate, image, message = _validate(data)
    key, secret, sender = credentials()
    raw_id = str(data.get("request_id") or "")
    try:
        uuid.UUID(raw_id)
    except ValueError:
        raise InsuranceDocumentError("발송 요청 번호가 올바르지 않습니다.")
    now = time.monotonic()
    with _idempotency_lock:
        stale = [k for k, (ts, _) in _idempotency.items() if now - ts > 86400]
        for k in stale:
            _idempotency.pop(k, None)
        existing = _idempotency.get(raw_id)
        if existing:
            return {**existing[1], "repeated_request": True}
        _idempotency[raw_id] = (now, {
            "state": "unknown", "title": "발송 접수 여부를 확인해야 합니다.",
            "action": "중복 발송을 피하려면 CoolSMS 콘솔에서 접수 내역을 확인하세요.",
            "technical": {"code": "", "detail": "동일 요청 진행 또는 불확실한 결과"},
            "delivery_confirmed": False,
        })
    try:
        with tempfile.TemporaryDirectory(prefix="warehouse-mms-") as folder:
            path = Path(folder) / "insurance.jpg"
            path.write_bytes(image)
            outcome = (provider or _send_with_provider)(path, key, secret, sender, recipient, message)
        state = outcome.get("state", "unknown")
        if state == "accepted":
            result = {
                "state": "accepted", "title": "MMS 발송 요청이 접수되었습니다.",
                "action": "통신사 최종 수신 완료는 별도 상태 조회가 필요합니다.",
                "group_id": outcome.get("group_id", ""),
                "technical": {"code": "", "detail": "CoolSMS API 접수 성공"},
                "delivery_confirmed": False,
            }
        else:
            human = explain_failure(outcome.get("code", ""), outcome.get("detail", ""))
            result = {**human, "state": state, "group_id": outcome.get("group_id", "")}
            if state == "unknown":
                result["title"] = "발송 접수 여부를 확인하지 못했습니다."
                result["action"] = "중복 발송을 피하도록 CoolSMS 콘솔에서 먼저 확인해 주세요."
    except Exception as exc:
        # 요청 직전 또는 전송 과정 예외: 접수 여부를 알 수 없으므로 자동 재시도 금지.
        code = str(getattr(exc, "code", "") or "")
        detail = str(getattr(exc, "msg", "") or exc)
        human = explain_failure(code, detail)
        is_config = isinstance(exc, InsuranceDocumentError)
        result = {**human, "state": "failed" if is_config else "unknown", "group_id": ""}
        if not is_config and ("timeout" in detail.lower() or "connection" in detail.lower()):
            result["title"] = "발송 접수 여부를 확인하지 못했습니다."
            result["action"] = "중복 발송을 피하기 위해 CoolSMS 발송 내역을 먼저 확인하세요."
    with _idempotency_lock:
        _idempotency[raw_id] = (now, result)
    return result
