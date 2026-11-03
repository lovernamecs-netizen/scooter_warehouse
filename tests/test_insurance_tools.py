"""합성 데이터만 사용하는 보험증권 도구 회귀 테스트. 실제 발송/고객 자료 없음."""
import base64
import csv
import io

import pytest

from server.insurance_documents import (
    InsuranceDocumentError,
    convert_pdf,
    extract_plate,
    normalize_plate,
    parse_contacts,
)
from server.insurance_mms import explain_failure


@pytest.mark.parametrize(("text", "expected"), [
    ("차량번호 : 경기 수원 너 4265", "경기수원너4265"),
    ("차량 번호: 경기수원너4265", "경기수원너4265"),
    ("등록번호 123가4567", "123가4567"),
    ("이륜차 번호: 12 가 3456", "12가3456"),
    ("차량번호: 1오8 6575", "1오86575"),
])
def test_plate_recognition(text, expected):
    result = extract_plate(text)
    assert result["plate"] == expected
    assert result["review_required"] is False


def test_ambiguous_number_requires_confirmation():
    result = extract_plate("차량번호: 123가4567\n차량번호: 234나5678")
    assert result["plate"] == ""
    assert result["review_required"] is True
    assert len(result["candidates"]) == 2


def test_unlabelled_number_requires_review():
    result = extract_plate("보험 대상 차량 123가4567")
    assert result["plate"] == "123가4567"
    assert result["review_required"] is True


def test_unrecognized_requires_review():
    result = extract_plate("보험 고지사항에 동의합니다.")
    assert result["plate"] == ""
    assert result["review_required"] is True


def test_plate_normalization():
    assert normalize_plate("경기 수원 너-4265") == "경기수원너4265"


def test_contacts_detect_conflicting_duplicate():
    data = "차량번호,연락처\n123가4567,010-1234-5678\n123가4567,010-0000-0000\n234나5678,010-5678-1234\n".encode("utf-8-sig")
    output = parse_contacts("고객.csv", data)
    assert output["contacts"] == {"234나5678": "01056781234"}
    assert output["conflicts"] == ["123가4567"]


def test_contacts_xlsx():
    from openpyxl import Workbook
    book = Workbook()
    sheet = book.active
    sheet.append(["차량 번호", "휴대폰"])
    sheet.append(["경기 수원 너 4265", "010-1234-5678"])
    buf = io.BytesIO()
    book.save(buf)
    assert parse_contacts("고객.xlsx", buf.getvalue())["contacts"]["경기수원너4265"] == "01012345678"


def test_mms_explanation_is_human_readable():
    result = explain_failure("1030", "잔액 부족")
    assert "잔액" in result["title"]
    assert result["technical"]["code"] == "1030"
    assert result["delivery_confirmed"] is False


def test_mms_detail_redacts_credentials():
    result = explain_failure("other", "authorization: secret-value")
    assert "secret-value" not in result["technical"]["detail"]


def test_pdf_color_layout_and_white_mask():
    fitz = pytest.importorskip("fitz")
    from PIL import Image

    source = fitz.open()
    page = source.new_page(width=600, height=850)
    # 가림 영역 밖은 파란색, 가림 안은 빨간색.
    page.draw_rect(fitz.Rect(60, 80, 160, 120), fill=(0, 0, 1), color=(0, 0, 1))
    page.draw_rect(fitz.Rect(350, 405, 400, 430), fill=(1, 0, 0), color=(1, 0, 0))
    result = convert_pdf(source.tobytes())
    assert result["mask_rect"] == [330, 400, 585, 435]
    record = result["pages"][0]
    assert record["within_limit"]
    assert record["size_bytes"] <= 199_000
    image = Image.open(io.BytesIO(base64.b64decode(record["jpeg_base64"])))
    assert image.mode == "RGB"
    assert abs(image.width / image.height - 600 / 850) < 0.002
    scale = image.width / 600
    blue = image.getpixel((round(100 * scale), round(100 * scale)))
    white = image.getpixel((round(370 * scale), round(415 * scale)))
    assert blue[2] > 180 and blue[0] < 80
    assert all(channel > 245 for channel in white)


def test_pdf_with_incompatible_page_stops_without_output():
    fitz = pytest.importorskip("fitz")
    source = fitz.open()
    source.new_page(width=200, height=300)
    with pytest.raises(InsuranceDocumentError, match="흰색 가림 영역"):
        convert_pdf(source.tobytes())


def test_pdf_rejects_invalid_data():
    with pytest.raises(InsuranceDocumentError):
        convert_pdf(b"not pdf")
