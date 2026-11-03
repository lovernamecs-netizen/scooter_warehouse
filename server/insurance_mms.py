"""MMS/RCS 발송 실패 원인을 사용자용 한국어로 바꾸는 독립 모듈.

이번 브랜치에서는 발송 API를 호출하지 않습니다. 발송 업체가 결정된 후
실제 발송 결과를 이 함수에 연결할 수 있습니다.
"""
from __future__ import annotations

import re

PATTERNS = (
    (("잔액", "충전", "balance", "insufficient funds"),
     "문자 발송 서비스의 잔액이 부족합니다.",
     "서비스 계정의 잔액을 확인하고 충전한 뒤 다시 시도하세요."),
    (("수신번호", "전화번호", "수신자", "invalid number", "invalid phone"),
     "받는 사람의 전화번호가 올바르지 않습니다.",
     "엑셀의 연락처와 원본 등록 정보를 다시 확인하세요."),
    (("발신번호", "발신자", "sender", "not registered"),
     "발신번호 인증 또는 등록에 문제가 있습니다.",
     "문자 서비스에 등록된 회사 발신번호를 확인하세요."),
    (("용량", "파일 크기", "file size", "too large", "attachment size"),
     "보험증권 이미지가 발송 가능한 용량을 초과했습니다.",
     "이미지 용량과 발송 서비스의 제한을 확인하세요. 문서 내용을 임의로 바꾸지 마세요."),
    (("이미지 형식", "지원하지 않는 이미지", "invalid image", "file type"),
     "이미지 형식이 문자 서비스의 지원 규격과 맞지 않습니다.",
     "JPG 형식과 파일 손상 여부를 확인하세요."),
    (("rate limit", "too many", "발송 제한", "전송량 제한"),
     "문자 발송 서비스의 전송량 제한에 걸렸습니다.",
     "계정의 발송 제한과 통신사 정책을 확인하세요."),
    (("timeout", "timed out", "시간 초과", "connection"),
     "문자 발송 서비스의 응답을 받지 못했습니다.",
     "중복 발송을 피하기 위해 발송 내역을 먼저 확인하세요."),
    (("인증", "unauthorized", "authentication", "invalid api"),
     "문자 발송 서비스의 인증에 실패했습니다.",
     "API 설정과 서비스 계정 권한을 관리자에게 확인해 주세요."),
)


def explain_failure(code: str = "", detail: str = "") -> dict:
    code = str(code or "").strip()[:50]
    # 공급자 오류 설명에 민감한 요청 헤더/토큰이 노출되지 않도록 원문은 제한합니다.
    detail = str(detail or "").strip()[:250]
    detail = re.sub(r"(?i)authorization\s*[:=]\s*bearer\s+\S+", "Authorization=[비공개]", detail)
    detail = re.sub(r"(?i)(api[_ -]?key|api[_ -]?secret|authorization|token|password)\s*[:=]\s*\S+",
                    r"\1=[비공개]", detail)
    haystack = (code + " " + detail).lower()
    if code == "1030":
        title = "문자 발송 서비스의 잔액이 부족합니다."
        action = "서비스 잔액을 확인한 후 충전하고 다시 시도하세요."
    else:
        title = "문자 발송을 완료하지 못했습니다."
        action = "서비스의 발송 내역을 확인하고, 고객에게 중복 전송되지 않았는지 확인하세요."
        for terms, candidate, recommendation in PATTERNS:
            if any(term in haystack for term in terms):
                title, action = candidate, recommendation
                break
    return {
        "success": False,
        "title": title,
        "action": action,
        "technical": {"code": code or "미제공", "detail": detail or "상세 오류 내용이 제공되지 않았습니다."},
        "delivery_confirmed": False,
    }
