"""Phân loại ý định nhanh (<1ms) cho Chat: Chitchat, RAG, Action Engine, Reasoning Engine và Version Diff."""
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from app.services.llm_service import is_conversational_query


@dataclass
class IntentDecision:
    kind: str  # chitchat | version_diff | create_quiz | create_flashcards | create_mindmap | create_plan | compose_document | deep_reasoning | rag_qa
    params: Dict[str, Any] = field(default_factory=dict)


_PURE_QUESTION_SUFFIX_RE = re.compile(
    r"(?:\b(?:là\s+gì|như\s+thế\s+nào|gồm\s+những\s+gì|tại\s+sao|vì\s+sao|ý\s+nghĩa\s+là\s+gì)\s*[?!.]*$)",
    re.IGNORECASE | re.UNICODE,
)
_IMPERATIVE_ACTION_RE = re.compile(
    r"(?:^|\b)(?:hãy|giúp\s+(?:tôi|mình)|làm\s+ơn|vui\s+lòng|tạo\s+cho|soạn\s+cho|viết\s+cho|lấy\s+.{1,40}\s+(?:tạo|làm)|ra\s+\d+\s+câu)",
    re.IGNORECASE | re.UNICODE,
)

_VERSION_DIFF_RE = re.compile(
    r"(?:"
    r"(?:so\s*sánh|đối\s*chiếu|khác\s*(?:nhau\s*)?gì|thay\s*đổi\s*gì|sửa\s*đổi\s*gì|cập\s*nhật\s*gì|điểm\s*mới)"
    r".{0,60}(?:phiên\s*bản|v\d+|bản\s*cũ|bản\s*mới|ngày\s*\d+|trước\s*đó|hiệu\s*lực|lần\s*trước)"
    r"|bản\s*mới.{0,30}(?:khác|thay\s*đổi|sửa)\s*(?:gì|những\s*gì|thế\s*nào)"
    r")",
    re.IGNORECASE | re.UNICODE,
)

_QUIZ_ACTION_RE = re.compile(
    r"(?:(?:tạo|ra|sinh|làm|soạn|thiết\s*kế|xây\s*dựng|biên\s*soạn).{0,36}"
    r"(?:đề\s*trắc\s*nghiệm|bài\s*trắc\s*nghiệm|trắc\s*nghiệm|quiz|bài\s*kiểm\s*tra|bài\s*test|đề\s*thi|câu\s*hỏi\s*(?:ôn\s*tập|kiểm\s*tra|trắc\s*nghiệm))"
    r"|\b\d+\s*câu\s*(?:hỏi\s*)?trắc\s*nghiệm\b)",
    re.IGNORECASE | re.UNICODE,
)

_FLASHCARD_ACTION_RE = re.compile(
    r"(?:tạo|ra|sinh|làm|soạn|lập).{0,32}(?:flashcard|flash\s*card|thẻ\s*ghi\s*nhớ|thẻ\s*học|thẻ\s*từ\s*vựng|bộ\s*thẻ)",
    re.IGNORECASE | re.UNICODE,
)

_MINDMAP_ACTION_RE = re.compile(
    r"(?:tạo|vẽ|sinh|lập|xây\s*dựng).{0,24}(?:mind\s*map|sơ\s*đồ\s*tư\s*duy|cây\s*kiến\s*thức)",
    re.IGNORECASE | re.UNICODE,
)

_PLAN_ACTION_RE = re.compile(
    r"(?:tạo|lập|xây\s*dựng|thiết\s*kế).{0,24}(?:lộ\s*trình\s*học|kế\s*hoạch\s*học|kế\s*hoạch\s*ôn\s*tập|study\s*plan)",
    re.IGNORECASE | re.UNICODE,
)

_COMPOSE_DOC_RE = re.compile(
    r"(?:soạn(?:\s*thảo)?|viết|tạo|lập|khởi\s*tạo).{0,28}"
    r"(?:văn\s*bản|công\s*văn|báo\s*cáo|biên\s*bản|đề\s*cương|tờ\s*trình|hợp\s*đồng|thông\s*báo|quyết\s*định|đơn\s*xin|bài\s*luận|tài\s*liệu\s*mẫu|mẫu\s*đề\s*xuất)",
    re.IGNORECASE | re.UNICODE,
)

_DEEP_REASONING_RE = re.compile(
    r"(?:"
    r"\b(?:áp\s*dụng\s*công\s*thức|giải\s*bài(?:\s*toán|\s*tập)?|tính\s*(?:giá\s*trị|tổng|tiền|lãi|lương|thuế|diện\s*tích|thể\s*tích|vận\s*tốc|xác\s*suất|trung\s*bình|tỷ\s*lệ|kết\s*quả)|thay\s*số\s*vào)\b"
    r"|\b(?:nếu\s+.{5,60}\s+thì\s+(?:xử\s*lý|tính|áp\s*dụng|quyết\s*định|vi\s*phạm|được\s*không|thế\s*nào|ra\s*sao))\b"
    r"|\b(?:giả\s*sử|tình\s*huống\s+(?:sau|này|trên)|có\s*vi\s*phạm\s+(?:quy\s*định|điều\s*khoản)|tự\s*suy\s*luận|suy\s*luận\s*sâu|phân\s*tích\s*sâu|đối\s*chiếu\s*(?:quy\s*định|điều\s*khoản))\b"
    r"|(?:so\s*sánh.{4,45}(?:rồi|và)\s*(?:đề\s*xuất|chọn|kết\s*luận))"
    r")",
    re.IGNORECASE | re.UNICODE,
)


def _extract_count(query: str, default: int, max_val: int) -> int:
    m = re.search(r"\b(\d{1,2})\s*(?:câu|thẻ|từ(?:\s*vựng)?|mục|nhiệm\s*vụ|bước)?\b", query, re.IGNORECASE)
    if not m:
        return default
    val = int(m.group(1))
    return min(max(val, 1), max_val)


def _detect_card_style(query: str) -> str:
    low = query.lower()
    if any(k in low for k in ("từ vựng", "kanji", "jlpt", "từ mới", "ngoại ngữ", "tiếng anh", "tiếng nhật")):
        return "vocabulary"
    if any(k in low for k in ("hỏi đáp", "q&a", "vấn đáp")):
        return "qa"
    if any(k in low for k in ("điền khuyết", "chỗ trống", "cloze")):
        return "cloze"
    return "term_definition"


def _detect_difficulty(query: str) -> str:
    low = query.lower()
    if any(k in low for k in ("dễ", "cơ bản", "nhẹ nhàng")):
        return "easy"
    if any(k in low for k in ("khó", "nâng cao", "chuyên sâu")):
        return "hard"
    return "medium"


def _detect_export_hint(query: str) -> str:
    low = query.lower()
    if "pdf" in low:
        return "pdf"
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

    if is_conversational_query(clean) and not has_image:
        return IntentDecision(kind="chitchat")

    if not has_image:
        if _VERSION_DIFF_RE.search(clean):
            return IntentDecision(kind="version_diff")

        is_pure_info_question = bool(_PURE_QUESTION_SUFFIX_RE.search(clean)) and not bool(
            _IMPERATIVE_ACTION_RE.search(clean)
        )

        if not is_pure_info_question:
            if _QUIZ_ACTION_RE.search(clean):
                return IntentDecision(
                    kind="create_quiz",
                    params={
                        "question_count": _extract_count(clean, default=5, max_val=20),
                        "difficulty": _detect_difficulty(clean),
                        "focus_prompt": clean,
                    },
                )
            if _FLASHCARD_ACTION_RE.search(clean):
                return IntentDecision(
                    kind="create_flashcards",
                    params={
                        "count": _extract_count(clean, default=10, max_val=30),
                        "card_style": _detect_card_style(clean),
                        "focus_prompt": clean,
                    },
                )
            if _MINDMAP_ACTION_RE.search(clean):
                return IntentDecision(
                    kind="create_mindmap",
                    params={"focus_prompt": clean},
                )
            if _PLAN_ACTION_RE.search(clean):
                days_match = re.search(r"\b(\d{1,2})\s*ngày\b", clean, re.IGNORECASE)
                day_span = min(max(int(days_match.group(1)), 1), 30) if days_match else 7
                return IntentDecision(
                    kind="create_plan",
                    params={"day_span": day_span, "focus_prompt": clean},
                )
            if _COMPOSE_DOC_RE.search(clean):
                return IntentDecision(
                    kind="compose_document",
                    params={"default_export_format": _detect_export_hint(clean)},
                )

    r_mode = (reasoning_mode or "auto").strip().lower()
    if r_mode == "deep":
        return IntentDecision(kind="deep_reasoning", params={"forced": True})
    if r_mode == "auto" and not has_image and _DEEP_REASONING_RE.search(clean):
        return IntentDecision(kind="deep_reasoning", params={"forced": False})

    return IntentDecision(kind="rag_qa")
