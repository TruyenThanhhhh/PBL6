# Knowledge AI — Frontend

Giao diện React (Vite + TypeScript + Tailwind) cho Personal AI Knowledge Platform. Lấy cảm hứng tối giản từ Notion, bản sắc riêng Knowledge AI.

## Cài đặt và chạy

Yêu cầu: Node.js 20+.

```bash
cd sourcecode/frontend
npm install
npm run dev
```

Mở http://localhost:5173

Backend FastAPI (tuỳ chọn, cổng 8000):

```bash
cd sourcecode/backend
python run.py
```

Vite proxy `/api` → `http://127.0.0.1:8000`. Nếu backend tắt, UI vẫn chạy với **dữ liệu mô phỏng** (banner vàng).

```bash
npm run build
npm run preview
```

## Biến môi trường

Sao chép `.env.example` thành `.env`:

| Biến | Mô tả |
| --- | --- |
| `VITE_API_BASE_URL` | Để trống khi dùng proxy. Đặt `http://127.0.0.1:8000` nếu frontend không cùng origin. |

## Cấu trúc

```
src/
  app/                 # router
  components/layout/   # sidebar, header, shell
  components/ui/       # button, input, dialog, badge
  components/common/
  features/
    dashboard/
    workspaces/
    documents/
    chat/
    citations/
    source-viewer/
    study-tools/
    research/
    search/
    settings/
  services/            # API + mock
  hooks/
  store/               # Zustand
  types/
  utils/
```

## Tính năng đã triển khai

- Sidebar thu gọn, workspace, notebook, hội thoại, trạng thái kết nối
- Dashboard thao tác nhanh, danh sách, trạng thái hệ thống
- Kho tri thức: list/grid, tạo/sửa/xóa workspace & notebook
- Document manager: kéo thả, lọc, pipeline trạng thái, đổi tên/xóa/thử lại
- AI Chat: 4 chế độ, gợi ý, markdown, streaming mô phỏng, copy/tạo lại
- Citation panel + Source Viewer (văn bản trích xuất)
- Global search Ctrl/Cmd+K
- Study: tóm tắt, ghi chú, quiz chấm điểm, flashcard, mindmap, kế hoạch
- Research assistant: pipeline 6 bước, báo cáo, xuất Markdown
- Settings: theme, AI mặc định, Local LLM, privacy, kiểm tra backend
- Dark mode, toast, empty/error, responsive drawer

## Đang dùng mock data

Toàn bộ seed trong `src/services/mock-data.ts` và localStorage `knowledge-ai-store`:

- Workspace, notebook, tài liệu mẫu, ghi chú
- Hội thoại và citation mẫu
- Quiz, flashcard, báo cáo nghiên cứu
- Pipeline upload khi **không** có backend
- Chat Web/Hybrid khi chưa có Web Search API
- Streaming ký tự trên client (backend hiện trả JSON một lần)

Nhãn **Dữ liệu mô phỏng** / **mẫu** đánh dấu nội dung không phải dữ liệu máy chủ.

## Cần backend để chạy thật

Đã nối sẵn (khi FastAPI online):

- `GET /api/v1/status`
- `GET /api/v1/workspaces`
- `GET /api/v1/workspaces/{id}/documents`
- `POST /api/v1/workspaces/{id}/documents/upload`
- `DELETE /api/v1/documents/{id}`
- `POST /api/v1/chat/query` (chế độ Local/Auto)

Chưa có API tương ứng (UI mock):

- CRUD workspace/notebook/ghi chú/hội thoại
- Streaming SSE, Web Search, Hybrid router
- Chunk/page evidence đầy đủ, PDF viewer
- Study tools & research pipeline phía server
- Embedding/vector DB live status
