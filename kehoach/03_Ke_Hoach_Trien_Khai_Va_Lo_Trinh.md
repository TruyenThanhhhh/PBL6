# KẾ HOẠCH TRIỂN KHAI VÀ LỘ TRÌNH PHÁT TRIỂN CHI TIẾT
## DỰ ÁN: PERSONAL AI KNOWLEDGE PLATFORM (PBL6)

> **Mã tài liệu:** PLAN-DEV-03  
> **Thời gian dự kiến:** 8 Giai đoạn triển khai tuần tự theo mô hình Agile / Iterative  
> **Định hướng:** Chạy được ngay sản phẩm cốt lõi (MVP) trong giai đoạn đầu, sau đó nâng cấp mở rộng.

---

## 1. Phân Rã Giai Đoạn Triển Khai (Milestones & Roadmap)

```
[Giai đoạn 1: MVP Local RAG Core]
       │
       ▼
[Giai đoạn 2: Nâng cấp Hybrid RAG & Reranker]
       │
       ▼
[Giai đoạn 3: Tối ưu Offline-First & Quản lý Tài nguyên Cục bộ]
       │
       ▼
[Giai đoạn 4: Tích hợp Tìm kiếm Web & Trích xuất Dữ liệu Thời gian thực]
       │
       ▼
[Giai đoạn 5: Phát triển AI Router & Hợp nhất Bằng chứng Đa nguồn]
       │
       ▼
[Giai đoạn 6: Bộ Công cụ Hỗ trợ Học tập (Summary, Flashcards, Quiz)]
       │
       ▼
[Giai đoạn 7: Trợ lý Nghiên cứu (Research Assistant & Đa Tài liệu)]
       │
       ▼
[Giai đoạn 8: Đánh giá Benchmark RAG, Viết Báo cáo & Hoàn thiện Sản phẩm]
```

---

## 2. Kế Hoạch Chi Tiết Từng Giai Đoạn (Work Breakdown Structure - WBS)

### 📌 Giai Đoạn 1: MVP Local RAG Core (Tuần 1 - Tuần 2)
* **Mục tiêu:** Xây dựng khung ứng dụng cơ bản, upload tài liệu đơn giản và hỏi đáp trực tiếp với Local LLM.
* **Các đầu việc cụ thể:**
  1. Thiết lập cấu trúc mã nguồn dự án: `sourcecode/backend` (FastAPI) và `sourcecode/frontend` (React + Vite + Tailwind).
  2. Cài đặt và tích hợp `Ollama` với mô hình `qwen2.5:3b-instruct`.
  3. Xây dựng module Document Parser: Hỗ trợ nạp file `.pdf`, `.docx`, `.txt`, `.md`.
  4. Triển khai Recursive Character Chunking cơ bản và nhúng vector bằng `BAAI/bge-m3` qua thư viện `fastembed`.
  5. Cài đặt `Qdrant Local` (lưu trữ file tại `./data/qdrant`) và thực hiện Vector Search Top-K.
  6. Xây dựng giao diện Chat UI cơ bản có hiển thị đoạn text trích dẫn (Context).
* **Kết quả bàn giao (Deliverables):**
  * Người dùng có thể upload tài liệu PDF/DOCX, đặt câu hỏi và nhận câu trả lời từ tài liệu đó khi không cần mạng.

---

### 📌 Giai Đoạn 2: Nâng Cấp Hybrid RAG Pipeline & Reranker (Tuần 3 - Tuần 4)
* **Mục tiêu:** Nâng cao độ chính xác truy xuất bằng cách kết hợp Vector Search và Từ khóa (BM25), loại bỏ nhiễu bằng Reranker.
* **Các đầu việc cụ thể:**
  1. Triển khai Sparse Lexical Search (sử dụng Sparse Vectors của BGE-M3 hoặc `rank-bm25`).
  2. Cài đặt thuật toán Reciprocal Rank Fusion (RRF) để gộp kết quả tìm kiếm ngữ nghĩa và tìm kiếm từ khóa.
  3. Tích hợp Cross-Encoder Reranker: `BAAI/bge-reranker-v2-m3` để xếp hạng lại Top-20 ứng viên lấy ra Top-4 chunks tốt nhất.
  4. Nâng cấp cơ chế trích xuất Citation: Trả về chính xác số trang (page number) và vị trí chunk.
  5. Thiết kế UI Citation Viewer: Click vào trích dẫn sẽ mở modal xem đoạn tài liệu gốc tương ứng.
* **Kết quả bàn giao:**
  * Giảm thiểu rõ rệt hiện tượng ảo giác (hallucination), bắt được chính xác các từ khóa kỹ thuật và tên riêng.

---

### 📌 Giai Đoạn 3: Tối Ưu Offline-First & Quản Lý Dữ Liệu Cục Bộ (Tuần 5)
* **Mục tiêu:** Hoàn thiện trải nghiệm người dùng không phụ thuộc vào Internet, quản trị bộ nhớ và an toàn dữ liệu.
* **Các đầu việc cụ thể:**
  1. Xây dựng Network Monitor: Tự động phát hiện trạng thái online/offline của hệ thống.
  2. Cơ chế Local Caching: Toàn bộ lịch sử chat, cài đặt người dùng, metadata lưu trữ tại SQLite cục bộ.
  3. Tối ưu hóa bộ nhớ: Giới hạn VRAM sử dụng của GPU RTX 3050 dưới 3.5GB để tránh tràn bộ nhớ.
  4. Đóng gói quản lý cấu hình: Cho phép người dùng chuyển đổi linh hoạt giữa Qwen 2.5 3B (Fast) và 7B (Deep).
* **Kết quả bàn giao:**
  * Hệ thống ngắt hoàn toàn kết nối WiFi vẫn khởi động và tra cứu tài liệu mượt mà, không gặp lỗi kết nối.

---

### 📌 Giai Đoạn 4: Tích Hợp Khai Thác Online Web Search (Tuần 6)
* **Mục tiêu:** Khả năng tra cứu thông tin mới từ Internet khi người dùng cho phép.
* **Các đầu việc cụ thể:**
  1. Tích hợp API tìm kiếm: DuckDuckGo Search (hoàn toàn miễn phí, không cần API Key) và tùy chọn Tavily Search.
  2. Xây dựng Web Content Extractor: Tự động tải HTML và làm sạch (bỏ quảng cáo, script, header/footer rác) bằng `trafilatura` hoặc `BeautifulSoup`.
  3. Chia nhỏ nội dung trang web thành chunks tạm thời (in-memory chunks) và đẩy qua Reranker.
  4. Đánh dấu URL nguồn trích dẫn rõ ràng trong câu trả lời.
* **Kết quả bàn giao:**
  * Trả lời được các câu hỏi thời sự, sự kiện cập nhật của năm hiện tại kèm liên kết nguồn web uy tín.

---

### 📌 Giai Đoạn 5: Phát Triển AI Router & Hợp Nhất Đa Nguồn (Tuần 7)
* **Mục tiêu:** Tự động hóa việc lựa chọn nguồn dữ liệu (Local / Web / Hybrid) một cách thông minh.
* **Các đầu việc cụ thể:**
  1. Xây dựng Intent Classifier & Time-sensitive Detector: Phân loại câu hỏi của người dùng.
  2. Xây dựng logic Fallback tự động: Khi người dùng chọn Web nhưng mất kết nối, hệ thống tự động cảnh báo và chuyển sang Local.
  3. Cơ chế Evidence Fusion: Kết hợp các đoạn bằng chứng từ file nội bộ và từ website, đưa vào một prompt duy nhất có cấu trúc rõ ràng.
  4. Bổ sung giao diện chọn chế độ: Auto / Local-only / Web-only / Hybrid trên thanh công cụ chat.
* **Kết quả bàn giao:**
  * Người dùng chỉ cần gõ câu hỏi, hệ thống tự động biết khi nào cần tra tài liệu máy và khi nào cần tra web.

---

### 📌 Giai Đoạn 6: Bộ Tính Năng Hỗ Trợ Học Tập Cá Nhân (Tuần 8 - Tuần 9)
* **Mục tiêu:** Biến hệ thống thành trợ lý học tập đắc lực (Personal Study Assistant).
* **Các đầu việc cụ thể:**
  1. **Tính năng Tóm tắt (Summarization):** Tóm tắt nhanh toàn bộ tài liệu hoặc theo từng chương (Bullet points, Mindmap text format).
  2. **Tính năng Flashcard:** Tự động quét tài liệu và sinh các cặp câu hỏi - câu trả lời dạng thẻ lật (Anki-style Flashcards).
  3. **Tính năng Trắc nghiệm (Quiz Generator):** Tự sinh đề kiểm tra trắc nghiệm 4 đáp án kèm giải thích chi tiết đáp án đúng.
  4. Lưu trữ và quản lý tiến độ học tập vào bảng `study_artifacts`.
* **Kết quả bàn giao:**
  * Giao diện học tập trực quan: Thẻ Flashcard tương tác lật mặt, bảng làm bài kiểm tra trắc nghiệm chấm điểm tự động.

---

### 📌 Giai Đoạn 7: Trợ Lý Nghiên Cứu (Research Assistant) (Tuần 10 - Tuần 11)
* **Mục tiêu:** Hỗ trợ đọc hiểu và so sánh đa tài liệu khoa học, xuất báo cáo nghiên cứu có cấu trúc.
* **Các đầu việc cụ thể:**
  1. Multi-document Synthesis: Cho phép chọn nhiều tài liệu cùng lúc trong Workspace để hỏi đáp đối chiếu (Ví dụ: So sánh giải pháp của Bài báo A và Bài báo B).
  2. Chức năng phát hiện khoảng trống nghiên cứu (Research Gap Analysis).
  3. Xuất kết quả nghiên cứu thành file Markdown / PDF có định dạng chuẩn kèm mục trích dẫn tài liệu tham khảo (References).
* **Kết quả bàn giao:**
  * Tạo được báo cáo tổng hợp tự động từ 3-5 tài liệu nghiên cứu đã nạp vào Workspace.

---

### 📌 Giai Đoạn 8: Đánh Giá Benchmark, Tối Ưu & Hoàn Thiện Báo Cáo (Tuần 12)
* **Mục tiêu:** Đo lường định lượng hiệu quả của Hybrid RAG, hoàn thiện tài liệu luận văn / báo cáo đồ án PBL6.
* **Các đầu việc cụ thể:**
  1. Thiết lập bộ dữ liệu kiểm thử (Evaluation Dataset): 50 câu hỏi tiếng Việt có sẵn ground truth.
  2. Đo lường chỉ số Retrieval: **Hit Rate@K**, **Recall@K**, **MRR (Mean Reciprocal Rank)**.
  3. Đo lường chỉ số Thế hệ (Generation): **Faithfulness (Độ trung thực)**, **Answer Relevance (Độ liên quan)**, **Hallucination Rate** sử dụng framework `Ragas`.
  4. So sánh thực nghiệm:
     * Dense Search thuần túy vs. Hybrid RAG (Dense + BM25).
     * Có Reranker vs. Không có Reranker.
     * Qwen 2.5 3B vs. Qwen 2.5 7B.
  5. Đóng gói mã nguồn, viết tài liệu hướng dẫn cài đặt và nghiệm thu sản phẩm.

---

## 3. Khung Đánh Giá Định Lượng (Benchmark Framework)

Để đảm bảo đề tài có tính khoa học cao trong báo cáo PBL6, hệ thống sẽ được đánh giá qua các chỉ số sau:

| Chỉ số | Mục tiêu kỳ vọng | Phương pháp đo đạc |
| :--- | :--- | :--- |
| **Hit Rate@5** | $\ge 88\%$ | Tỉ lệ câu hỏi mà ít nhất 1 chunk đúng nằm trong Top 5 kết quả sau Rerank. |
| **MRR@5** | $\ge 0.75$ | Điểm nghịch đảo thứ hạng của chunk đúng đầu tiên. |
| **Faithfulness** | $\ge 92\%$ | Đánh giá qua `Ragas`: Câu trả lời hoàn toàn suy diễn từ context, không bịa đặt. |
| **Answer Relevance** | $\ge 90\%$ | Câu trả lời giải quyết đúng trọng tâm câu hỏi của người dùng. |
| **Độ trễ phản hồi (First Token Latency)** | $\le 1.2$ giây (với Qwen 3B) | Thời gian từ lúc bấm gửi đến khi token đầu tiên xuất hiện. |
| **VRAM tiêu thụ tối đa** | $\le 3.6$ GB / 4 GB | Đảm bảo an toàn không gây tràn VRAM trên GPU RTX 3050 Laptop. |

---

## 4. Quản Trị Rủi Ro Kỹ Thuật (Risk Management)

| Rủi ro | Mức độ | Biện pháp phòng ngừa & Xử lý |
| :--- | :---: | :--- |
| **Tràn bộ nhớ GPU (CUDA OOM)** | Cao | Đặt `BAAI/bge-m3` và Reranker chạy trên CPU (qua ONNX FastEmbed đa luồng), dành trọn 4GB VRAM cho Ollama LLM. Giới hạn context window ở 8192 tokens. |
| **Định dạng file PDF quét (Scan/Ảnh)** | Trung bình | Ở giai đoạn MVP, thông báo yêu cầu file dạng Text-based. Ở giai đoạn mở rộng, tích hợp module OCR bằng `RapidOCR` / `PaddleOCR`. |
| **Tốc độ sinh text chậm khi dùng model 7B** | Trung bình | Thiết lập model mặc định là `qwen2.5:3b` để đảm bảo mượt mà. Chỉ gợi ý bật `qwen2.5:7b` khi thực hiện tác vụ nghiên cứu nặng. |
| **Web Search bị chặn IP hoặc Captcha** | Thấp | Sử dụng DuckDuckGo Search không cần API key, kết hợp xoay User-Agent và có fallback sang chế độ Local RAG. |
