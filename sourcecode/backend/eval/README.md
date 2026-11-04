# Ragas RAG benchmark

Thư mục này đo chất lượng pipeline Hybrid RAG bằng bộ câu hỏi vàng và Ragas.

## Cài đặt

```powershell
cd D:\PBl6\sourcecode\backend
pip install -r requirements-eval.txt
```

Ragas được pin ở `0.2.15` vì bản `0.4.x` kéo `scikit-network` không có wheel cho Python 3.14 trên Windows.

## Chạy benchmark mẫu

```powershell
cd D:\PBl6\sourcecode\backend
python eval/prepare_eval_workspace.py
python eval/ragas_eval.py --workspace ragas-eval --limit 3
```

`prepare_eval_workspace.py` tạo workspace riêng `ragas-eval` và index file mẫu `eval/fixtures/pbl6_rag_notes.md`.
Chạy lại lệnh này sẽ thay thế tài liệu mẫu cũ, không tạo trùng.

Muốn chấm toàn bộ 10 câu:

```powershell
python eval/ragas_eval.py --workspace ragas-eval
```

Kết quả nằm trong `eval/results/`:

- `predictions-*.jsonl`: câu hỏi, câu trả lời, context, chunk id, điểm rerank.
- `ragas-*.csv`: điểm từng câu.
- `ragas-*.summary.json`: điểm trung bình.

## Chấm trên tài liệu thật

1. Tạo file JSONL theo mẫu `golden.sample.jsonl`:

```json
{"id":"q1","question":"...","reference":"Câu trả lời đúng/ngắn gọn"}
```

2. Tải tài liệu của bạn vào workspace trên UI, hoặc dùng id workspace hiện có.
3. Chạy:

```powershell
python eval/ragas_eval.py --workspace default --golden eval/my_golden.jsonl
```

Nên có 50-100 câu, trải đều các tài liệu và dạng câu hỏi. Không dùng chính câu trả lời của model làm reference.

## Chỉ số

- `context_precision`: context lấy về có liên quan đến reference không.
- `context_recall`: context có chứa đủ thông tin để trả lời reference không.
- `faithfulness`: câu trả lời có bám context, không bịa không.
- `answer_relevancy`: câu trả lời có đúng trọng tâm câu hỏi không.
- `answer_correctness`: câu trả lời có khớp reference không.

Judge mặc định là `qwen2.5:3b`. Có thể đổi bằng:

```powershell
ollama pull qwen2.5:7b
python eval/ragas_eval.py --workspace ragas-eval --judge-model qwen2.5:7b
```

Judge càng mạnh thì điểm càng ổn định. Với bộ test lớn, nên dùng model 7B trở lên.

## Cấu hình reranker/RRF

Các biến môi trường trong `.env`:

```env
RETRIEVAL_CANDIDATE_MULTIPLIER=6
RRF_K=60
RERANK_ENABLED=true
RERANK_MODEL=jinaai/jina-reranker-v2-base-multilingual
RERANK_MAX_CANDIDATES=24
RERANK_BATCH_SIZE=16
```

Lần đầu chạy reranker sẽ tải model ONNX (~1.1 GB). Nếu máy yếu hoặc không có mạng, đặt `RERANK_ENABLED=false` để quay về RRF thuần.
