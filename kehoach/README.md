# THƯ MỤC TÀI LIỆU KẾ HOẠCH & ĐẶC TẢ KỸ THUẬT (PBL6)

Thư mục này chứa toàn bộ tài liệu nghiên cứu, so sánh mô hình, thiết kế kiến trúc và kế hoạch triển khai chi tiết cho đề tài:
**"XÂY DỰNG NỀN TẢNG TRỢ LÝ TRI THỨC CÁ NHÂN ĐA NGUỒN SỬ DỤNG HYBRID RAG VÀ LARGE LANGUAGE MODEL"**

---

### Danh mục tài liệu & Bảng tính:

1. **[Phan_Chia_Cong_Viec_Nhom_3_Nguoi_PBL6.xlsx](./Phan_Chia_Cong_Viec_Nhom_3_Nguoi_PBL6.xlsx)**
   * **Bảng tính Excel chuyên nghiệp** gồm 4 Sheets:
     * `Tong_Quan_Tien_Do`: Dashboard thống kê tiến độ, phân vai trò nhóm 3 người.
     * `Phan_Cong_Chi_Tiet_WBS`: Toàn bộ 28 tasks chi tiết, người phụ trách, deadline, deliverables.
     * `Cong_Viec_Da_Hoan_Thanh`: Bảng bàn giao các công việc đã làm xong kèm bằng chứng thực tế.
     * `Huong_Dan_Online_Sheet`: Hướng dẫn import lên Google Sheets để làm việc nhóm online.

2. **[04_Bang_Phan_Chia_Cong_Viec_Nhom_3_Nguoi.md](./04_Bang_Phan_Chia_Cong_Viec_Nhom_3_Nguoi.md)**
   * Bản báo cáo phân công công việc định dạng Markdown xem trực tiếp trên IDE/GitHub.
   * Danh mục 10 công việc đã hoàn thành và lộ trình các công việc tiếp theo cho 3 thành viên.

3. **[01_So_Sanh_Va_Lua_Chon_Mo_Hinh_AI.md](./01_So_Sanh_Va_Lua_Chon_Mo_Hinh_AI.md)**
   * Phân tích thông số phần cứng thực tế (NVIDIA RTX 3050 Laptop 4GB VRAM, 16GB RAM, Intel Core i5-12450H).
   * So sánh chi tiết các họ LLM mã nguồn mở (Qwen 2.5, Llama 3.2, Gemma 2, Phi-3.5, Vistral).
   * So sánh các Embedding Models đa ngữ (BGE-M3, Multilingual-E5, MiniLM) và Reranker Models.
   * Lựa chọn bộ cấu hình tối ưu: `Qwen 2.5 (3B/7B)` + `BAAI/bge-m3` + `bge-reranker-v2-m3`.

4. **[02_Kien_Truc_He_Thong_Va_Ky_Thuat.md](./02_Kien_Truc_He_Thong_Va_Ky_Thuat.md)**
   * Sơ đồ khối kiến trúc tổng thể phân lớp (Presentation, Backend, AI Core, Storage).
   * Đặc tả luồng Hybrid RAG Pipeline: Ingestion, Recursive Chunking, RRF và Rerank.
   * Thiết kế thuật toán AI Router (Auto, Local-first, Web Search, Hybrid, Network Fallback).
   * Toàn bộ Database Schema SQLite và Đặc tả API Endpoints RESTful + SSE Streaming.

5. **[03_Ke_Hoach_Trien_Khai_Va_Lo_Trinh.md](./03_Ke_Hoach_Trien_Khai_Va_Lo_Trinh.md)**
   * Lộ trình phát triển 8 giai đoạn từ MVP đến Advanced AI.
   * Bộ tiêu chí đánh giá định lượng Benchmark RAG (Hit Rate@K, MRR, Faithfulness, Answer Relevance).
   * Bảng phân tích rủi ro kỹ thuật và giải pháp dự phòng tương ứng.
