"""
Script tự động tạo Board và nạp 28 Thẻ công việc lên Trello qua API
Yêu cầu:
1. Lấy Trello API Key và Token tại: https://trello.com/app-key
2. Điền Key và Token vào bên dưới và chạy lệnh: python import_to_trello.py
"""

import sys
import time
import requests

# Cấu hình UTF-8 cho Windows console
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

# === ĐIỀN THÔNG TIN TRELLO CỦA BẠN VÀO ĐÂY ===
# 1. Truy cập https://trello.com/app-key để lấy Key
# 2. Bấm vào link "Generate a Token" để lấy Token
TRELLO_API_KEY = "YOUR_API_KEY_HERE"
TRELLO_TOKEN = "YOUR_TOKEN_HERE"

# Danh sách 28 Tasks chuẩn WBS của đề tài
TASKS = [
    # CỘT DONE (ĐÃ HOÀN THÀNH)
    {
        "id": "TASK-01",
        "name": "[TASK-01] Khảo sát phần cứng máy (RTX 3050 4GB) & tài liệu đề tài",
        "status": "done",
        "member": "TV1 (Lead/AI)",
        "priority": "Cao",
        "color": "blue",
        "desc": "**Giai đoạn:** GĐ 1: MVP Core\n**Người phụ trách:** Thành viên 1 (Lead / AI Specialist)\n**Độ ưu tiên:** Cao\n**Kết quả bàn giao:** File 01_So_Sanh_Va_Lua_Chon_Mo_Hinh_AI.md\n**Ghi chú:** Đã đo đạc GPU 4GB VRAM, 16GB RAM và cấu hình Golden Stack."
    },
    {
        "id": "TASK-02",
        "name": "[TASK-02] So sánh định lượng 6 họ LLM & chọn Qwen 2.5 3B",
        "status": "done",
        "member": "TV1 (Lead/AI)",
        "priority": "Cao",
        "color": "blue",
        "desc": "**Giai đoạn:** GĐ 1: MVP Core\n**Người phụ trách:** Thành viên 1\n**Độ ưu tiên:** Cao\n**Kết quả bàn giao:** Ma trận so sánh định lượng LLM\n**Ghi chú:** Chọn Qwen 2.5 3B chạy 100% VRAM GPU và BGE-M3 trên CPU."
    },
    {
        "id": "TASK-03",
        "name": "[TASK-03] Thiết kế kiến trúc phân tầng, SQLite Schema & API Spec",
        "status": "done",
        "member": "TV2 (Backend)",
        "priority": "Cao",
        "color": "purple",
        "desc": "**Giai đoạn:** GĐ 1: MVP Core\n**Người phụ trách:** Thành viên 2 (Backend & Data)\n**Độ ưu tiên:** Cao\n**Kết quả bàn giao:** File 02_Kien_Truc_He_Thong_Va_Ky_Thuat.md\n**Ghi chú:** Thiết kế 6 bảng SQLite, FTS5 BM25, API RESTful và SSE Stream."
    },
    {
        "id": "TASK-04",
        "name": "[TASK-04] Cài đặt Ollama & tải model Qwen 2.5 3B chạy trên GPU",
        "status": "done",
        "member": "TV1 (Lead/AI)",
        "priority": "Cao",
        "color": "blue",
        "desc": "**Giai đoạn:** GĐ 1: MVP Core\n**Người phụ trách:** Thành viên 1\n**Độ ưu tiên:** Cao\n**Kết quả bàn giao:** Ollama local cổng 11434 với model qwen2.5:3b (1.9GB)\n**Ghi chú:** Đã chạy thử nghiệm sinh text tiếng Việt cực nhanh (>40 tok/s)."
    },
    {
        "id": "TASK-05",
        "name": "[TASK-05] Bộ Document Parser bóc tách sạch file PDF, DOCX, PPTX, TXT",
        "status": "done",
        "member": "TV2 (Backend)",
        "priority": "Cao",
        "color": "purple",
        "desc": "**Giai đoạn:** GĐ 1: MVP Core\n**Người phụ trách:** Thành viên 2\n**Độ ưu tiên:** Cao\n**Kết quả bàn giao:** Module document_service.py\n**Ghi chú:** Hỗ trợ bóc tách slide PPTX, văn bản DOCX, trang PDF sạch sẽ."
    },
    {
        "id": "TASK-06",
        "name": "[TASK-06] Thuật toán Smart Recursive Text Chunking kèm metadata",
        "status": "done",
        "member": "TV2 (Backend)",
        "priority": "Cao",
        "color": "purple",
        "desc": "**Giai đoạn:** GĐ 1: MVP Core\n**Người phụ trách:** Thành viên 2\n**Độ ưu tiên:** Cao\n**Kết quả bàn giao:** Hàm recursive_chunk_text\n**Ghi chú:** Chunk size ~800 ký tự, overlap 150 ký tự giữ trọn ngữ cảnh."
    },
    {
        "id": "TASK-07",
        "name": "[TASK-07] CSDL SQLite knowledge.db & Full-Text Search FTS5 (BM25)",
        "status": "done",
        "member": "TV2 (Backend)",
        "priority": "Cao",
        "color": "purple",
        "desc": "**Giai đoạn:** GĐ 1: MVP Core\n**Người phụ trách:** Thành viên 2\n**Độ ưu tiên:** Cao\n**Kết quả bàn giao:** File knowledge.db và database.py\n**Ghi chú:** Tìm kiếm từ khóa cực nhanh, zero-setup không cần Docker."
    },
    {
        "id": "TASK-08",
        "name": "[TASK-08] Lõi AI Service: Trò chuyện + Tổng hợp ý nghĩa + Trích dẫn",
        "status": "done",
        "member": "TV1 (Lead/AI)",
        "priority": "Cao",
        "color": "blue",
        "desc": "**Giai đoạn:** GĐ 1: MVP Core\n**Người phụ trách:** Thành viên 1\n**Độ ưu tiên:** Cao\n**Kết quả bàn giao:** Module llm_service.py\n**Ghi chú:** Prompt đọc hiểu bản chất, chào hỏi tự nhiên, trích dẫn [Tài liệu X]."
    },
    {
        "id": "TASK-09",
        "name": "[TASK-09] Giao diện Web UI MVP kéo-thả upload file & chat RAG",
        "status": "done",
        "member": "TV3 (Frontend)",
        "priority": "Cao",
        "color": "green",
        "desc": "**Giai đoạn:** GĐ 1: MVP Core\n**Người phụ trách:** Thành viên 3 (Frontend & Feature Dev)\n**Độ ưu tiên:** Cao\n**Kết quả bàn giao:** File static/index.html\n**Ghi chú:** Giao diện kéo thả file, badge Ollama, chat bubbles đẹp mắt."
    },
    {
        "id": "TASK-10",
        "name": "[TASK-10] Script 1-click start_app.bat & kiểm thử trọn vẹn luồng RAG",
        "status": "done",
        "member": "Cả nhóm",
        "priority": "Cao",
        "color": "orange",
        "desc": "**Giai đoạn:** GĐ 1: MVP Core\n**Người phụ trách:** Cả nhóm\n**Độ ưu tiên:** Cao\n**Kết quả bàn giao:** File start_app.bat chạy hoàn hảo\n**Ghi chú:** Nạp file Tong_quan_de_tai.docx và trả lời chính xác kèm 4 trích dẫn."
    },

    # CỘT IN PROGRESS (ĐANG THỰC HIỆN)
    {
        "id": "TASK-11",
        "name": "[TASK-11] Tích hợp thư viện fastembed & Dense Embedding BGE-M3",
        "status": "inprogress",
        "member": "TV1 (Lead/AI)",
        "priority": "Cao",
        "color": "blue",
        "desc": "**Giai đoạn:** GĐ 2: Hybrid RAG\n**Người phụ trách:** Thành viên 1\n**Độ ưu tiên:** Cao\n**Kết quả bàn giao:** Module embedding_service.py sinh vector 1024 dims\n**Ghi chú:** Đã cài fastembed và onnxruntime, đang viết code nhúng vector."
    },
    {
        "id": "TASK-12",
        "name": "[TASK-12] Triển khai thuật toán Reciprocal Rank Fusion (RRF)",
        "status": "inprogress",
        "member": "TV1 (Lead/AI)",
        "priority": "Cao",
        "color": "blue",
        "desc": "**Giai đoạn:** GĐ 2: Hybrid RAG\n**Người phụ trách:** Thành viên 1\n**Độ ưu tiên:** Cao\n**Kết quả bàn giao:** Hàm reciprocal_rank_fusion(dense_hits, sparse_hits)\n**Ghi chú:** Gộp kết quả tìm kiếm ngữ nghĩa và từ khóa FTS5."
    },
    {
        "id": "TASK-14",
        "name": "[TASK-14] Citation Viewer Modal: Click vào trích dẫn xem đoạn trích gốc",
        "status": "inprogress",
        "member": "TV3 (Frontend)",
        "priority": "Trung bình",
        "color": "green",
        "desc": "**Giai đoạn:** GĐ 2: Hybrid RAG\n**Người phụ trách:** Thành viên 3\n**Độ ưu tiên:** Trung bình\n**Kết quả bàn giao:** Popup modal xem đoạn văn bản gốc khi bấm trích dẫn\n**Ghi chú:** Đang hoàn thiện modal hiển thị số trang và bôi vàng đoạn trích."
    },

    # CỘT TO DO (CẦN LÀM)
    {
        "id": "TASK-13",
        "name": "[TASK-13] Tích hợp Cross-Encoder Reranker (bge-reranker-v2-m3)",
        "status": "todo",
        "member": "TV1 (Lead/AI)",
        "priority": "Cao",
        "color": "blue",
        "desc": "**Giai đoạn:** GĐ 2: Hybrid RAG\n**Người phụ trách:** Thành viên 1\n**Độ ưu tiên:** Cao\n**Kết quả bàn giao:** Module reranker_service.py chấm điểm Top-4\n**Ghi chú:** Loại bỏ hoàn toàn các đoạn văn bản nhiễu trước khi cấp cho LLM."
    },
    {
        "id": "TASK-15",
        "name": "[TASK-15] Xây dựng Network Monitor & Giới hạn VRAM GPU < 3.5GB",
        "status": "todo",
        "member": "TV2 (Backend)",
        "priority": "Trung bình",
        "color": "purple",
        "desc": "**Giai đoạn:** GĐ 3: Offline-First\n**Người phụ trách:** Thành viên 2\n**Độ ưu tiên:** Trung bình\n**Kết quả bàn giao:** Module kiểm soát bộ nhớ an toàn\n**Ghi chú:** Đảm bảo hệ thống ngắt mạng 100% vẫn chạy tốt, không bị tràn VRAM."
    },
    {
        "id": "TASK-16",
        "name": "[TASK-16] Nút gạt chuyển đổi linh hoạt Qwen 3B (Fast) & 7B (Deep)",
        "status": "todo",
        "member": "TV3 + TV1",
        "priority": "Trung bình",
        "color": "green",
        "desc": "**Giai đoạn:** GĐ 3: Offline-First\n**Người phụ trách:** Thành viên 3 + Thành viên 1\n**Độ ưu tiên:** Trung bình\n**Kết quả bàn giao:** Model Switcher trên giao diện chat\n**Ghi chú:** Cho phép người dùng chuyển nhanh giữa tốc độ và độ thông minh."
    },
    {
        "id": "TASK-17",
        "name": "[TASK-17] Tích hợp DuckDuckGo Search API tra cứu Internet",
        "status": "todo",
        "member": "TV2 (Backend)",
        "priority": "Cao",
        "color": "purple",
        "desc": "**Giai đoạn:** GĐ 4: Online Search\n**Người phụ trách:** Thành viên 2\n**Độ ưu tiên:** Cao\n**Kết quả bàn giao:** Module web_search_service.py\n**Ghi chú:** Tìm kiếm tin tức mới nhất từ internet không tốn phí API key."
    },
    {
        "id": "TASK-18",
        "name": "[TASK-18] Web Content Extractor làm sạch HTML & gắn link URL",
        "status": "todo",
        "member": "TV2 (Backend)",
        "priority": "Trung bình",
        "color": "purple",
        "desc": "**Giai đoạn:** GĐ 4: Online Search\n**Người phụ trách:** Thành viên 2\n**Độ ưu tiên:** Trung bình\n**Kết quả bàn giao:** Bộ cào bài viết web dùng trafilatura\n**Ghi chú:** Bóc tách bài viết bỏ qua quảng cáo, trích dẫn link nguồn."
    },
    {
        "id": "TASK-19",
        "name": "[TASK-19] AI Router: Intent Classifier & Time-sensitive Detector",
        "status": "todo",
        "member": "TV1 (Lead/AI)",
        "priority": "Cao",
        "color": "blue",
        "desc": "**Giai đoạn:** GĐ 5: AI Router\n**Người phụ trách:** Thành viên 1\n**Độ ưu tiên:** Cao\n**Kết quả bàn giao:** Module router_service.py\n**Ghi chú:** Tự động phát hiện câu hỏi cần tin mới (Web) hoặc câu hỏi tài liệu (Local)."
    },
    {
        "id": "TASK-20",
        "name": "[TASK-20] Cơ chế Fallback tự động khi mất mạng hoặc Web lỗi",
        "status": "todo",
        "member": "TV2 (Backend)",
        "priority": "Cao",
        "color": "purple",
        "desc": "**Giai đoạn:** GĐ 5: AI Router\n**Người phụ trách:** Thành viên 2\n**Độ ưu tiên:** Cao\n**Kết quả bàn giao:** Logic Fallback mượt mà trong API chat\n**Ghi chú:** Khi tra web mất mạng -> tự chuyển về Local RAG kèm thông báo."
    },
    {
        "id": "TASK-21",
        "name": "[TASK-21] Backend API sinh Tóm tắt, Flashcard và Quiz",
        "status": "todo",
        "member": "TV2 (Backend)",
        "priority": "Cao",
        "color": "purple",
        "desc": "**Giai đoạn:** GĐ 6: Học Tập\n**Người phụ trách:** Thành viên 2\n**Độ ưu tiên:** Cao\n**Kết quả bàn giao:** Endpoints /api/v1/study/*\n**Ghi chú:** Lưu dữ liệu vào bảng study_artifacts."
    },
    {
        "id": "TASK-22",
        "name": "[TASK-22] Màn hình Study Center: Flashcard lật mặt & Bảng Quiz",
        "status": "todo",
        "member": "TV3 (Frontend)",
        "priority": "Cao",
        "color": "green",
        "desc": "**Giai đoạn:** GĐ 6: Học Tập\n**Người phụ trách:** Thành viên 3\n**Độ ưu tiên:** Cao\n**Kết quả bàn giao:** Màn hình tương tác Flashcard & Quiz\n**Ghi chú:** Thẻ bài lật mặt và bài test trắc nghiệm chấm điểm tự động."
    },
    {
        "id": "TASK-23",
        "name": "[TASK-23] Thuật toán đối chiếu và so sánh đa tài liệu (Multi-doc)",
        "status": "todo",
        "member": "TV1 (Lead/AI)",
        "priority": "Trung bình",
        "color": "blue",
        "desc": "**Giai đoạn:** GĐ 7: Research Assistant\n**Người phụ trách:** Thành viên 1\n**Độ ưu tiên:** Trung bình\n**Kết quả bàn giao:** Cơ chế so sánh quan điểm giữa 2-3 tài liệu\n**Ghi chú:** Tìm điểm chung, điểm khác biệt và khoảng trống nghiên cứu."
    },
    {
        "id": "TASK-24",
        "name": "[TASK-24] Tính năng xuất báo cáo nghiên cứu dạng Markdown/PDF",
        "status": "todo",
        "member": "TV3 (Frontend)",
        "priority": "Trung bình",
        "color": "green",
        "desc": "**Giai đoạn:** GĐ 7: Research Assistant\n**Người phụ trách:** Thành viên 3\n**Độ ưu tiên:** Trung bình\n**Kết quả bàn giao:** Nút xuất báo cáo kèm References\n**Ghi chú:** Hỗ trợ tải xuống file .md hoặc in PDF định dạng chuẩn khoa học."
    },
    {
        "id": "TASK-25",
        "name": "[TASK-25] Xây dựng bộ test Benchmark 50 câu hỏi tiếng Việt",
        "status": "todo",
        "member": "TV1 (Lead/AI)",
        "priority": "Cao",
        "color": "blue",
        "desc": "**Giai đoạn:** GĐ 8: Benchmark & Báo Cáo\n**Người phụ trách:** Thành viên 1\n**Độ ưu tiên:** Cao\n**Kết quả bàn giao:** File evaluation_dataset.json\n**Ghi chú:** 20 câu trích xuất, 15 câu tổng hợp, 15 câu thời sự web."
    },
    {
        "id": "TASK-26",
        "name": "[TASK-26] Đo lường định lượng Hit Rate@5, MRR, Ragas Faithfulness",
        "status": "todo",
        "member": "TV1 (Lead/AI)",
        "priority": "Cao",
        "color": "blue",
        "desc": "**Giai đoạn:** GĐ 8: Benchmark & Báo Cáo\n**Người phụ trách:** Thành viên 1\n**Độ ưu tiên:** Cao\n**Kết quả bàn giao:** Biểu đồ khoa học chứng minh hiệu quả\n**Ghi chú:** So sánh Dense vs BM25 vs Hybrid RAG có Reranker."
    },
    {
        "id": "TASK-27",
        "name": "[TASK-27] Viết toàn bộ Báo cáo Thuyết minh Đồ án PBL6",
        "status": "todo",
        "member": "Cả nhóm",
        "priority": "Cao",
        "color": "orange",
        "desc": "**Giai đoạn:** GĐ 8: Benchmark & Báo Cáo\n**Người phụ trách:** Cả nhóm\n**Độ ưu tiên:** Cao\n**Kết quả bàn giao:** Bản báo cáo đề tài đầy đủ các chương\n**Ghi chú:** TV1 viết chương AI/RAG; TV2 viết Backend/DB; TV3 viết UI/Kết quả."
    },
    {
        "id": "TASK-28",
        "name": "[TASK-28] Thiết kế Slide thuyết trình bảo vệ & quay Video Demo",
        "status": "todo",
        "member": "TV3 (Frontend)",
        "priority": "Cao",
        "color": "green",
        "desc": "**Giai đoạn:** GĐ 8: Benchmark & Báo Cáo\n**Người phụ trách:** Thành viên 3\n**Độ ưu tiên:** Cao\n**Kết quả bàn giao:** Bộ Slide PPTX & Video demo 5 phút\n**Ghi chú:** Chuẩn nhận diện trường và video demo rõ ràng các chức năng."
    }
]

def main():
    print("="*60)
    print("🚀 BẮT ĐẦU QUÁ TRÌNH TỰ ĐỘNG TẠO BẢNG & NẠP THẺ VÀO TRELLO")
    print("="*60)

    api_key = TRELLO_API_KEY.strip()
    token = TRELLO_TOKEN.strip()

    if api_key == "YOUR_API_KEY_HERE" or token == "YOUR_TOKEN_HERE" or not api_key or not token:
        print("\n⚠️ CHƯA CÓ API KEY HOẶC TOKEN!")
        print("Vui lòng lấy API Key và Token tại: https://trello.com/app-key")
        api_key = input("👉 Nhập Trello API Key: ").strip()
        token = input("👉 Nhập Trello Token: ").strip()

    auth_params = {"key": api_key, "token": token}

    # 1. Tạo Board mới trên Trello
    print("\n1. Đang tạo Board mới: 'PBL6 - Personal AI Knowledge Platform'...")
    board_url = "https://api.trello.com/1/boards/"
    board_payload = {
        **auth_params,
        "name": "PBL6 - Personal AI Knowledge Platform",
        "defaultLists": "false", # Không tạo các list mặc định để tự tạo theo chuẩn
        "prefs_background": "blue"
    }
    resp = requests.post(board_url, params=board_payload)
    if resp.status_code != 200:
        print(f"❌ Lỗi khi tạo Board: {resp.status_code} - {resp.text}")
        return

    board_id = resp.json()["id"]
    board_short_url = resp.json().get("shortUrl", f"https://trello.com/b/{board_id}")
    print(f"✅ Đã tạo thành công Board: {board_short_url}")

    # 2. Tạo 3 cột (Lists): Done, In Progress, To Do
    print("\n2. Đang tạo 3 cột (Lists) theo chuẩn Kanban...")
    list_url = f"https://api.trello.com/1/boards/{board_id}/lists"
    
    # Thứ tự hiển thị: To Do -> In Progress -> Done
    cols = {}
    for col_name, col_key in [("📋 Cần Làm (To Do)", "todo"), ("🚧 Đang Làm (In Progress)", "inprogress"), ("✅ Đã Xong (Done)", "done")]:
        r = requests.post(list_url, params={**auth_params, "name": col_name, "pos": "bottom"})
        if r.status_code == 200:
            cols[col_key] = r.json()["id"]
            print(f"   + Đã tạo cột: {col_name}")
        time.sleep(0.3)

    # 3. Tạo các Labels (Nhãn màu theo thành viên)
    print("\n3. Đang tạo Nhãn phân loại thành viên...")
    label_url = f"https://api.trello.com/1/boards/{board_id}/labels"
    labels = {}
    label_defs = [
        ("🔵 TV1: AI Specialist", "blue", "blue"),
        ("🟣 TV2: Backend & Data", "purple", "purple"),
        ("🟢 TV3: Frontend & UI", "green", "green"),
        ("👥 Cả nhóm", "orange", "orange"),
        ("🔴 Ưu tiên Cao", "red", "red")
    ]
    for name, color, key in label_defs:
        r = requests.post(label_url, params={**auth_params, "name": name, "color": color})
        if r.status_code == 200:
            labels[key] = r.json()["id"]
        time.sleep(0.2)

    # 4. Nạp 28 tasks vào từng cột
    print(f"\n4. Đang nạp {len(TASKS)} thẻ công việc vào các cột tương ứng...")
    card_url = "https://api.trello.com/1/cards"
    
    success_count = 0
    for i, t in enumerate(TASKS, 1):
        list_id = cols.get(t["status"])
        if not list_id:
            continue

        # Gắn nhãn màu
        id_labels = []
        if t["color"] in labels:
            id_labels.append(labels[t["color"]])
        if t["priority"] == "Cao" and "red" in labels:
            id_labels.append(labels["red"])

        card_payload = {
            **auth_params,
            "idList": list_id,
            "name": t["name"],
            "desc": t["desc"],
            "idLabels": ",".join(id_labels),
            "pos": "bottom"
        }

        r = requests.post(card_url, params=card_payload)
        if r.status_code == 200:
            print(f"   [{i}/{len(TASKS)}] ✅ Đã thêm: {t['id']}")
            success_count += 1
        else:
            print(f"   [{i}/{len(TASKS)}] ❌ Lỗi thêm {t['id']}: {r.status_code}")
        
        time.sleep(0.25) # Tránh bị Trello rate limit

    print("\n" + "="*60)
    print(f"🎉 HOÀN TẤT! Đã nạp thành công {success_count}/{len(TASKS)} thẻ lên Trello!")
    print(f"👉 Mở ngay bảng Trello của bạn tại: {board_short_url}")
    print("="*60)

if __name__ == "__main__":
    main()
