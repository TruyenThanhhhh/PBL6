# PBL6 RAG Architecture Notes

## Stack

PBL6 là nền tảng tri thức cá nhân dùng backend FastAPI và frontend React + Vite.
Máy chủ backend mặc định chạy tại http://localhost:8000, frontend dev chạy tại http://localhost:5173 hoặc http://localhost:5174.
Cơ sở dữ liệu là SQLite, lưu tài liệu, chunk, chỉ mục FTS5 và vector BGE-M3.

## Hybrid Retrieval

Pipeline truy hồi là Hybrid RAG, kết hợp Sparse Search bằng SQLite FTS5/BM25 với Dense Search bằng BGE-M3.
Hai danh sách kết quả được hợp nhất bằng Reciprocal Rank Fusion (RRF).
Công thức RRF cộng điểm 1 / (k + rank) cho từng chunk, với k mặc định bằng 60.

## Reranker

Sau RRF, hệ thống lấy tối đa 24 ứng viên và đưa qua Cross-Encoder Reranker đa ngôn ngữ.
Mô hình reranker mặc định là jinaai/jina-reranker-v2-base-multilingual, chạy bằng fastembed ONNX.
Reranker chấm lại cặp (query, chunk) rồi chọn top_k chunk cuối cùng, mặc định top_k bằng 4.
Nếu reranker không tải được, hệ thống giữ nguyên thứ tự RRF để không làm hỏng chức năng chat.

## Chunking And Embedding

Tài liệu được chia theo ký tự với CHUNK_SIZE mặc định 800 và CHUNK_OVERLAP 150.
Mỗi chunk được lưu vào bảng document_chunks, chunks_fts và chunk_embeddings.
Vector BGE-M3 được đóng gói dạng float32 và lưu trong SQLite.

## Generation

LLM cục bộ được gọi qua Ollama, model mặc định là qwen2.5:3b.
Model vision mặc định là qwen3-vl:2b-instruct, có fallback qwen2.5vl:3b.
Prompt yêu cầu trả lời dựa trên nguồn, không bịa, và gắn trích dẫn dạng [Tài liệu N] hoặc [Web N].

## Evaluation

Benchmark dùng Ragas với các chỉ số: context_precision, context_recall, faithfulness, answer_relevancy và answer_correctness.
Bộ câu hỏi vàng nên có trường question, reference và được chạy trên cùng workspace với tài liệu liên quan.
Kết quả nên được lưu lại để so sánh giữa các lần thay đổi chunking, retrieval, reranker, prompt và model.

## Authentication

Backend dùng JWT Bearer token. Người dùng đăng ký hoặc đăng nhập qua các endpoint /api/v1/auth/register và /api/v1/auth/login.
Frontend lưu token trong localStorage với key pbl6_access_token và gửi header Authorization cho các API workspace, tài liệu và chat.
