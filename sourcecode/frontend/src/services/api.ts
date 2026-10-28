import type { AIMode, KnowledgeDocument, SystemStatus, Workspace } from "@/types"
import { MOCK_ANSWER } from "@/store/app-store"
import { nowIso, uid } from "@/utils/format"

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? ""

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, init)
  if (!res.ok) {
    const text = await res.text()
    throw new Error(text || `HTTP ${res.status}`)
  }
  return res.json() as Promise<T>
}

export async function fetchSystemStatus(): Promise<SystemStatus> {
  const data = await request<{
    status: string
    ollama?: { running?: boolean; available_models?: string[]; message?: string }
  }>("/api/v1/status")
  return {
    backendOnline: true,
    ollamaRunning: Boolean(data.ollama?.running),
    ollamaModels: data.ollama?.available_models ?? [],
    internetOnline: navigator.onLine,
    usingMock: false,
    message: data.ollama?.message ?? "Backend đang phản hồi.",
  }
}

export async function fetchWorkspaces(): Promise<Workspace[]> {
  const data = await request<{ workspaces: Array<Record<string, string>> }>("/api/v1/workspaces")
  return (data.workspaces ?? []).map((w) => ({
    id: w.id,
    name: w.name,
    description: w.description ?? "",
    createdAt: w.created_at ?? nowIso(),
    updatedAt: w.created_at ?? nowIso(),
  }))
}

export async function fetchDocuments(workspaceId: string): Promise<KnowledgeDocument[]> {
  const data = await request<{ documents: Array<Record<string, unknown>> }>(
    `/api/v1/workspaces/${workspaceId}/documents`,
  )
  return (data.documents ?? []).map((d) => {
    const name = String(d.file_name ?? "document")
    const ext = name.split(".").pop()?.toLowerCase()
    const fileType =
      ext === "pdf" || ext === "docx" || ext === "pptx" || ext === "txt" || ext === "md"
        ? ext
        : "other"
    const statusRaw = String(d.status ?? "ready")
    const status =
      statusRaw === "ready" || statusRaw === "indexed" || statusRaw === "completed"
        ? "ready"
        : statusRaw === "failed" || statusRaw === "error"
          ? "failed"
          : "uploaded"
    return {
      id: String(d.id),
      workspaceId: String(d.workspace_id ?? workspaceId),
      notebookId: null,
      fileName: name,
      fileType,
      fileSize: Number(d.file_size ?? 0),
      status,
      createdAt: String(d.created_at ?? nowIso()),
      totalChunks: Number(d.total_chunks ?? 0),
      pageCount: Number(d.total_chunks ?? 0) > 0 ? Math.max(1, Math.ceil(Number(d.total_chunks) / 4)) : 0,
      extractedText: "",
      mock: false,
    } satisfies KnowledgeDocument
  })
}

export async function uploadDocument(workspaceId: string, file: File) {
  const form = new FormData()
  form.append("file", file)
  return request<{ message: string; document?: Record<string, unknown> }>(
    `/api/v1/workspaces/${workspaceId}/documents/upload`,
    { method: "POST", body: form },
  )
}

export function uploadDocumentWithProgress(
  workspaceId: string,
  file: File,
  options?: {
    notebookId?: string | null
    onProgress?: (percent: number) => void
    signal?: AbortSignal
  },
): Promise<{ message: string; document?: Record<string, unknown> }> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open("POST", `${API_BASE}/api/v1/workspaces/${workspaceId}/documents/upload`)

    if (options?.signal) {
      if (options.signal.aborted) {
        reject(new Error("Đã hủy tải lên."))
        return
      }
      options.signal.addEventListener("abort", () => {
        xhr.abort()
        reject(new Error("Đã hủy tải lên."))
      })
    }

    xhr.upload.onprogress = (ev) => {
      if (ev.lengthComputable && options?.onProgress) {
        const pct = Math.min(100, Math.round((ev.loaded / ev.total) * 100))
        options.onProgress(pct)
      }
    }

    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          resolve(JSON.parse(xhr.responseText))
        } catch {
          resolve({ message: "OK" })
        }
      } else {
        reject(new Error(xhr.responseText || `HTTP ${xhr.status}`))
      }
    }

    xhr.onerror = () => reject(new Error("Lỗi kết nối mạng khi tải tệp lên."))

    const form = new FormData()
    form.append("file", file)
    if (options?.notebookId) {
      form.append("notebook_id", options.notebookId)
    }
    xhr.send(form)
  })
}

export async function deleteDocumentApi(documentId: string) {
  return request<{ message: string }>(`/api/v1/documents/${documentId}`, { method: "DELETE" })
}

export interface ChatResult {
  answer: string
  citations: Array<{
    ref_id?: number
    document_id?: string
    document_name?: string
    page_number?: number
    chunk_index?: number
    snippet?: string
  }>
  model_used?: string
  engine?: string
}

export async function queryChat(payload: {
  workspaceId: string
  query: string
  model?: string
  mode: AIMode
}): Promise<ChatResult> {
  return request<ChatResult>("/api/v1/chat/query", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      workspace_id: payload.workspaceId,
      query: payload.query,
      model: payload.model,
    }),
  })
}

export function mockChatAnswer(query: string, mode: AIMode): ChatResult {
  const lower = query.toLowerCase()
  if (lower.includes("chào") || lower.includes("hello") || lower.length < 8) {
    return {
      answer:
        "Xin chào, tôi là trợ lý Knowledge AI. Hãy hỏi về tài liệu trong workspace hiện tại — câu trả lời mẫu này **không** đến từ Local LLM.",
      citations: [],
      engine: "mock_chitchat",
      model_used: "mock",
    }
  }
  if (mode === "web") {
    return {
      answer:
        "Chế độ Web đang dùng **dữ liệu mô phỏng**. Không có kết quả tìm kiếm Internet thật cho đến khi backend Web Search được kết nối.\n\n[1]",
      citations: [
        {
          ref_id: 1,
          document_id: undefined,
          document_name: "example.org/hybrid-rag (mô phỏng)",
          page_number: undefined,
          snippet: "Đoạn web mẫu — không phải kết quả tìm kiếm thật.",
        },
      ],
      engine: "mock_web",
      model_used: "mock",
    }
  }
  return {
    answer: MOCK_ANSWER.content,
    citations: MOCK_ANSWER.citations.map((c) => ({
      ref_id: c.refId,
      document_id: c.documentId ?? undefined,
      document_name: c.documentName,
      page_number: c.pageNumber ?? undefined,
      chunk_index: c.chunkIndex ?? undefined,
      snippet: c.snippet,
    })),
    engine: "mock_local_rag",
    model_used: "mock",
  }
}

export function mapChatResult(result: ChatResult, mode: AIMode) {
  return {
    id: uid("msg"),
    role: "assistant" as const,
    content: result.answer,
    createdAt: nowIso(),
    citations: (result.citations ?? []).map((c, i) => ({
      refId: c.ref_id ?? i + 1,
      documentId: c.document_id ?? null,
      documentName: c.document_name ?? "Nguồn",
      pageNumber: c.page_number ?? null,
      chunkIndex: c.chunk_index ?? null,
      snippet: c.snippet ?? "",
      sourceKind: (c.document_id ? "local" : mode === "web" ? "web" : "local") as "local" | "web",
      url: c.document_id ? undefined : c.document_name?.startsWith("http") ? c.document_name : undefined,
    })),
    modeRequested: mode,
    modeUsed: mode === "auto" ? "local" : mode,
    engine: result.engine,
    fallbackReason: undefined as string | undefined,
  }
}
