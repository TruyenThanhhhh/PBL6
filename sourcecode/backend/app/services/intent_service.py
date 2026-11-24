"""Phân loại ý định nhanh (<1ms) cho Chat: Chitchat, RAG, Action Engine, Reasoning Engine và Version Diff (hỗ trợ cả tiếng Việt có dấu & không dấu)."""
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from app.services.llm_service import is_conversational_query


@dataclass
class IntentDecision:
    kind: str  # chitchat | version_diff | create_quiz | create_flashcards | create_mindmap | create_plan | compose_document | export_previous | deep_reasoning | rag_qa
    params: Dict[str, Any] = field(default_factory=dict)


def _strip_vietnamese_accents(text: str) -> str:
    """Chuyển chuỗi tiếng Việt có dấu về không dấu (giữ nguyên chữ số và khoảng trắng) để nhận diện bền bỉ."""
    if not text:
        return ""
    s = text.replace("đ", "d").replace("Đ", "D")
    nfkd = unicodedata.normalize("NFKD", s)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


_PURE_QUESTION_SUFFIX_RE = re.compile(
    r"(?:\b(?:là\s+gì|như\s+thế\s+nào|gồm\s+những\s+gì|nói\s+(?:về\s+)?(?:nội\s+dung\s+)?gì|"
    r"chứa\s+(?:nội\s+dung\s+)?gì|có\s+những\s+gì|gồm\s+mấy\s+bước|tại\s+sao|vì\s+sao|ý\s+nghĩa\s+là\s+gì)\s*[?!.]*$)",
    re.IGNORECASE | re.UNICODE,
)
_PURE_QUESTION_SUFFIX_ASCII_RE = re.compile(
    r"(?:\b(?:la\s+gi|nhu\s+the\s+nao|gom\s+nhung\s+gi|noi\s+(?:ve\s+)?(?:noi\s+dung\s+)?gi|"
    r"chua\s+(?:noi\s+dung\s+)?gi|co\s+nhung\s+gi|gom\s+may\s+buoc|tai\s+sao|vi\s+sao|y\s+nghia\s+la\s+gi)\s*[?!.]*$)",
    re.IGNORECASE,
)

_IMPERATIVE_ACTION_RE = re.compile(
    r"(?:^|\b)(?:hãy|giúp\s+(?:tôi|mình)|làm\s+ơn|vui\s+lòng|tạo\s+cho|soạn\s+cho|viết\s+cho|lấy\s+.{1,40}\s+(?:tạo|làm)|ra\s+\d+\s+câu)",
    re.IGNORECASE | re.UNICODE,
)
_IMPERATIVE_ACTION_ASCII_RE = re.compile(
    r"(?:^|\b)(?:hay|giup\s+(?:toi|minh)|lam\s+on|vui\s+long|tao\s+cho|soan\s+cho|viet\s+cho|lay\s+.{1,40}\s+(?:tao|lam)|ra\s+\d+\s+cau)",
    re.IGNORECASE,
)

_VERSION_DIFF_RE = re.compile(
    r"(?:"
    r"(?:so\s*sánh|đối\s*chiếu|khác\s*(?:nhau\s*)?gì|thay\s*đổi\s*gì|sửa\s*đổi\s*gì|cập\s*nhật\s*gì|điểm\s*mới)"
    r".{0,60}(?:phiên\s*bản|v\d+|bản\s*cũ|bản\s*mới|ngày\s*\d+|trước\s*đó|hiệu\s*lực|lần\s*trước)"
    r"|bản\s*mới.{0,30}(?:khác|thay\s*đổi|sửa)\s*(?:gì|những\s*gì|thế\s*nào)"
    r")",
    re.IGNORECASE | re.UNICODE,
)
_VERSION_DIFF_ASCII_RE = re.compile(
    r"(?:"
    r"(?:so\s*sanh|doi\s*chieu|khac\s*(?:nhau\s*)?gi|thay\s*doi\s*gi|sua\s*doi\s*gi|cap\s*nhat\s*gi|diem\s*moi)"
    r".{0,60}(?:phien\s*ban|v\d+|ban\s*cu|ban\s*moi|ngay\s*\d+|truoc\s*do|hieu\s*luc|lan\s*truoc)"
    r"|ban\s*moi.{0,30}(?:khac|thay\s*doi|sua)\s*(?:gi|nhung\s*gi|the\s*nao)"
    r")",
    re.IGNORECASE,
)

_QUIZ_ACTION_RE = re.compile(
    r"(?:(?:tạo|ra|sinh|làm|soạn|thiết\s*kế|xây\s*dựng|biên\s*soạn).{0,36}"
    r"(?:đề\s*trắc\s*nghiệm|bài\s*trắc\s*nghiệm|trắc\s*nghiệm|quiz|bài\s*kiểm\s*tra|bài\s*test|đề\s*thi|câu\s*hỏi\s*(?:ôn\s*tập|kiểm\s*tra|trắc\s*nghiệm))"
    r"|\b\d+\s*câu\s*(?:hỏi\s*)?trắc\s*nghiệm\b)",
    re.IGNORECASE | re.UNICODE,
)
_QUIZ_ACTION_ASCII_RE = re.compile(
    r"(?:(?:tao|ra|sinh|lam|soan|thiet\s*ke|xay\s*dung|bien\s*soan).{0,36}"
    r"(?:de\s*trac\s*nghiem|bai\s*trac\s*nghiem|trac\s*nghiem|quiz|bai\s*kiem\s*tra|bai\s*test|de\s*thi|cau\s*hoi\s*(?:on\s*tap|kiem\s*tra|trac\s*nghiem))"
    r"|\b\d+\s*cau\s*(?:hoi\s*)?trac\s*nghiem\b)",
    re.IGNORECASE,
)

_FLASHCARD_ACTION_RE = re.compile(
    r"(?:tạo|ra|sinh|làm|soạn|lập).{0,32}(?:flashcard|flash\s*card|thẻ\s*ghi\s*nhớ|thẻ\s*học|thẻ\s*từ\s*vựng|bộ\s*thẻ)",
    re.IGNORECASE | re.UNICODE,
)
_FLASHCARD_ACTION_ASCII_RE = re.compile(
    r"(?:tao|ra|sinh|lam|soan|lap).{0,32}(?:flashcard|flash\s*card|the\s*ghi\s*nho|the\s*hoc|the\s*tu\s*vung|bo\s*the)",
    re.IGNORECASE,
)

_MINDMAP_ACTION_RE = re.compile(
    r"(?:tạo|vẽ|sinh|lập|xây\s*dựng).{0,24}(?:mind\s*map|sơ\s*đồ\s*tư\s*duy|cây\s*kiến\s*thức)",
    re.IGNORECASE | re.UNICODE,
)
_MINDMAP_ACTION_ASCII_RE = re.compile(
    r"(?:tao|ve|sinh|lap|xay\s*dung).{0,24}(?:mind\s*map|so\s*do\s*tu\s*duy|cay\s*kien\s*thuc)",
    re.IGNORECASE,
)

_PLAN_ACTION_RE = re.compile(
    r"(?:tạo|lập|xây\s*dựng|thiết\s*kế).{0,24}(?:lộ\s*trình\s*học|kế\s*hoạch\s*học|kế\s*hoạch\s*ôn\s*tập|study\s*plan)",
    re.IGNORECASE | re.UNICODE,
)
_PLAN_ACTION_ASCII_RE = re.compile(
    r"(?:tao|lap|xay\s*dung|thiet\s*ke).{0,24}(?:lo\s*trinh\s*hoc|ke\s*hoach\s*hoc|ke\s*hoach\s*on\s*tap|study\s*plan)",
    re.IGNORECASE,
)

_COMPOSE_DOC_RE = re.compile(
    r"(?:(?:soạn(?:\s*thảo)?|viết|tạo|lập|khởi\s*tạo).{0,28}"
    r"(?:văn\s*bản|công\s*văn|báo\s*cáo|biên\s*bản|đề\s*cương|tờ\s*trình|hợp\s*đồng|thông\s*báo|quyết\s*định|đơn\s*xin|bài\s*luận|tài\s*liệu\s*mẫu|mẫu\s*đề\s*xuất)"
    r"|(?:soạn(?:\s*thảo)?|viết|tạo|lập|xuất).{0,60}(?:ra|thành|sang)\s+(?:file|tệp)\s*(?:word|docx|pdf|excel|xlsx|markdown|md|pptx|powerpoint))",
    re.IGNORECASE | re.UNICODE,
)
_COMPOSE_DOC_ASCII_RE = re.compile(
    r"(?:(?:soan(?:\s*thao)?|viet|tao|lap|khoi\s*tao).{0,28}"
    r"(?:van\s*ban|cong\s*van|bao\s*cao|bien\s*ban|de\s*cuong|to\s*trinh|hop\s*dong|thong\s*bao|quyet\s*dinh|don\s*xin|bai\s*luan|tai\s*lieu\s*mau|mau\s*de\s*xuat)"
    r"|(?:soan(?:\s*thao)?|viet|tao|lap|xuat).{0,60}(?:ra|thanh|sang)\s+(?:file|tep)\s*(?:word|docx|pdf|excel|xlsx|markdown|md|pptx|powerpoint))",
    re.IGNORECASE,
)

_EXPORT_PREVIOUS_RE = re.compile(
    r"(?:xuất|lưu|tải|chuyển)\s+(?:lại\s+)?(?:câu\s*trả\s*lời|nội\s*dung|kết\s*quả|phần(?:\s*trả\s*lời)?|bảng)\s*"
    r"(?:vừa\s*rồi|ở\s*trên|trên|này|đó).{0,24}(?:word|docx|pdf|markdown|md|file|tệp|excel|xlsx|pptx|powerpoint)",
    re.IGNORECASE | re.UNICODE,
)
_EXPORT_PREVIOUS_ASCII_RE = re.compile(
    r"(?:xuat|luu|tai|chuyen)\s+(?:lai\s+)?(?:cau\s*tra\s*loi|noi\s*dung|ket\s*qua|phan(?:\s*tra\s*loi)?|bang)\s*"
    r"(?:vua\s*roi|o\s*tren|tren|nay|do).{0,24}(?:word|docx|pdf|markdown|md|file|tep|excel|xlsx|pptx|powerpoint)",
    re.IGNORECASE,
)

_DEEP_REASONING_RE = re.compile(
    r"(?:"
    r"\b(?:áp\s*dụng\s*công\s*thức|giải\s*bài(?:\s*toán|\s*tập)?|tính\s*(?:giá\s*trị|tổng|tiền|lãi|lương|thuế|diện\s*tích|thể\s*tích|đường\s*sinh|chu\s*vi|bán\s*kính|chiều\s*cao|đường\s*cao|khoảng\s*cách|vận\s*tốc|xác\s*suất|trung\s*bình|tỷ\s*lệ|kết\s*quả|chênh\s*lệch|tăng\s*trưởng|biên\s*lợi\s*nhuận)|thay\s*số\s*vào)\b"
    r"|(?:(?:tính|giải|tìm)\b.{0,80}(?:\d+(?:[.,]\d+)?\s*(?:cm|mm|dm|m|km|kg|g|%|đồng|triệu|tỷ)).{0,60}(?:\d+(?:[.,]\d+)?\s*(?:cm|mm|dm|m|km|kg|g|%|đồng|triệu|tỷ)))"
    r"|\b(?:nếu\s+.{5,60}\s+thì\s+(?:xử\s*lý|tính|áp\s*dụng|quyết\s*định|vi\s*phạm|được\s*không|có\s*bị|thế\s*nào|ra\s*sao))\b"
    r"|\b(?:giả\s*sử|tình\s*huống\s+(?:sau|này|trên)|có\s*vi\s*phạm\s+(?:quy\s*định|điều\s*khoản)|tự\s*suy\s*luận|suy\s*luận\s*sâu|phân\s*tích\s*sâu|đối\s*chiếu\s*(?:quy\s*định|điều\s*khoản)|có\s*rủi\s*ro|đánh\s*giá\s*rủi\s*ro|phân\s*tích\s*(?:nguyên\s*nhân|tác\s*động|hệ\s*quả|ưu\s*nhược\s*điểm|rủi\s*ro)|điểm\s*bất\s*lợi|có\s*hợp\s*lệ|đủ\s*điều\s*kiện)\b"
    r"|\b(?:nguyên\s*nhân\s*gốc\s*rễ|tối\s*ưu\s*(?:kiến\s*trúc|hiệu\s*năng|bộ\s*nhớ|truy\s*vấn)|đánh\s*đổi\s*(?:kỹ\s*thuật|hiệu\s*năng)|kiểm\s*tra\s*tính\s*hợp\s*lệ|có\s*đúng\s*quy\s*định|phát\s*hiện\s*(?:mâu\s*thuẫn|sai\s*sót|lỗ\s*hổng|thiếu\s*sót|nhầm\s*lẫn)|soát\s*lỗi|phản\s*biện|điểm\s*hòa\s*vốn|nên\s*chọn\s*(?:phương\s*án|kiến\s*trúc|công\s*nghệ)\s*nào|chiến\s*lược\s*tối\s*ưu)\b"
    r"|(?:(?:vì\s*sao|tại\s*sao).{4,50}(?:lỗi|chậm|treo|nghẽn|sai\s*sót|nhầm\s*lẫn|thất\s*bại))"
    r"|(?:(?:so\s*sánh|phân\s*tích|đánh\s*giá).{3,55}(?:rồi|và)\s*(?:đề\s*xuất|chọn|kết\s*luận|đánh\s*giá|nhận\s*xét|dự\s*báo))"
    r")",
    re.IGNORECASE | re.UNICODE,
)
_DEEP_REASONING_ASCII_RE = re.compile(
    r"(?:"
    r"\b(?:ap\s*dung\s*cong\s*thuc|giai\s*bai(?:\s*toan|\s*tap)?|tinh\s*(?:gia\s*tri|tong|tien|lai|luong|thue|dien\s*tich|the\s*tich|duong\s*sinh|chu\s*vi|ban\s*kinh|chieu\s*cao|duong\s*cao|khoang\s*cach|van\s*toc|xac\s*suat|trung\s*binh|ty\s*le|ket\s*qua|chenh\s*lech|tang\s*truong|bien\s*loi\s*nhuan)|thay\s*so\s*vao)\b"
    r"|(?:(?:tinh|giai|tim)\b.{0,80}(?:\d+(?:[.,]\d+)?\s*(?:cm|mm|dm|m|km|kg|g|%|dong|trieu|ty)).{0,60}(?:\d+(?:[.,]\d+)?\s*(?:cm|mm|dm|m|km|kg|g|%|dong|trieu|ty)))"
    r"|\b(?:neu\s+.{5,60}\s+thi\s+(?:xu\s*ly|tinh|ap\s*dung|quyet\s*dinh|vi\s*pham|duoc\s*khong|co\s*bi|the\s*nao|ra\s*sao))\b"
    r"|\b(?:gia\s*su|tinh\s*huong\s+(?:sau|nay|tren)|co\s*vi\s*pham\s+(?:quy\s*dinh|dieu\s*khoan)|tu\s*suy\s*luan|suy\s*luan\s*sau|phan\s*tich\s*sau|doi\s*chieu\s*(?:quy\s*dinh|dieu\s*khoan)|co\s*rui\s*ro|danh\s*gia\s*rui\s*ro|phan\s*tich\s*(?:nguyen\s*nhan|tac\s*dong|he\s*qua|uu\s*nhuoc\s*diem|rui\s*ro)|diem\s*bat\s*loi|co\s*hop\s*le|du\s*dieu\s*kien)\b"
    r"|\b(?:nguyen\s*nhan\s*goc\s*re|toi\s*uu\s*(?:kien\s*truc|hieu\s*nang|bo\s*nho|truy\s*van)|danh\s*doi\s*(?:ky\s*thuat|hieu\s*nang)|kiem\s*tra\s*tinh\s*hop\s*le|co\s*dung\s*quy\s*dinh|phat\s*hien\s*(?:mau\s*thuan|sai\s*sot|lo\s*hong|thieu\s*sot|nham\s*lan)|soat\s*loi|phan\s*bien|diem\s*hoa\s*von|nen\s*chon\s*(?:phuong\s*an|kien\s*truc|cong\s*nghe)\s*nao|chien\s*luoc\s*toi\s*uu)\b"
    r"|(?:(?:vi\s*sao|tai\s*sao).{4,50}(?:loi|cham|treo|nghen|sai\s*sot|nham\s*lan|that\s*bai))"
    r"|(?:(?:so\s*sanh|phan\s*tich|danh\s*gia).{3,55}(?:roi|va)\s*(?:de\s*xuat|chon|ket\s*luan|danh\s*gia|nhan\s*xet|du\s*bao))"
    r")",
    re.IGNORECASE,
)


def _extract_count(query: str, default: int, max_val: int) -> int:
    folded = _strip_vietnamese_accents(query)
    # Ưu tiên số có đơn vị đo rõ ràng (vd: "5 câu", "10 thẻ", "8 từ") và tránh bắt nhầm số chương/bài/toán 9
    m_unit = re.search(
        r"(?<!chuong\s)(?<!bai\s)(?<!phan\s)(?<!muc\s)(?<!dieu\s)(?<!toan\s)(?<!lop\s)"
        r"\b(\d{1,2})\s+(?:cau(?:\s*hoi)?|the|flash\s*cards?|quiz|tu(?:\s*vung)?|muc|nhiem\s*vu|buoc)\b",
        folded,
        re.IGNORECASE,
    )
    if m_unit:
        val = int(m_unit.group(1))
        return min(max(val, 1), max_val)
    return default


def _detect_card_style(query: str) -> str:
    low = _strip_vietnamese_accents(query.lower())
    if any(k in low for k in ("tu vung", "kanji", "jlpt", "tu moi", "ngoai ngu", "tieng anh", "tieng nhat")):
        return "vocabulary"
    if any(k in low for k in ("hoi dap", "q&a", "van dap")):
        return "qa"
    if any(k in low for k in ("dien khuyet", "cho trong", "cloze")):
        return "cloze"
    return "term_definition"


def _detect_difficulty(query: str) -> str:
    raw_low = (query or "").lower()
    low = _strip_vietnamese_accents(raw_low)
    if re.search(r"\b(?:kho|nang\s*cao|chuyen\s*sau|hard)\b", low):
        return "hard"
    # Phân biệt rõ "dễ" với "đề" (đề thi/đề trắc nghiệm) và "để"
    if re.search(r"\b(?:dễ|cơ\s*bản|nhẹ\s*nhàng|easy)\b", raw_low) or re.search(r"\b(?:co\s*ban|nhe\s*nhang)\b", low):
        return "easy"
    if re.search(r"\bde\b", low) and not re.search(r"\b(?:đề|để|vấn\s*đề)\b", raw_low) and not re.search(r"\bde\s*(?:thi|trac\s*nghiem|kiem\s*tra|cuong)\b", low):
        return "easy"
    return "medium"


def _detect_export_hint(query: str) -> str:
    low = query.lower()
    if "pdf" in low:
        return "pdf"
    if any(k in low for k in ("excel", "xlsx", ".xls")):
        return "xlsx"
    if any(k in low for k in ("pptx", "powerpoint", "slide")):
        return "pptx"
    if any(k in low for k in ("word", "docx", ".doc")):
        return "docx"
    if "markdown" in low or ".md" in low:
        return "md"
    return "docx"


def classify_chat_intent(
    query: str,
    reasoning_mode: Optional[str] = "auto",
    has_image: bool = False,
) -> IntentDecision:
    """
    Phân loại yêu cầu chat thành nhánh xử lý tối ưu.
    `reasoning_mode`: 'auto' | 'fast' | 'deep'
    """
    clean = (query or "").strip()
    if not clean:
        return IntentDecision(kind="rag_qa")

    folded = _strip_vietnamese_accents(clean)

    if (is_conversational_query(clean) or is_conversational_query(folded)) and not has_image:
        return IntentDecision(kind="chitchat")

    if not has_image:
        if _VERSION_DIFF_RE.search(clean) or _VERSION_DIFF_ASCII_RE.search(folded):
            return IntentDecision(kind="version_diff")

        is_pure_info_question = (
            bool(_PURE_QUESTION_SUFFIX_RE.search(clean) or _PURE_QUESTION_SUFFIX_ASCII_RE.search(folded))
            and not bool(_IMPERATIVE_ACTION_RE.search(clean) or _IMPERATIVE_ACTION_ASCII_RE.search(folded))
        )

        if not is_pure_info_question:
            if _QUIZ_ACTION_RE.search(clean) or _QUIZ_ACTION_ASCII_RE.search(folded):
                return IntentDecision(
                    kind="create_quiz",
                    params={
                        "question_count": _extract_count(clean, default=5, max_val=20),
                        "difficulty": _detect_difficulty(clean),
                        "focus_prompt": clean,
                    },
                )
            if _FLASHCARD_ACTION_RE.search(clean) or _FLASHCARD_ACTION_ASCII_RE.search(folded):
                return IntentDecision(
                    kind="create_flashcards",
                    params={
                        "count": _extract_count(clean, default=10, max_val=30),
                        "card_style": _detect_card_style(clean),
                        "focus_prompt": clean,
                    },
                )
            if _MINDMAP_ACTION_RE.search(clean) or _MINDMAP_ACTION_ASCII_RE.search(folded):
                return IntentDecision(
                    kind="create_mindmap",
                    params={"focus_prompt": clean},
                )
            if _PLAN_ACTION_RE.search(clean) or _PLAN_ACTION_ASCII_RE.search(folded):
                days_match = re.search(r"\b(\d{1,2})\s*(?:ngày|ngay)\b", folded, re.IGNORECASE)
                day_span = min(max(int(days_match.group(1)), 1), 30) if days_match else 7
                return IntentDecision(
                    kind="create_plan",
                    params={"day_span": day_span, "focus_prompt": clean},
                )
            if _EXPORT_PREVIOUS_RE.search(clean) or _EXPORT_PREVIOUS_ASCII_RE.search(folded):
                return IntentDecision(
                    kind="export_previous",
                    params={"default_export_format": _detect_export_hint(clean)},
                )
            if _COMPOSE_DOC_RE.search(clean) or _COMPOSE_DOC_ASCII_RE.search(folded):
                return IntentDecision(
                    kind="compose_document",
                    params={"default_export_format": _detect_export_hint(clean)},
                )

    r_mode = (reasoning_mode or "auto").strip().lower()
    if r_mode == "deep":
        return IntentDecision(kind="deep_reasoning", params={"forced": True})
    if r_mode == "auto" and not has_image and (
        _DEEP_REASONING_RE.search(clean) or _DEEP_REASONING_ASCII_RE.search(folded)
    ):
        return IntentDecision(kind="deep_reasoning", params={"forced": False})

    return IntentDecision(kind="rag_qa")
