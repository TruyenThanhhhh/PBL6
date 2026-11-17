"""
Service chuyển đổi và xuất nội dung học tập / báo cáo Markdown sang các định dạng:
- Markdown (.md)
- Word (.docx) qua python-docx
- PDF (.pdf) qua fpdf2 (hỗ trợ Unicode tiếng Việt và ký tự CJK)
"""
import io
import os
import re
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor
from fpdf import FPDF
from fpdf.fonts import FontFace

TEAL_HEX = "087F73"
TEAL_SOFT_HEX = "E6F3F1"
TEAL_RGB = (8, 127, 115)
INK_RGB = (23, 43, 41)
MUTED_RGB = (100, 124, 121)
CODE_BG_RGB = (241, 246, 245)

_SPAN_PATTERN = re.compile(
    r"(\*\*\*[^*\n]+\*\*\*|\*\*[^*\n]+\*\*|__[^_\n]+__|\*[^*\n]+\*|_[^_\n]+_|`[^`\n]+`|\[[^\]\n]+\]\([^\)\n]+\))"
)
_ORDERED_PATTERN = re.compile(r"^(\s*)(\d+[.)])\s+(.*)$")
_BULLET_PATTERN = re.compile(r"^(\s*)[-*+•]\s+(.*)$")
_HEADING_PATTERN = re.compile(r"^(#{1,4})\s+(.*)$")
_HR_PATTERN = re.compile(r"^\s*(?:---+|\*\*\*+|___+)\s*$")
_TABLE_SEP_PATTERN = re.compile(r"^\s*\|?(?:\s*:?-{2,}:?\s*\|)+(?:\s*:?-{2,}:?\s*)?\|?\s*$")


def _safe_filenames(title: str, ext: str) -> Tuple[str, str]:
    """Tạo cặp tên file (ascii fallback cho header chuẩn HTTP, utf-8 cho RFC 5987)."""
    clean_title = re.sub(r'[\\/:*?"<>|\r\n]+', " ", (title or "").strip())
    clean_title = re.sub(r"\s+", " ", clean_title).strip() or "Tai_lieu_hoc_tap"
    clean_title = clean_title[:80].strip(" ._") or "Tai_lieu_hoc_tap"

    utf8_name = f"{clean_title}.{ext}"
    normalized = unicodedata.normalize("NFKD", clean_title.replace("đ", "d").replace("Đ", "D"))
    ascii_stem = "".join(ch for ch in normalized if ord(ch) < 128)
    ascii_stem = re.sub(r"[^A-Za-z0-9._-]+", "_", ascii_stem).strip("_.-") or "tai_lieu_hoc_tap"
    return f"{ascii_stem}.{ext}", utf8_name


def _strip_pdf_unsupported_glyphs(text: str) -> str:
    """Loại bỏ emoji ngoài mặt phẳng BMP mà font TTF tiêu chuẩn không có glyph để tránh lỗi ký tự ô vuông."""
    cleaned_chars: List[str] = []
    for ch in text:
        code = ord(ch)
        if code > 0xFFFF:
            continue
        if ch in {"\uFE0E", "\uFE0F", "\u200D"}:
            continue
        if 0x2600 <= code <= 0x27BF:
            continue
        cleaned_chars.append(ch)
    result = "".join(cleaned_chars)
    return re.sub(r"^\s+", "", result) if cleaned_chars != list(text) else result


def _parse_inline_spans(text: str) -> List[Tuple[str, str]]:
    """Tách chuỗi Markdown một dòng thành danh sách (style, text)."""
    if not text:
        return [("text", "")]

    spans: List[Tuple[str, str]] = []
    pos = 0
    for match in _SPAN_PATTERN.finditer(text):
        if match.start() > pos:
            spans.append(("text", text[pos : match.start()]))

        token = match.group(0)
        if token.startswith("***") and token.endswith("***") and len(token) > 6:
            spans.append(("bold_italic", token[3:-3]))
        elif (token.startswith("**") and token.endswith("**")) or (
            token.startswith("__") and token.endswith("__")
        ):
            spans.append(("bold", token[2:-2]))
        elif (token.startswith("*") and token.endswith("*")) or (
            token.startswith("_") and token.endswith("_")
        ):
            spans.append(("italic", token[1:-1]))
        elif token.startswith("`") and token.endswith("`"):
            spans.append(("code", token[1:-1]))
        elif token.startswith("[") and "](" in token:
            label = token[1 : token.index("](")]
            spans.append(("text", label))
        else:
            spans.append(("text", token))
        pos = match.end()

    if pos < len(text):
        spans.append(("text", text[pos:]))
    return spans or [("text", text)]


def _split_table_row(line: str) -> List[str]:
    stripped = line.strip()
    if stripped.startswith("|"):
        stripped = stripped[1:]
    if stripped.endswith("|"):
        stripped = stripped[:-1]
    return [cell.strip() for cell in stripped.split("|")]


def _is_special_line(line: str) -> bool:
    stripped = line.strip()
    return bool(
        not stripped
        or stripped.startswith("```")
        or _HEADING_PATTERN.match(stripped)
        or _BULLET_PATTERN.match(line)
        or _ORDERED_PATTERN.match(line)
        or stripped.startswith(">")
        or _HR_PATTERN.match(stripped)
        or "|" in stripped
    )


def _parse_markdown_blocks(content: str) -> List[Dict[str, Any]]:
    """Phân tích văn bản Markdown thành các block có cấu trúc dùng chung cho DOCX và PDF."""
    lines = (content or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    blocks: List[Dict[str, Any]] = []
    idx = 0
    total = len(lines)

    while idx < total:
        line = lines[idx]
        stripped = line.strip()

        if not stripped:
            idx += 1
            continue

        # 1. Code block (``` ... ```)
        if stripped.startswith("```"):
            lang = stripped[3:].strip()
            code_lines: List[str] = []
            idx += 1
            while idx < total and not lines[idx].strip().startswith("```"):
                code_lines.append(lines[idx])
                idx += 1
            if idx < total:
                idx += 1
            blocks.append({"type": "code_block", "language": lang, "code": "\n".join(code_lines)})
            continue

        # 2. Horizontal rule
        if _HR_PATTERN.match(stripped):
            blocks.append({"type": "hr"})
            idx += 1
            continue

        # 3. Heading
        h_match = _HEADING_PATTERN.match(stripped)
        if h_match:
            blocks.append(
                {
                    "type": "heading",
                    "level": len(h_match.group(1)),
                    "text": h_match.group(2).strip(),
                }
            )
            idx += 1
            continue

        # 4. GFM Markdown Table
        if "|" in stripped and idx + 1 < total and _TABLE_SEP_PATTERN.match(lines[idx + 1]):
            headers = _split_table_row(line)
            idx += 2
            rows: List[List[str]] = []
            col_count = max(len(headers), 1)
            while idx < total and "|" in lines[idx] and lines[idx].strip():
                row_cells = _split_table_row(lines[idx])
                if len(row_cells) < col_count:
                    row_cells.extend([""] * (col_count - len(row_cells)))
                rows.append(row_cells[:col_count])
                idx += 1
            blocks.append({"type": "table", "headers": headers[:col_count], "rows": rows})
            continue

        # 5. Blockquote (> ...)
        if stripped.startswith(">"):
            quote_lines: List[str] = []
            while idx < total and lines[idx].strip().startswith(">"):
                quote_lines.append(lines[idx].strip().lstrip(">").strip())
                idx += 1
            blocks.append({"type": "blockquote", "text": " ".join(q for q in quote_lines if q)})
            continue

        # 6. Bullet item (- / * / +)
        b_match = _BULLET_PATTERN.match(line)
        if b_match:
            level = min(len(b_match.group(1).replace("\t", "  ")) // 2, 2)
            blocks.append({"type": "bullet_item", "level": level, "text": b_match.group(2).strip()})
            idx += 1
            continue

        # 7. Ordered item (1. / 1))
        o_match = _ORDERED_PATTERN.match(line)
        if o_match:
            level = min(len(o_match.group(1).replace("\t", "  ")) // 2, 2)
            blocks.append(
                {
                    "type": "ordered_item",
                    "level": level,
                    "marker": o_match.group(2),
                    "text": o_match.group(3).strip(),
                }
            )
            idx += 1
            continue

        # 8. Paragraph (gom nhiều dòng liên tiếp không phải block đặc biệt)
        para_lines = [stripped]
        idx += 1
        while idx < total and not _is_special_line(lines[idx]):
            para_lines.append(lines[idx].strip())
            idx += 1
        blocks.append({"type": "paragraph", "text": " ".join(para_lines)})

    return blocks


def _has_leading_title_heading(blocks: List[Dict[str, Any]], title: str) -> bool:
    if not blocks or blocks[0].get("type") != "heading":
        return False
    first_heading = blocks[0].get("text", "").strip().lower()
    clean_title = (title or "").strip().lower()
    return bool(clean_title and first_heading == clean_title)


def _set_cell_shading(cell: Any, fill_hex: str) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill_hex)
    tc_pr.append(shd)


def _append_docx_inline_runs(paragraph: Any, text: str, base_color: Optional[RGBColor] = None) -> None:
    for style, chunk in _parse_inline_spans(text):
        run = paragraph.add_run(chunk)
        if style in ("bold", "bold_italic"):
            run.bold = True
        if style in ("italic", "bold_italic"):
            run.italic = True
        if style == "code":
            run.font.name = "Consolas"
            run.font.size = Pt(10)
            run.font.color.rgb = RGBColor(*TEAL_RGB)
        elif base_color is not None:
            run.font.color.rgb = base_color


def export_markdown_bytes(title: str, content: str) -> bytes:
    """Xuất nội dung dưới dạng Markdown UTF-8."""
    clean_body = (content or "").strip()
    clean_title = (title or "").strip()
    if clean_title and not clean_body.startswith(f"# {clean_title}"):
        full_text = f"# {clean_title}\n\n{clean_body}\n"
    else:
        full_text = f"{clean_body}\n"
    return full_text.encode("utf-8")


def export_docx_bytes(title: str, content: str) -> bytes:
    """Chuyển đổi nội dung Markdown sang tài liệu Word (.docx) có định dạng sạch đẹp."""
    doc = Document()

    for section in doc.sections:
        section.top_margin = Cm(2.0)
        section.bottom_margin = Cm(2.0)
        section.left_margin = Cm(2.2)
        section.right_margin = Cm(2.2)

    normal_style = doc.styles["Normal"]
    normal_style.font.name = "Arial"
    normal_style.font.size = Pt(11)
    normal_style.font.color.rgb = RGBColor(*INK_RGB)

    blocks = _parse_markdown_blocks(content)
    clean_title = (title or "").strip()
    if clean_title and not _has_leading_title_heading(blocks, clean_title):
        title_p = doc.add_paragraph()
        title_p.paragraph_format.space_before = Pt(0)
        title_p.paragraph_format.space_after = Pt(10)
        title_run = title_p.add_run(clean_title)
        title_run.bold = True
        title_run.font.name = "Arial"
        title_run.font.size = Pt(18)
        title_run.font.color.rgb = RGBColor(*TEAL_RGB)

    heading_sizes = {1: 16, 2: 14, 3: 12, 4: 11}

    for block in blocks:
        btype = block["type"]

        if btype == "heading":
            level = min(max(int(block["level"]), 1), 4)
            p = doc.add_paragraph()
            p.paragraph_format.space_before = Pt(10 if level <= 2 else 6)
            p.paragraph_format.space_after = Pt(4)
            p.paragraph_format.keep_with_next = True
            _append_docx_inline_runs(
                p,
                block["text"],
                base_color=RGBColor(*(TEAL_RGB if level <= 2 else INK_RGB)),
            )
            for run in p.runs:
                run.bold = True
                run.font.size = Pt(heading_sizes.get(level, 12))

        elif btype == "paragraph":
            p = doc.add_paragraph()
            p.paragraph_format.space_after = Pt(6)
            p.paragraph_format.line_spacing = 1.25
            _append_docx_inline_runs(p, block["text"])

        elif btype == "bullet_item":
            p = doc.add_paragraph(style="List Bullet")
            p.paragraph_format.left_indent = Cm(0.7 + block["level"] * 0.5)
            p.paragraph_format.space_after = Pt(3)
            p.paragraph_format.line_spacing = 1.2
            _append_docx_inline_runs(p, block["text"])

        elif btype == "ordered_item":
            p = doc.add_paragraph(style="List Number")
            p.paragraph_format.left_indent = Cm(0.7 + block["level"] * 0.5)
            p.paragraph_format.space_after = Pt(3)
            p.paragraph_format.line_spacing = 1.2
            _append_docx_inline_runs(p, block["text"])

        elif btype == "blockquote":
            p = doc.add_paragraph()
            p.paragraph_format.left_indent = Cm(0.8)
            p.paragraph_format.space_before = Pt(4)
            p.paragraph_format.space_after = Pt(6)
            _append_docx_inline_runs(p, block["text"], base_color=RGBColor(*MUTED_RGB))
            for run in p.runs:
                run.italic = True

        elif btype == "code_block":
            p = doc.add_paragraph()
            p.paragraph_format.left_indent = Cm(0.4)
            p.paragraph_format.space_before = Pt(4)
            p.paragraph_format.space_after = Pt(6)
            run = p.add_run(block["code"])
            run.font.name = "Consolas"
            run.font.size = Pt(9.5)
            run.font.color.rgb = RGBColor(*INK_RGB)

        elif btype == "hr":
            p = doc.add_paragraph()
            p.paragraph_format.space_before = Pt(4)
            p.paragraph_format.space_after = Pt(4)
            run = p.add_run("─" * 48)
            run.font.color.rgb = RGBColor(200, 214, 211)

        elif btype == "table":
            headers = block["headers"]
            rows = block["rows"]
            col_count = max(len(headers), 1)
            table = doc.add_table(rows=1 + len(rows), cols=col_count)
            table.style = "Table Grid"
            for c_idx, h_text in enumerate(headers):
                cell = table.rows[0].cells[c_idx]
                _set_cell_shading(cell, TEAL_SOFT_HEX)
                cell.text = ""
                p = cell.paragraphs[0]
                _append_docx_inline_runs(p, h_text, base_color=RGBColor(*INK_RGB))
                for run in p.runs:
                    run.bold = True
                    run.font.size = Pt(10)
            for r_idx, row_vals in enumerate(rows, start=1):
                for c_idx in range(col_count):
                    cell = table.rows[r_idx].cells[c_idx]
                    cell.text = ""
                    p = cell.paragraphs[0]
                    val = row_vals[c_idx] if c_idx < len(row_vals) else ""
                    _append_docx_inline_runs(p, val)
                    for run in p.runs:
                        run.font.size = Pt(10)

    buffer = io.BytesIO()
    doc.save(buffer)
    return buffer.getvalue()


def _find_first_existing(paths: List[Path]) -> Optional[Path]:
    for path in paths:
        if path.exists():
            return path
    return None


def _configure_pdf_fonts(pdf: FPDF) -> Tuple[str, str]:
    """
    Đăng ký bộ font Unicode hỗ trợ tiếng Việt đầy đủ (ưu tiên Arial trên Windows
    hoặc DejaVuSans đi kèm matplotlib/Linux) và optional fallback CJK nếu có.
    """
    font_dirs: List[Path] = []
    try:
        import matplotlib

        font_dirs.append(Path(matplotlib.get_data_path()) / "fonts" / "ttf")
    except Exception:
        pass

    win_dir = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
    if win_dir.exists():
        font_dirs.append(win_dir)
    font_dirs.extend(
        [
            Path("/usr/share/fonts/truetype/dejavu"),
            Path("/usr/share/fonts/dejavu"),
            Path("/usr/share/fonts/TTF"),
            Path("/Library/Fonts"),
        ]
    )

    regular = _find_first_existing(
        [d / name for d in font_dirs for name in ("DejaVuSans.ttf", "arial.ttf", "segoeui.ttf")]
    )
    if regular is None:
        raise RuntimeError("Không tìm thấy font Unicode (.ttf) để xuất PDF tiếng Việt.")

    parent = regular.parent
    if "DejaVuSans" in regular.name:
        bold = _find_first_existing([parent / "DejaVuSans-Bold.ttf"]) or regular
        italic = _find_first_existing([parent / "DejaVuSans-Oblique.ttf"]) or regular
        bold_italic = _find_first_existing([parent / "DejaVuSans-BoldOblique.ttf"]) or bold
        mono = _find_first_existing([parent / "DejaVuSansMono.ttf", parent / "cour.ttf"]) or regular
    elif regular.name.lower() == "arial.ttf":
        bold = _find_first_existing([parent / "arialbd.ttf"]) or regular
        italic = _find_first_existing([parent / "ariali.ttf"]) or regular
        bold_italic = _find_first_existing([parent / "arialbi.ttf"]) or bold
        mono = _find_first_existing([parent / "cour.ttf", parent / "consola.ttf"]) or regular
    else:
        bold = _find_first_existing([parent / "segoeuib.ttf"]) or regular
        italic = _find_first_existing([parent / "segoeuii.ttf"]) or regular
        bold_italic = _find_first_existing([parent / "segoeuiz.ttf"]) or bold
        mono = _find_first_existing([parent / "consola.ttf", parent / "cour.ttf"]) or regular

    sans_family = "AppSans"
    mono_family = "AppMono"
    pdf.add_font(sans_family, "", str(regular))
    pdf.add_font(sans_family, "B", str(bold))
    pdf.add_font(sans_family, "I", str(italic))
    pdf.add_font(sans_family, "BI", str(bold_italic))
    pdf.add_font(mono_family, "", str(mono))

    cjk_font = _find_first_existing(
        [
            win_dir / name
            for name in ("YuGothR.ttc", "meiryo.ttc", "msgothic.ttc", "msyh.ttc")
        ]
        if win_dir.exists()
        else []
    )
    if cjk_font is not None:
        try:
            pdf.add_font("AppCJK", "", str(cjk_font))
            pdf.set_fallback_fonts(["AppCJK"])
        except Exception:
            pass

    return sans_family, mono_family


class _StudyPDF(FPDF):
    def __init__(self, sans_family: str = "Helvetica") -> None:
        super().__init__(orientation="P", unit="mm", format="A4")
        self.sans_family = sans_family

    def footer(self) -> None:
        self.set_y(-14)
        self.set_font(self.sans_family, "I", 8.5)
        self.set_text_color(*MUTED_RGB)
        self.cell(0, 8, f"Trang {self.page_no()} / {{nb}}", align="R")


def _write_pdf_inline_spans(
    pdf: _StudyPDF,
    sans_family: str,
    mono_family: str,
    text: str,
    line_height: float,
    font_size: float,
    base_style: str = "",
    base_color: Tuple[int, int, int] = INK_RGB,
) -> None:
    sanitized = _strip_pdf_unsupported_glyphs(text)
    for style, chunk in _parse_inline_spans(sanitized):
        if not chunk:
            continue
        if style == "code":
            pdf.set_font(mono_family, "", max(font_size - 0.5, 8.5))
            pdf.set_text_color(*TEAL_RGB)
            pdf.write(line_height, chunk)
            continue

        resolved_style = base_style
        if style == "bold":
            resolved_style = "BI" if "I" in base_style else "B"
        elif style == "italic":
            resolved_style = "BI" if "B" in base_style else "I"
        elif style == "bold_italic":
            resolved_style = "BI"

        pdf.set_font(sans_family, resolved_style, font_size)
        pdf.set_text_color(*base_color)
        pdf.write(line_height, chunk)


def export_pdf_bytes(title: str, content: str) -> bytes:
    """Chuyển đổi nội dung Markdown sang file PDF (.pdf) chuẩn A4, hỗ trợ Unicode tiếng Việt."""
    pdf = _StudyPDF()
    sans_family, mono_family = _configure_pdf_fonts(pdf)
    pdf.sans_family = sans_family

    base_margin = 18.0
    pdf.set_margins(base_margin, 18.0, base_margin)
    pdf.set_auto_page_break(auto=True, margin=18.0)
    pdf.alias_nb_pages()
    pdf.add_page()

    blocks = _parse_markdown_blocks(content)
    clean_title = _strip_pdf_unsupported_glyphs((title or "").strip())
    if clean_title and not _has_leading_title_heading(blocks, title):
        pdf.set_font(sans_family, "B", 17)
        pdf.set_text_color(*TEAL_RGB)
        pdf.multi_cell(0, 8.5, clean_title)
        pdf.ln(1.5)
        y = pdf.get_y()
        pdf.set_draw_color(*TEAL_RGB)
        pdf.set_line_width(0.45)
        pdf.line(base_margin, y, pdf.w - base_margin, y)
        pdf.ln(5)

    heading_specs = {
        1: (15.0, 7.5, TEAL_RGB),
        2: (13.0, 6.8, TEAL_RGB),
        3: (11.5, 6.2, INK_RGB),
        4: (10.5, 5.8, INK_RGB),
    }

    for block in blocks:
        btype = block["type"]

        if btype == "heading":
            level = min(max(int(block["level"]), 1), 4)
            font_size, line_h, color = heading_specs[level]
            if pdf.get_y() > pdf.h - 32:
                pdf.add_page()
            pdf.ln(2.5)
            pdf.set_left_margin(base_margin)
            pdf.set_x(base_margin)
            _write_pdf_inline_spans(
                pdf,
                sans_family,
                mono_family,
                block["text"],
                line_height=line_h,
                font_size=font_size,
                base_style="B",
                base_color=color,
            )
            pdf.ln(line_h + 1.5)

        elif btype == "paragraph":
            pdf.set_left_margin(base_margin)
            pdf.set_x(base_margin)
            _write_pdf_inline_spans(
                pdf,
                sans_family,
                mono_family,
                block["text"],
                line_height=6.0,
                font_size=10.5,
            )
            pdf.ln(7.5)

        elif btype in ("bullet_item", "ordered_item"):
            indent = base_margin + block["level"] * 5.0
            marker = "•" if btype == "bullet_item" else block["marker"]
            marker_width = 5.5 if btype == "bullet_item" else max(7.0, len(marker) * 2.4 + 2.0)

            pdf.set_left_margin(base_margin)
            pdf.set_x(indent)
            pdf.set_font(sans_family, "B", 10.5)
            pdf.set_text_color(*TEAL_RGB)
            pdf.cell(marker_width, 5.8, marker)

            pdf.set_left_margin(indent + marker_width)
            _write_pdf_inline_spans(
                pdf,
                sans_family,
                mono_family,
                block["text"],
                line_height=5.8,
                font_size=10.5,
            )
            pdf.ln(6.8)
            pdf.set_left_margin(base_margin)

        elif btype == "blockquote":
            if pdf.get_y() > pdf.h - 28:
                pdf.add_page()
            start_page = pdf.page
            start_y = pdf.get_y()
            pdf.set_left_margin(base_margin + 5.0)
            pdf.set_x(base_margin + 5.0)
            _write_pdf_inline_spans(
                pdf,
                sans_family,
                mono_family,
                block["text"],
                line_height=5.8,
                font_size=10.0,
                base_style="I",
                base_color=MUTED_RGB,
            )
            pdf.ln(7.0)
            end_y = pdf.get_y() - 1.5
            pdf.set_left_margin(base_margin)
            if pdf.page == start_page and end_y > start_y:
                pdf.set_draw_color(*TEAL_RGB)
                pdf.set_line_width(0.8)
                pdf.line(base_margin + 1.5, start_y, base_margin + 1.5, end_y)
                pdf.set_line_width(0.2)

        elif btype == "code_block":
            code_text = _strip_pdf_unsupported_glyphs(block["code"])
            pdf.set_left_margin(base_margin + 3.0)
            pdf.set_x(base_margin + 3.0)
            pdf.set_fill_color(*CODE_BG_RGB)
            pdf.set_font(mono_family, "", 9.0)
            pdf.set_text_color(*INK_RGB)
            pdf.multi_cell(pdf.w - 2 * base_margin - 6.0, 5.0, code_text, fill=True)
            pdf.set_left_margin(base_margin)
            pdf.ln(3.5)

        elif btype == "hr":
            pdf.ln(2.0)
            y = pdf.get_y()
            pdf.set_draw_color(210, 222, 219)
            pdf.line(base_margin, y, pdf.w - base_margin, y)
            pdf.ln(4.0)

        elif btype == "table":
            def _clean_cell(raw_cell: str) -> str:
                plain = "".join(chunk for _, chunk in _parse_inline_spans(raw_cell))
                return _strip_pdf_unsupported_glyphs(plain)

            headers = [_clean_cell(h) for h in block["headers"]]
            rows = [[_clean_cell(c) for c in row] for row in block["rows"]]
            pdf.set_left_margin(base_margin)
            pdf.set_x(base_margin)
            pdf.set_font(sans_family, "", 9.5)
            pdf.set_text_color(*INK_RGB)
            pdf.set_draw_color(210, 222, 219)
            headings_style = FontFace(
                emphasis="BOLD",
                color=INK_RGB,
                fill_color=(230, 243, 241),
            )
            with pdf.table(
                first_row_as_headings=True,
                headings_style=headings_style,
                line_height=5.5,
                padding=2.0,
                text_align="LEFT",
            ) as table:
                header_row = table.row()
                for cell_text in headers:
                    header_row.cell(cell_text)
                for row_vals in rows:
                    r = table.row()
                    for cell_text in row_vals:
                        r.cell(cell_text)
            pdf.ln(4.0)

    return bytes(pdf.output())


def build_export_payload(title: str, content: str, fmt: str) -> Tuple[bytes, str, str, str]:
    """Sinh dữ liệu file theo định dạng yêu cầu và trả về (bytes, media_type, ascii_name, utf8_name)."""
    normalized = (fmt or "md").strip().lower()
    if normalized == "md":
        ascii_name, utf8_name = _safe_filenames(title, "md")
        return export_markdown_bytes(title, content), "text/markdown; charset=utf-8", ascii_name, utf8_name
    if normalized == "docx":
        ascii_name, utf8_name = _safe_filenames(title, "docx")
        return (
            export_docx_bytes(title, content),
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ascii_name,
            utf8_name,
        )
    if normalized == "pdf":
        ascii_name, utf8_name = _safe_filenames(title, "pdf")
        return export_pdf_bytes(title, content), "application/pdf", ascii_name, utf8_name
    raise ValueError(f"Định dạng xuất không hỗ trợ: {fmt}")


def build_content_disposition(ascii_name: str, utf8_name: str) -> str:
    return f'attachment; filename="{ascii_name}"; filename*=UTF-8\'\'{quote(utf8_name)}'
