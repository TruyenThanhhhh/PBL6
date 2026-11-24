"""Tests for CJK/single-char exact lookup, positional queries, and RAG prompt token budgeting."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import app.database as db_mod  # noqa: E402
import app.services.document_service as doc_mod  # noqa: E402
from app.services.ai_router import _build_retrieval_query  # noqa: E402
from app.services.llm_service import (  # noqa: E402
    _build_bounded_history_messages,
    _prepare_rag_prompts_and_citations,
)
from app.services.retrieval_service import (  # noqa: E402
    detect_positional_intent,
    search_positional_chunks,
    search_relevant_chunks,
)


def _dummy_embed(texts):
    return [[0.1, 0.2, 0.3] for _ in texts]


class RetrievalCJKAndBudgetTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        tmp_path = Path(self.tmp_dir.name)
        self.orig_db_path = db_mod.DATABASE_PATH
        self.orig_data_dir = db_mod.DATA_DIR
        self.orig_db_upload = db_mod.UPLOAD_DIR
        self.orig_doc_upload = doc_mod.UPLOAD_DIR

        db_mod.DATA_DIR = tmp_path / "data"
        db_mod.UPLOAD_DIR = db_mod.DATA_DIR / "uploads"
        db_mod.DATABASE_PATH = db_mod.DATA_DIR / "test_retrieval.db"
        doc_mod.UPLOAD_DIR = db_mod.UPLOAD_DIR
        db_mod.init_db()

    def tearDown(self):
        db_mod.DATABASE_PATH = self.orig_db_path
        db_mod.DATA_DIR = self.orig_data_dir
        db_mod.UPLOAD_DIR = self.orig_db_upload
        doc_mod.UPLOAD_DIR = self.orig_doc_upload
        self.tmp_dir.cleanup()

    @patch("app.services.retrieval_service.rerank_documents", side_effect=lambda q, docs, top_k, **kw: docs[:top_k])
    @patch("app.services.retrieval_service.embed_texts", side_effect=_dummy_embed)
    @patch("app.services.document_service.embed_texts", side_effect=_dummy_embed)
    def test_single_kanji_and_compound_lookup_pinned_first(self, _m_doc, _m_ret, _m_rerank):
        # Giả lập file Excel từ vựng tiếng Nhật nhiều dòng, trong đó có 夢 (giấc mơ) và 夢中な (chú tâm)
        lines = [
            "1 | 先輩 | せんぱい | tiền bối | 66 | 希望 | きぼう | hi vọng",
            "2 | 資格 | しかく | bằng cấp | 127 | 倒れる | たおれる | đổ",
            "4 | 年上 | としうえ | hơn tuổi | 263 | 夢中な | むちゅうな | chú tâm",
            "7 | 後輩 | こうはい | hậu bối | 67 | 夢 | ゆめ | giấc mơ",
        ]
        # Tạo thêm nhiều nội dung khác để tách thành nhiều chunk
        filler = "\n".join(f"{100+i} | 言葉{i} | ことば{i} | từ vựng {i}" for i in range(60))
        content = (filler + "\n" + lines[2] + "\n" + ("999 | 別々 | べつべつ | riêng biệt\n" * 40) + lines[3]).encode("utf-8")

        doc = doc_mod.process_and_index_document("default", "mimikara.txt", content)
        res = search_relevant_chunks("default", "夢", top_k=5, document_ids=[doc["document_id"]])
        self.assertTrue(res)
        # Chunk chứa từ đứng độc lập '67 | 夢 | ゆめ | giấc mơ' phải đứng đầu [Tài liệu 1]
        self.assertIn("67 | 夢 | ゆめ | giấc mơ", res[0]["content"])
        # Không kéo các chunk rác không chứa '夢' vào kết quả tra cứu từ đơn lẻ
        for r in res:
            self.assertIn("夢", r["content"])

    @patch("app.services.document_service.embed_texts", side_effect=_dummy_embed)
    def test_positional_intent_and_starting_letter_lookup(self, _m_doc):
        # Trang bìa + trang từ vựng chữ A + các từ chữ P ở phía sau
        text = (
            "GIÁO TRÌNH 3000 TỪ TIẾNG ANH\nHotline: 0934489666\n\n"
            "abandon v. từ bỏ\nable adj. có khả năng\nabout prep. về\n"
            + ("word filler text line for spacing\n" * 80)
            + "photographer n. thợ chụp ảnh\npride n. niềm tự hào\n"
        ).encode("utf-8")
        doc = doc_mod.process_and_index_document("default", "3000_en.txt", text)

        pos = detect_positional_intent("liệt kê 10 từ vựng đầu tiên bắt đầu bằng chữ a")
        self.assertEqual(pos, ("start", "a"))

        chunks = search_positional_chunks(
            "default", position=pos[0], letter_filter=pos[1], max_chunks=3, document_ids=[doc["document_id"]]
        )
        self.assertTrue(chunks)
        self.assertIn("abandon", chunks[0]["content"])

    def test_retrieval_query_does_not_pollute_standalone_lookup(self):
        hist = [
            {"role": "user", "content": "lấy 10 từ vựng đầu tiên làm thành câu trắc nghiệm"},
            {"role": "user", "content": "nghĩa của từ ゆめ"},
        ]
        self.assertEqual(_build_retrieval_query("夢", hist), "夢")
        self.assertEqual(
            _build_retrieval_query("chi tiết hơn về nó", hist),
            "nghĩa của từ ゆめ chi tiết hơn về nó",
        )

    def test_prompt_token_budget_never_drops_first_document(self):
        long_history = [
            {"role": "user", "content": "Hỏi dài " * 80},
            {"role": "assistant", "content": "Đáp dài " * 400 + "\n---GỢI Ý TIẾP THEO---\n- 1\n- 2\n- 3"},
        ] * 4
        bounded_hist = _build_bounded_history_messages(long_history)
        self.assertLessEqual(len(bounded_hist), 4)
        for m in bounded_hist:
            self.assertNotIn("---GỢI Ý TIẾP THEO---", m["content"])

        chunks = [
            {
                "document_id": "d1",
                "document_name": "mimikara.xlsx",
                "page_number": 1,
                "chunk_index": i,
                "content": ("67 | 夢 | ゆめ | giấc mơ | " * 25) if i == 0 else ("別の単語 | từ khác | " * 55),
            }
            for i in range(6)
        ]
        _sys, user_prompt, citations = _prepare_rag_prompts_and_citations("夢", chunks)
        self.assertIn("[Tài liệu 1]: mimikara.xlsx", user_prompt)
        self.assertIn("67 | 夢 | ゆめ | giấc mơ", user_prompt)
        # Chỉ đưa đúng số tài liệu vừa ngân sách token (citations khớp 1-1 với prompt)
        self.assertLess(len(citations), 6)


if __name__ == "__main__":
    unittest.main()
