"""보험증권 변환 엔진. 외부 네트워크·DB·디스크 저장 없이 메모리에서 처리합니다."""
from __future__ import annotations

import base64
import csv
import io
import re
import unicodedata

MASK_RECT = (330, 400, 585, 435)
MAX_PDF_BYTES = 15 * 1024 * 1024
MAX_CONTACT_BYTES = 5 * 1024 * 1024
MAX_PAGES = 60
MAX_JPEG_BYTES = 199_000
MAX_MMS_WIDTH = 1500
MAX_MMS_HEIGHT = 1440

REGIONS = (
    "서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종",
    "경기", "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주",
)
REGION_ALT = "|".join(map(re.escape, REGIONS))
# 옛 지역식(경기 수원 너 4265), 신형(123가4567), 붙여 쓴 옛 지역식을 모두 처리.
OLD_SPACED = re.compile(r"(?<![가-힣])(?:" + REGION_ALT + r")\s+[가-힣]{2,5}\s+[가-힣]\s*\d{4,5}(?!\d)")
OLD_JOINED = re.compile(r"(?<![가-힣])(?:" + REGION_ALT + r")[가-힣]{2,5}[가-힣]\d{4,5}(?!\d)")
NEW_PLATE = re.compile(r"(?<![0-9가-힣])\d{1,3}\s*[가-힣]\s*\d(?:[ \t]?\d){3,4}(?!\d)")
PLATE_LABEL = re.compile(
    r"(?:차량\s*번호|차량\s*등록\s*번호|이륜(?:자동차|차)?\s*(?:등록)?\s*번호|등록\s*번호)\s*[:：\-]?\s*",
    flags=re.IGNORECASE,
)
PHONE_PATTERN = re.compile(r"^01[016789]\d{7,8}$")


class InsuranceDocumentError(ValueError):
    """사용자에게 표시해도 안전한 입력/변환 오류."""


def normalize_plate(value: str) -> str:
    value = unicodedata.normalize("NFKC", str(value or ""))
    return re.sub(r"[\s\-·・]", "", value)


def plate_candidates(text: str) -> list[str]:
    clean = unicodedata.normalize("NFKC", text or "")
    values = []
    for pattern in (OLD_SPACED, OLD_JOINED, NEW_PLATE):
        for match in pattern.finditer(clean):
            value = normalize_plate(match.group())
            if value not in values:
                values.append(value)
    return values


def extract_plate(text: str) -> dict:
    """명시된 '차량번호' 라벨을 우선 사용하고 중복/모호하면 사람의 검증을 요구합니다."""
    text = unicodedata.normalize("NFKC", text or "")
    labeled = []
    for label in PLATE_LABEL.finditer(text):
        fragment = text[label.end():label.end() + 90]
        # 다음 라벨/문단의 값을 잘못 가져오지 않도록 첫 두 줄까지만 검색.
        fragment = "\n".join(fragment.splitlines()[:2])
        for plate in plate_candidates(fragment):
            if plate not in labeled:
                labeled.append(plate)
    found = labeled or plate_candidates(text)
    if not found:
        return {"plate": "", "candidates": [], "review_required": True,
                "reason": "차량번호를 찾지 못했습니다. 원본 PDF를 확인하고 직접 입력해 주세요."}
    if len(found) != 1:
        return {"plate": "", "candidates": found, "review_required": True,
                "reason": "서로 다른 차량번호가 발견되었습니다. 원본을 확인하고 선택해 주세요."}
    return {"plate": found[0], "candidates": found, "review_required": not bool(labeled),
            "reason": "" if labeled else "차량번호 항목 밖에서 발견했습니다. 원본과 대조해 주세요."}


def _encode_jpeg(image, limit: int) -> tuple[bytes, bool, int, int]:
    """컬러(RGB), 가로세로 비율·전체 여백 유지. 199KiB 실패 시 발송금지 표시."""
    from PIL import Image
    # RGB 유지. MMS 업로드 규격 1500x1440 내로 비율만 축소하며, 자르지 않습니다.
    if image.width > MAX_MMS_WIDTH or image.height > MAX_MMS_HEIGHT:
        baseline = min(MAX_MMS_WIDTH / image.width, MAX_MMS_HEIGHT / image.height)
        image = image.resize((max(1, round(image.width * baseline)),
                              max(1, round(image.height * baseline))), Image.Resampling.LANCZOS)
    for scale in (1.0, .90, .80, .70, .60):
        candidate = image if scale == 1.0 else image.resize(
            (max(1, round(image.width * scale)), max(1, round(image.height * scale))),
            Image.Resampling.LANCZOS,
        )
        for quality in (95, 92, 89, 86, 82, 78, 74, 70, 66, 62):
            stream = io.BytesIO()
            candidate.save(stream, format="JPEG", quality=quality, optimize=True,
                           subsampling=0, progressive=False)
            data = stream.getvalue()
            if len(data) <= limit:
                return data, True, candidate.width, candidate.height
    # 크기에 맞추느라 문서를 더 훼손하지 않고 고화질 참고본을 반환합니다.
    stream = io.BytesIO()
    image.save(stream, format="JPEG", quality=90, optimize=True,
               subsampling=0, progressive=False)
    return stream.getvalue(), False, image.width, image.height


def convert_pdf(data: bytes, *, max_bytes: int = MAX_JPEG_BYTES) -> dict:
    if not data or len(data) > MAX_PDF_BYTES:
        raise InsuranceDocumentError("PDF 파일 크기가 허용 범위(15MB)를 초과하거나 비어 있습니다.")
    if not 50 * 1024 <= max_bytes <= 1024 * 1024:
        raise InsuranceDocumentError("이미지 용량 제한 설정이 올바르지 않습니다.")
    try:
        import fitz
        from PIL import Image
    except ImportError as exc:
        raise InsuranceDocumentError("PDF 처리 모듈(PyMuPDF/Pillow)이 설치되지 않았습니다.") from exc
    try:
        doc = fitz.open(stream=data, filetype="pdf")
    except Exception as exc:
        raise InsuranceDocumentError("PDF를 읽을 수 없습니다. 파일 형식을 확인해 주세요.") from exc
    result = []
    try:
        if doc.needs_pass:
            raise InsuranceDocumentError("암호화된 PDF는 처리할 수 없습니다.")
        if len(doc) > MAX_PAGES:
            raise InsuranceDocumentError("한 파일의 PDF 페이지는 최대 60장까지 처리할 수 있습니다.")
        for index, page in enumerate(doc):
            page_rect = page.rect
            mask = fitz.Rect(*MASK_RECT)
            if not page_rect.contains(mask):
                raise InsuranceDocumentError(
                    f"{index+1}페이지의 크기가 기존 흰색 가림 영역과 다릅니다. 해당 문서를 변환하지 않았습니다."
                )
            # 가림 적용 전에 원본 PDF 텍스트에서 차량번호 추출.
            plate_info = extract_plate(page.get_text("text"))
            # 새로운 1페이지 PDF에 복사한 후 고정 좌표 영역만 영구 가림.
            with fitz.open() as single:
                single.insert_pdf(doc, from_page=index, to_page=index)
                masked = single[0]
                masked.add_redact_annot(mask, fill=(1, 1, 1))
                masked.apply_redactions()
                # 2배 해상도에서 RGB를 유지한 채 JPEG 생성.
                pix = masked.get_pixmap(matrix=fitz.Matrix(2.0, 2.0),
                                         colorspace=fitz.csRGB, alpha=False)
                image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            jpg, within, width, height = _encode_jpeg(image, max_bytes)
            result.append({
                "page": index + 1,
                "plate": plate_info["plate"],
                "candidates": plate_info["candidates"],
                "review_required": plate_info["review_required"],
                "reason": plate_info["reason"],
                "within_limit": within,
                "size_bytes": len(jpg),
                "width": width,
                "height": height,
                "jpeg_base64": base64.b64encode(jpg).decode("ascii"),
                "warning": "" if within else "용량 제한 안에서 가독성을 유지하지 못했습니다. MMS 발송을 중단하세요.",
            })
    finally:
        doc.close()
    return {"pages": result, "limit_bytes": max_bytes, "color_mode": "RGB",
            "mask_rect": list(MASK_RECT)}


def _parse_table(headers, rows):
    cleaned = [re.sub(r"\s", "", str(col or "")).lower() for col in headers]
    car_i = next((i for i, col in enumerate(cleaned)
                  if "차량번호" in col or "등록번호" in col or "차번호" in col), None)
    phone_i = next((i for i, col in enumerate(cleaned)
                    if any(word in col for word in ("연락처", "전화", "핸드폰", "휴대폰"))), None)
    if car_i is None or phone_i is None:
        raise InsuranceDocumentError("첫 행에 차량번호와 연락처 열이 필요합니다.")
    mapping = {}
    conflicts = []
    for row in rows:
        if max(car_i, phone_i) >= len(row):
            continue
        plate = normalize_plate(row[car_i])
        phone = re.sub(r"\D", "", str(row[phone_i] or ""))
        if not plate or not PHONE_PATTERN.fullmatch(phone):
            continue
        if plate in mapping and mapping[plate] != phone:
            if plate not in conflicts:
                conflicts.append(plate)
        else:
            mapping[plate] = phone
    for plate in conflicts:
        mapping.pop(plate, None)
    return {"contacts": mapping, "conflicts": conflicts, "count": len(mapping)}


def parse_contacts(filename: str, data: bytes) -> dict:
    if not data or len(data) > MAX_CONTACT_BYTES:
        raise InsuranceDocumentError("연락처 파일이 비어 있거나 5MB를 초과했습니다.")
    if filename.lower().endswith(".csv"):
        try:
            decoded = data.decode("utf-8-sig")
        except UnicodeDecodeError:
            decoded = data.decode("cp949")
        table = csv.reader(io.StringIO(decoded))
        headers = next(table, None)
        if not headers:
            raise InsuranceDocumentError("CSV 파일에 열 제목이 없습니다.")
        return _parse_table(headers, table)
    if filename.lower().endswith(".xls"):
        try:
            import xlrd
            book = xlrd.open_workbook(file_contents=data)
            sheet = book.sheet_by_index(0)
            if sheet.nrows < 1:
                raise InsuranceDocumentError("엑셀 첫 번째 시트에 열 제목이 없습니다.")
            return _parse_table(sheet.row_values(0), (sheet.row_values(i) for i in range(1, sheet.nrows)))
        except InsuranceDocumentError:
            raise
        except Exception as exc:
            raise InsuranceDocumentError("구형 XLS 연락처 파일을 읽지 못했습니다.") from exc
    if filename.lower().endswith(".xlsx"):
        from openpyxl import load_workbook
        try:
            workbook = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        except Exception as exc:
            raise InsuranceDocumentError("엑셀 파일을 읽지 못했습니다.") from exc
        try:
            sheet = workbook.active
            lines = sheet.iter_rows(values_only=True)
            headers = next(lines, None)
            if not headers:
                raise InsuranceDocumentError("엑셀 첫 번째 시트에 열 제목이 없습니다.")
            return _parse_table(headers, lines)
        finally:
            workbook.close()
    raise InsuranceDocumentError("연락처 파일은 CSV, XLS, XLSX 형식만 지원합니다.")
