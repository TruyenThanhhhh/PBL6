import os
import csv
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

# Đường dẫn file xuất ra
XLSX_PATH = r"D:\PBl6\kehoach\Phan_Chia_Cong_Viec_Nhom_3_Nguoi_PBL6.xlsx"
CSV_PATH = r"D:\PBl6\kehoach\Phan_Chia_Cong_Viec_Nhom_3_Nguoi.csv"

# Danh sách công việc (WBS)
TASKS = [
    # GIAI ĐOẠN 1: MVP LOCAL CORE
    {
        "id": "TASK-01",
        "phase": "GĐ 1: MVP Local Core",
        "name": "Nghiên cứu tài liệu đề tài & phân tích phần cứng thực tế (RTX 3050 4GB)",
        "assignee": "Thành viên 1 (Lead / AI Specialist)",
        "priority": "Cao",
        "status": "Đã Hoàn Thành",
        "start": "Tuần 1",
        "deadline": "Tuần 1",
        "deliverable": "File 01_So_Sanh_Va_Lua_Chon_Mo_Hinh_AI.md",
        "notes": "Đã đo đạc GPU 4GB VRAM, RAM 16GB, CPU i5-12450H và đề xuất Golden Stack"
    },
    {
        "id": "TASK-02",
        "phase": "GĐ 1: MVP Local Core",
        "name": "So sánh định lượng các dòng LLM, Embedding, Reranker & Vector DB",
        "assignee": "Thành viên 1 (Lead / AI Specialist)",
        "priority": "Cao",
        "status": "Đã Hoàn Thành",
        "start": "Tuần 1",
        "deadline": "Tuần 1",
        "deliverable": "Ma trận so sánh 6 họ LLM & lựa chọn Qwen 2.5 3B",
        "notes": "Chọn Qwen 2.5 3B chạy 100% VRAM GPU, BGE-M3 trên CPU ONNX"
    },
    {
        "id": "TASK-03",
        "phase": "GĐ 1: MVP Local Core",
        "name": "Thiết kế kiến trúc hệ thống tổng thể, SQLite Schema & API Spec",
        "assignee": "Thành viên 2 (Backend & Data Engineer)",
        "priority": "Cao",
        "status": "Đã Hoàn Thành",
        "start": "Tuần 1",
        "deadline": "Tuần 2",
        "deliverable": "File 02_Kien_Truc_He_Thong_Va_Ky_Thuat.md",
        "notes": "Thiết kế 6 bảng SQLite, FTS5 BM25, API RESTful và SSE Stream"
    },
    {
        "id": "TASK-04",
        "phase": "GĐ 1: MVP Local Core",
        "name": "Cài đặt Ollama và kéo model Qwen 2.5 3B Instruct về máy",
        "assignee": "Thành viên 1 (Lead / AI Specialist)",
        "priority": "Cao",
        "status": "Đã Hoàn Thành",
        "start": "Tuần 2",
        "deadline": "Tuần 2",
        "deliverable": "Ollama local chạy cổng 11434 với model qwen2.5:3b (1.9GB)",
        "notes": "Đã tải xong 100%, test sinh text tiếng Việt cực nhanh (>40 tok/s)"
    },
    {
        "id": "TASK-05",
        "phase": "GĐ 1: MVP Local Core",
        "name": "Xây dựng Document Parser hỗ trợ PDF, DOCX, PPTX, TXT",
        "assignee": "Thành viên 2 (Backend & Data Engineer)",
        "priority": "Cao",
        "status": "Đã Hoàn Thành",
        "start": "Tuần 2",
        "deadline": "Tuần 2",
        "deliverable": "Module document_service.py hoàn chỉnh",
        "notes": "Đã hỗ trợ bóc tách slide PPTX, văn bản DOCX, trang PDF sạch sẽ"
    },
    {
        "id": "TASK-06",
        "phase": "GĐ 1: MVP Local Core",
        "name": "Phát triển thuật toán Smart Recursive Text Chunking kèm Metadata",
        "assignee": "Thành viên 2 (Backend & Data Engineer)",
        "priority": "Cao",
        "status": "Đã Hoàn Thành",
        "start": "Tuần 2",
        "deadline": "Tuần 2",
        "deliverable": "Hàm recursive_chunk_text trong document_service.py",
        "notes": "Chunk size ~800 ký tự, overlap 150 ký tự giữ trọn vẹn ngữ cảnh"
    },
    {
        "id": "TASK-07",
        "phase": "GĐ 1: MVP Local Core",
        "name": "Xây dựng SQLite CSDL và bảng FTS5 Full-Text Search BM25",
        "assignee": "Thành viên 2 (Backend & Data Engineer)",
        "priority": "Cao",
        "status": "Đã Hoàn Thành",
        "start": "Tuần 2",
        "deadline": "Tuần 2",
        "deliverable": "File knowledge.db và module database.py",
        "notes": "Chỉ mục tìm kiếm từ khóa cực nhanh, zero-setup không cần Docker"
    },
    {
        "id": "TASK-08",
        "phase": "GĐ 1: MVP Local Core",
        "name": "Xây dựng Retrieval & LLM Service: Trò chuyện + Tổng hợp ý nghĩa + Trích dẫn",
        "assignee": "Thành viên 1 (Lead / AI Specialist)",
        "priority": "Cao",
        "status": "Đã Hoàn Thành",
        "start": "Tuần 2",
        "deadline": "Tuần 2",
        "deliverable": "Module retrieval_service.py & llm_service.py",
        "notes": "Đã nâng cấp prompt đọc hiểu bản chất, chào hỏi tự nhiên, trích dẫn [Tài liệu X]"
    },
    {
        "id": "TASK-09",
        "phase": "GĐ 1: MVP Local Core",
        "name": "Xây dựng Giao diện Web MVP tương tác (Upload file, Chat RAG)",
        "assignee": "Thành viên 3 (Frontend & Feature Dev)",
        "priority": "Cao",
        "status": "Đã Hoàn Thành",
        "start": "Tuần 2",
        "deadline": "Tuần 2",
        "deliverable": "File static/index.html & API kết nối",
        "notes": "Giao diện kéo thả file, badge trạng thái Ollama, chat bubble đẹp mắt"
    },
    {
        "id": "TASK-10",
        "phase": "GĐ 1: MVP Local Core",
        "name": "Kiểm thử tích hợp luồng hỏi đáp Local RAG với tài liệu mẫu",
        "assignee": "Cả nhóm (Thành viên 1, 2, 3)",
        "priority": "Cao",
        "status": "Đã Hoàn Thành",
        "start": "Tuần 2",
        "deadline": "Tuần 2",
        "deliverable": "File start_app.bat chạy 1-click & log kiểm thử thành công",
        "notes": "Đã nạp file Tong_quan_de_tai.docx và trả lời chính xác kèm 4 trích dẫn"
    },

    # GIAI ĐOẠN 2: HYBRID RAG & RERANKER
    {
        "id": "TASK-11",
        "phase": "GĐ 2: Hybrid RAG",
        "name": "Tích hợp thư viện fastembed & Dense Embedding BGE-M3",
        "assignee": "Thành viên 1 (Lead / AI Specialist)",
        "priority": "Cao",
        "status": "Đang Thực Hiện",
        "start": "Tuần 3",
        "deadline": "Tuần 3",
        "deliverable": "Module embedding_service.py sinh vector 1024 dims",
        "notes": "Đã cài đặt fastembed & onnxruntime thành công trên máy, đang code module nhúng"
    },
    {
        "id": "TASK-12",
        "phase": "GĐ 2: Hybrid RAG",
        "name": "Triển khai thuật toán Reciprocal Rank Fusion (RRF) gộp Dense + BM25",
        "assignee": "Thành viên 1 (Lead / AI Specialist)",
        "priority": "Cao",
        "status": "Đang Thực Hiện",
        "start": "Tuần 3",
        "deadline": "Tuần 4",
        "deliverable": "Hàm reciprocal_rank_fusion(dense_hits, sparse_hits)",
        "notes": "Công thức RRF score = sum(1 / (60 + rank)) lấy Top 20 ứng viên"
    },
    {
        "id": "TASK-13",
        "phase": "GĐ 2: Hybrid RAG",
        "name": "Tích hợp Cross-Encoder Reranker (bge-reranker-v2-m3)",
        "assignee": "Thành viên 1 (Lead / AI Specialist)",
        "priority": "Cao",
        "status": "Chưa Bắt Đầu",
        "start": "Tuần 4",
        "deadline": "Tuần 4",
        "deliverable": "Module reranker_service.py chấm điểm Top 20 -> Top 4",
        "notes": "Chạy ONNX trên CPU để loại bỏ hoàn toàn các đoạn nhiễu"
    },
    {
        "id": "TASK-14",
        "phase": "GĐ 2: Hybrid RAG",
        "name": "Phát triển Citation Viewer Modal xem đoạn trích gốc trong tài liệu",
        "assignee": "Thành viên 3 (Frontend & Feature Dev)",
        "priority": "Trung bình",
        "status": "Đang Thực Hiện",
        "start": "Tuần 3",
        "deadline": "Tuần 4",
        "deliverable": "Giao diện popup hiển thị đoạn văn bản gốc khi bấm trích dẫn",
        "notes": "Người dùng click vào [Tài liệu 1] sẽ mở modal xem đúng trang và đoạn gốc"
    },

    # GIAI ĐOẠN 3: OFFLINE-FIRST & TỐI ƯU HÓA
    {
        "id": "TASK-15",
        "phase": "GĐ 3: Offline-First",
        "name": "Xây dựng Network Monitor & kiểm soát VRAM GPU < 3.5GB",
        "assignee": "Thành viên 2 (Backend & Data Engineer)",
        "priority": "Trung bình",
        "status": "Chưa Bắt Đầu",
        "start": "Tuần 5",
        "deadline": "Tuần 5",
        "deliverable": "Module network_guard.py & bộ giới hạn context window",
        "notes": "Đảm bảo máy ngắt mạng 100% vẫn chạy trơn tru, không bị tràn VRAM"
    },
    {
        "id": "TASK-16",
        "phase": "GĐ 3: Offline-First",
        "name": "Tính năng Toggle chuyển đổi linh hoạt Qwen 3B (Fast) & 7B (Deep)",
        "assignee": "Thành viên 3 (Frontend & Feature Dev)",
        "priority": "Trung bình",
        "status": "Chưa Bắt Đầu",
        "start": "Tuần 5",
        "deadline": "Tuần 5",
        "deliverable": "Nút gạt chuyển model trên giao diện người dùng",
        "notes": "Thành viên 1 cấu hình tham số Ollama, Thành viên 3 làm UI"
    },

    # GIAI ĐOẠN 4: ONLINE WEB SEARCH
    {
        "id": "TASK-17",
        "phase": "GĐ 4: Online Search",
        "name": "Tích hợp DuckDuckGo Search API tra cứu thông tin Internet",
        "assignee": "Thành viên 2 (Backend & Data Engineer)",
        "priority": "Cao",
        "status": "Chưa Bắt Đầu",
        "start": "Tuần 6",
        "deadline": "Tuần 6",
        "deliverable": "Module web_search_service.py không cần API Key",
        "notes": "Tìm kiếm kết quả web mới nhất khi người dùng hỏi sự kiện hiện tại"
    },
    {
        "id": "TASK-18",
        "phase": "GĐ 4: Online Search",
        "name": "Xây dựng Web Content Extractor làm sạch HTML & gắn trích dẫn URL",
        "assignee": "Thành viên 2 (Backend & Data Engineer)",
        "priority": "Trung bình",
        "status": "Chưa Bắt Đầu",
        "start": "Tuần 6",
        "deadline": "Tuần 6",
        "deliverable": "Hàm extract_web_text dùng trafilatura / BeautifulSoup",
        "notes": "Bóc tách bài viết bỏ qua quảng cáo, trích dẫn link gốc có thể click được"
    },

    # GIAI ĐOẠN 5: AI ROUTER & MULTI-SOURCE FUSION
    {
        "id": "TASK-19",
        "phase": "GĐ 5: AI Router",
        "name": "Phát triển AI Router: Intent Classifier & Time-sensitive Detector",
        "assignee": "Thành viên 1 (Lead / AI Specialist)",
        "priority": "Cao",
        "status": "Chưa Bắt Đầu",
        "start": "Tuần 7",
        "deadline": "Tuần 7",
        "deliverable": "Module router_service.py tự động phân loại Local/Web/Hybrid",
        "notes": "Tự phát hiện câu hỏi cần tin mới để bật web hoặc câu hỏi file để tra máy"
    },
    {
        "id": "TASK-20",
        "phase": "GĐ 5: AI Router",
        "name": "Triển khai cơ chế Fallback tự động khi Web lỗi hoặc mất mạng",
        "assignee": "Thành viên 2 (Backend & Data Engineer)",
        "priority": "Cao",
        "status": "Chưa Bắt Đầu",
        "start": "Tuần 7",
        "deadline": "Tuần 7",
        "deliverable": "Logic fallback mượt mà trong chat endpoint",
        "notes": "Khi tra web mất kết nối -> tự động chuyển sang tài liệu máy kèm thông báo"
    },

    # GIAI ĐOẠN 6: CÔNG CỤ HỖ TRỢ HỌC TẬP (LEARNING TOOLS)
    {
        "id": "TASK-21",
        "phase": "GĐ 6: Learning Tools",
        "name": "Xây dựng Backend sinh Tóm tắt, Flashcard và Quiz trắc nghiệm",
        "assignee": "Thành viên 2 (Backend & Data Engineer)",
        "priority": "Cao",
        "status": "Chưa Bắt Đầu",
        "start": "Tuần 8",
        "deadline": "Tuần 8",
        "deliverable": "Endpoints /api/v1/study/* và lưu bảng study_artifacts",
        "notes": "Prompt JSON có cấu trúc rõ ràng: câu hỏi, 4 đáp án, đáp án đúng và giải thích"
    },
    {
        "id": "TASK-22",
        "phase": "GĐ 6: Learning Tools",
        "name": "Phát triển Giao diện Học tập: Thẻ Flashcard lật mặt & Bảng Quiz",
        "assignee": "Thành viên 3 (Frontend & Feature Dev)",
        "priority": "Cao",
        "status": "Chưa Bắt Đầu",
        "start": "Tuần 8",
        "deadline": "Tuần 9",
        "deliverable": "Màn hình Study Center tương tác trực quan",
        "notes": "Animation lật thẻ Flashcard ghi nhớ từ khóa và làm bài test chấm điểm tự động"
    },

    # GIAI ĐOẠN 7: TRỢ LÝ NGHIÊN CỨU (RESEARCH ASSISTANT)
    {
        "id": "TASK-23",
        "phase": "GĐ 7: Research Assistant",
        "name": "Phát triển tính năng suy luận và đối chiếu đa tài liệu (Multi-doc reasoning)",
        "assignee": "Thành viên 1 (Lead / AI Specialist)",
        "priority": "Trung bình",
        "status": "Chưa Bắt Đầu",
        "start": "Tuần 10",
        "deadline": "Tuần 10",
        "deliverable": "Cơ chế so sánh quan điểm giữa các bài báo/tài liệu trong Workspace",
        "notes": "Cho phép chọn 2-3 tài liệu cùng lúc để yêu cầu so sánh ưu/nhược điểm"
    },
    {
        "id": "TASK-24",
        "phase": "GĐ 7: Research Assistant",
        "name": "Tính năng xuất báo cáo nghiên cứu tổng hợp dạng Markdown/PDF",
        "assignee": "Thành viên 3 (Frontend & Feature Dev)",
        "priority": "Trung bình",
        "status": "Chưa Bắt Đầu",
        "start": "Tuần 10",
        "deadline": "Tuần 11",
        "deliverable": "Nút xuất báo cáo kèm mục References chuẩn APA",
        "notes": "Hỗ trợ tải xuống file .md hoặc in PDF định dạng chuẩn khoa học"
    },

    # GIAI ĐOẠN 8: BENCHMARK & NGHIỆM THU ĐỒ ÁN
    {
        "id": "TASK-25",
        "phase": "GĐ 8: Benchmark & Báo Cáo",
        "name": "Xây dựng bộ dữ liệu kiểm thử Benchmark 50 câu hỏi tiếng Việt",
        "assignee": "Thành viên 1 (Lead / AI Specialist)",
        "priority": "Cao",
        "status": "Chưa Bắt Đầu",
        "start": "Tuần 11",
        "deadline": "Tuần 11",
        "deliverable": "File evaluation_dataset.json có sẵn ground-truth",
        "notes": "Phân chia: 20 câu trích xuất chính xác, 15 câu tổng hợp ý, 15 câu web/thời sự"
    },
    {
        "id": "TASK-26",
        "phase": "GĐ 8: Benchmark & Báo Cáo",
        "name": "Đo lường định lượng: Hit Rate@5, MRR, Faithfulness bằng framework Ragas",
        "assignee": "Thành viên 1 (Lead / AI Specialist)",
        "priority": "Cao",
        "status": "Chưa Bắt Đầu",
        "start": "Tuần 12",
        "deadline": "Tuần 12",
        "deliverable": "Biểu đồ so sánh Dense vs BM25 vs Hybrid RAG",
        "notes": "Chứng minh sự vượt trội của Hybrid RAG có Reranker so với RAG truyền thống"
    },
    {
        "id": "TASK-27",
        "phase": "GĐ 8: Benchmark & Báo Cáo",
        "name": "Viết toàn bộ Báo cáo Thuyết minh Đồ án PBL6",
        "assignee": "Cả nhóm (Thành viên 1, 2, 3)",
        "priority": "Cao",
        "status": "Chưa Bắt Đầu",
        "start": "Tuần 11",
        "deadline": "Tuần 12",
        "deliverable": "File Word / PDF báo cáo đề tài đầy đủ các chương",
        "notes": "TV1 viết chương AI/RAG; TV2 viết chương Backend/DB; TV3 viết chương UI/Kết quả"
    },
    {
        "id": "TASK-28",
        "phase": "GĐ 8: Benchmark & Báo Cáo",
        "name": "Thiết kế Slide thuyết trình bảo vệ đồ án & quay Video Demo sản phẩm",
        "assignee": "Thành viên 3 (Frontend & Feature Dev)",
        "priority": "Cao",
        "status": "Chưa Bắt Đầu",
        "start": "Tuần 12",
        "deadline": "Tuần 12",
        "deliverable": "Bộ Slide PPTX chuyên nghiệp & video demo 5 phút",
        "notes": "Slide chuẩn nhận diện trường, video demo rõ nét các chức năng cốt lõi"
    }
]

def create_excel():
    wb = openpyxl.Workbook()
    
    # ------------------ SHEET 1: TỔNG QUAN ------------------
    ws1 = wb.active
    ws1.title = "Tong_Quan_Tien_Do"
    ws1.views.sheetView[0].showGridLines = True
    
    font_title = Font(name="Segoe UI", size=16, bold=True, color="1E3A8A")
    font_sub = Font(name="Segoe UI", size=11, italic=True, color="475569")
    font_header = Font(name="Segoe UI", size=10, bold=True, color="FFFFFF")
    font_sec = Font(name="Segoe UI", size=12, bold=True, color="0F172A")
    font_normal = Font(name="Segoe UI", size=10, color="1E293B")
    
    fill_blue_dark = PatternFill(start_color="1E40AF", end_color="1E40AF", fill_type="solid")
    fill_blue_light = PatternFill(start_color="3B82F6", end_color="3B82F6", fill_type="solid")
    
    thin_border = Border(
        left=Side(style='thin', color='CBD5E1'),
        right=Side(style='thin', color='CBD5E1'),
        top=Side(style='thin', color='CBD5E1'),
        bottom=Side(style='thin', color='CBD5E1')
    )
    
    ws1.merge_cells("A1:G1")
    ws1["A1"] = "BẢNG ĐIỀU PHỐI VÀ TIẾN ĐỘ DỰ ÁN PBL6 (NHÓM 3 THÀNH VIÊN)"
    ws1["A1"].font = font_title
    ws1["A1"].alignment = Alignment(horizontal="center", vertical="center")
    
    ws1.merge_cells("A2:G2")
    ws1["A2"] = "Đề tài: Nền tảng Trợ lý Tri thức Cá nhân Đa nguồn (Hybrid RAG + Local LLM)"
    ws1["A2"].font = font_sub
    ws1["A2"].alignment = Alignment(horizontal="center", vertical="center")
    
    # Bảng phân chia vai trò
    ws1["A4"] = "1. PHÂN CÔNG VAI TRÒ VÀ TRÁCH NHIỆM TRONG NHÓM"
    ws1["A4"].font = font_sec
    
    headers1 = ["STT", "Vai Trò", "Phạm Vi Trách Nhiệm", "Thành Viên Đảm Nhận", "Tasks Đảm Nhận", "Tiến Độ Hoàn Thành"]
    for c_idx, h in enumerate(headers1, 1):
        cell = ws1.cell(row=5, column=c_idx, value=h)
        cell.font = font_header
        cell.fill = fill_blue_dark
        cell.alignment = Alignment(horizontal="center", vertical="center")
        
    roles = [
        [1, "Thành viên 1 (Lead & AI Specialist)", "Lõi AI, Mô hình LLM (Ollama), Dense Embedding (BGE-M3), Reranker, RRF Fusion, Prompt Engineering, Benchmark Ragas", "Bạn (Trưởng nhóm)", "11 Tasks", "45% (Đã xong MVP AI)"],
        [2, "Thành viên 2 (Backend & Data Engineer)", "Pipeline trích xuất tài liệu (PDF/DOCX/PPTX), CSDL SQLite FTS5, API FastAPI, Web Search, AI Router, Network Fallback", "Thành viên 2", "10 Tasks", "40% (Đã xong Parser & FTS5)"],
        [3, "Thành viên 3 (Frontend & Feature Dev)", "Giao diện Web/Desktop UI, Quản lý Workspace, Citation Viewer Popup, Tính năng Học tập (Flashcard/Quiz), Báo cáo & Slide", "Thành viên 3", "7 Tasks", "30% (Đã xong Web UI MVP)"]
    ]
    for r_idx, row in enumerate(roles, 6):
        for c_idx, val in enumerate(row, 1):
            cell = ws1.cell(row=r_idx, column=c_idx, value=val)
            cell.font = font_normal
            cell.border = thin_border
            cell.alignment = Alignment(horizontal="center" if c_idx in [1, 5, 6] else "left", vertical="center")
            
    # Thống kê tiến độ task
    ws1["A10"] = "2. THỐNG KÊ TIẾN ĐỘ CÔNG VIỆC TỔNG THỂ"
    ws1["A10"].font = font_sec
    
    headers2 = ["Trạng Thái Công Việc", "Số Lượng Task", "Tỷ Lệ Phần Trăm", "Nhận Xét & Đánh Giá Hiện Trạng"]
    for c_idx, h in enumerate(headers2, 1):
        cell = ws1.cell(row=11, column=c_idx, value=h)
        cell.font = font_header
        cell.fill = fill_blue_light
        cell.alignment = Alignment(horizontal="center", vertical="center")
        
    done_count = sum(1 for t in TASKS if t["status"] == "Đã Hoàn Thành")
    in_prog_count = sum(1 for t in TASKS if t["status"] == "Đang Thực Hiện")
    todo_count = sum(1 for t in TASKS if t["status"] == "Chưa Bắt Đầu")
    total_count = len(TASKS)
    
    stats = [
        ["Đã Hoàn Thành (Done)", done_count, f"{(done_count/total_count)*100:.1f}%", "Đã hoàn thành xuất sắc Giai đoạn 1 (MVP Local Core + Ollama Qwen 3B + Web UI)"],
        ["Đang Thực Hiện (In Progress)", in_prog_count, f"{(in_prog_count/total_count)*100:.1f}%", "Đang tích hợp thư viện fastembed BGE-M3 Dense Vector và Citation Modal"],
        ["Chưa Bắt Đầu (To Do)", todo_count, f"{(todo_count/total_count)*100:.1f}%", "Các tính năng tiếp theo: Web Search, AI Router, Quiz/Flashcard, Benchmark"],
        ["Tổng Cộng", total_count, "100.0%", "Toàn bộ 28 đầu việc phân bổ đều cho 8 giai đoạn của đồ án PBL6"]
    ]
    for r_idx, row in enumerate(stats, 12):
        for c_idx, val in enumerate(row, 1):
            cell = ws1.cell(row=r_idx, column=c_idx, value=val)
            cell.font = Font(name="Segoe UI", size=10, bold=(r_idx==15), color="1E293B")
            cell.border = thin_border
            cell.alignment = Alignment(horizontal="center" if c_idx in [2, 3] else "left", vertical="center")
            if c_idx == 1:
                if "Hoàn Thành" in str(val): cell.fill = PatternFill(start_color="DCFCE7", end_color="DCFCE7", fill_type="solid")
                elif "Đang Thực Hiện" in str(val): cell.fill = PatternFill(start_color="FEF9C3", end_color="FEF9C3", fill_type="solid")
                elif "Chưa Bắt Đầu" in str(val): cell.fill = PatternFill(start_color="F1F5F9", end_color="F1F5F9", fill_type="solid")

    # ------------------ SHEET 2: PHÂN CÔNG CHI TIẾT (WBS) ------------------
    ws2 = wb.create_sheet("Phan_Cong_Chi_Tiet_WBS")
    ws2.views.sheetView[0].showGridLines = True
    
    headers_wbs = [
        "Mã Task", "Giai Đoạn", "Tên Công Việc Chi Tiết", "Người Phụ Trách", 
        "Độ Ưu Tiên", "Trạng Thái", "Bắt Đầu", "Hạn Chót", "Kết Quả Bàn Giao (Deliverables)", "Ghi Chú Tiến Độ Thực Tế"
    ]
    for c_idx, h in enumerate(headers_wbs, 1):
        cell = ws2.cell(row=1, column=c_idx, value=h)
        cell.font = font_header
        cell.fill = fill_blue_dark
        cell.alignment = Alignment(horizontal="center", vertical="center")
        
    for r_idx, t in enumerate(TASKS, 2):
        row_vals = [
            t["id"], t["phase"], t["name"], t["assignee"], t["priority"],
            t["status"], t["start"], t["deadline"], t["deliverable"], t["notes"]
        ]
        for c_idx, val in enumerate(row_vals, 1):
            cell = ws2.cell(row=r_idx, column=c_idx, value=val)
            cell.font = font_normal
            cell.border = thin_border
            
            # Căn lề
            if c_idx in [1, 5, 6, 7, 8]:
                cell.alignment = Alignment(horizontal="center", vertical="center")
            else:
                cell.alignment = Alignment(horizontal="left", vertical="center")
                
            # Tô màu trạng thái
            if c_idx == 6:
                if val == "Đã Hoàn Thành":
                    cell.fill = PatternFill(start_color="DCFCE7", end_color="DCFCE7", fill_type="solid")
                    cell.font = Font(name="Segoe UI", size=10, bold=True, color="166534")
                elif val == "Đang Thực Hiện":
                    cell.fill = PatternFill(start_color="FEF9C3", end_color="FEF9C3", fill_type="solid")
                    cell.font = Font(name="Segoe UI", size=10, bold=True, color="854D0E")
                else:
                    cell.fill = PatternFill(start_color="F1F5F9", end_color="F1F5F9", fill_type="solid")
                    cell.font = Font(name="Segoe UI", size=10, color="64748B")
                    
            if c_idx == 5:
                if val == "Cao":
                    cell.font = Font(name="Segoe UI", size=10, bold=True, color="B91C1C")
                else:
                    cell.font = Font(name="Segoe UI", size=10, color="475569")

    # ------------------ SHEET 3: CÔNG VIỆC ĐÃ HOÀN THÀNH ------------------
    ws3 = wb.create_sheet("Cong_Viec_Da_Hoan_Thanh")
    ws3.views.sheetView[0].showGridLines = True
    
    headers_done = ["Mã Task", "Giai Đoạn", "Hạng Mục Đã Xong", "Người Thực Hiện", "Kết Quả Bàn Giao", "Bằng Chứng Kiểm Thử Thực Tế"]
    for c_idx, h in enumerate(headers_done, 1):
        cell = ws3.cell(row=1, column=c_idx, value=h)
        cell.font = font_header
        cell.fill = PatternFill(start_color="166534", end_color="166534", fill_type="solid")
        cell.alignment = Alignment(horizontal="center", vertical="center")
        
    done_tasks = [t for t in TASKS if t["status"] == "Đã Hoàn Thành"]
    for r_idx, t in enumerate(done_tasks, 2):
        row_vals = [t["id"], t["phase"], t["name"], t["assignee"], t["deliverable"], t["notes"]]
        for c_idx, val in enumerate(row_vals, 1):
            cell = ws3.cell(row=r_idx, column=c_idx, value=val)
            cell.font = font_normal
            cell.border = thin_border
            cell.alignment = Alignment(horizontal="center" if c_idx == 1 else "left", vertical="center")

    # ------------------ SHEET 4: HƯỚNG DẪN IMPORT GOOGLE SHEETS ------------------
    ws4 = wb.create_sheet("Huong_Dan_Online_Sheet")
    ws4.views.sheetView[0].showGridLines = True
    
    ws4.merge_cells("A1:F1")
    ws4["A1"] = "HƯỚNG DẪN TẢI LÊN GOOGLE SHEETS ĐỂ LÀM VIỆC NHÓM ONLINE"
    ws4["A1"].font = font_title
    ws4["A1"].alignment = Alignment(horizontal="center", vertical="center")
    
    guides = [
        ["Bước 1", "Mở trình duyệt truy cập vào Google Drive cá nhân của bạn: https://drive.google.com"],
        ["Bước 2", "Bấm vào nút '+ Mới' (New) -> Chọn 'Tải tệp lên' (File upload)"],
        ["Bước 3", "Chọn file 'Phan_Chia_Cong_Viec_Nhom_3_Nguoi_PBL6.xlsx' tại thư mục 'D:\\PBl6\\kehoach\\'"],
        ["Bước 4", "Nhấp đúp vào file vừa tải lên trên Drive -> Chọn 'Mở bằng Google Trang tính' (Open with Google Sheets)"],
        ["Bước 5", "Bấm nút 'Chia sẻ' (Share) ở góc trên bên phải -> Thêm email của 2 thành viên còn lại (quyền Người chỉnh sửa - Editor)"],
        ["Bước 6", "Hàng tuần mỗi thành viên cập nhật cột 'Trạng Thái' và 'Ghi Chú Tiến Độ' để cả nhóm và giảng viên theo dõi realtime!"]
    ]
    for r_idx, (b, desc) in enumerate(guides, 3):
        cell_b = ws4.cell(row=r_idx, column=1, value=b)
        cell_b.font = Font(name="Segoe UI", size=10, bold=True, color="1E40AF")
        cell_b.alignment = Alignment(horizontal="center", vertical="center")
        cell_b.border = thin_border
        
        ws4.merge_cells(start_row=r_idx, start_column=2, end_row=r_idx, end_column=6)
        cell_desc = ws4.cell(row=r_idx, column=2, value=desc)
        cell_desc.font = font_normal
        cell_desc.alignment = Alignment(horizontal="left", vertical="center")
        cell_desc.border = thin_border

    # Tự động căn chỉnh độ rộng cột cho tất cả các sheet
    for ws in [ws1, ws2, ws3, ws4]:
        for col in ws.columns:
            max_len = 0
            col_letter = get_column_letter(col[0].column)
            for cell in col:
                val = str(cell.value or "")
                if len(val) > max_len and len(val) < 80: # tránh dãn cột quá to do tiêu đề merge
                    max_len = len(val)
            ws.column_dimensions[col_letter].width = max(max_len + 3, 12)
            
    # Điều chỉnh kích thước cụ thể cho Sheet WBS
    ws2.column_dimensions['A'].width = 12
    ws2.column_dimensions['B'].width = 20
    ws2.column_dimensions['C'].width = 38
    ws2.column_dimensions['D'].width = 30
    ws2.column_dimensions['E'].width = 14
    ws2.column_dimensions['F'].width = 18
    ws2.column_dimensions['G'].width = 12
    ws2.column_dimensions['H'].width = 12
    ws2.column_dimensions['I'].width = 38
    ws2.column_dimensions['J'].width = 45

    wb.save(XLSX_PATH)
    print(f"Đã tạo thành công file Excel: {XLSX_PATH}")

def create_csv():
    with open(CSV_PATH, mode='w', encoding='utf-8-sig', newline='') as f:
        writer = csv.writer(f)
        writer.writerow([
            "Mã Task", "Giai Đoạn", "Tên Công Việc", "Người Phụ Trách", 
            "Độ Ưu Tiên", "Trạng Thái", "Bắt Đầu", "Hạn Chót", "Kết Quả Bàn Giao", "Ghi Chú Tiến Độ"
        ])
        for t in TASKS:
            writer.writerow([
                t["id"], t["phase"], t["name"], t["assignee"], t["priority"],
                t["status"], t["start"], t["deadline"], t["deliverable"], t["notes"]
            ])
    print(f"Đã tạo thành công file CSV: {CSV_PATH}")

if __name__ == "__main__":
    create_excel()
    create_csv()
