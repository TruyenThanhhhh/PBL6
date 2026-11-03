import type {
  AIMode,
  ChatMessage,
  Citation,
  Conversation,
  KnowledgeDocument,
} from "@/types"
import { queryChat, type ChatResult } from "@/services/api"
import { nowIso, uid } from "@/utils/format"

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? ""

/**
 * Thông tin mô tả từng chế độ AI (Auto, Local, Web, Hybrid)
 */
export interface AIModeDescriptor {
  id: AIMode
  label: string
  shortHint: string
  description: string
  requiresWebPermission?: boolean
  backendIntegrated: boolean
}

export const AI_MODE_DESCRIPTORS: AIModeDescriptor[] = [
  {
    id: "auto",
    label: "Tự động",
    shortHint: "Tự động chọn cách tìm kiếm phù hợp",
    description:
      "Tự động ưu tiên tìm trong tài liệu cá nhân và chọn nguồn phù hợp nhất theo câu hỏi.",
    backendIntegrated: true,
  },
  {
    id: "local",
    label: "Tài liệu cá nhân",
    shortHint: "Chỉ tìm trong tài liệu đã tải lên",
    description:
      "Chỉ tìm câu trả lời trong các tài liệu và ghi chú của bạn. Không gửi dữ liệu ra Internet.",
    backendIntegrated: true,
  },
  {
    id: "web",
    label: "Internet",
    shortHint: "Tìm thông tin trên Internet",
    description:
      "Mở rộng tìm kiếm thông tin từ các nguồn trên Internet.",
    requiresWebPermission: true,
    backendIntegrated: false,
  },
  {
    id: "hybrid",
    label: "Kết hợp",
    shortHint: "Tài liệu cá nhân + Internet",
    description:
      "Kết hợp nội dung từ tài liệu cá nhân với thông tin trên Internet để đối chiếu.",
    requiresWebPermission: true,
    backendIntegrated: false,
  },
]

/**
 * Cấu hình lựa chọn Model với nhãn thân thiện cho người dùng
 */
export interface AIModelOption {
  id: string
  label: string
  provider: "ollama-local" | "cloud-api"
  description: string
}

export const AI_MODEL_OPTIONS: AIModelOption[] = [
  {
    id: "qwen2.5:3b",
    label: "Nhanh & Nhẹ (Qwen 2.5)",
    provider: "ollama-local",
    description: "Phản hồi nhanh cho các câu hỏi tra cứu hàng ngày.",
  },
  {
    id: "qwen2.5:7b",
    label: "Chi tiết & Sâu (Qwen 7B)",
    provider: "ollama-local",
    description: "Độ chính xác cao hơn khi tổng hợp tài liệu dài.",
  },
  {
    id: "llama3.2:3b",
    label: "Đa năng (Llama 3.2)",
    provider: "ollama-local",
    description: "Phù hợp để tóm tắt ngắn gọn và đối chiếu thông tin.",
  },
]

/**
 * Gợi ý câu hỏi mẫu hiển thị ở Empty State
 */
export interface ChatPromptSuggestion {
  id: string
  title: string
  prompt: string
  category: string
  recommendedMode: AIMode
}

export const CHAT_PROMPT_SUGGESTIONS: ChatPromptSuggestion[] = [
  {
    id: "sug-hybrid-rag",
    title: "So sánh Hybrid RAG và Vector Search",
    prompt:
      "Hybrid RAG khác vector search thuần túy như thế nào? Hãy trình bày kèm bảng so sánh và ví dụ công thức RRF.",
    category: "Kiến trúc RAG",
    recommendedMode: "auto",
  },
  {
    id: "sug-citation",
    title: "Cấu trúc Citation & Kiểm chứng bằng chứng",
    prompt:
      "Citation trong hệ thống cần những trường dữ liệu nào để người dùng kiểm chứng được đoạn trích gốc?",
    category: "Kiểm chứng nguồn",
    recommendedMode: "local",
  },
  {
    id: "sug-privacy",
    title: "Nguyên tắc Local-first & Quyền Web Search",
    prompt:
      "Khi nào hệ thống được phép dùng Web Search và nguyên tắc bảo mật dữ liệu cá nhân hoạt động ra sao?",
    category: "Quyền riêng tư",
    recommendedMode: "local",
  },
  {
    id: "sug-pipeline",
    title: "Tóm tắt Pipeline xử lý tài liệu 6 bước",
    prompt:
      "Hãy tóm tắt quy trình 6 bước từ Upload đến Index và đoạn mã cấu hình chunking mẫu.",
    category: "Xử lý tài liệu",
    recommendedMode: "auto",
  },
]

/**
 * Interface chuẩn cho yêu cầu gửi tin nhắn AI Chat
 */
export interface SendChatRequest {
  conversationId: string
  workspaceId: string
  notebookScopeId?: string | null
  attachedDocumentIds?: string[]
  query: string
  mode: AIMode
  modelId: string
  backendOnline: boolean
  contextDocuments?: KnowledgeDocument[]
  signal?: AbortSignal
  /** Callback nhận từng phần nội dung nếu backend trả về luồng streaming thật */
  onStreamChunk?: (partialContent: string) => void
}

/**
 * Kết quả chuẩn hóa trả về từ Chat Service
 */
export interface SendChatResponse {
  message: ChatMessage
}

/**
 * Interface chuẩn bị cho đồng bộ lịch sử hội thoại với Backend trong tương lai
 */
export interface ConversationHistoryService {
  listConversations: (workspaceId: string) => Promise<Conversation[]>
  createConversation: (workspaceId: string, title?: string) => Promise<Conversation>
  renameConversation: (conversationId: string, title: string) => Promise<void>
  deleteConversation: (conversationId: string) => Promise<void>
}

export function getModeDescriptor(mode: AIMode): AIModeDescriptor {
  return AI_MODE_DESCRIPTORS.find((m) => m.id === mode) ?? AI_MODE_DESCRIPTORS[0]
}

/**
 * Thử gọi endpoint streaming thật nếu backend hỗ trợ `/api/v1/chat/stream`
 * Nếu endpoint không tồn tại (404/405), fallback về `/api/v1/chat/query` chuẩn.
 */
async function tryStreamOrQueryBackend(
  req: SendChatRequest,
): Promise<{ result: ChatResult; streamed: boolean }> {
  try {
    const res = await fetch(`${API_BASE}/api/v1/chat/stream`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "text/event-stream, application/x-ndjson, application/json",
      },
      body: JSON.stringify({
        workspace_id: req.workspaceId,
        notebook_id: req.notebookScopeId ?? undefined,
        document_ids: req.attachedDocumentIds?.length ? req.attachedDocumentIds : undefined,
        query: req.query,
        model: req.modelId,
        mode: req.mode,
      }),
      signal: req.signal,
    })

    const contentType = res.headers.get("content-type") ?? ""
    if (
      res.ok &&
      res.body &&
      (contentType.includes("text/event-stream") || contentType.includes("application/x-ndjson"))
    ) {
      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let accumulated = ""
      let citations: ChatResult["citations"] = []
      let engine = "backend_stream"
      let modelUsed = req.modelId

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        const chunkText = decoder.decode(value, { stream: true })
        const lines = chunkText.split("\n").filter((l) => l.trim().length > 0)
        for (const rawLine of lines) {
          const cleaned = rawLine.startsWith("data:") ? rawLine.slice(5).trim() : rawLine.trim()
          if (cleaned === "[DONE]") continue
          try {
            const parsed = JSON.parse(cleaned) as {
              delta?: string
              answer?: string
              citations?: ChatResult["citations"]
              engine?: string
              model_used?: string
            }
            if (typeof parsed.delta === "string") {
              accumulated += parsed.delta
              req.onStreamChunk?.(accumulated)
            } else if (typeof parsed.answer === "string") {
              accumulated = parsed.answer
              req.onStreamChunk?.(accumulated)
            }
            if (Array.isArray(parsed.citations)) {
              citations = parsed.citations
            }
            if (parsed.engine) engine = parsed.engine
            if (parsed.model_used) modelUsed = parsed.model_used
          } catch {
            accumulated += cleaned
            req.onStreamChunk?.(accumulated)
          }
        }
      }

      return {
        result: {
          answer: accumulated,
          citations,
          engine,
          model_used: modelUsed,
        },
        streamed: true,
      }
    }
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") {
      throw err
    }
    // Nếu endpoint /stream chưa được backend cung cấp, chuyển sang /api/v1/chat/query chuẩn
  }

  if (req.signal?.aborted) {
    throw new DOMException("Đã hủy yêu cầu.", "AbortError")
  }

  const res = await fetch(`${API_BASE}/api/v1/chat/query`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      workspace_id: req.workspaceId,
      query: req.query,
      model: req.modelId,
    }),
    signal: req.signal,
  })

  if (!res.ok) {
    const text = await res.text()
    throw new Error(text || `HTTP ${res.status}`)
  }

  const data = (await res.json()) as ChatResult
  return { result: data, streamed: false }
}

/**
 * Tạo phản hồi mô phỏng có cấu trúc Markdown đầy đủ (heading, list, bảng, inline code, code block)
 * và ghi chú minh bạch đây là dữ liệu mô phỏng (không phải LLM thật).
 */
export function generateMockChatResponse(req: SendChatRequest): ChatMessage {
  const q = req.query.toLowerCase()
  const attachedDocs = (req.contextDocuments ?? []).filter((d) =>
    req.attachedDocumentIds?.includes(d.id),
  )

  const attachedNote =
    attachedDocs.length > 0
      ? `\n\n> **Phạm vi tài liệu đính kèm:** Đang ưu tiên đối chiếu trên ${attachedDocs.map((d) => `\`${d.fileName}\``).join(", ")}.`
      : ""

  let content = ""
  let citations: Citation[] = []

  if (q.includes("lỗi") || q.includes("error_test")) {
    throw new Error("Mô phỏng lỗi kết nối dịch vụ AI để kiểm thử trạng thái Error trên giao diện.")
  }

  if (req.mode === "web" || req.mode === "hybrid") {
    content = `## Kết quả tổng hợp (${req.mode === "hybrid" ? "Hybrid: Kho cá nhân + Web" : "Web Mode"} — Mô phỏng)

Hiện tại chế độ **${req.mode.toUpperCase()}** chỉ lưu lựa chọn trên giao diện và sử dụng dữ liệu mẫu để minh họa cấu trúc hiển thị (chưa kết nối Web Search API hay chuyển đổi model thực tế).${attachedNote}

### 1. Điểm chính từ tài liệu nội bộ & nguồn đối chiếu
- **Kho tri thức cá nhân (\`Local Index\`):** Giữ vai trò nguồn chuẩn xác thực cho các khái niệm nội bộ [1].
- **Nguồn Web mở rộng (\`Web Snippet\`):** Bổ sung thông tin tham khảo bên ngoài khi kho cá nhân chưa có dữ liệu [2].

### 2. Bảng phân tách nguồn dữ liệu

| Tiêu chí | Kho cá nhân (Local) | Nguồn trực tuyến (Web) |
| :--- | :--- | :--- |
| **Độ tin cậy trích dẫn** | Kiểm chứng tới từng trang & chunk | Phụ thuộc vào URL nguồn |
| **Quyền riêng tư** | Lưu trữ hoàn toàn trên máy | Gửi truy vấn tìm kiếm ra ngoài |
| **Trạng thái tích hợp** | Hỗ trợ qua \`/api/v1/chat/query\` | Đang hiển thị mẫu UI (\`mock\`) |

### 3. Cấu hình truy vấn minh họa

\`\`\`json
{
  "mode": "${req.mode}",
  "model": "${req.modelId}",
  "web_search_integrated": false,
  "attached_documents": ${JSON.stringify(req.attachedDocumentIds ?? [])}
}
\`\`\``

    citations = [
      {
        refId: 1,
        documentId: "doc_hybrid_rag",
        documentName: "Hybrid-RAG-Survey.pdf",
        pageNumber: 3,
        chunkIndex: 4,
        snippet:
          "Hybrid Retrieval-Augmented Generation (Hybrid RAG) kết hợp hai kênh truy xuất dense và sparse.",
        sourceKind: "local",
        highlight: "kết hợp hai kênh truy xuất",
      },
      {
        refId: 2,
        documentId: null,
        documentName: "docs.example.org/rag-architecture (Mô phỏng Web)",
        pageNumber: null,
        chunkIndex: null,
        snippet:
          "Nguồn web mô phỏng dùng để kiểm thử giao diện hiển thị trích dẫn trực tuyến.",
        sourceKind: "web",
        url: "https://example.org/rag-architecture",
      },
    ]
  } else if (q.includes("citation") || q.includes("kiểm chứng") || q.includes("trường")) {
    content = `## Cấu trúc Citation để kiểm chứng bằng chứng

Để một câu trả lời trong **Knowledge AI** có thể kiểm chứng được (verifiable), mỗi trích dẫn \`[1]\` cần ánh xạ tường minh về đoạn văn bản gốc trong kho tri thức [1].${attachedNote}

### Các trường thông tin bắt buộc
1. **Định danh tham chiếu (\`refId\`):** Số thứ tự hiển thị ngay trong văn bản (ví dụ \`[1]\`, \`[2]\`).
2. **Thông tin tài liệu gốc (\`documentId\`, \`documentName\`):** Liên kết trực tiếp sang trình đọc tài liệu.
3. **Vị trí trích xuất (\`pageNumber\`, \`chunkIndex\`):** Giúp định vị trang và đoạn văn cụ thể.
4. **Đoạn bằng chứng (\`snippet\`):** Trích nguyên văn đoạn văn bản được retriever trả về.

| Trường dữ liệu | Kiểu | Mục đích hiển thị trên UI |
| :--- | :--- | :--- |
| \`refId\` | \`number\` | Nút chip \`[1]\` tương tác trong bài viết |
| \`pageNumber\` | \`number \\| null\` | Điều hướng nhanh tới trang tài liệu |
| \`chunkIndex\` | \`number \\| null\` | Tô sáng chunk trong Source Viewer |
| \`snippet\` | \`string\` | Hiển thị nguyên văn trong Citation Panel |

\`\`\`typescript
interface Citation {
  refId: number
  documentId: string | null
  documentName: string
  pageNumber: number | null
  chunkIndex: number | null
  snippet: string
}
\`\`\``

    citations = [
      {
        refId: 1,
        documentId: "doc_citation",
        documentName: "Citation-and-Evidence.md",
        pageNumber: 1,
        chunkIndex: 2,
        snippet:
          "Câu trả lời cần gắn citation [1] với tên tài liệu, số trang và đoạn evidence. Nếu không đủ bằng chứng, hệ thống phải nêu rõ thay vì khẳng định.",
        sourceKind: "local",
        highlight: "tên tài liệu, số trang và đoạn evidence",
      },
    ]
  } else if (q.includes("pipeline") || q.includes("6 bước") || q.includes("chunk")) {
    content = `## Quy trình xử lý tài liệu 6 bước (Ingestion Pipeline)

Trước khi có thể truy xuất trong AI Chat, mọi tài liệu đều đi qua pipeline chuẩn hóa gồm **6 giai đoạn** tuần tự [1]:${attachedNote}

- **Bước 1 — Upload:** Tiếp nhận tệp (\`.pdf\`, \`.docx\`, \`.pptx\`, \`.txt\`, \`.md\`) và kiểm tra định dạng.
- **Bước 2 — Extract:** Trích xuất văn bản thô và thông tin số trang.
- **Bước 3 — Clean:** Loại bỏ ký tự nhiễu, chuẩn hóa khoảng trắng và bảng biểu.
- **Bước 4 — Chunk:** Chia văn bản thành các đoạn có độ gối (\`chunk_overlap\`) để giữ ngữ cảnh.
- **Bước 5 — Embed:** Tạo vector biểu diễn ngữ nghĩa bằng mô hình embedding.
- **Bước 6 — Index:** Lưu vào chỉ mục kép (Vector Index + BM25 FTS5).

| Bước | Đầu vào | Đầu ra |
| :--- | :--- | :--- |
| \`Extract → Clean\` | Tệp nhị phân / văn bản | Văn bản sạch theo trang |
| \`Chunk → Embed\` | Văn bản sạch | Danh sách chunks + dense vectors |
| \`Index\` | Chunks + Vectors | Chỉ mục sẵn sàng cho Hybrid RAG |

\`\`\`python
# Ví dụ cấu hình chia đoạn (Chunking) chuẩn bị cho Hybrid RAG
chunk_config = {
    "chunk_size": 512,
    "chunk_overlap": 64,
    "separators": ["\\n\\n", "\\n", ". ", " "]
}
\`\`\``

    citations = [
      {
        refId: 1,
        documentId: "doc_hybrid_rag",
        documentName: "Hybrid-RAG-Survey.pdf",
        pageNumber: 2,
        chunkIndex: 2,
        snippet:
          "Hybrid Retrieval-Augmented Generation (Hybrid RAG) kết hợp hai kênh truy xuất sau khi tài liệu được trích xuất, chia đoạn và lập chỉ mục.",
        sourceKind: "local",
        highlight: "kết hợp hai kênh truy xuất",
      },
    ]
  } else {
    content = `## Phân tích câu hỏi với Hybrid RAG

Trong hệ thống **Personal Knowledge**, phương pháp **Hybrid RAG** kết hợp hai kênh truy xuất bổ trợ lẫn nhau trước khi đưa ngữ cảnh vào mô hình ngôn ngữ [1][2]:${attachedNote}

### 1. Hai kênh truy xuất cốt lõi
- **Dense Retrieval (\`Vector Search\`):** Mã hóa câu hỏi và đoạn văn thành vector ngữ nghĩa, giúp bắt đúng ý ngay cả khi người dùng dùng từ đồng nghĩa.
- **Sparse Retrieval (\`BM25 / FTS5\`):** Khớp từ khóa chính xác cho tên riêng, mã lỗi, ký hiệu toán học hoặc thuật ngữ chuyên ngành.

### 2. Bảng so sánh hiệu quả truy xuất

| Phương pháp | Ưu điểm chính | Hạn chế khi dùng đơn lẻ |
| :--- | :--- | :--- |
| **Vector Search** | Hiểu ngữ nghĩa, câu hỏi tự nhiên | Dễ trượt mã hiệu, từ khóa hiếm |
| **BM25 (Lexical)** | Chính xác tuyệt đối với từ khóa | Không hiểu từ đồng nghĩa / diễn đạt khác |
| **Hybrid RAG + Rerank** | Cân bằng cả ngữ nghĩa lẫn từ khóa | Cần thêm bước hợp nhất \`RRF\` |

### 3. Công thức hợp nhất Reciprocal Rank Fusion (RRF)

\`\`\`python
def compute_rrf_score(ranks: list[int], k: int = 60) -> float:
    """Hợp nhất thứ hạng từ Dense Retriever và BM25 Retriever."""
    return sum(1.0 / (k + rank) for rank in ranks)
\`\`\`

> **Lưu ý minh bạch:** Phản hồi này đang được tạo từ \`chat-service\` ở chế độ **mô phỏng (Mock Data)** để kiểm thử giao diện Markdown và Citation — chưa phải câu trả lời sinh từ LLM thật.`

    citations = [
      {
        refId: 1,
        documentId: "doc_hybrid_rag",
        documentName: "Hybrid-RAG-Survey.pdf",
        pageNumber: 3,
        chunkIndex: 4,
        snippet:
          "Kênh dense (vector search) mã hóa câu hỏi và đoạn văn thành vector ngữ nghĩa. Kênh sparse (BM25 / FTS5) khớp từ khóa chính xác.",
        sourceKind: "local",
        highlight: "vector ngữ nghĩa",
      },
      {
        refId: 2,
        documentId: "doc_hybrid_rag",
        documentName: "Hybrid-RAG-Survey.pdf",
        pageNumber: 5,
        chunkIndex: 8,
        snippet:
          "Reciprocal Rank Fusion (RRF) gộp hai danh sách xếp hạng. Sau đó Cross-Encoder Reranker chấm lại cặp (câu hỏi, đoạn văn) để loại nhiễu.",
        sourceKind: "local",
        highlight: "Reciprocal Rank Fusion (RRF)",
      },
    ]
  }

  const modeInfo = getModeDescriptor(req.mode)
  const fallbackReason = !req.backendOnline
    ? `Backend chưa kết nối — Đang hiển thị dữ liệu mô phỏng (chưa gọi LLM "${req.modelId}" thật).`
    : !modeInfo.backendIntegrated
      ? `Chế độ ${modeInfo.label} chưa tích hợp API thực tế — Lựa chọn "${modeInfo.label}" chỉ lưu trên UI và hiển thị phản hồi mô phỏng.`
      : undefined

  return {
    id: uid("msg"),
    role: "assistant",
    content,
    createdAt: nowIso(),
    citations,
    modeRequested: req.mode,
    modeUsed: req.mode === "auto" ? "local" : req.mode,
    modelId: req.modelId,
    engine: "mock_service",
    isMock: true,
    streaming: false,
    fallbackReason,
    attachedDocumentIds: req.attachedDocumentIds,
    notebookScopeId: req.notebookScopeId ?? null,
  }
}

/**
 * Hàm dịch vụ chính xử lý gửi câu hỏi AI Chat
 */
export async function sendChatMessageService(req: SendChatRequest): Promise<SendChatResponse> {
  if (req.signal?.aborted) {
    throw new DOMException("Đã hủy yêu cầu.", "AbortError")
  }

  const modeInfo = getModeDescriptor(req.mode)

  // Khi backend online và chế độ đã được tích hợp (auto / local)
  if (req.backendOnline && modeInfo.backendIntegrated) {
    const { result } = await tryStreamOrQueryBackend(req)
    const citations: Citation[] = (result.citations ?? []).map((c, i) => ({
      refId: c.ref_id ?? i + 1,
      documentId: c.document_id ?? null,
      documentName: c.document_name ?? "Tài liệu",
      pageNumber: c.page_number ?? null,
      chunkIndex: c.chunk_index ?? null,
      snippet: c.snippet ?? "",
      sourceKind: c.document_id ? "local" : "web",
    }))

    return {
      message: {
        id: uid("msg"),
        role: "assistant",
        content: result.answer,
        createdAt: nowIso(),
        citations,
        modeRequested: req.mode,
        modeUsed: req.mode === "auto" ? "local" : req.mode,
        modelId: result.model_used ?? req.modelId,
        engine: result.engine ?? "backend_rag",
        isMock: false,
        streaming: false,
        attachedDocumentIds: req.attachedDocumentIds,
        notebookScopeId: req.notebookScopeId ?? null,
      },
    }
  }

  // Chế độ mô phỏng: chờ ngắn 350ms để thể hiện trạng thái loading rõ ràng và cho phép bấm Hủy nếu cần
  await new Promise<void>((resolve, reject) => {
    const timer = window.setTimeout(resolve, 350)
    if (req.signal) {
      req.signal.addEventListener(
        "abort",
        () => {
          window.clearTimeout(timer)
          reject(new DOMException("Đã hủy yêu cầu.", "AbortError"))
        },
        { once: true },
      )
    }
  })

  return {
    message: generateMockChatResponse(req),
  }
}

// Giữ tham chiếu hàm queryChat để đảm bảo tương thích ngược với các module khác
export { queryChat }
