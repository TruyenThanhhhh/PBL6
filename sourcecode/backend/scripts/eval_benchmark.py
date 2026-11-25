"""Automated 20-case AI Evaluation Benchmark CLI for Personal AI Knowledge Platform (PBL6).

Usage:
    cd sourcecode/backend
    python scripts/eval_benchmark.py [--model auto]
"""
import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_ROOT))

from app.services import ai_router, intent_service  # noqa: E402

DEFAULT_WS_ID = "a7c59340-db90-4c34-8fd5-6b6fe6ecd5ff"
DOC_HDT = "a53832cb-8f3a-4256-96f8-b0158a811d3c"
DOC_N3 = "a990cd7f-489f-4d69-9157-c1c0f9ba802f"
DOC_TOAN9 = "e5b5987b-334a-49d3-9c26-f685a9c38679"


def _has_any(text: str, needles: list[str]) -> bool:
    low = (text or "").lower()
    return any(n.lower() in low for n in needles)


def _has_all(text: str, needles: list[str]) -> bool:
    low = (text or "").lower()
    return all(n.lower() in low for n in needles)


INTENT_CASES = [
    ("I1_QUIZ", "Tạo cho tôi 5 câu hỏi trắc nghiệm về hằng đẳng thức đáng nhớ", "create_quiz"),
    ("I2_INFO_GUARD", "Bài kiểm tra trắc nghiệm trong tài liệu nói về nội dung gì?", "rag_qa"),
    ("I3_EXPORT_PREV", "Xuất câu trả lời vừa rồi ra file PDF giúp tôi", "export_previous"),
    ("I4_FLASHCARDS", "Làm flashcard ôn 10 từ vựng Bài 1 Mimikara N3", "create_flashcards"),
    ("I5_MATH_QA", "Giải phương trình bậc 2 x^2 - 5x + 6 = 0", "deep_reasoning"),
    ("I6_COMPOSE_DOCX", "Viết bảng tổng hợp công thức Toán 9 ra file Word docx", "compose_document"),
]

RAG_CASES = [
    {
        "id": "Q1_HDT7",
        "query": "hằng đẳng thức số 7 là gì",
        "sdoc": DOC_HDT,
        "dlist": None,
        "history": [],
        "check": lambda ans, cits: _has_any(ans, ["a³ - b³", "a^3 - b^3"]) and _has_any(ans, ["(a - b)", "(a-b)"]),
    },
    {
        "id": "Q2_CH9",
        "query": "Nội dung chương 9: Hai đường thẳng cắt nhau thỏa mãn điều kiện K",
        "sdoc": DOC_TOAN9,
        "dlist": None,
        "history": [],
        "check": lambda ans, cits: _has_any(ans, ["điều kiện k", "giao điểm", "bước 1"]) and "không chứa thông tin" not in ans.lower(),
    },
    {
        "id": "Q3_CJK",
        "query": "後半 là gì",
        "sdoc": DOC_N3,
        "dlist": None,
        "history": [],
        "check": lambda ans, cits: "こうはん" in ans and "phần cuối" in ans.lower() and not _has_any(ans, ["是指", "对应的", "在提供"]),
    },
    {
        "id": "Q4_N3_BAI3",
        "query": "Liệt kê 5 từ đầu tiên của Bài 3 kèm phiên âm và nghĩa",
        "sdoc": DOC_N3,
        "dlist": None,
        "history": [],
        "check": lambda ans, cits: _has_all(ans, ["飾り", "遊び", "集まり", "教え", "踊り"]) and "12 bài học" not in ans.lower(),
    },
    {
        "id": "Q5_OOS_FERMAT",
        "query": "Trong tài liệu Toán 9 có chứng minh định lý Fermat lớn không?",
        "sdoc": DOC_TOAN9,
        "dlist": None,
        "history": [],
        "check": lambda ans, cits: _has_any(ans, ["không chứa", "không có", "không đề cập", "không tìm thấy"]),
    },
    {
        "id": "Q6_TRICK_INTEGRAL",
        "query": "Tài liệu Hằng đẳng thức đáng nhớ có dạy về tích phân và đạo hàm không?",
        "sdoc": DOC_HDT,
        "dlist": None,
        "history": [],
        "check": lambda ans, cits: _has_any(ans, ["không dạy", "không chứa", "không đề cập", "không có"]),
    },
    {
        "id": "Q7A_ISOLATION",
        "query": "後半 là gì",
        "sdoc": None,
        "dlist": None,
        "history": [
            {"role": "user", "content": "nội dung chương 9"},
            {"role": "assistant", "content": "Chương 9 nói về hai đường thẳng cắt nhau thỏa mãn điều kiện K."},
        ],
        "check": lambda ans, cits: "こうはん" in ans and "phần cuối" in ans.lower() and "chương 9" not in ans.lower(),
    },
    {
        "id": "Q7B_FOLLOWUP",
        "query": "Giải thích rõ hơn bước 3 của chương này",
        "sdoc": DOC_TOAN9,
        "dlist": None,
        "history": [
            {"role": "user", "content": "nội dung chương 9"},
            {"role": "assistant", "content": "Chương 9: Hai đường thẳng cắt nhau thỏa mãn điều kiện K gồm 3 bước giải."},
        ],
        "check": lambda ans, cits: _has_any(ans, ["điều kiện k", "thay", "tìm m", "đối chiếu"]),
    },
    {
        "id": "Q8_MULTI_DOC_3TICKED",
        "query": "Trong kho tài liệu hiện tại có những tài liệu nào và mỗi tài liệu nói về chủ đề chính gì?",
        "sdoc": None,
        "dlist": [DOC_HDT, DOC_N3, DOC_TOAN9],
        "history": [],
        "check": lambda ans, cits: (
            all(c.get("source_type") != "web" for c in cits)
            and _has_any(ans, ["hằng đẳng thức", "hang-dang-thuc"])
            and _has_any(ans, ["mimikara", "từ vựng"])
            and _has_any(ans, ["toán 9", "toan 9"])
        ),
    },
]

REASONING_CASES = [
    {
        "id": "R1_FRUSTUM_DEEP",
        "query": "Cho hình nón cụt có bán kính 2 đáy lần lượt là 15cm và 10cm, chiều cao 24cm. Tính đường sinh, diện tích xung quanh, diện tích toàn phần và thể tích của hình nón cụt đó.",
        "doc": DOC_TOAN9,
        "check": lambda ans: _has_any(ans, ["24,5", "24.5"]) and _has_any(ans, ["1.925", "1925"]) and _has_any(ans, ["2.946", "2946"]) and _has_any(ans, ["11.938", "11938"]),
    },
    {
        "id": "R2_ALGEBRA_GENERAL",
        "query": "Cho x - y = 5 và xy = 6. Áp dụng hằng đẳng thức đáng nhớ trong tài liệu, hãy tính giá trị biểu thức B = x³ - y³ + (x - y)²",
        "doc": DOC_HDT,
        "check": lambda ans: "240" in ans and "226" not in ans,
    },
    {
        "id": "R3_CYLINDER_DEEP",
        "query": "Một hình trụ có bán kính đáy R = 7cm và chiều cao h = 10cm. Dựa vào công thức trong tài liệu Toán 9, tính chu vi đáy, diện tích xung quanh và thể tích hình trụ đó.",
        "doc": DOC_TOAN9,
        "check": lambda ans: _has_any(ans, ["43,98", "43.98"]) and _has_any(ans, ["439,82", "439.82"]) and _has_any(ans, ["1.539,38", "1539.38", "1539,38"]),
    },
    {
        "id": "R4_COMPARE_SOLIDS",
        "query": "So sánh thể tích hình nón cụt (R=15cm, r=10cm, h=24cm) với hình trụ có bán kính đáy 12cm và chiều cao 24cm. Hình nào có thể tích lớn hơn và lớn hơn bao nhiêu phần trăm?",
        "doc": DOC_TOAN9,
        "check": lambda ans: _has_any(ans, ["11.938", "11938"]) and _has_any(ans, ["10.857", "10857"]) and _has_any(ans, ["9,95", "9.95"]),
    },
    {
        "id": "R5_EXCEL_COUNT_COMPARE",
        "query": "Trong file từ vựng Mimikara N3, Bài 1 và Bài 2 bài nào có nhiều từ vựng hơn và chênh lệch bao nhiêu từ?",
        "doc": DOC_N3,
        "check": lambda ans: "120" in ans and "100" in ans and "20" in ans and "760" not in ans,
    },
]


async def run_benchmark(model_id: str, workspace_id: str) -> dict:
    report = {"model": model_id, "intents": [], "rag": [], "reasoning": []}

    print(f"=== 1. INTENT CLASSIFICATION (6 CASES) ===", flush=True)
    for cid, q, exp in INTENT_CASES:
        got = intent_service.classify_chat_intent(q).kind
        ok = got == exp
        report["intents"].append({"id": cid, "ok": ok, "expected": exp, "got": got})
        print(f"  [{'PASS' if ok else 'FAIL'}] {cid}: exp={exp} got={got}", flush=True)

    print(f"\n=== 2. AI TRUY VẤN RAG (9 CASES · model={model_id}) ===", flush=True)
    for c in RAG_CASES:
        t0 = time.perf_counter()
        res = await ai_router.answer_query(
            workspace_id=workspace_id,
            query=c["query"],
            model=model_id,
            history=c["history"],
            selected_document_id=c["sdoc"],
            document_ids=c["dlist"],
            mode="local_only",
            reasoning_mode="auto",
        )
        dt = round(time.perf_counter() - t0, 2)
        ans = (res.get("answer") or "").split("---GỢI Ý TIẾP THEO---")[0].strip()
        cits = res.get("citations") or []
        ok = bool(c["check"](ans, cits))
        report["rag"].append({"id": c["id"], "ok": ok, "elapsed": dt, "model": res.get("model_used"), "cits": len(cits)})
        print(f"  [{'PASS' if ok else 'FAIL'}] {c['id']} ({dt}s | {res.get('model_used')} | cits={len(cits)})", flush=True)

    print(f"\n=== 3. AI SUY LUẬN & PYTHON SANDBOX (5 CASES · model={model_id}) ===", flush=True)
    for c in REASONING_CASES:
        t0 = time.perf_counter()
        tokens, done_p, meta = [], {}, {}
        async for raw in ai_router.stream_query(
            workspace_id=workspace_id,
            query=c["query"],
            model=model_id,
            history=[],
            selected_document_id=c["doc"],
            mode="local_only",
            reasoning_mode="deep",
        ):
            if not raw.startswith("data: "):
                continue
            try:
                ev = json.loads(raw[6:].strip())
            except Exception:
                continue
            if "delta" in ev:
                tokens.append(ev["delta"])
            if "model_used" in ev or "citations" in ev:
                meta.update(ev)
            if ev.get("done"):
                done_p = ev
        dt = round(time.perf_counter() - t0, 2)
        ans = (done_p.get("answer") or "".join(tokens)).split("---GỢI Ý TIẾP THEO---")[0].strip()
        ok = bool(c["check"](ans))
        report["reasoning"].append({"id": c["id"], "ok": ok, "elapsed": dt, "model": meta.get("model_used"), "cits": len(meta.get("citations") or [])})
        print(f"  [{'PASS' if ok else 'FAIL'}] {c['id']} ({dt}s | {meta.get('model_used')} | cits={len(meta.get('citations') or [])})", flush=True)

    ip = sum(x["ok"] for x in report["intents"])
    rp = sum(x["ok"] for x in report["rag"])
    sp = sum(x["ok"] for x in report["reasoning"])
    tot = ip + rp + sp
    avg_rag = round(sum(x["elapsed"] for x in report["rag"]) / len(report["rag"]), 2)
    avg_reas = round(sum(x["elapsed"] for x in report["reasoning"]) / len(report["reasoning"]), 2)
    print(f"\n=== SUMMARY: TOTAL {tot}/20 ({tot/20*100:.1f}%) | Intent {ip}/6 | RAG {rp}/9 (avg {avg_rag}s) | Reasoning {sp}/5 (avg {avg_reas}s) ===", flush=True)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run 20-case automated AI evaluation benchmark.")
    parser.add_argument("--model", default="auto", help="Model ID (auto, qwen2.5:3b, gemma3:4b, qwen2.5:7b)")
    parser.add_argument("--workspace", default=DEFAULT_WS_ID, help="Workspace ID")
    args = parser.parse_args()
    asyncio.run(run_benchmark(args.model, args.workspace))
