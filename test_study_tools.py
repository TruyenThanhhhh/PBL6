"""
Kiểm thử Bộ công cụ học tập AI (6 công cụ):
- Tóm tắt (Summary)
- Ghi chú học tập (Notes)
- Quiz trắc nghiệm
- Flashcards
- Sơ đồ tư duy (Mindmap)
- Lộ trình học tập (Study Plan)
"""
import asyncio
import os
import sys
from datetime import date

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.abspath("sourcecode/backend"))

from app.database import get_db_connection
from app.services.study_service import (
    generate_ai_summary,
    generate_ai_quiz,
    generate_ai_flashcards,
    generate_ai_mindmap,
    generate_ai_notes,
    generate_ai_plan,
)


async def test_study_tools() -> None:
    print("=== BẮT ĐẦU KIỂM THỬ BỘ CÔNG CỤ HỌC TẬP AI ===")
    conn = get_db_connection()
    doc = conn.execute("SELECT workspace_id, id, file_name FROM documents LIMIT 1").fetchone()
    conn.close()

    if not doc:
        print("Không có tài liệu nào trong DB để kiểm thử.")
        return

    ws_id = doc["workspace_id"]
    doc_id = doc["id"]
    print(f"Sử dụng tài liệu: {doc['file_name']} (id={doc_id})")

    # 1. Summary
    print("\n--- 1. Kiểm thử Sinh Tóm tắt AI ---")
    summary = await generate_ai_summary(ws_id, doc_id)
    print(f"Title: {summary['title']}")
    print(f"Is Mock: {summary['is_mock']}")
    print("Trích đoạn nội dung:\n" + summary["markdown"][:300] + "...\n")
    assert not summary["is_mock"], "Phải sinh bằng AI thật khi Ollama đang chạy"
    assert len(summary["markdown"]) > 50

    # 2. Notes
    print("\n--- 2. Kiểm thử Sinh Ghi chú AI ---")
    notes = await generate_ai_notes(ws_id, doc_id)
    print(f"Title: {notes['title']}")
    print(f"Is Mock: {notes['is_mock']}")
    print("Trích đoạn ghi chú:\n" + notes["markdown"][:300] + "...\n")
    assert not notes["is_mock"], "Ghi chú phải sinh bằng AI thật"
    assert len(notes["markdown"]) > 50

    # 3. Quiz
    print("\n--- 3. Kiểm thử Sinh Quiz trắc nghiệm AI ---")
    quiz = await generate_ai_quiz(ws_id, doc_id, difficulty="medium", question_count=3)
    print(f"Title: {quiz.get('title')}")
    print(f"Số câu hỏi: {len(quiz.get('questions', []))}")
    for i, q in enumerate(quiz.get("questions", [])):
        print(f"  Câu {i + 1}: {q['prompt']}")
        for opt_idx, opt in enumerate(q["options"]):
            prefix = "[*]" if opt_idx == q["answerIndex"] else "[ ]"
            print(f"    {prefix} {opt}")
        print(f"    Giải thích: {q['explanation']}\n")
    assert not quiz.get("is_mock"), "Quiz phải sinh bằng AI thật"
    assert len(quiz.get("questions", [])) > 0, "Quiz phải có ít nhất 1 câu hỏi"

    # 4. Flashcards
    print("\n--- 4. Kiểm thử Sinh Flashcards AI ---")
    cards = await generate_ai_flashcards(ws_id, doc_id, count=4)
    print(f"Số thẻ Flashcards: {len(cards.get('flashcards', []))}")
    for i, c in enumerate(cards.get("flashcards", [])):
        print(f"  Thẻ {i + 1}: Mặt trước: {c['front']} | Mặt sau: {c['back']}")
    assert not cards.get("is_mock"), "Flashcards phải sinh bằng AI thật"
    assert len(cards.get("flashcards", [])) > 0, "Phải có ít nhất 1 thẻ Flashcard"

    # 5. Mindmap
    print("\n--- 5. Kiểm thử Sinh Mindmap AI ---")
    mindmap = await generate_ai_mindmap(ws_id, doc_id, max_depth=3)
    print(f"Is Mock: {mindmap['is_mock']}")
    root = mindmap.get("root")
    assert not mindmap.get("is_mock"), "Mindmap phải sinh bằng AI thật"
    assert root and root.get("label"), "Mindmap phải có node gốc"
    print(f"Nhánh gốc: {root['label']}")
    for child in (root.get("children") or [])[:6]:
        print(f"  - {child['label']} ({len(child.get('children') or [])} nhánh con)")

    # 6. Study Plan
    print("\n--- 6. Kiểm thử Sinh Lộ trình học tập AI ---")
    plan = await generate_ai_plan(ws_id, doc_id, start_date=date.today().isoformat(), day_span=7)
    print(f"Is Mock: {plan['is_mock']}")
    assert not plan.get("is_mock"), "Lộ trình phải sinh bằng AI thật"
    assert len(plan.get("tasks", [])) > 0, "Lộ trình phải có ít nhất 1 nhiệm vụ"
    for i, task in enumerate(plan.get("tasks", [])):
        print(f"  {i + 1}. [{task['due_date']}] {task['title']}")

    print("\n=== TẤT CẢ 6 CÔNG CỤ HỌC TẬP AI ĐỀU CHẠY THỰC TẾ THÀNH CÔNG! ===")


if __name__ == "__main__":
    asyncio.run(test_study_tools())
