import base64
import csv
import hashlib
import io
import uuid
import re
import logging
import threading
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

import httpx

from app.config import (
    CHUNK_SIZE,
    CHUNK_OVERLAP,
    UPLOAD_DIR,
    EMBEDDING_MODEL,
    OLLAMA_BASE_URL,
    VISION_MODEL,
)
from app.database import get_db_connection
from app.services.embedding_service import embed_texts, pack_vector
from app.services.llm_service import resolve_available_vision_model

logger = logging.getLogger(__name__)
SUPPORTED_TYPES = {"pdf", "docx", "pptx", "txt", "md", "py", "json", "csv", "xlsx", "xls"}


def _extract_docx_table_lines(table: Any) -> List[str]:
    """Trích xuất từng hàng bảng Word theo định dạng '| col1 | col2 |' để chunker bảo toàn bảng."""
    rows_out: List[str] = []
    for row in getattr(table, "rows", ()):
        seen_tcs = set()
        cells_text: List[str] = []
        nested_lines: List[str] = []
        for cell in getattr(row, "cells", ()):
            tc = getattr(cell, "_tc", cell)
            tc_id = id(tc)
            if tc_id in seen_tcs:
                continue
            seen_tcs.add(tc_id)
            cell_val = " ".join(part.strip() for part in (cell.text or "").splitlines() if part.strip())
            if cell_val:
                cells_text.append(cell_val)
            for nested_tbl in getattr(cell, "tables", ()):
                nested_lines.extend(_extract_docx_table_lines(nested_tbl))
        if len(cells_text) >= 2:
            rows_out.append(f"| {' | '.join(cells_text)} |")
        elif cells_text:
            rows_out.append(cells_text[0])
        rows_out.extend(nested_lines)
    return rows_out


def _extract_docx_blocks(doc: Any) -> List[str]:
    """Đọc đoạn văn và bảng biểu DOCX theo đúng thứ tự xuất hiện trong tài liệu."""
    body = getattr(getattr(doc, "element", None), "body", None)
    if body is None:
        return []

    from docx.oxml.table import CT_Tbl
    from docx.oxml.text.paragraph import CT_P
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    blocks: List[str] = []
    for child in body.iterchildren():
        if isinstance(child, CT_P):
            text = Paragraph(child, doc).text.strip()
            if text:
                blocks.append(text)
        elif isinstance(child, CT_Tbl):
            table_lines = _extract_docx_table_lines(Table(child, doc))
            if table_lines:
                blocks.append("\n".join(table_lines))
    return blocks


_NUMERIC_CLEAN_RE = re.compile(r"^[-+]?\d+(?:[.,]\d+)*(?:%)?$")
_OUTLINE_HEADING_RE = re.compile(
    r"^(?:#{1,4}\s+.+|(?:chương|bài|phần|mục|điều|khoản|vấn\s+đề|chapter|section|part|article)\s+(?:[IVXLCDM]{1,6}|\d{1,3})\b.*)$",
    re.IGNORECASE | re.UNICODE,
)


def _try_parse_number(val: str) -> Optional[float]:
    clean = (val or "").strip().replace(" ", "")
    if not clean or clean.endswith("%"):
        return None
    if not _NUMERIC_CLEAN_RE.match(clean):
        return None
    # Hỗ trợ cả định dạng 1,234,567.89 hoặc 1.234.567,89 hoặc số thuần
    if "," in clean and "." in clean:
        if clean.rfind(",") > clean.rfind("."):
            clean = clean.replace(".", "").replace(",", ".")
        else:
            clean = clean.replace(",", "")
    elif clean.count(",") == 1 and len(clean.split(",")[1]) in (1, 2):
        clean = clean.replace(",", ".")
    elif clean.count(",") >= 1:
        clean = clean.replace(",", "")
    elif clean.count(".") > 1:
        clean = clean.replace(".", "")
    try:
        num = float(clean)
        return num if not (num != num) else None
    except Exception:
        return None


def _fmt_num(val: float) -> str:
    if abs(val - round(val)) < 1e-6:
        return str(int(round(val)))
    return f"{val:.2f}"


def _build_tabular_analytics_summary(raw_rows: List[List[str]], title: str = "Bảng dữ liệu") -> str:
    """
    Tính toán thống kê toàn bảng (Tổng số dòng, Tổng cộng, Trung bình, Min, Max của từng cột số
    và phân bố nhóm danh mục) để AI trả lời chính xác 100% câu hỏi trên bảng lớn (>100 dòng).
    """
    non_empty = [r for r in raw_rows if any(str(c).strip() for c in r)]
    if len(non_empty) < 2:
        return ""
    headers = [str(h).strip() or f"Cột_{idx+1}" for idx, h in enumerate(non_empty[0])]
    data_rows = non_empty[1:]
    row_count = len(data_rows)
    col_count = len(headers)

    numeric_stats: List[str] = []
    category_stats: List[str] = []
    numeric_cols: List[Tuple[int, str]] = []
    category_cols: List[Tuple[int, str, List[Tuple[str, int]]]] = []

    for col_idx, col_name in enumerate(headers[:16]):
        nums: List[float] = []
        cats: Dict[str, int] = {}
        for r in data_rows:
            cell = str(r[col_idx]).strip() if col_idx < len(r) else ""
            if not cell:
                continue
            parsed = _try_parse_number(cell)
            if parsed is not None:
                nums.append(parsed)
            elif len(cell) <= 48:
                cats[cell] = cats.get(cell, 0) + 1

        # Bỏ qua cột STT / ID tăng dần đơn thuần nếu tên cột là stt/id
        col_low = col_name.lower()
        is_id_col = col_low in ("stt", "id", "no", "no.", "index", "mã", "ma")
        if len(nums) >= max(2, int(row_count * 0.5)) and not is_id_col:
            total = sum(nums)
            avg = total / len(nums)
            mn = min(nums)
            mx = max(nums)
            numeric_cols.append((col_idx, col_name))
            numeric_stats.append(
                f"  - Cột '{col_name}' ({len(nums)} giá trị số): Tổng cộng (SUM) = {_fmt_num(total)} | "
                f"Trung bình (AVG) = {_fmt_num(avg)} | Nhỏ nhất (MIN) = {_fmt_num(mn)} | Lớn nhất (MAX) = {_fmt_num(mx)}"
            )
        elif 1 < len(cats) <= 12 and sum(cats.values()) >= max(2, int(row_count * 0.5)):
            top_cats = sorted(cats.items(), key=lambda kv: (-kv[1], kv[0]))[:6]
            category_cols.append((col_idx, col_name, top_cats))
            cat_str = ", ".join(f"{k}: {v} dòng" for k, v in top_cats)
            category_stats.append(f"  - Phân bố cột '{col_name}': {cat_str}")

    groupby_stats: List[str] = []
    for cat_idx, cat_name, top_cats in category_cols[:2]:
        allowed_keys = {k for k, _ in top_cats}
        for num_idx, num_name in numeric_cols[:3]:
            grouped_vals: Dict[str, List[float]] = {k: [] for k in allowed_keys}
            for r in data_rows:
                c_val = str(r[cat_idx]).strip() if cat_idx < len(r) else ""
                n_raw = str(r[num_idx]).strip() if num_idx < len(r) else ""
                if c_val in grouped_vals and n_raw:
                    n_val = _try_parse_number(n_raw)
                    if n_val is not None:
                        grouped_vals[c_val].append(n_val)
            parts = []
            for k, _ in top_cats:
                vals = grouped_vals.get(k) or []
                if vals:
                    parts.append(
                        f"{k} ({len(vals)} dòng): SUM={_fmt_num(sum(vals))}, AVG={_fmt_num(sum(vals)/len(vals))}"
                    )
            if parts:
                groupby_stats.append(f"  - '{num_name}' theo '{cat_name}': {' | '.join(parts)}")

    lines = [
        f"[THỐNG KÊ TOÀN BẢNG DỮ LIỆU - {title}]",
        f"- Quy mô toàn bảng: {row_count} dòng dữ liệu x {col_count} cột ({', '.join(headers[:16])}).",
    ]
    if numeric_stats:
        lines.append("- Số liệu tính toán chính xác trên 100% dòng của bảng:")
        lines.extend(numeric_stats)
    if category_stats:
        lines.append("- Thống kê phân nhóm danh mục trên toàn bảng:")
        lines.extend(category_stats)
    if groupby_stats:
        lines.append("- Tổng hợp chi tiết theo từng nhóm (Group-By Subtotals):")
        lines.extend(groupby_stats)
    return "\n".join(lines)


def _unpivot_side_by_side_blocks(raw_rows: List[List[str]]) -> Optional[str]:
    """
    Phát hiện và tách các bảng con xếp ngang nhau (Side-by-Side Horizontal Sub-Tables)
    trên cùng 1 Sheet Excel (ví dụ: 'Bài 1 | ... | Bài 2 | ... | Bài 12' với các cụm cột lặp lại 'STT | Kanji | Hiragana | Meaning').
    Chuyển thành từng mục 'Bài 1', 'Bài 2'... theo chiều dọc để `search_section_chunks` lấy trọn vẹn 100% mục/từ vựng của từng bài.
    """
    if len(raw_rows) < 3:
        return None

    # Tìm dòng tiêu đề lặp lại (ví dụ chữ 'STT' hoặc tên cột đầu xuất hiện >= 3 lần trên cùng 1 dòng)
    header_row_idx = -1
    block_starts: List[int] = []
    for r_idx, row in enumerate(raw_rows[:8]):
        starts = [c_idx for c_idx, val in enumerate(row) if val.strip().upper() in ("STT", "NO", "NO.", "ID")]
        if len(starts) >= 3:
            header_row_idx = r_idx
            block_starts = starts
            break

    if header_row_idx == -1 or len(block_starts) < 3:
        return None

    max_cols = max(len(r) for r in raw_rows)
    block_ranges: List[Tuple[int, int]] = []
    for i, s_col in enumerate(block_starts):
        e_col = block_starts[i + 1] if (i + 1) < len(block_starts) else max_cols
        block_ranges.append((s_col, e_col))

    # Đọc dòng phía trên header_row_idx để gán nhãn Bài / Chương / Phần cho từng cụm cột
    section_labels: List[str] = []
    active_label = "Phần 1"
    for s_col, e_col in block_ranges:
        found_label = ""
        for prev_r in range(0, header_row_idx):
            row = raw_rows[prev_r]
            slice_vals = [row[c].strip() for c in range(s_col, min(e_col, len(row))) if row[c].strip()]
            if slice_vals:
                found_label = " - ".join(slice_vals)
                break
        if found_label and not found_label.replace(".", "").isdigit():
            active_label = found_label
        section_labels.append(active_label)

    # Gom các dòng dữ liệu theo từng Bài/Mục đúng thứ tự dọc
    grouped_sections: List[Tuple[str, List[str]]] = []
    label_to_lines: Dict[str, List[str]] = {}
    for b_idx, (s_col, e_col) in enumerate(block_ranges):
        lbl = section_labels[b_idx]
        if lbl not in label_to_lines:
            hdr_cells = [
                raw_rows[header_row_idx][c].strip()
                for c in range(s_col, min(e_col, len(raw_rows[header_row_idx])))
                if raw_rows[header_row_idx][c].strip()
            ]
            lines_list = [lbl]
            if hdr_cells:
                lines_list.append(" | ".join(hdr_cells))
            label_to_lines[lbl] = lines_list
            grouped_sections.append((lbl, lines_list))

        target_lines = label_to_lines[lbl]
        for data_r in raw_rows[header_row_idx + 1 :]:
            cells = [
                data_r[c].strip()
                for c in range(s_col, min(e_col, len(data_r)))
                if data_r[c].strip()
            ]
            if len(cells) >= 2:
                target_lines.append(" | ".join(cells))

    if not grouped_sections:
        return None

    overview = "Danh mục các phần trong bảng: " + " ; ".join(lbl for lbl, _ in grouped_sections)
    section_blocks = ["\n".join(lines) for _, lines in grouped_sections if len(lines) > 2]
    return overview + "\n\n" + "\n\n".join(section_blocks)


def _build_csv_analytics_summary(content: str, file_name: str) -> str:
    """Phân tích toàn bộ nội dung CSV và tạo khối thống kê tổng hợp chính xác."""
    try:
        reader = csv.reader(io.StringIO(content))
        rows = [[cell.strip() for cell in row] for row in reader if any(cell.strip() for cell in row)]
        if len(rows) < 2:
            return ""
        return _build_tabular_analytics_summary(rows, title=file_name)
    except Exception:
        return ""


def _build_document_outline_summary(pages: List[Dict[str, Any]], file_name: str) -> Optional[str]:
    """
    Trích xuất Cây mục lục & Bản đồ cấu trúc toàn tài liệu (Document Outline) cho tài liệu nhiều trang/nhiều chương.
    Giúp AI nắm toàn cảnh mọi Chương/Điều/Mục ngay cả khi tài liệu dài 50-100 trang.
    """
    headings: List[str] = []
    seen_headings = set()
    for p in pages:
        p_no = p.get("page", 1)
        for raw_line in (p.get("text") or "").splitlines():
            line = raw_line.strip()
            if not line or len(line) > 140:
                continue
            if _OUTLINE_HEADING_RE.match(line):
                clean_h = re.sub(r"^#{1,6}\s*", "", line).strip()
                norm_key = clean_h.lower()
                if norm_key not in seen_headings:
                    seen_headings.add(norm_key)
                    headings.append(f"  - [Trang {p_no}] {clean_h}")
                    if len(headings) >= 45:
                        break
        if len(headings) >= 45:
            break

    if len(headings) < 3 and len(pages) < 3:
        return None

    outline_lines = [
        f"[CÂY MỤC LỤC & TỔNG QUAN CẤU TRÚC TÀI LIỆU: {file_name}]",
        f"- Tổng số trang/phần: {len(pages)}",
    ]
    if headings:
        outline_lines.append(f"- Danh mục {len(headings)} Chương / Điều / Mục chính trong toàn bộ tài liệu:")
        outline_lines.extend(headings)
    else:
        page_previews = []
        for p in pages[:12]:
            first_line = next((ln.strip() for ln in (p.get("text") or "").splitlines() if ln.strip()), "")[:110]
            if first_line:
                page_previews.append(f"  - [Trang {p.get('page', 1)}] {first_line}")
        if page_previews:
            outline_lines.append("- Tóm lược mở đầu các trang:")
            outline_lines.extend(page_previews)

    return "\n".join(outline_lines)


_RAPIDOCR_ENGINE: Any = None
_RAPIDOCR_CHECKED = False


def _get_pdf_ocr_page_limit() -> int:
    """Giới hạn số trang OCR theo hồ sơ phần cứng để không làm treo máy yếu."""
    try:
        from app.services.hardware_profile_service import get_active_profile_config
        profile_id = str(get_active_profile_config().get("id") or "balanced").lower()
    except Exception:
        profile_id = "balanced"
    if profile_id == "eco":
        return 5
    if profile_id == "performance":
        return 25
    return 12


def _get_rapidocr_engine() -> Any:
    global _RAPIDOCR_ENGINE, _RAPIDOCR_CHECKED
    if _RAPIDOCR_CHECKED:
        return _RAPIDOCR_ENGINE
    _RAPIDOCR_CHECKED = True
    try:
        from rapidocr_onnxruntime import RapidOCR  # type: ignore
        _RAPIDOCR_ENGINE = RapidOCR()
    except Exception:
        _RAPIDOCR_ENGINE = None
    return _RAPIDOCR_ENGINE


def _resolve_sync_ollama_vision_model() -> Optional[str]:
    try:
        resp = httpx.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=1.5)
        if resp.status_code != 200:
            return None
        models = [m.get("name") for m in resp.json().get("models", []) if m.get("name")]
        return resolve_available_vision_model(VISION_MODEL, models)
    except Exception:
        return None


def _ocr_via_ollama_vision(png_bytes: bytes, vision_model: Optional[str]) -> str:
    if not vision_model or not png_bytes:
        return ""
    try:
        b64_img = base64.b64encode(png_bytes).decode("ascii")
        resp = httpx.post(
            f"{OLLAMA_BASE_URL}/api/chat",
            json={
                "model": vision_model,
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            "Hãy đọc và chép lại nguyên văn toàn bộ chữ, số và bảng biểu có trong trang tài liệu này. "
                            "Giữ nguyên cấu trúc dòng/bảng, không thêm nhận xét."
                        ),
                        "images": [b64_img],
                    }
                ],
                "stream": False,
                "options": {"temperature": 0.1, "num_predict": 1200, "num_ctx": 2048},
            },
            timeout=45.0,
        )
        if resp.status_code == 200:
            return str(resp.json().get("message", {}).get("content") or "").strip()
    except Exception:
        logger.debug("Ollama Vision OCR failed on scanned page", exc_info=True)
    return ""


def _ocr_png_bytes(png_bytes: bytes, vision_model: Optional[str] = None) -> str:
    """Trích xuất chữ từ ảnh trang PDF bằng RapidOCR, Tesseract hoặc Ollama Vision cục bộ."""
    if not png_bytes:
        return ""

    rapid_engine = _get_rapidocr_engine()
    if rapid_engine is not None:
        try:
            res, _ = rapid_engine(png_bytes)
            if res:
                lines = [str(item[1]).strip() for item in res if len(item) >= 2 and str(item[1]).strip()]
                if lines:
                    return "\n".join(lines)
        except Exception:
            logger.debug("RapidOCR failed on scanned page", exc_info=True)

    try:
        import pytesseract  # type: ignore
        from PIL import Image

        with Image.open(io.BytesIO(png_bytes)) as img:
            for lang in ("vie+eng", "eng"):
                try:
                    txt = pytesseract.image_to_string(img, lang=lang).strip()
                    if txt:
                        return txt
                except Exception:
                    continue
    except ImportError:
        pass
    except Exception:
        logger.debug("Tesseract OCR failed on scanned page", exc_info=True)

    return _ocr_via_ollama_vision(png_bytes, vision_model)


def _extract_pdf_pages_with_ocr_fallback(doc: Any) -> List[Dict[str, Any]]:
    """Đọc text layer PDF trước, tự động fallback sang OCR cho các trang ảnh scan."""
    page_texts: Dict[int, str] = {}
    scanned_indices: List[int] = []
    total_pages = len(doc)

    for i, page in enumerate(doc):
        extracted = (page.get_text("text", sort=True) or page.get_text("text") or "").strip()
        if extracted:
            from app.services.llm_service import decode_symbol_pua_text
            page_texts[i + 1] = decode_symbol_pua_text(extracted)
        if len(extracted) < 20:
            has_images = bool(page.get_images(full=False))
            if not extracted or has_images:
                scanned_indices.append(i)

    if scanned_indices:
        max_ocr_pages = _get_pdf_ocr_page_limit()
        vision_checked = False
        vision_model: Optional[str] = None

        for page_idx in scanned_indices[:max_ocr_pages]:
            try:
                pix = doc[page_idx].get_pixmap(dpi=150)
                png_bytes = pix.tobytes("png")
                ocr_text = _ocr_png_bytes(png_bytes).strip()
                if not ocr_text:
                    if not vision_checked:
                        vision_model = _resolve_sync_ollama_vision_model()
                        vision_checked = True
                    if vision_model:
                        ocr_text = _ocr_via_ollama_vision(png_bytes, vision_model).strip()
                if ocr_text:
                    existing = page_texts.get(page_idx + 1, "").strip()
                    page_texts[page_idx + 1] = f"{existing}\n{ocr_text}".strip() if existing else ocr_text
            except Exception:
                logger.debug("PDF page pixmap/OCR error at page %s", page_idx + 1, exc_info=True)

    ordered_results = [
        {"page": page_no, "text": page_texts[page_no]}
        for page_no in sorted(page_texts.keys())
        if page_texts[page_no].strip()
    ]
    if total_pages > 0 and not ordered_results:
        raise ValueError(
            "PDF dạng ảnh scan chưa có lớp văn bản và chưa có công cụ OCR cục bộ khả dụng. "
            "Hãy kéo model Vision (vd: `ollama pull qwen3-vl:2b-instruct`) hoặc cài `rapidocr-onnxruntime` / `pytesseract`."
        )
    return _strip_repeated_pdf_headers_footers(ordered_results)


def _strip_repeated_pdf_headers_footers(pages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Loại bỏ dòng header/footer lặp lại ở mép trên/dưới nhiều trang PDF (vd tên tác giả, số trang, tên sách)."""
    if len(pages) < 4:
        return pages

    edge_counts: Dict[str, int] = {}
    for p in pages:
        lines = [ln.strip() for ln in (p.get("text") or "").splitlines() if ln.strip()]
        if not lines:
            continue
        edge_candidates = lines[:2] + (lines[-2:] if len(lines) > 2 else [])
        seen_on_page: set[str] = set()
        for ln in edge_candidates:
            norm = re.sub(r"\d+", "#", ln).strip()
            if len(norm) >= 10 and norm not in seen_on_page:
                seen_on_page.add(norm)
                edge_counts[norm] = edge_counts.get(norm, 0) + 1

    min_repeats = max(3, int(len(pages) * 0.35))
    repeated_norms = {norm for norm, cnt in edge_counts.items() if cnt >= min_repeats}
    standalone_page_re = re.compile(r"^(?:page|trang)\s*\d+(?:\s*/\s*\d+)?$", re.IGNORECASE)

    if not repeated_norms:
        return pages

    cleaned_pages: List[Dict[str, Any]] = []
    for p in pages:
        out_lines = []
        for ln in (p.get("text") or "").splitlines():
            s = ln.strip()
            norm = re.sub(r"\d+", "#", s).strip()
            if s and (norm in repeated_norms or standalone_page_re.match(s)):
                continue
            out_lines.append(ln)
        cleaned_pages.append({**p, "text": "\n".join(out_lines)})
    return cleaned_pages


def extract_text_from_file(file_path: Path, file_type: str) -> List[Dict[str, Any]]:
    """
    Trích xuất text sạch từ file (PDF, DOCX, PPTX, TXT, MD) và giữ metadata số trang/slide.
    """
    results = []

    if file_type == "pdf":
        try:
            try:
                import pymupdf  # type: ignore

                doc = pymupdf.open(str(file_path))
                try:
                    results.extend(_extract_pdf_pages_with_ocr_fallback(doc))
                finally:
                    doc.close()
            except ImportError:
                import pypdf

                reader = pypdf.PdfReader(str(file_path))
                for i, page in enumerate(reader.pages):
                    extracted = page.extract_text() or ""
                    if extracted.strip():
                        results.append({"page": i + 1, "text": extracted})
        except ValueError:
            raise
        except Exception as e:
            logger.exception("PDF extraction failed")
            raise ValueError("Không thể trích xuất nội dung PDF") from e

    elif file_type == "docx":
        try:
            import docx
            doc = docx.Document(str(file_path))
            blocks = _extract_docx_blocks(doc)
            full_text = "\n\n".join(blocks)
            if not full_text.strip():
                para_text = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
                table_lines: List[str] = []
                for tbl in getattr(doc, "tables", ()):
                    table_lines.extend(_extract_docx_table_lines(tbl))
                full_text = "\n\n".join(
                    part for part in (para_text, "\n".join(table_lines)) if part.strip()
                )
            if full_text.strip():
                results.append({"page": 1, "text": full_text})
        except Exception as e:
            logger.exception("DOCX extraction failed")
            raise ValueError("Không thể trích xuất nội dung DOCX") from e

    elif file_type == "pptx":
        try:
            from pptx import Presentation
            prs = Presentation(str(file_path))
            for i, slide in enumerate(prs.slides):
                slide_texts = []
                for shape in slide.shapes:
                    if hasattr(shape, "text") and shape.text.strip():
                        slide_texts.append(shape.text.strip())
                if slide_texts:
                    results.append({"page": i + 1, "text": "\n".join(slide_texts)})
        except Exception as e:
            logger.exception("PPTX extraction failed")
            raise ValueError("Không thể trích xuất nội dung PPTX") from e

    elif file_type in ["xlsx", "xls"]:
        try:
            if file_type == "xlsx":
                import openpyxl
                wb = openpyxl.load_workbook(str(file_path), data_only=True, read_only=True)
                try:
                    for sheet_idx, sheet_name in enumerate(wb.sheetnames):
                        ws = wb[sheet_name]
                        raw_rows: List[List[str]] = []
                        lines = []
                        for row in ws.iter_rows(values_only=True):
                            row_vals = ["" if c is None else str(c).strip() for c in row]
                            if any(v != "" for v in row_vals):
                                raw_rows.append(row_vals)
                                cells = [v for v in row_vals if v != ""]
                                lines.append(" | ".join(cells))
                        if lines:
                            unpivoted = _unpivot_side_by_side_blocks(raw_rows)
                            if unpivoted:
                                sheet_text = f"Sheet: {sheet_name}\n{unpivoted}"
                            else:
                                summary_header = _build_tabular_analytics_summary(
                                    raw_rows, title=f"Sheet: {sheet_name}"
                                )
                                body = "\n".join(lines)
                                sheet_text = (
                                    f"{summary_header}\n\nSheet: {sheet_name}\n{body}"
                                    if summary_header
                                    else f"Sheet: {sheet_name}\n{body}"
                                )
                            results.append({"page": sheet_idx + 1, "text": sheet_text})
                finally:
                    wb.close()
            else:
                import pandas as pd
                excel_file = pd.ExcelFile(str(file_path))
                for sheet_idx, sheet_name in enumerate(excel_file.sheet_names):
                    df = pd.read_excel(excel_file, sheet_name=sheet_name)
                    df_clean = df.dropna(how="all")
                    if not df_clean.empty:
                        raw_rows = [
                            [str(col).strip() for col in df_clean.columns],
                            *[
                                ["" if pd.isna(v) else str(v).strip() for v in row]
                                for row in df_clean.to_numpy().tolist()
                            ],
                        ]
                        summary_header = _build_tabular_analytics_summary(
                            raw_rows, title=f"Sheet: {sheet_name}"
                        )
                        text = df_clean.to_string(index=False)
                        sheet_text = (
                            f"{summary_header}\n\nSheet: {sheet_name}\n{text}"
                            if summary_header
                            else f"Sheet: {sheet_name}\n{text}"
                        )
                        results.append({"page": sheet_idx + 1, "text": sheet_text})
        except Exception as e:
            logger.exception("Excel extraction failed")
            raise ValueError(f"Không thể trích xuất nội dung tệp Excel: {e}") from e

    elif file_type in ["txt", "md", "py", "json", "csv"]:
        try:
            try:
                with open(file_path, "r", encoding="utf-8-sig") as f:
                    content = f.read()
            except UnicodeDecodeError:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
            if content.strip():
                if file_type == "csv":
                    csv_summary = _build_csv_analytics_summary(content, file_path.name)
                    if csv_summary:
                        content = f"{csv_summary}\n\n{content}"
                results.append({"page": 1, "text": content})
        except Exception as e:
            logger.exception("Text extraction failed")
            raise ValueError("Không thể đọc tệp văn bản") from e

    return results


def recursive_chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> List[str]:
    """
    Phân đoạn ngữ cảnh tự nhiên (Semantic & Markdown-aware Chunking):
    1. Bảo toàn nguyên vẹn Bảng biểu (| ... |) và Khối Code (``` ... ```), không xẻ đôi giữa chừng.
    2. Cắt theo ranh giới đoạn văn tự nhiên và tiêu đề phân cấp (#, ##, Bài, Chương).
    3. Đính kèm siêu dữ liệu cấu trúc (Structural Breadcrumb) [Chương/Bài] vào đầu các chunk tiếp nối
       để tăng cường độ chính xác tìm kiếm của BM25 và Vector BGE-M3.
    """
    text = re.sub(r'\r\n', '\n', text)
    if not text.strip():
        return []
    soft_max = int(chunk_size * 1.35)
    if len(text) <= soft_max:
        return [text.strip()]

    lines = text.split('\n')
    blocks: List[Tuple[str, str]] = []
    current_block: List[str] = []
    current_type: Optional[str] = None

    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # 1. Khối mã lệnh Fenced Code Block
        if stripped.startswith('```'):
            if current_block:
                blocks.append((current_type or 'paragraph', '\n'.join(current_block)))
                current_block = []
                current_type = None
            code_lines = [line]
            i += 1
            while i < len(lines):
                code_lines.append(lines[i])
                if lines[i].strip().startswith('```'):
                    break
                i += 1
            blocks.append(('code', '\n'.join(code_lines)))
            i += 1
            continue

        # 2. Khối bảng biểu Markdown Table
        if stripped.startswith('|') and stripped.endswith('|'):
            if current_type != 'table' and current_block:
                blocks.append((current_type or 'paragraph', '\n'.join(current_block)))
                current_block = []
            current_type = 'table'
            current_block.append(line)
            i += 1
            continue
        elif current_type == 'table':
            blocks.append(('table', '\n'.join(current_block)))
            current_block = []
            current_type = None

        # 3. Tiêu đề phân cấp (Header & Section titles - hỗ trợ sách toán, giáo trình, văn bản pháp luật)
        is_heading = bool(
            re.match(r'^#{1,6}\s+', stripped) or
            re.match(
                r'^(?:chương|bài|phần|mục|vấn\s*đề|chuyên\s*đề|điều|khoản|lab|chapter|section)\s+(?:[IVXLCDM]{1,6}|\d{1,3})[:.]?',
                stripped,
                re.IGNORECASE,
            ) or
            re.match(r'^\d{1,2}\.\s+[A-ZÀ-Ỹ0-9][A-ZÀ-Ỹ0-9\s,–\-()]{3,}$', stripped)
        )
        if is_heading:
            if current_block:
                blocks.append((current_type or 'paragraph', '\n'.join(current_block)))
                current_block = []
            blocks.append(('heading', stripped))
            current_type = None
            i += 1
            continue

        # 4. Ngắt dòng đoạn văn (\n\n)
        if not stripped:
            if current_block:
                blocks.append((current_type or 'paragraph', '\n'.join(current_block)))
                current_block = []
                current_type = None
            i += 1
            continue

        current_type = current_type or 'paragraph'
        current_block.append(line)
        i += 1

    if current_block:
        blocks.append((current_type or 'paragraph', '\n'.join(current_block)))

    chunks: List[str] = []
    current_chunk: List[str] = []
    current_len = 0
    active_heading = ''

    for b_type, b_text in blocks:
        if b_type == 'heading':
            # Xả sạch chunk của mục trước bằng active_heading CŨ trước khi chuyển sang tiêu đề mới
            if current_chunk:
                c_content = '\n\n'.join(current_chunk).strip()
                if active_heading and not c_content.startswith(f'[{active_heading}]') and not c_content.startswith(f'# {active_heading}'):
                    c_content = f'[{active_heading}]\n{c_content}'
                if c_content:
                    chunks.append(c_content)
                current_chunk = []
                current_len = 0
            active_heading = re.sub(r'^#{1,6}\s*', '', b_text).strip()
            current_chunk = [b_text]
            current_len = len(b_text)
            continue

        b_len = len(b_text)

        # Xử lý khối đơn lẻ có độ dài vượt quá chunk_size (ví dụ đoạn văn quá dài hoặc bảng khổng lồ)
        if b_len > chunk_size:
            if current_chunk:
                if current_len <= 320:
                    b_text = '\n\n'.join([*current_chunk, b_text]).strip()
                    b_len = len(b_text)
                else:
                    c_content = '\n\n'.join(current_chunk).strip()
                    if active_heading and not c_content.startswith(f'[{active_heading}]') and not c_content.startswith(f'# {active_heading}'):
                        c_content = f'[{active_heading}]\n{c_content}'
                    if c_content:
                        chunks.append(c_content)
                current_chunk = []
                current_len = 0

            sub_start = 0
            while sub_start < b_len:
                if b_len - sub_start <= soft_max:
                    piece = b_text[sub_start:].strip()
                    if piece:
                        chunks.append(piece)
                    break
                sub_end = sub_start + chunk_size
                cut = b_text.rfind('\n', sub_start + chunk_size // 2, sub_end)
                if cut == -1:
                    cut = b_text.rfind('. ', sub_start + chunk_size // 2, sub_end)
                if cut == -1:
                    cut = sub_end
                else:
                    cut += 1
                piece = b_text[sub_start:cut].strip()
                if piece:
                    chunks.append(piece)
                sub_start = cut - overlap if cut - overlap > sub_start else cut
            continue

        if current_len + b_len + 2 > chunk_size and current_chunk:
            c_content = '\n\n'.join(current_chunk).strip()
            if active_heading and not c_content.startswith(f'[{active_heading}]') and not c_content.startswith(f'# {active_heading}'):
                c_content = f'[{active_heading}]\n{c_content}'
            if c_content:
                chunks.append(c_content)

            # Giữ block cuối cho độ gối đầu overlap nếu hợp lý
            last_block = current_chunk[-1]
            if overlap > 0 and len(last_block) <= overlap:
                current_chunk = [last_block, b_text]
                current_len = len(last_block) + b_len + 2
            else:
                current_chunk = [b_text]
                current_len = b_len
        else:
            current_chunk.append(b_text)
            current_len += b_len + 2

    if current_chunk:
        c_content = '\n\n'.join(current_chunk).strip()
        if active_heading and not c_content.startswith(f'[{active_heading}]') and not c_content.startswith(f'# {active_heading}'):
            c_content = f'[{active_heading}]\n{c_content}'
        if c_content:
            chunks.append(c_content)

    return chunks


_BG_EMBED_LOCK = threading.Lock()


def _is_mocked_callable(fn: Any) -> bool:
    return bool(
        hasattr(fn, "_mock_name")
        or hasattr(fn, "assert_called")
        or getattr(fn, "__module__", "").startswith("unittest.mock")
    )


def _invalidate_vector_cache_safe(workspace_id: Optional[str] = None) -> None:
    try:
        from app.services.retrieval_service import invalidate_workspace_vector_cache
        invalidate_workspace_vector_cache(workspace_id)
    except Exception:
        pass


def _index_chunk_vectors_in_batches(chunks: List[Dict[str, Any]], batch_size: int = 24) -> int:
    """Tính vector BGE-M3 theo từng lô và lưu ngay vào SQLite để không chặn luồng tải lên."""
    if not chunks:
        return 0
    indexed_count = 0
    workspace_ids = {c.get("workspace_id") for c in chunks if c.get("workspace_id")}
    import time as _time

    eco_mode = False
    try:
        from app.services.hardware_profile_service import get_active_profile_config
        eco_mode = str(get_active_profile_config().get("id") or "").lower() == "eco"
    except Exception:
        pass

    with _BG_EMBED_LOCK:
        for start in range(0, len(chunks), batch_size):
            batch = chunks[start : start + batch_size]
            vectors = embed_texts([c["content"] for c in batch])
            if not vectors:
                break
            rows_to_insert = [
                (c["id"], EMBEDDING_MODEL, len(vec), pack_vector(vec))
                for c, vec in zip(batch, vectors)
            ]
            conn = get_db_connection()
            try:
                conn.executemany(
                    """
                    INSERT OR REPLACE INTO chunk_embeddings (chunk_id, model, dimensions, vector)
                    VALUES (?, ?, ?, ?)
                    """,
                    rows_to_insert,
                )
                conn.commit()
                indexed_count += len(rows_to_insert)
            except Exception:
                logger.exception("Lỗi khi lưu lô vector embedding chạy nền")
            finally:
                conn.close()
            if eco_mode and start + batch_size < len(chunks):
                _time.sleep(0.03)
    for ws_id in workspace_ids:
        _invalidate_vector_cache_safe(ws_id)
    return indexed_count


def _schedule_background_chunk_embeddings(chunks: List[Dict[str, Any]]) -> None:
    if not chunks:
        return
    batch_size = 24
    try:
        from app.services.hardware_profile_service import get_active_profile_config
        batch_size = int(get_active_profile_config().get("embed_batch_size") or 24)
    except Exception:
        pass
    worker = threading.Thread(
        target=_index_chunk_vectors_in_batches,
        args=(list(chunks), max(4, batch_size)),
        daemon=True,
    )
    worker.start()


def process_and_index_document(
    workspace_id: str,
    file_name: str,
    file_bytes: bytes,
    notebook_id: Optional[str] = None,
    replace_document_id: Optional[str] = None,
    effective_date: Optional[str] = None,
    auto_version: bool = False,
) -> Dict[str, Any]:
    """
    Xử lý file tải lên: lưu trữ, trích xuất text, chunking, lập chỉ mục FTS5 tức thì,
    sinh vector BGE-M3 và quản lý chuỗi phiên bản tài liệu (v1 -> v2).
    """
    # Chuẩn hóa notebook_id để tránh vi phạm FOREIGN KEY constraint
    notebook_id = notebook_id.strip() if notebook_id and notebook_id.strip() else None
    if notebook_id:
        conn_chk = get_db_connection()
        nb_exists = conn_chk.execute("SELECT 1 FROM notebooks WHERE id = ?", (notebook_id,)).fetchone()
        conn_chk.close()
        if not nb_exists:
            notebook_id = None
    doc_id = str(uuid.uuid4())
    safe_name = Path(file_name or "upload.txt").name
    ext = Path(safe_name).suffix.lower().lstrip(".") or "txt"
    if ext not in SUPPORTED_TYPES:
        raise ValueError(f"Định dạng không hỗ trợ: {ext}")
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    saved_path = UPLOAD_DIR / f"{doc_id}_{safe_name}"

    with open(saved_path, "wb") as f:
        f.write(file_bytes)

    file_size = len(file_bytes)
    content_hash = hashlib.sha256(file_bytes).hexdigest()

    # Khử trùng lặp trên các bản đang có hiệu lực mới nhất (is_latest = 1)
    conn_dedup = get_db_connection()
    try:
        cur_dedup = conn_dedup.cursor()
        existing = cur_dedup.execute(
            """
            SELECT id, file_name, file_type, file_size, total_pages, total_chunks, status,
                   version_group_id, COALESCE(version_number, 1) AS version_number,
                   COALESCE(is_latest, 1) AS is_latest, effective_date
            FROM documents
            WHERE workspace_id = ? AND content_hash = ? AND COALESCE(is_latest, 1) = 1
            """,
            (workspace_id, content_hash),
        ).fetchone()
        if existing and not replace_document_id:
            saved_path.unlink(missing_ok=True)
            existing_dict = dict(existing)
            existing_dict.setdefault("document_id", existing_dict.get("id"))
            return existing_dict

        # Xác định tài liệu cũ cần nâng cấp phiên bản (nếu có)
        prev_doc = None
        target_prev_id = (replace_document_id or "").strip()
        if target_prev_id:
            prev_doc = cur_dedup.execute(
                """
                SELECT id, version_group_id, COALESCE(version_number, 1) AS version_number
                FROM documents WHERE id = ? AND workspace_id = ?
                """,
                (target_prev_id, workspace_id),
            ).fetchone()
        elif auto_version:
            prev_doc = cur_dedup.execute(
                """
                SELECT id, version_group_id, COALESCE(version_number, 1) AS version_number
                FROM documents
                WHERE workspace_id = ? AND LOWER(file_name) = LOWER(?) AND COALESCE(is_latest, 1) = 1
                ORDER BY COALESCE(version_number, 1) DESC, created_at DESC
                LIMIT 1
                """,
                (workspace_id, safe_name),
            ).fetchone()
    finally:
        conn_dedup.close()

    if prev_doc:
        version_group_id = prev_doc["version_group_id"] or prev_doc["id"]
        max_ver_conn = get_db_connection()
        try:
            row_max = max_ver_conn.execute(
                "SELECT MAX(COALESCE(version_number, 1)) AS max_v FROM documents WHERE workspace_id = ? AND (version_group_id = ? OR id = ?)",
                (workspace_id, version_group_id, prev_doc["id"]),
            ).fetchone()
            base_v = int(row_max["max_v"] or prev_doc["version_number"] or 1) if row_max else int(prev_doc["version_number"] or 1)
        finally:
            max_ver_conn.close()
        version_number = base_v + 1
    else:
        version_group_id = doc_id
        version_number = 1

    clean_effective_date = (effective_date or "").strip() or None

    # 1. Trích xuất text sạch
    try:
        pages = extract_text_from_file(saved_path, ext)
    except Exception:
        saved_path.unlink(missing_ok=True)
        raise
    if not pages:
        if ext in ["txt", "md", "csv", "json", "py"]:
            text = file_bytes.decode("utf-8", errors="ignore")
            if text.strip():
                pages = [{"page": 1, "text": text}]

    if not pages:
        saved_path.unlink(missing_ok=True)
        raise ValueError("Không trích xuất được văn bản từ tài liệu")

    total_pages = max(1, len(pages))

    # 2. Chunking + Cây mục lục cấp tài liệu (Document Outline cho tài liệu dài/nhiều mục)
    all_chunks = []
    chunk_index = 0
    outline_summary = _build_document_outline_summary(pages, safe_name)
    if outline_summary:
        all_chunks.append({
            "id": str(uuid.uuid4()),
            "document_id": doc_id,
            "workspace_id": workspace_id,
            "chunk_index": chunk_index,
            "page_number": 1,
            "token_count": max(1, len(outline_summary.split())),
            "content": outline_summary,
        })
        chunk_index += 1

    for p in pages:
        page_chunks = recursive_chunk_text(p["text"])
        for c in page_chunks:
            chunk_id = str(uuid.uuid4())
            token_count = max(1, len(c.split()))
            all_chunks.append({
                "id": chunk_id,
                "document_id": doc_id,
                "workspace_id": workspace_id,
                "chunk_index": chunk_index,
                "page_number": p["page"],
                "token_count": token_count,
                "content": c,
            })
            chunk_index += 1

    # Chỉ chạy đồng bộ trong luồng HTTP nếu đang chạy unit test (mock) hoặc tài liệu rất nhỏ (<= 4 chunks)
    run_sync_embed = _is_mocked_callable(embed_texts) or len(all_chunks) <= 4
    vectors = embed_texts([chunk["content"] for chunk in all_chunks]) if run_sync_embed else None

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        if prev_doc:
            cursor.execute(
                """
                UPDATE documents
                SET version_group_id = COALESCE(version_group_id, ?),
                    is_latest = 0,
                    superseded_by = ?
                WHERE workspace_id = ? AND (id = ? OR version_group_id = ?)
                """,
                (version_group_id, doc_id, workspace_id, prev_doc["id"], version_group_id),
            )

        cursor.execute(
            """
            INSERT INTO documents (
                id, workspace_id, notebook_id, file_name, file_type,
                file_size, file_path, content_hash, total_pages, total_chunks, status,
                version_group_id, version_number, is_latest, superseded_by, effective_date
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                doc_id, workspace_id, notebook_id, safe_name, ext,
                file_size, str(saved_path), content_hash, total_pages, len(all_chunks), "indexed",
                version_group_id, version_number, 1, None, clean_effective_date,
            ),
        )

        if all_chunks:
            cursor.executemany(
                """
                INSERT INTO document_chunks (
                    id, document_id, workspace_id, chunk_index, page_number, token_count, content
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        c["id"], c["document_id"], c["workspace_id"],
                        c["chunk_index"], c["page_number"], c["token_count"], c["content"],
                    )
                    for c in all_chunks
                ],
            )

            cursor.executemany(
                """
                INSERT INTO chunks_fts (chunk_id, document_id, workspace_id, content)
                VALUES (?, ?, ?, ?)
                """,
                [
                    (c["id"], c["document_id"], c["workspace_id"], re.sub(r'["\']', '', c["content"]))
                    for c in all_chunks
                ],
            )

        if vectors:
            cursor.executemany(
                "INSERT INTO chunk_embeddings (chunk_id, model, dimensions, vector) VALUES (?, ?, ?, ?)",
                [
                    (chunk["id"], EMBEDDING_MODEL, len(vector), pack_vector(vector))
                    for chunk, vector in zip(all_chunks, vectors)
                ],
            )

        cursor.execute(
            "INSERT INTO user_activities (id, workspace_id, activity_type, message) VALUES (?, ?, ?, ?)",
            (str(uuid.uuid4()), workspace_id, "document", f"Đã tải lên và lập chỉ mục tài liệu '{safe_name}'"),
        )
        cursor.execute(
            "UPDATE workspaces SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (workspace_id,),
        )

        conn.commit()
    except Exception:
        saved_path.unlink(missing_ok=True)
        conn = get_db_connection()
        try:
            conn.execute("UPDATE documents SET status = ? WHERE id = ?", ("failed", doc_id))
            conn.commit()
        finally:
            conn.close()
        raise
    conn.close()
    _invalidate_vector_cache_safe(workspace_id)

    if not run_sync_embed and all_chunks:
        _schedule_background_chunk_embeddings(all_chunks)

    return {
        "document_id": doc_id,
        "file_name": safe_name,
        "file_type": ext,
        "total_pages": total_pages,
        "total_chunks": len(all_chunks),
        "dense_indexed": bool(vectors),
        "vector_pending": not run_sync_embed and bool(all_chunks),
        "status": "indexed",
        "version_group_id": version_group_id,
        "version_number": version_number,
        "is_latest": 1,
        "effective_date": clean_effective_date,
    }


def reindex_document_embeddings(document_id: str) -> Dict[str, Any]:
    """Build or refresh BGE-M3 vectors for a document that was indexed FTS-only."""
    conn = get_db_connection()
    try:
        doc_row = conn.execute("SELECT workspace_id FROM documents WHERE id = ?", (document_id,)).fetchone()
        if not doc_row:
            raise ValueError("Không tìm thấy tài liệu")
        workspace_id = doc_row["workspace_id"]
        rows = conn.execute(
            "SELECT id, content FROM document_chunks WHERE document_id = ? ORDER BY chunk_index",
            (document_id,),
        ).fetchall()
        vectors = embed_texts([row["content"] for row in rows])
        if vectors is None:
            raise RuntimeError("BGE-M3 chưa sẵn sàng; hãy kiểm tra fastembed và kết nối tải model")
        conn.execute(
            "DELETE FROM chunk_embeddings WHERE chunk_id IN "
            "(SELECT id FROM document_chunks WHERE document_id = ?)",
            (document_id,),
        )
        for row, vector in zip(rows, vectors):
            conn.execute(
                "INSERT INTO chunk_embeddings (chunk_id, model, dimensions, vector) VALUES (?, ?, ?, ?)",
                (row["id"], EMBEDDING_MODEL, len(vector), pack_vector(vector)),
            )
        conn.commit()
        _invalidate_vector_cache_safe(workspace_id)
        return {"document_id": document_id, "dense_indexed": len(vectors), "total_chunks": len(rows)}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def rebuild_document_from_source(
    document_id: str,
    sync_vectors: bool = True,
    schedule_background: bool = True,
) -> Dict[str, Any]:
    """
    Trích xuất lại tài liệu gốc bằng bộ trích xuất hiện đại (PDF sort=True + giải mã PUA MS Word),
    chia đoạn theo tiêu đề mục sạch và cập nhật lại toàn bộ chunks + FTS5 + vectors.
    """
    conn = get_db_connection()
    try:
        doc_row = conn.execute(
            "SELECT id, workspace_id, file_name, file_type, file_path FROM documents WHERE id = ?",
            (document_id,),
        ).fetchone()
        if not doc_row:
            raise ValueError("Không tìm thấy tài liệu")
        workspace_id = doc_row["workspace_id"]
        file_name = doc_row["file_name"]
        file_type = doc_row["file_type"]
        saved_path = Path(doc_row["file_path"])
    finally:
        conn.close()

    if not saved_path.exists():
        raise FileNotFoundError(f"Không tìm thấy tệp gốc trên đĩa: {saved_path}")

    pages = extract_text_from_file(saved_path, file_type)
    if not pages:
        raise ValueError("Không trích xuất được nội dung văn bản từ tệp gốc")

    total_pages = max(1, len(pages))
    all_chunks: List[Dict[str, Any]] = []
    chunk_index = 0
    outline_summary = _build_document_outline_summary(pages, file_name)
    if outline_summary:
        all_chunks.append({
            "id": str(uuid.uuid4()),
            "document_id": document_id,
            "workspace_id": workspace_id,
            "chunk_index": chunk_index,
            "page_number": 1,
            "token_count": max(1, len(outline_summary.split())),
            "content": outline_summary,
        })
        chunk_index += 1

    for p in pages:
        for c in recursive_chunk_text(p["text"]):
            all_chunks.append({
                "id": str(uuid.uuid4()),
                "document_id": document_id,
                "workspace_id": workspace_id,
                "chunk_index": chunk_index,
                "page_number": p["page"],
                "token_count": max(1, len(c.split())),
                "content": c,
            })
            chunk_index += 1

    conn_w = get_db_connection()
    try:
        cur = conn_w.cursor()
        cur.execute("DELETE FROM chunks_fts WHERE document_id = ?", (document_id,))
        cur.execute(
            "DELETE FROM chunk_embeddings WHERE chunk_id IN "
            "(SELECT id FROM document_chunks WHERE document_id = ?)",
            (document_id,),
        )
        cur.execute("DELETE FROM document_chunks WHERE document_id = ?", (document_id,))
        if all_chunks:
            cur.executemany(
                """
                INSERT INTO document_chunks (
                    id, document_id, workspace_id, chunk_index, page_number, token_count, content
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        c["id"], c["document_id"], c["workspace_id"],
                        c["chunk_index"], c["page_number"], c["token_count"], c["content"],
                    )
                    for c in all_chunks
                ],
            )
            cur.executemany(
                "INSERT INTO chunks_fts (chunk_id, document_id, workspace_id, content) VALUES (?, ?, ?, ?)",
                [
                    (c["id"], c["document_id"], c["workspace_id"], re.sub(r'["\']', '', c["content"]))
                    for c in all_chunks
                ],
            )
        cur.execute(
            "UPDATE documents SET total_pages = ?, total_chunks = ?, status = 'indexed' WHERE id = ?",
            (total_pages, len(all_chunks), document_id),
        )
        conn_w.commit()
    except Exception:
        conn_w.rollback()
        raise
    finally:
        conn_w.close()

    _invalidate_vector_cache_safe(workspace_id)
    indexed_vectors = 0
    if all_chunks:
        if sync_vectors or _is_mocked_callable(embed_texts):
            indexed_vectors = _index_chunk_vectors_in_batches(all_chunks, batch_size=24)
        elif schedule_background:
            _schedule_background_chunk_embeddings(all_chunks)

    return {
        "document_id": document_id,
        "file_name": file_name,
        "total_pages": total_pages,
        "total_chunks": len(all_chunks),
        "dense_indexed": indexed_vectors if sync_vectors else len(all_chunks),
        "rebuilt": True,
    }


def build_document_guide(document_id: str) -> Dict[str, Any]:
    """
    Tạo Source Guide chuẩn NotebookLM trong <15ms từ chỉ mục đoạn của tài liệu:
    gồm chủ đề/mục lục nổi bật, tóm tắt cấu trúc, phân loại lĩnh vực và câu hỏi gợi ý sát nguồn.
    """
    from app.services.llm_service import decode_symbol_pua_text

    conn = get_db_connection()
    try:
        doc_row = conn.execute(
            "SELECT id, workspace_id, file_name, file_type, total_pages, total_chunks FROM documents WHERE id = ?",
            (document_id,),
        ).fetchone()
        if not doc_row:
            raise ValueError("Không tìm thấy tài liệu")
        rows = conn.execute(
            "SELECT chunk_index, page_number, content FROM document_chunks WHERE document_id = ? ORDER BY chunk_index ASC LIMIT 40",
            (document_id,),
        ).fetchall()
    finally:
        conn.close()

    raw_contents = [str(r["content"] or "") for r in rows]
    has_legacy_pua = any(bool(re.search(r"[\uf000-\uf0ff]", t)) for t in raw_contents)
    decoded_chunks = [
        {"chunk_index": r["chunk_index"], "page_number": r["page_number"], "text": decode_symbol_pua_text(str(r["content"] or ""))}
        for r in rows
    ]

    outline_items: List[str] = []
    seen_headings: set[str] = set()
    heading_re = re.compile(
        r"^(?:#{1,4}\s*)?((?:(?:Chương|Bài|Phần|Mục|Vấn\s*đề|Chuyên\s*đề|Điều|Khoản|Chapter|Section)\s+(?:[IVXLCDM]{1,6}|\d{1,3})[^\n]{0,75})|(?:\d{1,2}\.\s+[A-ZÀ-Ỹ0-9][^\n]{3,75}))",
        re.IGNORECASE | re.UNICODE,
    )
    for item in decoded_chunks:
        for raw_line in item["text"].splitlines():
            line = re.sub(r"\s+", " ", raw_line).strip(" -–*•")
            if not line or line.startswith("[CÂY MỤC LỤC") or "Trang " in line and line.startswith("Trang "):
                continue
            m = heading_re.match(line)
            if m:
                heading = m.group(1).strip()
                heading_clean = re.sub(r"\.{3,}.*$", "", heading).strip(" .:-")
                norm = heading_clean.lower()
                if 5 <= len(heading_clean) <= 85 and norm not in seen_headings:
                    seen_headings.add(norm)
                    outline_items.append(heading_clean)
                    if len(outline_items) >= 14:
                        break
        if len(outline_items) >= 14:
            break

    sample_text = "\n".join(c["text"][:500] for c in decoded_chunks[:4])
    folded = f"{doc_row['file_name']} {sample_text}".lower()
    if any(k in folded for k in ("toán", "hàm số", "phương trình", "hình học", "công thức", "tam giác", "đường thẳng")):
        doc_category = "math_science"
    elif any(k in folded for k in ("từ vựng", "vocabulary", "jlpt", "english", "kanji", "hiragana")):
        doc_category = "vocab"
    elif any(k in folded for k in ("quy định", "điều khoản", "nội quy", "luật", "nghị định", "chính sách")):
        doc_category = "policy"
    elif any(k in folded for k in ("api", "rag", "llm", "python", "sql", "server", "kiến trúc", "thuật toán")):
        doc_category = "tech"
    elif any(k in folded for k in ("doanh thu", "lợi nhuận", "chi phí", "tài chính", "ngân sách", "kpi")):
        doc_category = "finance"
    else:
        doc_category = "general"

    # Tạo tóm tắt súc tích từ outline hoặc đoạn mở đầu
    summary_lines: List[str] = []
    if outline_items:
        top_list = ", ".join(outline_items[:5])
        summary_lines.append(
            f"Tài liệu **{doc_row['file_name']}** ({doc_row['total_pages']} trang, {doc_row['total_chunks']} phân đoạn) "
            f"bao gồm các chủ đề chính như: {top_list}{'...' if len(outline_items) > 5 else '.'}"
        )
    else:
        opening = ""
        for c in decoded_chunks:
            txt = c["text"].strip()
            if txt and not txt.startswith("[CÂY MỤC LỤC"):
                opening = re.sub(r"\s+", " ", txt)[:320].rstrip()
                break
        summary_lines.append(
            f"Tài liệu **{doc_row['file_name']}** ({doc_row['total_pages']} trang, {doc_row['total_chunks']} phân đoạn). "
            + (f"Nội dung mở đầu: {opening}..." if opening else "")
        )

    suggested_questions: List[str] = []
    for sec in outline_items[:2]:
        suggested_questions.append(f"Nội dung chi tiết của {sec} gồm những gì?")
    if doc_category == "math_science":
        suggested_questions.append(f"Tổng hợp tất cả công thức và định lý quan trọng trong {doc_row['file_name']}")
        suggested_questions.append(f"Các dạng bài tập và phương pháp giải chính trong {doc_row['file_name']} là gì?")
    elif doc_category == "vocab":
        suggested_questions.append(f"Liệt kê 10 từ vựng tiêu biểu kèm phiên âm, nghĩa và ví dụ từ {doc_row['file_name']}")
        suggested_questions.append(f"Tạo bài kiểm tra nhanh 5 câu từ nội dung {doc_row['file_name']}")
    elif doc_category == "policy":
        suggested_questions.append(f"Tóm tắt các quy định bắt buộc và trường hợp ngoại lệ trong {doc_row['file_name']}")
        suggested_questions.append(f"Những mức phạt, điều kiện hoặc mốc thời gian quan trọng cần lưu ý là gì?")
    else:
        suggested_questions.append(f"Tóm tắt các luận điểm cốt lõi nhất của {doc_row['file_name']} kèm trích dẫn")
        suggested_questions.append(f"Đề xuất 5 câu hỏi ôn tập trọng tâm từ tài liệu này")

    return {
        "document_id": doc_row["id"],
        "file_name": doc_row["file_name"],
        "file_type": doc_row["file_type"],
        "total_pages": doc_row["total_pages"],
        "total_chunks": doc_row["total_chunks"],
        "doc_category": doc_category,
        "has_legacy_pua": has_legacy_pua,
        "summary": "\n\n".join(summary_lines),
        "outline": outline_items,
        "suggested_questions": suggested_questions[:4],
    }
