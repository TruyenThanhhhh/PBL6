# Personal AI Knowledge Platform (PBL6)

> **Xây dựng Nền tảng Trợ lý Tri thức Cá nhân Đa nguồn sử dụng Hybrid RAG và Large Language Model**  
> *Hỗ trợ hoạt động Offline và khai thác thông tin Online*

[![FastAPI](https://img.shields.io/badge/Backend-FastAPI-009688?logo=fastapi)](https://fastapi.tiangolo.com)
[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python)](https://python.org)
[![Ollama](https://img.shields.io/badge/Local%20LLM-Ollama%20(Qwen%202.5)-black)](https://ollama.com)
[![SQLite](https://img.shields.io/badge/Database-SQLite%20FTS5-003B57?logo=sqlite)](https://sqlite.org)
[![License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

---

## 📌 1. Giới Thiệu Đề Tài
Dự án nhằm giải quyết bài toán quản lý và khai thác tri thức cá nhân theo hướng **Local-first**:
* **Bảo mật tuyệt đối & Hoạt động Offline**: Dữ liệu tài liệu cá nhân được lưu trữ và xử lý cục bộ trên máy tính. Chạy thông qua mô hình mã nguồn mở cục bộ (**Qwen 2.5 3B/7B**) bằng **Ollama**, không gửi dữ liệu ra bên ngoài khi chưa có sự đồng ý.
* **Khai thác Online khi cần**: Kết hợp công cụ tìm kiếm Web khi người dùng hỏi các thông tin thời sự, mới nhất.
* **Hybrid RAG Pipeline**: Kết hợp giữa **Dense Vector Search** (ngữ nghĩa) và **Sparse Lexical Search** (BM25 / FTS5), gộp kết quả qua **Reciprocal Rank Fusion (RRF)** và lọc lại bằng **Cross-Encoder Reranker** để loại bỏ ảo giác (hallucination).
* **Grounded Generation & Citations**: Mọi câu trả lời đều được gắn nhãn trích dẫn nguồn (tên tài liệu, trang, đoạn trích) để kiểm chứng.

---

## 📂 2. Cấu Trúc Dự Án

```
PBL6/
├── kehoach/                        # Tài liệu nghiên cứu & Kế hoạch WBS
│   ├── 01_So_Sanh_Va_Lua_Chon_Mo_Hinh_AI.md
│   ├── 02_Kien_Truc_He_Thong_Va_Ky_Thuat.md
│   ├── 03_Ke_Hoach_Trien_Khai_Va_Lo_Trinh.md
│   ├── 04_Bang_Phan_Chia_Cong_Viec_Nhom_3_Nguoi.md
│   ├── Phan_Chia_Cong_Viec_Nhom_3_Nguoi_PBL6.xlsx   # File Excel phân chia 28 tasks
│   └── README.md
├── sourcecode/
│   └── backend/                    # Máy chủ FastAPI & Lõi RAG
│       ├── app/
│       │   ├── api/                # API Endpoints (Workspaces, Documents, Chat)
│       │   ├── services/           # Document Parser, Retrieval FTS5, LLM Service
│       │   ├── static/             # Giao diện Web UI (HTML5 + Tailwind)
│       │   ├── config.py           # Cấu hình hệ thống
│       │   ├── database.py         # CSDL SQLite & FTS5
│       │   └── main.py             # Entrypoint FastAPI
│       ├── data/                   # Thư mục chứa SQLite database & uploads
│       ├── requirements.txt
│       └── run.py
├── tailieu/                        # Tài liệu tổng quan đề tài gốc (.docx)
├── .gitignore
├── start_app.bat                   # Script khởi động 1-click
└── README.md
```

---

## 🚀 3. Hướng Dẫn Cài Đặt & Khởi Chạy

### Yêu cầu hệ thống:
* **Hệ điều hành:** Windows 10/11, Linux, macOS.
* **Python:** 3.10 trở lên.
* **Ollama:** Cài đặt từ [ollama.com](https://ollama.com/download).

### Bước 1: Clone Repository
```bash
git clone https://github.com/TruyenThanhhhh/<tên-repo>.git
cd PBL6
```

### Bước 2: Cài Đặt Thư Viện Python
```bash
cd sourcecode/backend
pip install -r requirements.txt
```

### Bước 3: Tải Mô Hình AI Cục Bộ (Ollama)
```bash
ollama run qwen2.5:3b
```

### Bước 4: Khởi Chạy Ứng Dụng
* **Cách 1:** Nhấp đúp vào file `start_app.bat` ở thư mục gốc.
* **Cách 2:** Chạy bằng dòng lệnh:
```bash
cd sourcecode/backend
python run.py
```
* Mở trình duyệt Web tại: **http://localhost:8000**
* Xem Swagger API Docs: **http://localhost:8000/docs**

---

## 👥 4. Phân Công Trách Nhiệm Nhóm 3 Thành Viên
* **Thành viên 1 (Lead & AI Specialist):** Lõi AI, Mô hình LLM (Ollama), Dense Embedding (BGE-M3), Reranker, RRF, Prompt Engineering, Benchmark Ragas.
* **Thành viên 2 (Backend & Data Engineer):** Parser tài liệu (PDF/DOCX/PPTX), CSDL SQLite FTS5, API FastAPI, Web Search, AI Router.
* **Thành viên 3 (Frontend & Feature Dev):** Giao diện Web UI, Quản lý Workspace, Citation Viewer, Bộ công cụ học tập (Flashcards/Quiz), Slide thuyết trình.

Chi tiết phân chia 28 công việc theo dõi tại: [`kehoach/Phan_Chia_Cong_Viec_Nhom_3_Nguoi_PBL6.xlsx`](./kehoach/Phan_Chia_Cong_Viec_Nhom_3_Nguoi_PBL6.xlsx).
