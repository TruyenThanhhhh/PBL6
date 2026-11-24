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

export type FileKind =
  | "pdf"
  | "docx"
  | "pptx"
  | "txt"
  | "md"
  | "xlsx"
  | "xls"
  | "csv"
  | "other"

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
  category?: string
  icon?: string
  docCount?: number
  conversationCount?: number
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
  versionGroupId?: string
  versionNumber?: number
  isLatest?: boolean
  supersededBy?: string | null
  effectiveDate?: string | null
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

export interface SavedSummary {
  id: string
  workspaceId: string
  documentId: string | null
  documentName?: string | null
  title: string
  markdown: string
  focusPrompt?: string
  isMock: boolean
  createdAt: string
}

export interface Citation {
  refId: number
  /** ID nguồn ổn định (documentId cho nguồn local hoặc URL/slug cho nguồn web) */
  sourceId?: string
  documentId: string | null
  documentName: string
  pageNumber: number | null
  pageLabel?: string | null
  chunkIndex: number | null
  snippet: string
  fullText?: string
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
  pageLabel?: string | null
  chunkId: string | null
  snippet: string
  fullText?: string
  hasExactOffset: boolean
}

export type ReasoningMode = "auto" | "fast" | "deep"

export interface ReasoningStepTrace {
  step: number
  title: string
  detail: string
  status: string
}

export interface ChatActionArtifact {
  action_type:
    | "create_quiz"
    | "create_flashcards"
    | "create_mindmap"
    | "create_plan"
    | "compose_document"
    | "version_diff"
    | "reasoning_result"
  artifact_id?: string | null
  title?: string
  summary?: string
  study_tab?: string
  preview_items?: string[]
  markdown?: string
  default_format?: "docx" | "pdf" | "md"
  export_formats?: Array<"docx" | "pdf" | "md">
  goal?: string
  reasoning_steps?: ReasoningStepTrace[]
  sandbox?: {
    ok: boolean
    steps: Array<{ expr: string; value: unknown }>
    final_result: unknown
  } | null
  quiz?: Record<string, unknown>
  deck?: Record<string, unknown>
  similarity_percent?: number
  total_changes?: number
  changes?: Array<{ kind: string; before: string; after: string }>
}

export interface ChatImageAttachment {
  base64: string
  mimeType: "image/png" | "image/jpeg" | "image/webp"
  dataUrl: string
  name: string
  sizeBytes: number
}

export interface ChatMessage {
  id: string
  role: "user" | "assistant"
  content: string
  createdAt: string
  citations: Citation[]
  modeRequested?: AIMode
  modeUsed?: AIMode
  reasoningMode?: ReasoningMode
  modelId?: string
  engine?: string
  latencySeconds?: number
  fallbackReason?: string
  streaming?: boolean
  progressStage?: string
  progressLabel?: string
  reasoningSteps?: ReasoningStepTrace[]
  actionArtifact?: ChatActionArtifact | null
  imageDataUrl?: string
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
  citations?: Citation[]
  isMock?: boolean
  createdAt: string
  updatedAt: string
}

export interface QuizCitation {
  documentId: string | null
  documentName: string
  pageNumber: number | null
  chunkIndex?: number | null
  snippet?: string
}

export interface QuizQuestion {
  id: string
  prompt: string
  options: string[]
  answerIndex: number
  explanation: string
  citation?: QuizCitation | null
}

export interface QuizAttempt {
  id: string
  submittedAt: string
  score: number
  total: number
  percentage: number
  durationSeconds?: number
  answers: Record<string, number>
  wrongQuestionIds: string[]
}

export type QuizStyle = "auto" | "vocabulary" | "concept" | "application" | "mixed"

export interface Quiz {
  id: string
  workspaceId: string
  documentId: string | null
  documentName?: string | null
  focusPrompt?: string
  quizStyle?: QuizStyle
  title: string
  difficulty: "easy" | "medium" | "hard"
  questions: QuizQuestion[]
  answers: Record<string, number>
  submitted: boolean
  timeLimitMinutes?: number | null
  createdAt?: string
  attempts?: QuizAttempt[]
  isMock?: boolean
}

export type FlashcardStyle = "term_definition" | "qa" | "vocabulary" | "cloze"

export interface Flashcard {
  id: string
  workspaceId: string
  documentId: string | null
  deckId?: string | null
  front: string
  back: string
  example?: string
  cardStyle?: FlashcardStyle
  citation?: QuizCitation | null
  status: "new" | "remembered" | "review"
  reviewCount?: number
  intervalDays?: number
  nextReviewAt?: string | null
  lastReviewedAt?: string | null
  isMock?: boolean
}

export interface FlashcardDeck {
  id: string
  workspaceId: string
  documentId: string | null
  documentName?: string | null
  title: string
  cardStyle: FlashcardStyle
  focusPrompt?: string
  cards: Flashcard[]
  createdAt: string
  updatedAt: string
  lastStudiedAt?: string | null
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

export type HardwareProfileMode = "auto" | "eco" | "balanced" | "performance"

export interface HardwareSpecs {
  cpuCount: number
  totalRamGb: number
  availableRamGb: number
  gpuName: string | null
  gpuVramMb: number
  hasDedicatedGpu: boolean
}

export interface HardwareProfileOption {
  id: "eco" | "balanced" | "performance"
  label: string
  description: string
  topK: number
  numCtx: number
  rerankEnabled: boolean
  ftsFirstShortcut: boolean
  maxReasoningSteps: number
  preferredModels: string[]
}

export interface HardwareProfileSummary {
  activeId: "eco" | "balanced" | "performance"
  activeLabel: string
  selectedMode: HardwareProfileMode
  recommendedId: "eco" | "balanced" | "performance"
  specs: HardwareSpecs
  profiles: HardwareProfileOption[]
}

export interface SystemStatus {
  backendOnline: boolean
  ollamaRunning: boolean
  ollamaModels: string[]
  visionAvailable?: boolean
  internetOnline: boolean
  usingMock: boolean
  message: string
  hardwareProfile?: HardwareProfileSummary
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
  workspaceId?: string
  title: string
  snippet: string
  path: string
  trail: string
}
