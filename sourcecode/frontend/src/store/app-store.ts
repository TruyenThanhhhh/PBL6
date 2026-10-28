import { create } from "zustand"
import { persist } from "zustand/middleware"
import type {
  AIMode,
  Activity,
  ChatMessage,
  Citation,
  Conversation,
  Flashcard,
  KnowledgeDocument,
  Note,
  Notebook,
  Quiz,
  ResearchProject,
  StudyTask,
  SystemStatus,
  Toast,
  Workspace,
} from "@/types"
import {
  seedActivities,
  seedConversations,
  seedDocuments,
  seedFlashcards,
  seedNotebooks,
  seedNotes,
  seedQuizzes,
  seedResearch,
  seedWorkspaces,
} from "@/services/mock-data"
import { fileKindFromName, nowIso, uid } from "@/utils/format"

const seedStudyTasks: StudyTask[] = [
  {
    id: "st_1",
    workspaceId: "ws_research",
    documentId: "doc_hybrid_rag",
    title: "Đọc tóm tắt cơ chế kết hợp Dense Retrieval và BM25",
    dueDate: "2026-10-30",
    completed: true,
    isMock: true,
  },
  {
    id: "st_2",
    workspaceId: "ws_research",
    documentId: "doc_hybrid_rag",
    title: "Hoàn thành bài Quiz kiểm tra công thức RRF & Reranker",
    dueDate: "2026-11-02",
    completed: false,
    isMock: true,
  },
  {
    id: "st_3",
    workspaceId: "ws_research",
    documentId: "doc_citation",
    title: "Ôn lại các thẻ Flashcard ở trạng thái Cần ôn tập",
    dueDate: "2026-11-05",
    completed: false,
    isMock: true,
  },
]

interface AppState {
  theme: "light" | "dark"
  language: "vi" | "en"
  sidebarCollapsed: boolean
  mobileNavOpen: boolean
  citationOpen: boolean
  citationPanelWidth: number
  activeCitation: number | null
  currentWorkspaceId: string
  aiMode: AIMode
  defaultAiMode: AIMode
  webSearchEnabled: boolean
  confirmBeforeExternal: boolean
  localLlmModel: string
  embeddingModel: string
  vectorDb: string
  storagePath: string
  status: SystemStatus
  workspaces: Workspace[]
  notebooks: Notebook[]
  documents: KnowledgeDocument[]
  notes: Note[]
  conversations: Conversation[]
  researchProjects: ResearchProject[]
  quizzes: Quiz[]
  flashcards: Flashcard[]
  studyTasks: StudyTask[]
  activities: Activity[]
  toasts: Toast[]
  seedVersion: number

  setTheme: (theme: "light" | "dark") => void
  setLanguage: (language: "vi" | "en") => void
  toggleSidebar: () => void
  setMobileNavOpen: (open: boolean) => void
  setCitationOpen: (open: boolean) => void
  setCitationPanelWidth: (width: number) => void
  setActiveCitation: (ref: number | null) => void
  setCurrentWorkspace: (id: string) => void
  setAiMode: (mode: AIMode) => void
  updateSettings: (
    patch: Partial<
      Pick<
        AppState,
        | "defaultAiMode"
        | "webSearchEnabled"
        | "confirmBeforeExternal"
        | "localLlmModel"
        | "embeddingModel"
        | "vectorDb"
        | "storagePath"
        | "language"
      >
    >,
  ) => void
  setStatus: (status: SystemStatus) => void
  toast: (toast: Omit<Toast, "id">) => void
  dismissToast: (id: string) => void
  log: (text: string, kind: Activity["kind"]) => void

  createWorkspace: (name: string, description: string) => Workspace
  renameWorkspace: (id: string, name: string) => void
  updateWorkspace: (id: string, patch: Partial<Pick<Workspace, "name" | "description">>) => void
  deleteWorkspace: (id: string) => void
  createNotebook: (workspaceId: string, name: string) => Notebook
  renameNotebook: (id: string, name: string) => void
  deleteNotebook: (id: string) => void
  moveNotebook: (id: string, workspaceId: string) => void

  addDocument: (doc: KnowledgeDocument) => void
  updateDocument: (id: string, patch: Partial<KnowledgeDocument>) => void
  deleteDocument: (id: string) => void
  replaceDocumentsFromBackend: (docs: KnowledgeDocument[]) => void
  mergeWorkspacesFromBackend: (rows: Workspace[]) => void

  saveNote: (note: Note) => void
  deleteNote: (id: string) => void

  createConversation: (workspaceId: string, title?: string) => Conversation
  renameConversation: (id: string, title: string) => void
  deleteConversation: (id: string) => void
  appendMessage: (conversationId: string, message: ChatMessage) => void
  updateMessage: (conversationId: string, messageId: string, patch: Partial<ChatMessage>) => void

  upsertResearch: (project: ResearchProject) => void
  renameResearch: (id: string, title: string) => void
  deleteResearch: (id: string) => void

  upsertQuiz: (quiz: Quiz) => void
  setFlashStatus: (id: string, status: Flashcard["status"]) => void
  addFlashcards: (cards: Flashcard[]) => void
  deleteFlashcard: (id: string) => void

  addStudyTask: (task: StudyTask) => void
  updateStudyTask: (id: string, patch: Partial<StudyTask>) => void
  toggleStudyTask: (id: string) => void
  deleteStudyTask: (id: string) => void

  clearLocalData: () => void
}

const SEED_VERSION = 3

const emptyStatus: SystemStatus = {
  backendOnline: false,
  ollamaRunning: false,
  ollamaModels: [],
  internetOnline: typeof navigator !== "undefined" ? navigator.onLine : true,
  usingMock: true,
  message: "Đang dùng dữ liệu mô phỏng cho đến khi backend phản hồi.",
}

export const useAppStore = create<AppState>()(
  persist(
    (set, get) => ({
      theme: "light",
      language: "vi",
      sidebarCollapsed: false,
      mobileNavOpen: false,
      citationOpen: false,
      citationPanelWidth: 320,
      activeCitation: null,
      currentWorkspaceId: "ws_default",
      aiMode: "auto",
      defaultAiMode: "auto",
      webSearchEnabled: false,
      confirmBeforeExternal: true,
      localLlmModel: "qwen2.5:3b",
      embeddingModel: "BGE-M3 (dự kiến)",
      vectorDb: "SQLite FTS5 + Vector (dự kiến)",
      storagePath: "./sourcecode/backend/data",
      status: emptyStatus,
      workspaces: seedWorkspaces,
      notebooks: seedNotebooks,
      documents: seedDocuments,
      notes: seedNotes,
      conversations: seedConversations,
      researchProjects: seedResearch,
      quizzes: seedQuizzes,
      flashcards: seedFlashcards,
      studyTasks: seedStudyTasks,
      activities: seedActivities,
      toasts: [],
      seedVersion: SEED_VERSION,

      setTheme: (theme) => {
        set({ theme })
        document.documentElement.classList.toggle("dark", theme === "dark")
      },
      setLanguage: (language) => set({ language }),
      toggleSidebar: () => set({ sidebarCollapsed: !get().sidebarCollapsed }),
      setMobileNavOpen: (mobileNavOpen) => set({ mobileNavOpen }),
      setCitationOpen: (citationOpen) => set({ citationOpen }),
      setCitationPanelWidth: (citationPanelWidth) =>
        set({ citationPanelWidth: Math.min(460, Math.max(280, citationPanelWidth)) }),
      setActiveCitation: (activeCitation) => set({ activeCitation, citationOpen: true }),
      setCurrentWorkspace: (currentWorkspaceId) => set({ currentWorkspaceId }),
      setAiMode: (aiMode) => set({ aiMode }),
      updateSettings: (patch) => set(patch),
      setStatus: (status) => set({ status }),
      toast: (toast) => {
        const id = uid("toast")
        set({ toasts: [...get().toasts, { ...toast, id }] })
        window.setTimeout(() => get().dismissToast(id), 4000)
      },
      dismissToast: (id) => set({ toasts: get().toasts.filter((t) => t.id !== id) }),
      log: (text, kind) =>
        set({
          activities: [{ id: uid("act"), text, at: nowIso(), kind }, ...get().activities].slice(
            0,
            40,
          ),
        }),

      createWorkspace: (name, description) => {
        const ws: Workspace = {
          id: uid("ws"),
          name,
          description,
          createdAt: nowIso(),
          updatedAt: nowIso(),
        }
        set({ workspaces: [ws, ...get().workspaces], currentWorkspaceId: ws.id })
        get().log(`Tạo workspace ${name}`, "workspace")
        return ws
      },
      updateWorkspace: (id, patch) =>
        set({
          workspaces: get().workspaces.map((w) =>
            w.id === id ? { ...w, ...patch, updatedAt: nowIso() } : w,
          ),
        }),
      renameWorkspace: (id, name) =>
        set({
          workspaces: get().workspaces.map((w) =>
            w.id === id ? { ...w, name, updatedAt: nowIso() } : w,
          ),
        }),
      deleteWorkspace: (id) => {
        const next = get().workspaces.filter((w) => w.id !== id)
        set({
          workspaces: next,
          notebooks: get().notebooks.filter((n) => n.workspaceId !== id),
          documents: get().documents.filter((d) => d.workspaceId !== id),
          notes: get().notes.filter((n) => n.workspaceId !== id),
          conversations: get().conversations.filter((c) => c.workspaceId !== id),
          researchProjects: get().researchProjects.filter((p) => p.workspaceId !== id),
          quizzes: get().quizzes.filter((q) => q.workspaceId !== id),
          flashcards: get().flashcards.filter((f) => f.workspaceId !== id),
          studyTasks: get().studyTasks.filter((t) => t.workspaceId !== id),
          currentWorkspaceId:
            get().currentWorkspaceId === id ? next[0]?.id ?? "" : get().currentWorkspaceId,
        })
        get().log("Đã xóa một workspace", "workspace")
      },
      createNotebook: (workspaceId, name) => {
        const nb: Notebook = { id: uid("nb"), workspaceId, name, createdAt: nowIso() }
        set({
          notebooks: [...get().notebooks, nb],
          workspaces: get().workspaces.map((w) =>
            w.id === workspaceId ? { ...w, updatedAt: nowIso() } : w,
          ),
        })
        return nb
      },
      renameNotebook: (id, name) =>
        set({
          notebooks: get().notebooks.map((n) => (n.id === id ? { ...n, name } : n)),
        }),
      deleteNotebook: (id) =>
        set({
          notebooks: get().notebooks.filter((n) => n.id !== id),
          documents: get().documents.map((d) =>
            d.notebookId === id ? { ...d, notebookId: null } : d,
          ),
          notes: get().notes.map((n) => (n.notebookId === id ? { ...n, notebookId: null } : n)),
        }),
      moveNotebook: (id, workspaceId) =>
        set({
          notebooks: get().notebooks.map((n) => (n.id === id ? { ...n, workspaceId } : n)),
          documents: get().documents.map((d) =>
            d.notebookId === id ? { ...d, workspaceId } : d,
          ),
          notes: get().notes.map((n) => (n.notebookId === id ? { ...n, workspaceId } : n)),
        }),

      addDocument: (doc) => {
        set({ documents: [doc, ...get().documents] })
        get().log(`Tải lên ${doc.fileName}`, "document")
      },
      updateDocument: (id, patch) =>
        set({
          documents: get().documents.map((d) => (d.id === id ? { ...d, ...patch } : d)),
        }),
      deleteDocument: (id) => {
        set({ documents: get().documents.filter((d) => d.id !== id) })
        get().log("Đã xóa một tài liệu", "document")
      },
      replaceDocumentsFromBackend: (docs) => {
        const localOnly = get().documents.filter((d) => d.mock)
        const merged = [...docs, ...localOnly.filter((d) => !docs.some((x) => x.id === d.id))]
        set({ documents: merged })
      },
      mergeWorkspacesFromBackend: (rows) => {
        const local = get().workspaces
        const extra = rows.filter((r) => !local.some((l) => l.id === r.id || l.name === r.name))
        if (extra.length) set({ workspaces: [...local, ...extra] })
      },

      saveNote: (note) => {
        const exists = get().notes.some((n) => n.id === note.id)
        set({
          notes: exists
            ? get().notes.map((n) => (n.id === note.id ? note : n))
            : [note, ...get().notes],
        })
      },
      deleteNote: (id) => set({ notes: get().notes.filter((n) => n.id !== id) }),

      createConversation: (workspaceId, title = "Cuộc trò chuyện mới") => {
        const conv: Conversation = {
          id: uid("conv"),
          workspaceId,
          title,
          updatedAt: nowIso(),
          messages: [],
        }
        set({ conversations: [conv, ...get().conversations] })
        return conv
      },
      renameConversation: (id, title) =>
        set({
          conversations: get().conversations.map((c) => (c.id === id ? { ...c, title } : c)),
        }),
      deleteConversation: (id) =>
        set({ conversations: get().conversations.filter((c) => c.id !== id) }),
      appendMessage: (conversationId, message) =>
        set({
          conversations: get().conversations.map((c) =>
            c.id === conversationId
              ? { ...c, updatedAt: nowIso(), messages: [...c.messages, message] }
              : c,
          ),
        }),
      updateMessage: (conversationId, messageId, patch) =>
        set({
          conversations: get().conversations.map((c) =>
            c.id === conversationId
              ? {
                  ...c,
                  messages: c.messages.map((m) => (m.id === messageId ? { ...m, ...patch } : m)),
                }
              : c,
          ),
        }),

      upsertResearch: (project) => {
        const exists = get().researchProjects.some((p) => p.id === project.id)
        set({
          researchProjects: exists
            ? get().researchProjects.map((p) => (p.id === project.id ? project : p))
            : [project, ...get().researchProjects],
        })
      },
      renameResearch: (id, title) =>
        set({
          researchProjects: get().researchProjects.map((p) =>
            p.id === id ? { ...p, title, updatedAt: nowIso() } : p,
          ),
        }),
      deleteResearch: (id) =>
        set({
          researchProjects: get().researchProjects.filter((p) => p.id !== id),
        }),

      upsertQuiz: (quiz) =>
        set({
          quizzes: get().quizzes.some((q) => q.id === quiz.id)
            ? get().quizzes.map((q) => (q.id === quiz.id ? quiz : q))
            : [quiz, ...get().quizzes],
        }),
      setFlashStatus: (id, status) =>
        set({
          flashcards: get().flashcards.map((f) => (f.id === id ? { ...f, status } : f)),
        }),
      addFlashcards: (cards) => set({ flashcards: [...cards, ...get().flashcards] }),
      deleteFlashcard: (id) =>
        set({ flashcards: get().flashcards.filter((f) => f.id !== id) }),

      addStudyTask: (task) =>
        set({ studyTasks: [task, ...get().studyTasks] }),
      updateStudyTask: (id, patch) =>
        set({
          studyTasks: get().studyTasks.map((t) => (t.id === id ? { ...t, ...patch } : t)),
        }),
      toggleStudyTask: (id) =>
        set({
          studyTasks: get().studyTasks.map((t) =>
            t.id === id ? { ...t, completed: !t.completed } : t,
          ),
        }),
      deleteStudyTask: (id) =>
        set({ studyTasks: get().studyTasks.filter((t) => t.id !== id) }),

      clearLocalData: () => {
        set({
          workspaces: seedWorkspaces,
          notebooks: seedNotebooks,
          documents: seedDocuments,
          notes: seedNotes,
          conversations: seedConversations,
          researchProjects: seedResearch,
          quizzes: seedQuizzes,
          flashcards: seedFlashcards,
          studyTasks: seedStudyTasks,
          activities: seedActivities,
          seedVersion: SEED_VERSION,
        })
        get().toast({ title: "Đã khôi phục dữ liệu mẫu", tone: "warning" })
      },
    }),
    {
      name: "knowledge-ai-store",
      version: 3,
      migrate: (persistedState: unknown, version: number) => {
        const state = (persistedState ?? {}) as Record<string, unknown>
        if (version < 3) {
          const workspaces = Array.isArray(state.workspaces) ? state.workspaces : []
          const hasDefault = workspaces.some((w: any) => w.id === "ws_default")
          const defaultWs = {
            id: "ws_default",
            name: "Không gian mặc định",
            description: "Không gian làm việc cá nhân của bạn. Bắt đầu bằng việc tải tài liệu hoặc tạo cuộc trò chuyện AI mới.",
            createdAt: new Date().toISOString(),
            updatedAt: new Date().toISOString(),
          }
          return {
            ...state,
            workspaces: hasDefault ? workspaces : [defaultWs, ...workspaces],
            currentWorkspaceId: "ws_default",
            seedVersion: 3,
          }
        }
        return state
      },
      partialize: (s) => ({
        theme: s.theme,
        language: s.language,
        sidebarCollapsed: s.sidebarCollapsed,
        currentWorkspaceId: s.currentWorkspaceId,
        aiMode: s.aiMode,
        defaultAiMode: s.defaultAiMode,
        webSearchEnabled: s.webSearchEnabled,
        confirmBeforeExternal: s.confirmBeforeExternal,
        localLlmModel: s.localLlmModel,
        embeddingModel: s.embeddingModel,
        vectorDb: s.vectorDb,
        storagePath: s.storagePath,
        workspaces: s.workspaces,
        notebooks: s.notebooks,
        documents: s.documents,
        notes: s.notes,
        conversations: s.conversations,
        researchProjects: s.researchProjects,
        quizzes: s.quizzes,
        flashcards: s.flashcards,
        studyTasks: s.studyTasks,
        activities: s.activities,
        seedVersion: s.seedVersion,
      }),
    },
  ),
)

export function buildUploadedDocument(
  file: File,
  workspaceId: string,
  notebookId: string | null,
): KnowledgeDocument {
  return {
    id: uid("doc"),
    workspaceId,
    notebookId,
    fileName: file.name,
    fileType: fileKindFromName(file.name),
    fileSize: file.size,
    status: "uploaded",
    createdAt: nowIso(),
    totalChunks: 0,
    pageCount: 0,
    extractedText: "",
    mock: true,
  }
}

export const MOCK_ANSWER: { content: string; citations: Citation[] } = {
  content: `## Tóm tắt

Hybrid RAG kết hợp **vector search** và **BM25**, rồi hợp nhất bằng RRF trước khi rerank.[1]

### Điểm khác biệt
- Dense: nắm ý, kể cả khi diễn đạt khác từ.
- Sparse: giữ từ khóa, tên riêng, mã kỹ thuật.[2]

Nếu không tìm thấy đoạn phù hợp trong kho, câu trả lời **không được coi là đã kiểm chứng**.`,
  citations: [
    {
      refId: 1,
      sourceId: "doc_hybrid_rag",
      documentId: "doc_hybrid_rag",
      documentName: "Hybrid-RAG-Survey.pdf",
      pageNumber: 3,
      chunkIndex: 4,
      snippet:
        "Hybrid Retrieval-Augmented Generation (Hybrid RAG) kết hợp hai kênh truy xuất.",
      sourceKind: "local",
      highlight: "kết hợp hai kênh truy xuất",
      isMock: true,
    },
    {
      refId: 2,
      sourceId: "doc_hybrid_rag",
      documentId: "doc_hybrid_rag",
      documentName: "Hybrid-RAG-Survey.pdf",
      pageNumber: 4,
      chunkIndex: 6,
      snippet:
        "Kênh sparse (BM25 / FTS5) khớp từ khóa chính xác, tên riêng, mã hiệu và thuật ngữ kỹ thuật.",
      sourceKind: "local",
      highlight: "khớp từ khóa chính xác",
      isMock: true,
    },
  ],
}
