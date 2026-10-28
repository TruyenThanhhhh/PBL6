export type AIMode = "auto" | "local" | "web" | "hybrid"

export type DocumentStatus =
  | "uploaded"
  | "extracting"
  | "cleaning"
  | "chunking"
  | "embedding"
  | "indexing"
  | "ready"
  | "failed"

export type FileKind = "pdf" | "docx" | "pptx" | "txt" | "md" | "other"

export type SourceKind = "local" | "web"

export type ConnectionState =
  | "online"
  | "offline"
  | "local-ai-ready"
  | "local-ai-unavailable"
  | "web-unavailable"
  | "fallback-local"

export interface Workspace {
  id: string
  name: string
  description: string
  createdAt: string
  updatedAt: string
}

export interface Notebook {
  id: string
  workspaceId: string
  name: string
  createdAt: string
}

export interface KnowledgeDocument {
  id: string
  workspaceId: string
  notebookId: string | null
  fileName: string
  fileType: FileKind
  fileSize: number
  status: DocumentStatus
  createdAt: string
  totalChunks: number
  pageCount: number
  extractedText: string
  mock?: boolean
}

export interface Note {
  id: string
  workspaceId: string
  notebookId: string | null
  documentId: string | null
  title: string
  content: string
  updatedAt: string
}

export interface Citation {
  refId: number
  /** ID nguồn ổn định (documentId cho nguồn local hoặc URL/slug cho nguồn web) */
  sourceId?: string
  documentId: string | null
  documentName: string
  pageNumber: number | null
  chunkIndex: number | null
  snippet: string
  sourceKind: SourceKind
  url?: string
  highlight?: string
  isMock?: boolean
}

export interface SourceDescriptor {
  id: string
  title: string
  kind: SourceKind
  fileType?: FileKind
  workspaceId?: string
  notebookId?: string | null
  url?: string
  exists: boolean
  isMock: boolean
}

export interface EvidenceItem {
  citation: Citation
  source: SourceDescriptor
  pageNumber: number | null
  chunkId: string | null
  snippet: string
  hasExactOffset: boolean
}

export interface ChatMessage {
  id: string
  role: "user" | "assistant"
  content: string
  createdAt: string
  citations: Citation[]
  modeRequested?: AIMode
  modeUsed?: AIMode
  modelId?: string
  engine?: string
  fallbackReason?: string
  streaming?: boolean
  isMock?: boolean
  error?: string
  attachedDocumentIds?: string[]
  notebookScopeId?: string | null
}

export interface Conversation {
  id: string
  workspaceId: string
  notebookId?: string | null
  title: string
  updatedAt: string
  messages: ChatMessage[]
}

export interface ResearchProject {
  id: string
  workspaceId: string
  notebookId?: string | null
  title: string
  question: string
  documentIds: string[]
  allowWeb: boolean
  mode: AIMode
  status: "draft" | "running" | "completed"
  step: number
  report: string
  isMock?: boolean
  createdAt: string
  updatedAt: string
}

export interface QuizQuestion {
  id: string
  prompt: string
  options: string[]
  answerIndex: number
  explanation: string
}

export interface Quiz {
  id: string
  workspaceId: string
  documentId: string | null
  title: string
  difficulty: "easy" | "medium" | "hard"
  questions: QuizQuestion[]
  answers: Record<string, number>
  submitted: boolean
  isMock?: boolean
}

export interface Flashcard {
  id: string
  workspaceId: string
  documentId: string | null
  front: string
  back: string
  status: "new" | "remembered" | "review"
  isMock?: boolean
}

export interface MindmapNode {
  id: string
  label: string
  detail?: string
  children?: MindmapNode[]
}

export interface StudyTask {
  id: string
  workspaceId: string
  documentId: string | null
  title: string
  dueDate: string
  completed: boolean
  isMock?: boolean
}

export interface Activity {
  id: string
  text: string
  at: string
  kind: "workspace" | "document" | "chat" | "study" | "research"
}

export interface SystemStatus {
  backendOnline: boolean
  ollamaRunning: boolean
  ollamaModels: string[]
  internetOnline: boolean
  usingMock: boolean
  message: string
}

export interface Toast {
  id: string
  title: string
  description?: string
  tone: "info" | "success" | "warning" | "error"
}

export interface SearchHit {
  id: string
  kind: "workspace" | "notebook" | "document" | "note" | "conversation" | "research"
  title: string
  snippet: string
  path: string
  trail: string
}
