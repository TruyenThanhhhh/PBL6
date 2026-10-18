# BẢNG KANBAN THEO DÕI CÔNG VIỆC DỰ ÁN PBL6 (NHÓM 3 THÀNH VIÊN)

> **Mô hình quản lý:** Agile / Kanban Board  
> **Cập nhật:** Tuần 3 - Triển khai Giai đoạn 2 (Hybrid RAG & UI)  
> **Quy ước màu thẻ thành viên:**
> * 🔵 **Thành viên 1 (Lead / AI Specialist)**: Lõi AI, LLM, Embedding, Reranker, Benchmark
> * 🟣 **Thành viên 2 (Backend & Data Engineer)**: Pipeline bóc tách tài liệu, SQLite FTS5, API, Web Search, AI Router
> * 🟢 **Thành viên 3 (Frontend & Feature Dev)**: Giao diện Web UI, Citation Modal, Flashcard, Quiz, Slide & Demo

---

## 📌 BẢNG KANBAN TỔNG QUAN

```
┌────────────────────────────────┬────────────────────────────────┬────────────────────────────────┐
│   📋 TO DO (CHƯA BẮT ĐẦU)      │   🚧 IN PROGRESS (ĐANG LÀM)    │      ✅ DONE (ĐÃ XONG)         │
│           [15 Tasks]           │           [3 Tasks]            │           [10 Tasks]           │
└────────────────────────────────┴────────────────────────────────┴────────────────────────────────┘
```

---

### 1. 📋 CỘT: TO DO (CHƯA BẮT ĐẦU) - 15 Đầu Việc

| Mã Thẻ | Tên Công Việc | Người Phụ Trách | Độ Ưu Tiên | Giai Đoạn | Kết Quả Bàn Giao |
| :---: | :--- | :---: | :---: | :---: | :--- |
| **TASK-13** | Tích hợp Cross-Encoder Reranker (`bge-reranker-v2-m3`) | 🔵 TV 1 | 🔴 Cao | GĐ 2 | Module `reranker_service.py` chấm điểm Top-4 |
| **TASK-15** | Xây dựng Network Monitor & Giới hạn VRAM GPU < 3.5GB | 🟣 TV 2 | 🟡 Trung bình | GĐ 3 | Module kiểm soát bộ nhớ an toàn |
| **TASK-16** | Nút gạt Toggle chuyển đổi Qwen 3B (Fast) & 7B (Deep) | 🟢 TV 3 + 🔵 TV 1 | 🟡 Trung bình | GĐ 3 | Model Switcher trên giao diện |
| **TASK-17** | Tích hợp DuckDuckGo Search API tra cứu Internet | 🟣 TV 2 | 🔴 Cao | GĐ 4 | Module `web_search_service.py` không cần API Key |
| **TASK-18** | Web Content Extractor làm sạch HTML & gắn link URL | 🟣 TV 2 | 🟡 Trung bình | GĐ 4 | Bóc tách bài viết web bỏ qua quảng cáo |
| **TASK-19** | AI Router: Intent Classifier & Time-sensitive Detector | 🔵 TV 1 | 🔴 Cao | GĐ 5 | Tự động phân loại câu hỏi Local/Web/Hybrid |
| **TASK-20** | Cơ chế Fallback tự động khi mất mạng/Web lỗi | 🟣 TV 2 | 🔴 Cao | GĐ 5 | Tự động chuyển về Local RAG kèm thông báo |
| **TASK-21** | Backend API sinh Tóm tắt, Flashcard và Quiz | 🟣 TV 2 | 🔴 Cao | GĐ 6 | Endpoints `/api/v1/study/*` & lưu SQLite |
| **TASK-22** | Màn hình Study Center: Flashcard lật mặt & Làm Quiz | 🟢 TV 3 | 🔴 Cao | GĐ 6 | Giao diện học tập tương tác chấm điểm tự động |
| **TASK-23** | Thuật toán đối chiếu và so sánh đa tài liệu (Multi-doc) | 🔵 TV 1 | 🟡 Trung bình | GĐ 7 | Tổng hợp so sánh quan điểm giữa 2-3 tài liệu |
| **TASK-24** | Tính năng xuất báo cáo nghiên cứu dạng Markdown/PDF | 🟢 TV 3 | 🟡 Trung bình | GĐ 7 | Nút xuất báo cáo kèm mục References chuẩn |
| **TASK-25** | Xây dựng bộ test Benchmark 50 câu hỏi tiếng Việt | 🔵 TV 1 | 🔴 Cao | GĐ 8 | File `evaluation_dataset.json` có ground-truth |
| **TASK-26** | Đo lường định lượng Hit Rate@5, MRR, Ragas Faithfulness | 🔵 TV 1 | 🔴 Cao | GĐ 8 | Biểu đồ chứng minh hiệu quả Hybrid RAG |
| **TASK-27** | Viết toàn bộ Báo cáo Thuyết minh Đồ án PBL6 | 👥 Cả nhóm | 🔴 Cao | GĐ 8 | File Word / PDF báo cáo đề tài đầy đủ các chương |
| **TASK-28** | Thiết kế Slide thuyết trình bảo vệ & quay Video Demo | 🟢 TV 3 | 🔴 Cao | GĐ 8 | Bộ Slide PPTX chuyên nghiệp & Video 5 phút |

---

### 2. 🚧 CỘT: IN PROGRESS (ĐANG THỰC HIỆN) - 3 Đầu Việc

| Mã Thẻ | Tên Công Việc | Người Phụ Trách | Độ Ưu Tiên | Giai Đoạn | Tiến Độ & Việc Cần Làm Ngay |
| :---: | :--- | :---: | :---: | :---: | :--- |
| **TASK-11** | Tích hợp thư viện `fastembed` & Dense Embedding `BGE-M3` | 🔵 **Thành viên 1** | 🔴 Cao | GĐ 2 | Đã cài xong `fastembed` và `onnxruntime`. Đang viết code sinh vector 1024 dims cho từng chunk. |
| **TASK-12** | Triển khai thuật toán Reciprocal Rank Fusion (RRF) | 🔵 **Thành viên 1** | 🔴 Cao | GĐ 2 | Đang viết hàm gộp danh sách Top-20 từ BM25 FTS5 và Top-20 từ Dense Vector. |
| **TASK-14** | Citation Viewer Modal: Click vào trích dẫn xem đoạn văn bản gốc | 🟢 **Thành viên 3** | 🟡 Trung bình | GĐ 2 | Đang làm popup modal trên giao diện: bấm vào `[Tài liệu 1]` sẽ nhảy đến đúng trang và bôi vàng đoạn trích. |

---

### 3. ✅ CỘT: DONE (ĐÃ HOÀN THÀNH) - 10 Đầu Việc

| Mã Thẻ | Tên Công Việc | Người Phụ Trách | Hoàn Thành | Kết Quả Đã Bàn Giao |
| :---: | :--- | :---: | :---: | :--- |
| **TASK-01** | Khảo sát phần cứng máy (RTX 3050 4GB VRAM) & tài liệu đề tài | 🔵 TV 1 | Tuần 1 | Tài liệu [`01_So_Sanh_Va_Lua_Chon_Mo_Hinh_AI.md`](file:///D:/PBl6/kehoach/01_So_Sanh_Va_Lua_Chon_Mo_Hinh_AI.md) |
| **TASK-02** | So sánh 6 họ LLM & chọn `Qwen 2.5 3B` + `BGE-M3` | 🔵 TV 1 | Tuần 1 | Bộ cấu hình tối ưu Golden Stack phù hợp phần cứng |
| **TASK-03** | Thiết kế kiến trúc phân tầng, SQLite Schema 6 bảng & API Spec | 🟣 TV 2 | Tuần 2 | Tài liệu [`02_Kien_Truc_He_Thong_Va_Ky_Thuat.md`](file:///D:/PBl6/kehoach/02_Kien_Truc_He_Thong_Va_Ky_Thuat.md) |
| **TASK-04** | Cài đặt Ollama & tải mô hình `qwen2.5:3b` chạy trên GPU | 🔵 TV 1 | Tuần 2 | Ollama local cổng 11434, tốc độ sinh text >40 tok/s |
| **TASK-05** | Bộ Document Parser bóc tách sạch file `.pdf`, `.docx`, `.pptx`, `.txt` | 🟣 TV 2 | Tuần 2 | Module [`document_service.py`](file:///D:/PBl6/sourcecode/backend/app/services/document_service.py) |
| **TASK-06** | Thuật toán Smart Recursive Text Chunking kèm metadata số trang | 🟣 TV 2 | Tuần 2 | Hàm `recursive_chunk_text` (~800 ký tự, overlap 150) |
| **TASK-07** | CSDL SQLite `knowledge.db` & bảng FTS5 Full-Text Search (BM25) | 🟣 TV 2 | Tuần 2 | CSDL SQLite cục bộ siêu nhẹ, không cần Docker |
| **TASK-08** | Lõi AI Service: Trò chuyện tự nhiên + Tổng hợp ý nghĩa + Trích dẫn | 🔵 TV 1 | Tuần 2 | Module [`llm_service.py`](file:///D:/PBl6/sourcecode/backend/app/services/llm_service.py) |
| **TASK-09** | Giao diện Web UI MVP kéo-thả upload file & chat RAG | 🟢 TV 3 | Tuần 2 | Giao diện Web tại [`static/index.html`](file:///D:/PBl6/sourcecode/backend/app/static/index.html) |
| **TASK-10** | Script khởi động 1-click `start_app.bat` & kiểm thử trọn vẹn luồng | 👥 Cả nhóm | Tuần 2 | Đã test thành công với file tài liệu thực tế của đề tài |

---

## 💡 HƯỚNG DẪN QUY TRÌNH LÀM VIỆC THEO KANBAN CHO NHÓM:
1. Mỗi đầu tuần, nhóm họp 10 phút để rà soát cột **IN PROGRESS**. Mỗi thành viên chỉ nhận **tối đa 1 đến 2 tasks** trong cột này cùng một lúc (nguyên tắc WIP - Work In Progress limit).
2. Khi làm xong một task:
   * Chuyển thẻ từ **IN PROGRESS** sang **DONE**.
   * Chọn task tiếp theo từ cột **TO DO** kéo vào cột **IN PROGRESS**.
3. Bằng cách này, các bạn luôn biết chính xác hôm nay mình cần làm gì, ai đang làm gì và đề tài đã hoàn thành được bao nhiêu % để báo cáo thầy hướng dẫn!
