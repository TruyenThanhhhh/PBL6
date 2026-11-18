import type {
  AIMode,
  ChatMessage,
  Conversation,
  KnowledgeDocument,
  SearchHit,
  SystemStatus,
  Workspace,
} from "@/types"
import { MOCK_ANSWER } from "@/store/app-store"
import { authHeaders, clearSession } from "@/services/auth-service"
import { fileKindFromName, nowIso, uid } from "@/utils/format"

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? ""

async function authorizedFetch(path: string, init?: RequestInit): Promise<Response> {
  const headers = new Headers(init?.headers)
  Object.entries(authHeaders()).forEach(([key, value]) => headers.set(key, value))
  const res = await fetch(`${API_BASE}${path}`, { ...init, headers })
  if (!res.ok) {
    if (res.status === 401) clearSession()
    const text = await res.text()
    throw new Error(text || `HTTP ${res.status}`)
  }
  return res
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await authorizedFetch(path, init)
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

export function mapBackendWorkspace(w: Record<string, unknown>): Workspace {
  const createdAt = String(w.created_at ?? nowIso())
  const updatedAt = String(w.updated_at ?? createdAt)
  return {
    id: String(w.id),
    name: String(w.name ?? "Workspace mới"),
    description: String(w.description ?? ""),
    category: w.category ? String(w.category) : "Chung",
    icon: w.icon ? String(w.icon) : "folder",
    docCount: w.doc_count != null ? Number(w.doc_count) : undefined,
    conversationCount: w.conversation_count != null ? Number(w.conversation_count) : undefined,
    createdAt,
    updatedAt,
  }
}

export async function fetchWorkspaces(): Promise<Workspace[]> {
  const data = await request<{ workspaces: Array<Record<string, unknown>> }>("/api/v1/workspaces")
  return (data.workspaces ?? []).map(mapBackendWorkspace)
}

export async function createWorkspaceApi(
  name = "",
  description = "",
  category = "Chung",
): Promise<Workspace> {
  const data = await request<{ workspace: Record<string, unknown> }>(
    "/api/v1/workspaces",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, description, category }),
    },
  )
  return mapBackendWorkspace(data.workspace)
}

export async function updateWorkspaceApi(
  workspaceId: string,
  name: string,
  description = "",
  category?: string,
) {
  const body: Record<string, string> = { name, description }
  if (category !== undefined) body.category = category
  const data = await request<{ workspace: Record<string, unknown> }>(
    `/api/v1/workspaces/${workspaceId}`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    },
  )
  return { workspace: mapBackendWorkspace(data.workspace) }
}

export async function deleteWorkspaceApi(workspaceId: string) {
  return request<{ message: string }>(`/api/v1/workspaces/${workspaceId}`, { method: "DELETE" })
}

export async function generateWorkspaceMetadataApi(workspaceId: string): Promise<{
  updated: boolean
  source: string
  workspace: Workspace | null
}> {
  const data = await request<{
    updated: boolean
    source: string
    workspace?: Record<string, unknown> | null
  }>(`/api/v1/workspaces/${workspaceId}/generate-metadata`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({}),
  })
  return {
    updated: Boolean(data.updated),
    source: String(data.source ?? "ai"),
    workspace: data.workspace ? mapBackendWorkspace(data.workspace) : null,
  }
}

export async function searchWorkspacesSemanticApi(
  query: string,
  signal?: AbortSignal,
): Promise<{ workspaces: Workspace[]; searchMode: string }> {
  const params = new URLSearchParams({ q: query })
  const data = await request<{ workspaces: Array<Record<string, unknown>>; search_mode?: string }>(
    `/api/v1/workspaces/search?${params.toString()}`,
    { signal },
  )
  return {
    workspaces: (data.workspaces ?? []).map(mapBackendWorkspace),
    searchMode: String(data.search_mode ?? "semantic"),
  }
}

export async function searchGlobalSemanticApi(
  query: string,
  kind = "all",
  signal?: AbortSignal,
): Promise<{ hits: SearchHit[]; searchMode: string }> {
  const params = new URLSearchParams({ q: query, kind })
  const data = await request<{ hits: SearchHit[]; search_mode?: string }>(
    `/api/v1/search?${params.toString()}`,
    { signal },
  )
  return {
    hits: data.hits ?? [],
    searchMode: String(data.search_mode ?? "semantic"),
  }
}

export async function fetchDocuments(workspaceId: string): Promise<KnowledgeDocument[]> {
  const data = await request<{ documents: Array<Record<string, unknown>> }>(
    `/api/v1/workspaces/${workspaceId}/documents`,
  )
  return (data.documents ?? []).map((d) => {
    const name = String(d.file_name ?? "document")
    const fileType = fileKindFromName(name)
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
    deferMetadata?: boolean
    onProgress?: (percent: number) => void
    signal?: AbortSignal
  },
): Promise<{
  message: string
  document?: Record<string, unknown>
  workspace?: Record<string, unknown> | null
  metadata_source?: string
}> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open("POST", `${API_BASE}/api/v1/workspaces/${workspaceId}/documents/upload`)
    Object.entries(authHeaders()).forEach(([key, value]) => xhr.setRequestHeader(key, value))

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
    if (options?.deferMetadata) {
      form.append("defer_metadata", "true")
    }
    xhr.send(form)
  })
}

export async function deleteDocumentApi(documentId: string) {
  return request<{ message: string }>(`/api/v1/documents/${documentId}`, { method: "DELETE" })
}

export async function fetchConversations(workspaceId: string): Promise<Conversation[]> {
  const data = await request<{ conversations: Array<Record<string, unknown>> }>(
    `/api/v1/workspaces/${workspaceId}/conversations`,
  )
  return (data.conversations ?? []).map((c) => ({
    id: String(c.id),
    workspaceId: String(c.workspaceId ?? workspaceId),
    notebookId: (c.notebookId as string | null) ?? null,
    title: String(c.title ?? "Cuộc trò chuyện mới"),
    updatedAt: String(c.updatedAt ?? nowIso()),
    messages: [],
  }))
}

export async function createConversationApi(
  workspaceId: string,
  title = "Cuộc trò chuyện mới",
  notebookId?: string | null,
): Promise<Conversation> {
  const data = await request<{ conversation: Record<string, unknown> }>(
    `/api/v1/workspaces/${workspaceId}/conversations`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title, notebook_id: notebookId ?? null }),
    },
  )
  const c = data.conversation
  return {
    id: String(c.id),
    workspaceId: String(c.workspaceId ?? workspaceId),
    notebookId: (c.notebookId as string | null) ?? null,
    title: String(c.title ?? title),
    updatedAt: String(c.updatedAt ?? nowIso()),
    messages: [],
  }
}

export async function fetchConversationMessages(conversationId: string): Promise<ChatMessage[]> {
  const data = await request<{ messages: Array<Record<string, unknown>> }>(
    `/api/v1/conversations/${conversationId}/messages`,
  )
  return (data.messages ?? []).map((m) => ({
    id: String(m.id),
    role: (m.role as "user" | "assistant") || "user",
    content: String(m.content ?? ""),
    createdAt: String(m.createdAt ?? nowIso()),
    citations: (m.citations as any[]) ?? [],
    modeUsed: m.modeUsed as AIMode | undefined,
    streaming: false,
    isMock: false,
  }))
}

export async function renameConversationApi(conversationId: string, title: string) {
  return request<{ message: string; title: string }>(`/api/v1/conversations/${conversationId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title }),
  })
}

export async function deleteConversationApi(conversationId: string) {
  return request<{ message: string }>(`/api/v1/conversations/${conversationId}`, {
    method: "DELETE",
  })
}

export interface ChatResult {
  answer: string
  citations: Array<{
    ref_id?: number
    document_id?: string
    document_name?: string
    title?: string
    url?: string
    source_type?: string
    page_number?: number
    page_label?: string
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
    citations: (result.citations ?? []).map((c, i) => {
      const rawName = c.document_name ?? c.title
      let docName = rawName
      const url = c.url ?? (c.document_id ? undefined : c.document_name?.startsWith("http") ? c.document_name : undefined)
      if (!docName || docName.toLowerCase() === "nguồn web" || docName.toLowerCase() === "web") {
        if (url) {
          try {
            docName = new URL(url).hostname.replace(/^www\./, "")
          } catch {
            docName = "Nguồn Web"
          }
        } else {
          docName = c.document_id ? "Tài liệu" : "Nguồn Web"
        }
      }

      return {
        refId: c.ref_id ?? i + 1,
        documentId: c.document_id ?? null,
        documentName: docName,
        pageNumber: c.page_number ?? null,
        chunkIndex: c.chunk_index ?? null,
        snippet: c.snippet ?? "",
        sourceKind: (c.document_id ? "local" : mode === "web" ? "web" : "local") as "local" | "web",
        url,
      }
    }),
    modeRequested: mode,
    modeUsed: mode === "auto" ? "local" : mode,
    engine: result.engine,
    fallbackReason: undefined as string | undefined,
  }
}

export interface DocumentChunkRecord {
  id: string
  document_id: string
  workspace_id: string
  chunk_index: number
  page_number: number
  token_count: number
  content: string
  created_at?: string
}

export interface DocumentChunksApiResponse {
  document: {
    id: string
    workspace_id: string
    workspace_name?: string
    file_name: string
    file_type: string
    file_size: number
    total_pages: number
    total_chunks: number
    status: string
    created_at: string
  }
  chunks: DocumentChunkRecord[]
  total: number
  total_chunks: number
}

export async function fetchDocumentChunks(
  documentId: string,
  page?: number,
): Promise<DocumentChunksApiResponse> {
  const url = page != null && page > 0
    ? `/api/v1/documents/${documentId}/chunks?page=${page}`
    : `/api/v1/documents/${documentId}/chunks`
  return request<DocumentChunksApiResponse>(url)
}

export async function fetchDocumentDetail(
  documentId: string,
): Promise<{ document: DocumentChunksApiResponse["document"] }> {
  return request<{ document: DocumentChunksApiResponse["document"] }>(`/api/v1/documents/${documentId}`)
}

// ==========================================
// AI Study Tools APIs
// ==========================================

export interface StudySummaryPayload {
  workspace_id: string
  document_id?: string | null
  document_ids?: string[] | null
  focus_prompt?: string
  model?: string
}

export interface StudySummaryResponse {
  title: string
  markdown: string
  is_mock: boolean
  error?: string
}

export async function fetchAiSummaryApi(
  payload: StudySummaryPayload,
  signal?: AbortSignal,
): Promise<StudySummaryResponse> {
  return request<StudySummaryResponse>("/api/v1/study/summary", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    signal,
  })
}

export async function streamAiSummaryApi(
  payload: StudySummaryPayload,
  onProgress?: (partialMarkdown: string, title: string) => void,
  signal?: AbortSignal,
): Promise<StudySummaryResponse> {
  const res = await authorizedFetch("/api/v1/study/summary/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    signal,
  })

  if (!res.body) {
    return fetchAiSummaryApi(payload, signal)
  }

  const reader = res.body.getReader()
  const decoder = new TextDecoder("utf-8")
  let buffer = ""
  let title = "Tóm tắt AI"
  let markdown = ""
  let isMock = false
  let errorMsg: string | undefined

  while (true) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split("\n")
    buffer = lines.pop() ?? ""

    for (const rawLine of lines) {
      const line = rawLine.trim()
      if (!line.startsWith("data:")) continue
      const jsonStr = line.slice(5).trim()
      if (!jsonStr) continue
      try {
        const evt = JSON.parse(jsonStr) as {
          type?: string
          title?: string
          content?: string
          markdown?: string
          error?: string
          is_mock?: boolean
        }
        if (evt.title) title = evt.title
        if (typeof evt.is_mock === "boolean") isMock = evt.is_mock
        if (evt.type === "token" && evt.content) {
          markdown += evt.content
          onProgress?.(markdown, title)
        } else if (evt.type === "done") {
          if (typeof evt.markdown === "string") {
            markdown = evt.markdown
          }
          onProgress?.(markdown, title)
        } else if (evt.type === "error") {
          errorMsg = evt.error || "Quá trình sinh tóm tắt gặp lỗi."
          isMock = true
        }
      } catch {
        // Bỏ qua dòng SSE không hợp lệ
      }
    }
  }

  return {
    title,
    markdown: markdown.trim(),
    is_mock: isMock,
    error: errorMsg,
  }
}

export interface StudyQuizPayload {
  workspace_id: string
  document_id?: string | null
  document_ids?: string[] | null
  difficulty?: "easy" | "medium" | "hard"
  question_count?: number
  focus_prompt?: string | null
  model?: string
}

export interface StudyQuizCitationPayload {
  documentId?: string | null
  documentName: string
  pageNumber?: number | null
  chunkIndex?: number | null
  snippet?: string
}

export interface StudyQuizResponse {
  title: string
  difficulty: "easy" | "medium" | "hard"
  questions: Array<{
    id: string
    prompt: string
    options: string[]
    answerIndex: number
    explanation: string
    citation?: StudyQuizCitationPayload | null
  }>
  is_mock: boolean
  error?: string
}

export async function fetchAiQuizApi(
  payload: StudyQuizPayload,
  signal?: AbortSignal,
): Promise<StudyQuizResponse> {
  return request<StudyQuizResponse>("/api/v1/study/quiz", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    signal,
  })
}

export type FlashcardStyleApi = "term_definition" | "qa" | "vocabulary" | "cloze"

export interface StudyFlashcardsPayload {
  workspace_id: string
  document_id?: string | null
  document_ids?: string[] | null
  count?: number
  card_style?: FlashcardStyleApi
  focus_prompt?: string | null
  model?: string
}

export interface StudyFlashcardsResponse {
  title?: string
  card_style?: FlashcardStyleApi
  flashcards: Array<{
    id: string
    front: string
    back: string
    example?: string
    cardStyle?: FlashcardStyleApi
    citation?: StudyQuizCitationPayload | null
    status: "new" | "remembered" | "review"
    is_mock: boolean
  }>
  is_mock: boolean
  error?: string
}

export async function fetchAiFlashcardsApi(
  payload: StudyFlashcardsPayload,
  signal?: AbortSignal,
): Promise<StudyFlashcardsResponse> {
  return request<StudyFlashcardsResponse>("/api/v1/study/flashcards", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    signal,
  })
}

export interface StudyMindmapNodePayload {
  id?: string
  label: string
  detail?: string
  children?: StudyMindmapNodePayload[]
}

export interface StudyMindmapPayload {
  workspace_id: string
  document_id?: string | null
  document_ids?: string[] | null
  focus_prompt?: string
  max_depth?: number
  model?: string
}

export interface StudyMindmapResponse {
  root: StudyMindmapNodePayload | null
  is_mock: boolean
  error?: string
}

export async function fetchAiMindmapApi(payload: StudyMindmapPayload): Promise<StudyMindmapResponse> {
  return request<StudyMindmapResponse>("/api/v1/study/mindmap", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  })
}

export interface StudyNotesPayload {
  workspace_id: string
  document_id?: string | null
  document_ids?: string[] | null
  focus_prompt?: string
  model?: string
}

export interface StudyNotesResponse {
  title: string
  markdown: string
  is_mock: boolean
  error?: string
}

export async function fetchAiNotesApi(payload: StudyNotesPayload): Promise<StudyNotesResponse> {
  return request<StudyNotesResponse>("/api/v1/study/notes", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  })
}

export interface StudyPlanPayload {
  workspace_id: string
  document_id?: string | null
  document_ids?: string[] | null
  start_date?: string
  day_span?: number
  focus_prompt?: string | null
  model?: string
}

export interface StudyPlanTaskResponse {
  title: string
  due_date: string
  detail?: string
}

export interface StudyPlanResponse {
  tasks: StudyPlanTaskResponse[]
  is_mock: boolean
  error?: string
}

export async function fetchAiPlanApi(payload: StudyPlanPayload): Promise<StudyPlanResponse> {
  return request<StudyPlanResponse>("/api/v1/study/plan", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  })
}

export interface StudyArtifactRecord {
  id: string
  workspace_id: string
  document_id?: string | null
  artifact_type: string
  title: string
  data: any
  created_at?: string
}

export async function fetchStudyArtifactsApi(
  workspaceId: string,
  artifactType?: string,
): Promise<{ artifacts: StudyArtifactRecord[] }> {
  const qs = artifactType ? `?artifact_type=${encodeURIComponent(artifactType)}` : ""
  return request<{ artifacts: StudyArtifactRecord[] }>(
    `/api/v1/workspaces/${workspaceId}/study-artifacts${qs}`,
  )
}

export async function saveStudyArtifactApi(
  workspaceId: string,
  payload: { document_id?: string | null; artifact_type: string; title: string; data: any }
): Promise<{ artifact: StudyArtifactRecord }> {
  return request<{ artifact: StudyArtifactRecord }>(`/api/v1/workspaces/${workspaceId}/study-artifacts`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  })
}

export async function updateStudyArtifactApi(
  workspaceId: string,
  artifactId: string,
  payload: { title?: string; data?: any }
): Promise<{ artifact: StudyArtifactRecord }> {
  return request<{ artifact: StudyArtifactRecord }>(
    `/api/v1/workspaces/${workspaceId}/study-artifacts/${artifactId}`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
  )
}

export async function deleteStudyArtifactApi(
  workspaceId: string,
  artifactId: string
): Promise<{ message: string; id: string }> {
  return request<{ message: string; id: string }>(`/api/v1/workspaces/${workspaceId}/study-artifacts/${artifactId}`, {
    method: "DELETE",
  })
}

export type ExportDocumentFormat = "md" | "docx" | "pdf"

export async function exportStudyDocumentApi(payload: {
  title: string
  content: string
  format: ExportDocumentFormat
}): Promise<Blob> {
  const res = await authorizedFetch("/api/v1/study/export", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  })
  return res.blob()
}
