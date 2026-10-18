# BÁO CÁO PHÂN TÍCH, SO SÁNH VÀ LỰA CHỌN MÔ HÌNH AI CHO HỆ THỐNG PERSONAL AI KNOWLEDGE PLATFORM

> **Ngày lập:** 30/09/2026  
> **Dự án:** Trợ lý tri thức cá nhân đa nguồn sử dụng Hybrid RAG và LLM (PBL6)  
> **Mục tiêu:** Phân tích định lượng, so sánh đa tiêu chí và lựa chọn bộ mô hình AI tối ưu nhất đáp ứng triết lý **Local-first**, **hỗ trợ song ngữ Việt - Anh**, và **vận hành mượt mà trên phần cứng thực tế**.

---

## 1. Phân Tích Hiện Trạng Phần Cứng Thực Tế

Hệ thống được thiết kế chạy trên máy tính cá nhân của người dùng với cấu hình phần cứng đo đạc thực tế:
* **Hệ điều hành:** Windows 11 (64-bit)
* **CPU:** 12th Gen Intel(R) Core(TM) i5-12450H (8 Cores: 4P-cores + 4E-cores, 12 Threads)
* **RAM hệ thống:** 16 GB DDR4/DDR5
* **GPU rời:** NVIDIA GeForce RTX 3050 Laptop GPU (4 GB VRAM GDDR6, CUDA 12.9)

### Ràng buộc kỹ thuật & Chiến lược phân bổ tài nguyên (Resource Allocation Strategy):
1. **Dung lượng VRAM (4 GB):**
   * VRAM 4 GB là giới hạn quan trọng. Nếu nạp mô hình vượt quá 4 GB, GPU sẽ bị lỗi `CUDA Out of Memory (OOM)` hoặc hệ thống phải đẩy bộ nhớ sang Shared GPU Memory qua PCIe gây sụt giảm tốc độ suy luận nghiêm trọng (throttling).
   * **Chiến lược 1 (Toàn bộ trên GPU - Zero CPU Latency):** Chọn mô hình LLM kích thước nhỏ (3B - 4B tham số) lượng tử hóa 4-bit (`Q4_K_M`), chiếm ~2.0 - 2.5 GB VRAM. Phần VRAM còn lại (~1.5 GB) dành cho Embedding model và KV Cache context (4k - 8k tokens).
   * **Chiến lược 2 (Hybrid GPU-CPU Offloading qua Ollama/llama.cpp):** Chọn mô hình 7B - 8B tham số lượng tử hóa `Q4_K_M` (~4.5 - 5.0 GB). Nạp 20-25 layers vào 4GB VRAM của GPU, các layers còn lại chạy trên CPU + 16GB RAM. Tốc độ sinh text đạt ~12 - 18 tokens/giây, hoàn toàn đủ cho trải nghiệm đọc tương tác.

---

## 2. So Sánh Chi Tiết Các Mô Hình Local Large Language Model (LLM)

### 2.1. Tiêu chí đánh giá
1. **Khả năng hiểu và sinh tiếng Việt:** Ngữ pháp chuẩn, tự nhiên, không bị lai tạp từ vựng vô nghĩa.
2. **Khả năng tuân thủ ngữ cảnh (Instruction-Following & Grounded Generation):** Không bịa đặt (hallucination), bám sát các đoạn trích dẫn (evidence chunks) được cung cấp từ RAG.
3. **Kích thước & Yêu cầu phần cứng:** Khả năng chạy trên 4GB VRAM hoặc kết hợp 16GB RAM.
4. **Context Window:** Hỗ trợ tối thiểu 8K - 32K context để nạp nhiều tài liệu trích xuất.

### 2.2. Bảng ma trận so sánh các dòng LLM

| Mô hình | Nhà phát triển | Số tham số | Context Window | Chất lượng Tiếng Việt | RAG Grounding / Trích dẫn | Dung lượng Q4_K_M | Đánh giá tính khả thi trên RTX 3050 4GB |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Qwen 2.5 - 3B Instruct** | Alibaba Cloud | 3.09B | 32k (hỗ trợ tới 128k) | ⭐⭐⭐⭐⭐ (Xuất sắc) | ⭐⭐⭐⭐ (Rất tốt) | **~1.9 GB** | **100% trên VRAM GPU**, tốc độ > 35-45 tok/s, cực kỳ mát và nhanh. |
| **Qwen 2.5 - 7B Instruct** | Alibaba Cloud | 7.61B | 32k (hỗ trợ tới 128k) | ⭐⭐⭐⭐⭐ (Hàng đầu mã nguồn mở) | ⭐⭐⭐⭐⭐ (Xuất sắc, suy luận logic vượt trội) | **~4.7 GB** | **Offload 60% GPU + 40% CPU**, tốc độ ~14-18 tok/s. Khả năng lập luận tài liệu phức tạp tốt nhất. |
| **Llama 3.2 - 3B Instruct** | Meta AI | 3.21B | 128k | ⭐⭐⭐ (Khá, dịch máy đôi lúc gượng) | ⭐⭐⭐⭐ (Tốt) | **~2.0 GB** | Chạy 100% GPU, nhưng tiếng Việt kém hơn Qwen 2.5 rõ rệt. |
| **Llama 3.1 - 8B Instruct** | Meta AI | 8.03B | 128k | ⭐⭐⭐⭐ (Khá - Tốt) | ⭐⭐⭐⭐⭐ (Rất mạnh) | **~4.9 GB** | Offload CPU + GPU, nặng hơn Qwen, tiếng Việt cần prompt kỹ. |
| **Phi-3.5-mini Instruct** | Microsoft | 3.82B | 128k | ⭐⭐ (Yếu tiếng Việt) | ⭐⭐⭐⭐ (Rất mạnh logic/code) | **~2.4 GB** | Chạy 100% GPU, tuy nhiên tiếng Việt hay bị lỗi ngữ pháp/từ ngữ. |
| **Gemma 2 - 2B / 9B** | Google | 2.6B / 9.2B | 8k | ⭐⭐⭐ (Trung bình khá) | ⭐⭐⭐ (Dễ bị lặp từ) | 1.6 GB / 5.5 GB | Context ngắn (8k), kiến trúc sliding window gây khó khi RAG dài. |
| **Vistral 7B Chat** | Cung cấp bởi FPT/VietAI (dựa trên Mistral) | 7B | 8k | ⭐⭐⭐⭐ (Tốt) | ⭐⭐⭐ (Prompt theo định dạng cũ) | **~4.5 GB** | Đã cũ so với Qwen 2.5, context ngắn, suy luận tổng hợp đa tài liệu yếu hơn. |

### 2.3. Lựa chọn LLM đề xuất:
* **Mô hình chính (Default Choice):** **`Qwen 2.5 - 3B Instruct`** (chạy 100% trên GPU 4GB VRAM) cho chế độ phản hồi tức thì, mượt mà, độ trễ cực thấp (phù hợp cho hỏi đáp nhanh, tìm kiếm tài liệu hàng ngày, sinh flashcard/quiz).
* **Mô hình nâng cao (Power Mode):** **`Qwen 2.5 - 7B Instruct`** (chạy GPU + CPU Offload qua Ollama) cho chế độ Trợ lý nghiên cứu (Research Assistant), tổng hợp đa tài liệu, viết báo cáo dài, nơi cần khả năng lập luận sâu và đối chiếu nguồn khắt khe.
* **Cơ chế chuyển đổi (Model Toggle):** Cho phép người dùng chọn cấu hình trực tiếp trên UI (Fast Mode 3B vs Deep Mode 7B).

---

## 3. So Sánh Chi Tiết Mô Hình Tạo Vector Nhúng (Embedding Model)

### 3.1. Tiêu chí lựa chọn
1. **Hỗ trợ Đa ngữ & Tiếng Việt:** Khả năng hiểu ngữ nghĩa tiếng Việt có dấu, cấu trúc câu tiếng Việt.
2. **Hỗ trợ Hybrid Search:** Lý tưởng nhất là hỗ trợ cả Dense Embedding và Sparse Vector / Lexical Weighting.
3. **Độ dài Sequence (Max Token Length):** Tài liệu văn bản thường có đoạn dài; model hỗ trợ context chunking lớn (>= 512, lý tưởng 8192 tokens).
4. **Hiệu năng & Tối ưu hóa:** Có thể chạy mượt mà bằng CPU (qua ONNX / FastEmbed) hoặc GPU nhẹ nhàng.

### 3.2. Bảng so sánh các Embedding Models

| Mô hình | Kích thước & Chiều Vector | Max Tokens | Hỗ trợ Tiếng Việt | Tính năng đặc biệt | Tài nguyên yêu cầu |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **BAAI/bge-m3** | 1024 dims (~1.1 GB) | **8192 tokens** | ⭐⭐⭐⭐⭐ (Cực tốt) | **3-in-1:** Hỗ trợ cùng lúc Dense, Sparse (Lexical weights tương đương BM25) và ColBERT Multi-vector. | ~1.1 GB RAM/VRAM. Chạy ONNX CPU cực nhanh. |
| **intfloat/multilingual-e5-base** | 768 dims (~560 MB) | 512 tokens | ⭐⭐⭐⭐ (Rất tốt) | Cần tiền tố `query:` và `passage:` khi nhúng. | Rất nhẹ (~600MB). |
| **sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2** | 384 dims (~470 MB) | 128 tokens | ⭐⭐⭐ (Khá) | Tốc độ cực nhanh, nhưng context ngắn (128) không phù hợp tài liệu dài. | Siêu nhẹ (~400MB). |
| **bkai-foundation-models/vietnamese-bi-encoder** | 768 dims (~420 MB) | 256 tokens | ⭐⭐⭐⭐ (Chuyên sâu tiếng Việt) | Chỉ chuyên tiếng Việt, tài liệu song ngữ hoặc code tiếng Anh bị giảm hiệu quả. | Nhẹ. |

### 3.3. Lựa chọn Embedding đề xuất:
* **Lựa chọn số 1 (Vô địch cho Hybrid RAG):** **`BAAI/bge-m3`**
  * *Lý do:* `bge-m3` là mô hình duy nhất hiện nay hỗ trợ toàn diện cả Dense Retrieval, Multi-lingual (hơn 100 ngôn ngữ, tiếng Việt thuộc nhóm xuất sắc nhất), context lên tới **8192 tokens** (không lo vỡ nghĩa khi chunk dài), và tích hợp sẵn cơ chế Sparse Weighting giúp làm Hybrid Search mà không phụ thuộc hoàn toàn vào engine BM25 truyền thống nếu muốn tối giản.
  * Chạy thông qua thư viện `fastembed` (dựa trên ONNX Runtime đa luồng CPU C++) giúp giải phóng hoàn toàn VRAM của GPU dành riêng cho LLM!

---

## 4. So Sánh Chi Tiết Mô Hình Xếp Hạng Lại (Reranker Model)

Trong kiến trúc Hybrid RAG, việc kết hợp kết quả từ Dense Search (Vector) và Sparse Search (BM25) thường dẫn đến danh sách kết quả hỗn hợp. **Reranker (Cross-Encoder)** là thành phần tối quan trọng để chấm điểm tương quan ngữ nghĩa chính xác giữa câu hỏi và từng chunk văn bản, lọc bỏ nhiễu trước khi đưa vào LLM.

### 4.1. Bảng so sánh Reranker

| Mô hình | Kích thước | Max Tokens | Hỗ trợ Tiếng Việt | Hiệu năng / Tốc độ |
| :--- | :--- | :--- | :--- | :--- |
| **BAAI/bge-reranker-v2-m3** | ~1.1 GB (hoặc ONNX ~560 MB) | 8192 tokens | ⭐⭐⭐⭐⭐ | Độ chính xác cao nhất cho tiếng Việt và tài liệu kỹ thuật. |
| **FlashRank (ms-marco / MiniLM)** | ~100 MB | 512 tokens | ⭐⭐⭐ | Siêu nhẹ, tốc độ mili-giây trên CPU, nhưng tiếng Việt trung bình. |
| **BAAI/bge-reranker-base** | ~560 MB | 512 tokens | ⭐⭐⭐⭐ | Rất tốt, cân bằng giữa độ chính xác và tài nguyên. |

### 4.2. Lựa chọn Reranker đề xuất:
* **`BAAI/bge-reranker-v2-m3` (chạy ONNX qua FastEmbed)**: Chấm điểm lại Top-20 chunks được lấy từ giai đoạn Retrieval để chọn ra Top-3 đến Top-5 chunks tinh tuý nhất cấp cho LLM. Quá trình rerank chỉ mất khoảng 80-150ms trên CPU i5-12450H.

---

## 5. So Sánh & Lựa Chọn Cơ Sở Dữ Liệu Vector (Vector Database)

| Cơ sở dữ liệu | Kiến trúc lưu trữ | Hybrid Search (Vector + Sparse BM25) | Cơ chế nhúng cục bộ (Embedded/Local) | Tài nguyên tiêu thụ | Nhận xét |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Qdrant** | Rust Core (Client-Server hoặc Embedded) | **Tích hợp sẵn gốc (Native Sparse Vectors)** | Có Qdrant Local File hoặc Docker | Rất thấp, tối ưu bộ nhớ cực tốt | **Đề xuất hàng đầu**. Hỗ trợ Payload metadata filter mạnh, tích hợp Dense + Sparse trong 1 query. |
| **LanceDB** | Serverless / File-based (Apache Arrow) | Hỗ trợ FTS qua Tantivy | Chạy trực tiếp trong Python process | Gần như bằng 0 khi idle | Rất phù hợp Desktop/Local-first, nhưng cộng đồng và tính năng hybrid mới hơn Qdrant. |
| **ChromaDB** | Python / SQLite | Cần cấu hình BM25 ngoài | Cực dễ setup | Trung bình | Dễ dùng nhưng hiệu năng quy mô lớn và khả năng Native Hybrid Search kém hơn Qdrant. |
| **PostgreSQL + pgvector** | RDBMS truyền thống | Kết hợp pg_trgm / fulltext | Cần cài đặt PostgreSQL server | Khá nặng nề cho ứng dụng Desktop cá nhân | Quá cồng kềnh cho người dùng cài đặt máy cá nhân local-first. |

### Lựa chọn đề xuất:
* **`Qdrant`**: Có thể chạy dưới dạng Docker container nội bộ hoặc sử dụng `qdrant-client` với chế độ lưu trữ file cục bộ (`path="./data/qdrant_storage"`), không yêu cầu người dùng phải tự cấu hình database phức tạp. Hỗ trợ chuẩn Native Hybrid Search (kết hợp Dense Vector của BGE-M3 và Sparse BM25).

---

## 6. Tổng Kết: BỘ CẤU HÌNH TỐI ƯU (GOLDEN STACK) ĐƯỢC CHỌN

| Thành phần | Lựa chọn chính thức | Cách thức triển khai | Mục đích & Rationale |
| :--- | :--- | :--- | :--- |
| **Local LLM Engine** | **Ollama** | Service chạy nền cục bộ trên Windows | Quản lý model nhẹ nhàng, tối ưu hóa lượng tử hóa GGUF, hỗ trợ REST API chuẩn OpenAI. |
| **Mô hình LLM Mặc định** | **`qwen2.5:3b-instruct`** | Chạy 100% trên GPU RTX 3050 (4GB) | Tốc độ cực nhanh (>40 tok/s), ngữ pháp tiếng Việt hoàn hảo, grounding context chính xác, không nóng máy. |
| **Mô hình LLM Nâng cao** | **`qwen2.5:7b-instruct-q4_K_M`** | Chạy Offload GPU (60%) + CPU (40%) | Dành cho tác vụ nghiên cứu chuyên sâu, tổng hợp báo cáo phức tạp, suy luận so sánh đa nguồn. |
| **Embedding Engine** | **`fastembed` (ONNX) với `BAAI/bge-m3`** | Chạy trên CPU đa luồng (i5-12450H) | Giải phóng 100% VRAM GPU cho LLM. Hỗ trợ cả Dense + Sparse, context 8192 tokens, xuất sắc tiếng Việt. |
| **Reranker Engine** | **`bge-reranker-v2-m3`** | Chạy ONNX qua CPU | Đảm bảo tính chính xác tuyệt đối của evidence trước khi sinh câu trả lời. |
| **Vector DB & Indexing** | **Qdrant (Local Persistent Storage)** | Lưu file cục bộ trong thư mục ứng dụng | Không cần cài đặt server bên ngoài, hỗ trợ Hybrid Search (Dense + Sparse) tự nhiên. |
| **Web Search Provider** | **DuckDuckGo Search / Tavily API** | Python HTTP Client (Fallback miễn phí) | Không tốn phí, tìm kiếm tin tức thời sự online khi người dùng kích hoạt Online/Hybrid mode. |
