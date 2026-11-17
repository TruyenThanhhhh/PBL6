"""Unit & API integration tests for Markdown, DOCX, and PDF study document export."""
import io
import sys
import unittest
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from docx import Document  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from pypdf import PdfReader  # noqa: E402

from app.main import app  # noqa: E402

SAMPLE_MARKDOWN = """# 📌 Tổng Quan Cốt Lõi

Đề thi **JLPT N3** gồm các phần *Từ vựng*, `Ngữ pháp`, Đọc hiểu và Nghe hiểu.

## 🔑 Các Khái Niệm Then Chốt

- Phần 1: Kiến thức ngôn ngữ (文字・語彙)
- Phần 2: Đọc hiểu & Ngữ pháp — luyện tập thường xuyên [1]

1. Ôn tập theo lộ trình từng tuần
2. Làm đề thi thử định kỳ

> Ghi chú quan trọng: Đọc kỹ câu hỏi trước khi chọn đáp án.

| Kỹ năng | Thời lượng | Ghi chú |
| --- | --- | --- |
| Từ vựng | 30 phút | Ôn Kanji cơ bản |
| Đọc hiểu | 70 phút | Luyện tốc độ |

```python
score = sum([50, 55, 60])
```
"""


class ExportServiceTestCase(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_export_markdown(self):
        resp = self.client.post(
            "/api/v1/study/export",
            json={
                "title": "Tóm tắt AI · Đề thi JLPT N3",
                "content": SAMPLE_MARKDOWN,
                "format": "md",
            },
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertIn("text/markdown", resp.headers["content-type"])
        self.assertIn('filename="Tom_tat_AI_De_thi_JLPT_N3.md"', resp.headers["content-disposition"])
        text = resp.content.decode("utf-8")
        self.assertIn("# Tóm tắt AI · Đề thi JLPT N3", text)
        self.assertIn("Đề thi **JLPT N3**", text)

    def test_export_docx_valid_structure_and_vietnamese(self):
        resp = self.client.post(
            "/api/v1/study/export",
            json={
                "title": "Tóm tắt Đề thi JLPT N3",
                "content": SAMPLE_MARKDOWN,
                "format": "docx",
            },
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertIn(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            resp.headers["content-type"],
        )
        self.assertIn('filename="Tom_tat_De_thi_JLPT_N3.docx"', resp.headers["content-disposition"])

        doc = Document(io.BytesIO(resp.content))
        para_text = "\n".join(p.text for p in doc.paragraphs)
        self.assertIn("Tóm tắt Đề thi JLPT N3", para_text)
        self.assertIn("Tổng Quan Cốt Lõi", para_text)
        self.assertIn("JLPT N3", para_text)
        self.assertIn("score = sum([50, 55, 60])", para_text)
        self.assertEqual(len(doc.tables), 1)
        self.assertEqual(doc.tables[0].rows[0].cells[0].text, "Kỹ năng")
        self.assertEqual(doc.tables[0].rows[1].cells[2].text, "Ôn Kanji cơ bản")

    def test_export_pdf_valid_unicode_and_tables(self):
        resp = self.client.post(
            "/api/v1/study/export",
            json={
                "title": "Báo cáo tổng hợp tiếng Việt",
                "content": SAMPLE_MARKDOWN,
                "format": "pdf",
            },
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(resp.headers["content-type"], "application/pdf")
        self.assertTrue(resp.content.startswith(b"%PDF-"))

        reader = PdfReader(io.BytesIO(resp.content))
        self.assertGreaterEqual(len(reader.pages), 1)
        extracted = "\n".join((page.extract_text() or "") for page in reader.pages)
        self.assertIn("JLPT N3", extracted)
        self.assertIn("Từ vựng", extracted)
        self.assertIn("Đọc hiểu", extracted)
        self.assertIn("Ôn Kanji cơ bản", extracted)
        self.assertNotIn("📌", extracted)

    def test_export_rejects_empty_content_and_unsupported_format(self):
        empty_resp = self.client.post(
            "/api/v1/study/export",
            json={"title": "Empty", "content": "   ", "format": "pdf"},
        )
        self.assertEqual(empty_resp.status_code, 400)

        bad_fmt = self.client.post(
            "/api/v1/study/export",
            json={"title": "Bad", "content": "Hello", "format": "exe"},
        )
        self.assertEqual(bad_fmt.status_code, 422)


if __name__ == "__main__":
    unittest.main()
