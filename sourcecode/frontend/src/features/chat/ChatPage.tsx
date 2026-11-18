import { useEffect, useMemo, useRef, useState } from "react"
import { useNavigate, useParams } from "react-router-dom"
import {
  ArrowUpRight,
  BookOpen,
  Check,
  Compass,
  Copy,
  FileQuestion,
  FileText,
  GraduationCap,
  Layers,
  MoreHorizontal,
  PanelRightOpen,
  Pencil,
  Plus,
  Quote,
  RefreshCw,
  Search,
  Sparkles,
  ThumbsDown,
  ThumbsUp,
  Trash2,
  Network,
  Calendar,
} from "lucide-react"
import { InlineEdit } from "@/components/common/InlineEdit"
import { ConfirmDialog, NameDialog } from "@/components/common/NameDialog"
import {
  Alert,
  Button,
  DropdownMenu,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  Tooltip,
} from "@/components/ui"
import { CitationMarkdown } from "@/features/citations/CitationMarkdown"
import {
  createConversationApi,
  deleteConversationApi,
  fetchDocuments,
  fetchConversationMessages,
  renameConversationApi,
  saveStudyArtifactApi,
  uploadDocumentWithProgress,
} from "@/services/api"
import { getAuthToken } from "@/services/auth-service"
import {
  getModeDescriptor,
  sendChatMessageService,
} from "@/services/chat-service"
import {
  generateStudyFlashcardDeckAsync,
  generateStudyMindmapAsync,
  generateStudyPlanAsync,
  generateStudyQuizAsync,
  type StudySourceContext,
} from "@/services/study-service"
import { useAppStore } from "@/store/app-store"
import { formatDate, nowIso, uid } from "@/utils/format"
import type { AIMode, ChatMessage, Conversation } from "@/types"
import { cn } from "@/utils/cn"
import { ModeSelector } from "./ModeSelector"
import { CitationPanel } from "./CitationPanel"
import { ChatComposer } from "./ChatComposer"

function parseMessageSuggestions(rawContent: string): { mainContent: string; suggestions: string[] } {
  if (!rawContent) return { mainContent: "", suggestions: [] }
  const separator = "---GỢI Ý TIẾP THEO---"
  const idx = rawContent.indexOf(separator)
  if (idx === -1) {
    // Ẩn marker đang stream dở ở cuối nếu có (ví dụ: "\n\n---GỢI...")
    const streamTrim = rawContent.replace(/\n+---(?:G(?:Ợ(?:I(?: (?:\w*)?)?)?)?)?$/i, "")
    return { mainContent: streamTrim, suggestions: [] }
  }
  const mainContent = rawContent.slice(0, idx).trimEnd()
  const rawSuggestions = rawContent.slice(idx + separator.length).trim()
  const suggestions = rawSuggestions
    .split("\n")
    .map((line) =>
      line
        // Xóa gạch đầu dòng, số thứ tự dạng 1., 1), [1], (1), v.v.
        .replace(/^[-*•\s]*(?:\[?\d+[\]\).:]\s*)?/, "")
        .trim()
    )
    .filter((line) => line.length > 3 && line.length < 150 && !line.startsWith("---"))
    .slice(0, 3)

  return { mainContent, suggestions }
}

export function ChatPage() {
  const { conversationId } = useParams()
  const navigate = useNavigate()

  const conversations = useAppStore((s) => s.conversations)
  const workspaces = useAppStore((s) => s.workspaces)
  const notebooks = useAppStore((s) => s.notebooks)
  const documents = useAppStore((s) => s.documents)
  const currentWs = useAppStore((s) => s.currentWorkspaceId)
  const createConversation = useAppStore((s) => s.createConversation)
  const renameConversation = useAppStore((s) => s.renameConversation)
  const deleteConversation = useAppStore((s) => s.deleteConversation)
  const replaceDocumentsFromBackend = useAppStore((s) => s.replaceDocumentsFromBackend)
  const appendMessage = useAppStore((s) => s.appendMessage)
  const updateMessage = useAppStore((s) => s.updateMessage)
  const setConversationMessages = useAppStore((s) => s.setConversationMessages)

  const saveNote = useAppStore((s) => s.saveNote)
  const upsertQuiz = useAppStore((s) => s.upsertQuiz)
  const upsertFlashcardDeck = useAppStore((s) => s.upsertFlashcardDeck)
  const addStudyTask = useAppStore((s) => s.addStudyTask)

  const aiMode = useAppStore((s) => s.aiMode)
  const setAiMode = useAppStore((s) => s.setAiMode)
  const citationOpen = useAppStore((s) => s.citationOpen)
  const setCitationOpen = useAppStore((s) => s.setCitationOpen)
  const setActiveCitation = useAppStore((s) => s.setActiveCitation)
  const status = useAppStore((s) => s.status)
  const toast = useAppStore((s) => s.toast)
  const webSearchEnabled = useAppStore((s) => s.webSearchEnabled)
  const confirmBeforeExternal = useAppStore((s) => s.confirmBeforeExternal)
  const localLlmModel = useAppStore((s) => s.localLlmModel)
  const updateSettings = useAppStore((s) => s.updateSettings)

  const [input, setInput] = useState("")
  const [busy, setBusy] = useState(false)
  const [uploadingAttachment, setUploadingAttachment] = useState(false)
  const [copiedMsgId, setCopiedMsgId] = useState<string | null>(null)
  const [feedbackMap, setFeedbackMap] = useState<Record<string, "up" | "down">>({})

  const [selectedNotebookId, setSelectedNotebookId] = useState<string | null>(null)
  const [attachedDocIds, setAttachedDocIds] = useState<string[]>([])

  const [renameTarget, setRenameTarget] = useState<Conversation | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<Conversation | null>(null)
  const [loadingMessages, setLoadingMessages] = useState(false)
  const loadedConvIdsRef = useRef<Set<string>>(new Set())

  const abortRef = useRef<AbortController | null>(null)
  const bottomRef = useRef<HTMLDivElement>(null)

  const currentWorkspace = workspaces.find((w) => w.id === currentWs) ?? workspaces[0]
  const currentWsId = currentWorkspace?.id ?? "ws_default"

  const workspaceNotebooks = useMemo(
    () => notebooks.filter((n) => n.workspaceId === currentWsId),
    [notebooks, currentWsId],
  )
  const workspaceDocuments = useMemo(
    () => documents.filter((d) => d.workspaceId === currentWsId),
    [documents, currentWsId],
  )

  const wsConversations = useMemo(
    () => conversations.filter((c) => c.workspaceId === currentWsId),
    [conversations, currentWsId],
  )

  const conversation = useMemo(() => {
    if (conversationId) {
      return wsConversations.find((c) => c.id === conversationId) ?? null
    }
    return wsConversations[0] ?? null
  }, [wsConversations, conversationId])

  useEffect(() => {
    const convId = conversation?.id
    if (!convId || !getAuthToken()) {
      setLoadingMessages(false)
      return
    }
    if (loadedConvIdsRef.current.has(convId)) {
      setLoadingMessages(false)
      return
    }
    if (conversation.messages.length > 0) {
      loadedConvIdsRef.current.add(convId)
      setLoadingMessages(false)
      return
    }

    let active = true
    setLoadingMessages(true)
    fetchConversationMessages(convId)
      .then((msgs) => {
        if (active) {
          loadedConvIdsRef.current.add(convId)
          setConversationMessages(convId, msgs)
        }
      })
      .catch((err) => {
        console.error("Failed to load conversation messages:", err)
      })
      .finally(() => {
        if (active) setLoadingMessages(false)
      })

    return () => {
      active = false
    }
  }, [conversation?.id, conversation?.messages.length, setConversationMessages])

  useEffect(() => {
    if (conversationId) {
      const targetConv = conversations.find((c) => c.id === conversationId)
      if (targetConv && targetConv.workspaceId !== currentWsId) {
        if (wsConversations[0]) {
          navigate(`/chat/${wsConversations[0].id}`, { replace: true })
        } else {
          navigate("/chat", { replace: true })
        }
      }
    } else if (wsConversations[0]) {
      navigate(`/chat/${wsConversations[0].id}`, { replace: true })
    }
  }, [conversationId, currentWsId, conversations, wsConversations, navigate])

  const scopedAttachedDocIds = useMemo(
    () => attachedDocIds.filter((id) => workspaceDocuments.some((d) => d.id === id)),
    [attachedDocIds, workspaceDocuments],
  )

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [conversation?.messages.length, busy])

  const lastAssistant = useMemo(
    () => [...(conversation?.messages ?? [])].reverse().find((m) => m.role === "assistant"),
    [conversation?.messages],
  )

  const readyDocs = useMemo(
    () => workspaceDocuments.filter((d) => d.status === "ready"),
    [workspaceDocuments],
  )

  // Tối đa 4 suggestion cards, mỗi card có icon, tiêu đề và mô tả ngắn gọn
  const suggestionCards = useMemo(() => {
    const firstDoc = readyDocs[0] || workspaceDocuments[0]
    const secondDoc = readyDocs[1] || workspaceDocuments[1]

    if (firstDoc && secondDoc) {
      return [
        {
          icon: FileText,
          title: "Tóm tắt ý chính",
          description: `Rút trích các luận điểm cốt lõi trong ${firstDoc.fileName}.`,
          prompt: `Tóm tắt các luận điểm cốt lõi trong tài liệu "${firstDoc.fileName}" kèm trích dẫn số trang.`,
        },
        {
          icon: Layers,
          title: "Đối chiếu tài liệu",
          description: `So sánh điểm chung & khác biệt giữa 2 tài liệu.`,
          prompt: `Đối chiếu và so sánh các ý chính giữa "${firstDoc.fileName}" và "${secondDoc.fileName}".`,
        },
        {
          icon: Compass,
          title: "Thuật ngữ trọng tâm",
          description: `Giải thích các khái niệm quan trọng nhất.`,
          prompt: `Liệt kê và định nghĩa các thuật ngữ kỹ thuật trọng tâm trong kho tài liệu này.`,
        },
        {
          icon: FileQuestion,
          title: "Bộ câu hỏi ôn tập",
          description: `Tạo 5 câu hỏi kiểm tra kèm đáp án đối chiếu.`,
          prompt: `Tạo 5 câu hỏi ôn tập kèm đáp án dựa trên các tài liệu đã tải lên.`,
        },
      ]
    }

    if (firstDoc) {
      return [
        {
          icon: FileText,
          title: "Tóm tắt nội dung",
          description: `Tổng quan ý chính từ ${firstDoc.fileName}.`,
          prompt: `Tóm tắt nội dung chính trong tài liệu "${firstDoc.fileName}" kèm trích dẫn.`,
        },
        {
          icon: Compass,
          title: "Phân tích phát hiện",
          description: `Các kết luận quan trọng nhất được nêu trong tài liệu.`,
          prompt: `Những kết luận hoặc phương pháp quan trọng nhất trong "${firstDoc.fileName}" là gì?`,
        },
        {
          icon: Search,
          title: "Định nghĩa khái niệm",
          description: `Tra cứu các thuật ngữ chuyên ngành có trong tệp.`,
          prompt: `Giải thích các thuật ngữ chuyên ngành xuất hiện trong "${firstDoc.fileName}".`,
        },
        {
          icon: FileQuestion,
          title: "Câu hỏi kiểm tra",
          description: `Đặt câu hỏi trắc nghiệm tự ôn tập.`,
          prompt: `Đặt 5 câu hỏi ôn tập từ nội dung của "${firstDoc.fileName}".`,
        },
      ]
    }

    return [
      {
        icon: Compass,
        title: "Tổng quan chủ đề",
        description: "Khái quát các kiến thức nền tảng trong không gian.",
        prompt: `Tóm tắt các kiến thức nền tảng trong không gian làm việc này.`,
      },
      {
        icon: Layers,
        title: "Kiến trúc Hybrid RAG",
        description: "Dense vector, BM25 và Reciprocal Rank Fusion.",
        prompt: "Phân tích sự kết hợp giữa Dense Search, BM25 và RRF trong truy xuất tri thức.",
      },
      {
        icon: Quote,
        title: "Kiểm chứng trích dẫn",
        description: "Đối chiếu câu trả lời với từng chunk và trang.",
        prompt: "Làm thế nào để kiểm chứng câu trả lời AI thông qua Citation trích dẫn?",
      },
      {
        icon: FileQuestion,
        title: "Lộ trình ôn tập",
        description: "Gợi ý kế hoạch đọc hiểu tài liệu hiệu quả.",
        prompt: "Gợi ý kế hoạch đọc hiểu và ghi chú cho chủ đề nghiên cứu hiện tại.",
      },
    ]
  }, [readyDocs, workspaceDocuments])

  const handleModeChange = (nextMode: AIMode) => {
    setAiMode(nextMode)
    const desc = getModeDescriptor(nextMode)
    toast({
      title: `Chế độ truy xuất: ${desc.label}`,
      description: desc.shortHint,
      tone: "info",
    })
  }

  const handleModelChange = (nextModel: string) => {
    updateSettings({ localLlmModel: nextModel })
    toast({
      title: "Đã đổi mô hình trả lời",
      tone: "info",
    })
  }

  const handleCreateConversation = async () => {
    if (getAuthToken()) {
      try {
        const created = await createConversationApi(currentWsId, "Cuộc trò chuyện mới")
        useAppStore.setState((s) => ({
          conversations: [created, ...s.conversations],
        }))
        navigate(`/chat/${created.id}`)
        return
      } catch (err) {
        console.error("Create conversation API error:", err)
      }
    }
    const created = createConversation(currentWsId, "Cuộc trò chuyện mới")
    navigate(`/chat/${created.id}`)
  }

  const handleRenameConversation = async (convId: string, newTitle: string) => {
    renameConversation(convId, newTitle)
    if (getAuthToken()) {
      try {
        await renameConversationApi(convId, newTitle)
      } catch (err) {
        console.error("Rename conversation API error:", err)
      }
    }
  }

  const handleConfirmDeleteConversation = async () => {
    if (!deleteTarget) return
    const targetId = deleteTarget.id
    if (getAuthToken()) {
      try {
        await deleteConversationApi(targetId)
      } catch (err) {
        console.error("Delete conversation API error:", err)
      }
    }
    deleteConversation(targetId)
    setDeleteTarget(null)
    toast({ title: "Đã xóa cuộc trò chuyện", description: deleteTarget.title, tone: "info" })
    if (conversation?.id === targetId) {
      const remaining = wsConversations.filter((c) => c.id !== targetId)
      if (remaining[0]) {
        navigate(`/chat/${remaining[0].id}`)
      } else {
        navigate("/chat")
      }
    }
  }

  const handleCancelRequest = () => {
    if (abortRef.current) {
      abortRef.current.abort()
      abortRef.current = null
    }
  }

  const handleUploadAttachment = async (files: File[]) => {
    if (uploadingAttachment || files.length === 0) return
    if (!status.backendOnline) {
      toast({ title: "Cần kết nối Backend để tải và lập chỉ mục tệp", tone: "warning" })
      return
    }

    setUploadingAttachment(true)
    const uploadedIds: string[] = []
    try {
      for (const file of files) {
        if (file.size > 25 * 1024 * 1024) {
          throw new Error(`Tệp “${file.name}” vượt quá giới hạn 25 MB.`)
        }
        const result = await uploadDocumentWithProgress(currentWsId, file, { deferMetadata: true })
        const documentId = String(result.document?.document_id ?? "")
        if (!documentId) throw new Error(`Backend chưa trả về mã của tệp “${file.name}”.`)
        uploadedIds.push(documentId)
      }

      const refreshedDocs = await fetchDocuments(currentWsId)
      const otherWorkspaceDocs = useAppStore.getState().documents.filter(
        (doc) => doc.workspaceId !== currentWsId,
      )
      replaceDocumentsFromBackend([...otherWorkspaceDocs, ...refreshedDocs])

      const indexedIds = uploadedIds.filter((id) => refreshedDocs.some(
        (doc) => doc.id === id && doc.status === "ready",
      ))
      if (indexedIds.length > 0) {
        setAttachedDocIds(indexedIds)
      }
      if (indexedIds.length !== uploadedIds.length) {
        throw new Error("Một số tệp chưa lập chỉ mục xong. Hãy thử lại từ mục Tài liệu.")
      }

      toast({
        title: indexedIds.length === 1 ? "Đã tải và thêm tệp vào cuộc trò chuyện" : `Đã tải và thêm ${indexedIds.length} tệp vào cuộc trò chuyện`,
        tone: "success",
      })
    } catch (error) {
      toast({
        title: "Không thể thêm tệp",
        description: error instanceof Error ? error.message : String(error),
        tone: "error",
      })
    } finally {
      setUploadingAttachment(false)
    }
  }

  const sendQuery = async (queryText: string, regenerateAssistantId?: string) => {
    const trimmed = queryText.trim()
    if (!trimmed || busy) return

    let activeConv = conversation
    if (!activeConv) {
      if (getAuthToken()) {
        try {
          activeConv = await createConversationApi(currentWsId, trimmed.slice(0, 68))
          useAppStore.setState((s) => ({
            conversations: [activeConv!, ...s.conversations],
          }))
        } catch {
          activeConv = createConversation(currentWsId, trimmed.slice(0, 68))
        }
      } else {
        activeConv = createConversation(currentWsId, trimmed.slice(0, 68))
      }
      navigate(`/chat/${activeConv.id}`, { replace: true })
    }

    const mode: AIMode = aiMode
    if ((mode === "web" || mode === "hybrid") && !webSearchEnabled && confirmBeforeExternal) {
      const ok = window.confirm(
        "Chế độ Internet / Kết hợp có thể tìm kiếm thông tin bên ngoài. Bạn có muốn tiếp tục?",
      )
      if (!ok) return
    }

    const convId = activeConv.id

    if (!regenerateAssistantId) {
      appendMessage(convId, {
        id: uid("msg"),
        role: "user",
        content: trimmed,
        createdAt: nowIso(),
        citations: [],
        modeRequested: mode,
        attachedDocumentIds: scopedAttachedDocIds.length ? [...scopedAttachedDocIds] : undefined,
        notebookScopeId: selectedNotebookId,
      })
      if (activeConv.title === "Cuộc trò chuyện mới") {
        void handleRenameConversation(convId, trimmed.slice(0, 68))
      }
      setInput("")
    }

    const assistantId = regenerateAssistantId ?? uid("msg")
    if (regenerateAssistantId) {
      updateMessage(convId, assistantId, {
        content: "",
        streaming: true,
        error: undefined,
        fallbackReason: undefined,
        modeRequested: mode,
        modelId: localLlmModel,
      })
    } else {
      appendMessage(convId, {
        id: assistantId,
        role: "assistant",
        content: "",
        createdAt: nowIso(),
        citations: [],
        streaming: true,
        modeRequested: mode,
        modelId: localLlmModel,
      })
    }

    setBusy(true)
    const controller = new AbortController()
    abortRef.current = controller

    try {
      const { message } = await sendChatMessageService({
        conversationId: convId,
        workspaceId: currentWsId,
        notebookScopeId: selectedNotebookId,
        attachedDocumentIds: attachedDocIds,
        query: trimmed,
        mode,
        modelId: localLlmModel,
        backendOnline: status.backendOnline,
        contextDocuments: workspaceDocuments,
        signal: controller.signal,
        onStreamChunk: (partial) => {
          updateMessage(convId, assistantId, {
            content: partial,
            streaming: true,
          })
        },
      })

      updateMessage(convId, assistantId, {
        ...message,
        id: assistantId,
        streaming: false,
        error: undefined,
      })

      if (message.citations[0]) {
        setActiveCitation(message.citations[0].refId)
        setCitationOpen(true)
      }
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") {
        updateMessage(convId, assistantId, {
          content: "*(Đã dừng tạo câu trả lời)*",
          streaming: false,
          isMock: !status.backendOnline,
        })
      } else {
        const errMsg = err instanceof Error ? err.message : String(err)
        updateMessage(convId, assistantId, {
          content: "",
          streaming: false,
          error: errMsg || "Không thể nhận phản hồi từ dịch vụ AI.",
        })
        toast({
          title: "Lỗi khi tạo câu trả lời",
          description: errMsg,
          tone: "error",
        })
      }
    } finally {
      setBusy(false)
      abortRef.current = null
    }
  }

  const findPrecedingUserPrompt = (assistantMsgId: string): string | null => {
    if (!conversation) return null
    const idx = conversation.messages.findIndex((m) => m.id === assistantMsgId)
    if (idx <= 0) {
      const lastUser = [...conversation.messages].reverse().find((m) => m.role === "user")
      return lastUser?.content ?? null
    }
    for (let i = idx - 1; i >= 0; i -= 1) {
      if (conversation.messages[i].role === "user") {
        return conversation.messages[i].content
      }
    }
    return null
  }

  const handleCopyMessage = async (msg: ChatMessage) => {
    if (!msg.content) return
    const { mainContent } = parseMessageSuggestions(msg.content)
    try {
      await navigator.clipboard.writeText(mainContent || msg.content)
      setCopiedMsgId(msg.id)
      window.setTimeout(() => setCopiedMsgId(null), 1800)
      toast({ title: "Đã sao chép câu trả lời", tone: "success" })
    } catch {
      toast({ title: "Không thể sao chép tự động", tone: "warning" })
    }
  }

  const handleFeedback = (msgId: string, vote: "up" | "down") => {
    setFeedbackMap((prev) => ({ ...prev, [msgId]: vote }))
    toast({
      title: vote === "up" ? "Cảm ơn phản hồi của bạn" : "Đã ghi nhận phản hồi",
      tone: "info",
    })
  }

  const handleCreateStudyFromMessage = async (
    msg: ChatMessage,
    kind: "summary" | "quiz" | "flashcards" | "mindmap" | "plan",
  ) => {
    const { mainContent } = parseMessageSuggestions(msg.content)
    const effectiveContent = mainContent || msg.content
    const promptTitle = findPrecedingUserPrompt(msg.id) || conversation?.title || "Nội dung AI"
    const citedDocId = msg.citations[0]?.documentId ?? workspaceDocuments[0]?.id ?? null
    const citedDoc = workspaceDocuments.find((d) => d.id === citedDocId) ?? null
    const ctx: StudySourceContext = {
      workspaceId: currentWsId,
      notebook: workspaceNotebooks.find((n) => n.id === selectedNotebookId) ?? null,
      document: citedDoc,
      documentsInScope: workspaceDocuments,
    }

    if (kind === "summary") {
      saveNote({
        id: uid("note"),
        workspaceId: currentWsId,
        notebookId: selectedNotebookId,
        documentId: citedDocId,
        title: `Tóm tắt: ${promptTitle.slice(0, 48)}`,
        content: effectiveContent,
        updatedAt: nowIso(),
      })
      toast({
        title: "Đã lưu vào Học liệu",
        tone: "success",
      })
      navigate("/study?tab=notes")
      return
    }

    if (kind === "quiz") {
      toast({
        title: "AI đang soạn bộ câu hỏi Quiz...",
        tone: "info",
      })
      try {
        const quiz = await generateStudyQuizAsync(ctx, "medium", 5, promptTitle.slice(0, 50))
        upsertQuiz({
          ...quiz,
          title: `Quiz: ${promptTitle.slice(0, 40)}`,
        })
        toast({
          title: "Đã tạo bộ câu hỏi Quiz AI thành công",
          tone: "success",
        })
        navigate("/study?tab=quiz")
      } catch (e) {
        toast({
          title: "Không thể tạo Quiz lúc này",
          tone: "error",
        })
      }
      return
    }

    if (kind === "flashcards") {
      toast({
        title: "AI đang tạo bộ Flashcards...",
        tone: "info",
      })
      try {
        const deck = await generateStudyFlashcardDeckAsync(ctx, 10, promptTitle.slice(0, 50))
        let savedDeck = deck
        if (getAuthToken() && status.backendOnline) {
          try {
            const saved = await saveStudyArtifactApi(currentWsId, {
              document_id: deck.documentId,
              artifact_type: "flashcard_deck",
              title: deck.title,
              data: {
                documentName: deck.documentName ?? null,
                cardStyle: deck.cardStyle,
                focusPrompt: deck.focusPrompt ?? "",
                cards: deck.cards,
                updatedAt: deck.updatedAt,
                lastStudiedAt: deck.lastStudiedAt ?? null,
                isMock: Boolean(deck.isMock),
              },
            })
            savedDeck = { ...deck, id: saved.artifact.id }
          } catch {
            // Lưu local nếu API artifact tạm thời lỗi
          }
        }
        upsertFlashcardDeck(savedDeck)
        toast({
          title: `Đã tạo bộ ${savedDeck.cards.length} Flashcards AI thành công`,
          tone: "success",
        })
        navigate("/study?tab=flashcards")
      } catch {
        toast({
          title: "Không thể tạo Flashcards lúc này",
          tone: "error",
        })
      }
      return
    }

    if (kind === "mindmap") {
      toast({
        title: "AI đang kiến tạo Sơ đồ tư duy...",
        tone: "info",
      })
      try {
        await generateStudyMindmapAsync(ctx, promptTitle.slice(0, 50))
        toast({
          title: "Đã tạo Sơ đồ tư duy AI thành công",
          tone: "success",
        })
        navigate("/study?tab=mindmap")
      } catch (e) {
        toast({
          title: "Không thể tạo Mindmap lúc này",
          tone: "error",
        })
      }
      return
    }

    if (kind === "plan") {
      toast({
        title: "AI đang thiết kế Lộ trình học tập...",
        tone: "info",
      })
      try {
        const today = new Date().toISOString().slice(0, 10)
        const res = await generateStudyPlanAsync(ctx, today, 7, promptTitle.slice(0, 50))
        for (const item of res.tasks) {
          addStudyTask(item)
        }
        toast({
          title: `Đã tạo ${res.tasks.length} nhiệm vụ học tập thành công`,
          tone: "success",
        })
        navigate("/study?tab=plan")
      } catch (e) {
        toast({
          title: "Không thể tạo lộ trình học tập lúc này",
          tone: "error",
        })
      }
      return
    }
  }

  const toggleAttachDoc = (docId: string) => {
    setAttachedDocIds((prev) =>
      prev.includes(docId) ? prev.filter((id) => id !== docId) : [...prev, docId],
    )
  }

  const citationCount = lastAssistant?.citations.length ?? 0

  return (
    <div className="relative flex h-full w-full min-w-0 overflow-hidden bg-white">
      {/* =====================================================================
          MAIN CHAT AREA (64% chiều rộng - Khu vực nổi bật nhất)
      ===================================================================== */}
      <div className="flex h-full min-w-0 flex-1 flex-col overflow-hidden bg-white">
        {/* Header phiên hội thoại: gọn gàng, tinh tế */}
        <header className="flex h-11 shrink-0 items-center justify-between gap-2 border-b border-[#DCE7E4] bg-white px-3 md:px-5">
          <div className="flex min-w-0 flex-1 items-center gap-2">
            {conversation ? (
              <div className="min-w-0 max-w-md flex-1">
                <InlineEdit
                  value={conversation.title}
                  ariaLabel="Tiêu đề cuộc trò chuyện"
                  validate={(next) => (!next.trim() ? "Tiêu đề không được để trống." : null)}
                  onSave={(next) => {
                    void handleRenameConversation(conversation.id, next)
                    toast({ title: "Đã đổi tên hội thoại", tone: "success" })
                  }}
                  className="truncate text-xs font-semibold text-[#172B29]"
                />
              </div>
            ) : (
              <span className="truncate text-xs font-semibold text-[#172B29]">
                Hỏi đáp AI
              </span>
            )}
          </div>

          <div className="flex items-center gap-1.5">
            <ModeSelector value={aiMode} onChange={handleModeChange} />

            <Tooltip
              content={citationOpen ? "Ẩn bảng ngữ cảnh" : "Mở bảng ngữ cảnh"}
              side="bottom"
            >
              <button
                type="button"
                onClick={() => setCitationOpen(!citationOpen)}
                className={cn(
                  "inline-flex h-7 items-center gap-1.5 rounded-md border px-2 text-xs font-medium transition-colors",
                  citationOpen
                    ? "border-[#087F73] bg-[#087F73] text-white"
                    : "border-[#DCE7E4] bg-white text-[#172B29] hover:border-[#087F73]",
                )}
                aria-label="Đóng/mở Context Panel"
              >
                <PanelRightOpen className="h-3 w-3" />
                <span className="hidden sm:inline text-[11px]">
                  {citationCount > 0 ? `Nguồn (${citationCount})` : `Kho (${workspaceDocuments.length})`}
                </span>
              </button>
            </Tooltip>

            {conversation ? (
              <DropdownMenu
                align="end"
                trigger={
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-7 w-7 text-[#647C79] hover:bg-[#F1F6F5] hover:text-[#172B29]"
                    aria-label="Tùy chọn hội thoại"
                  >
                    <MoreHorizontal className="h-3.5 w-3.5" />
                  </Button>
                }
              >
                <DropdownMenuItem
                  icon={<Plus className="h-3.5 w-3.5" />}
                  onClick={handleCreateConversation}
                >
                  Hội thoại mới
                </DropdownMenuItem>
                <DropdownMenuItem
                  icon={<Pencil className="h-3.5 w-3.5" />}
                  onClick={() => setRenameTarget(conversation)}
                >
                  Đổi tên hội thoại
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem
                  tone="danger"
                  icon={<Trash2 className="h-3.5 w-3.5" />}
                  onClick={() => setDeleteTarget(conversation)}
                >
                  Xóa cuộc trò chuyện
                </DropdownMenuItem>
              </DropdownMenu>
            ) : null}
          </div>
        </header>

        {/* Vùng nội dung Chat: Tối ưu chiều cao, ưu tiên diện tích cho câu trả lời */}
        <div className="min-h-0 flex-1 overflow-y-auto bg-white px-4 py-4 md:px-8">
          <div className="mx-auto flex min-h-full w-full max-w-3xl flex-col">
            {loadingMessages ? (
              <div className="my-auto flex flex-col items-center justify-center py-12 text-center">
                <div className="flex items-center gap-2 text-xs text-[#647C79]">
                  <span className="h-2 w-2 animate-ping rounded-full bg-[#087F73]" />
                  <span>Đang tải lịch sử trò chuyện...</span>
                </div>
              </div>
            ) : !conversation || conversation.messages.length === 0 ? (
              /* EMPTY STATE NGẮN GỌN THEO YÊU CẦU:
                 - Không có tiêu đề workspace quá lớn ở giữa màn hình
                 - Tiêu đề ngắn gọn: "Bạn muốn tìm hiểu điều gì?"
                 - Mô tả ngắn về số lượng tài liệu
                 - Tối đa 4 suggestion cards nhỏ gọn (icon + title + description) */
              <div className="my-auto flex flex-col items-center justify-center py-6 text-center">
                <div className="mb-3 flex h-9 w-9 items-center justify-center rounded-xl bg-[#087F73] text-white shadow-2xs">
                  <Sparkles className="h-4.5 w-4.5" />
                </div>

                <h2 className="text-xl font-bold tracking-tight text-[#172B29] sm:text-2xl">
                  Bạn muốn tìm hiểu điều gì?
                </h2>

                {/* 4 Suggestion Cards nhỏ gọn: chỉ giữ lại dòng mô tả chính các câu hỏi nhanh */}
                <div className="mt-6 grid w-full max-w-xl grid-cols-1 gap-2.5 sm:grid-cols-2 text-left">
                  {suggestionCards.map((item) => (
                    <button
                      key={item.title}
                      type="button"
                      onClick={() => void sendQuery(item.prompt)}
                      className="group flex items-center justify-between gap-2.5 rounded-xl border border-[#DCE7E4] bg-[#F1F6F5] px-3.5 py-3 transition-all hover:border-[#087F73] hover:bg-white shadow-2xs"
                    >
                      <div className="flex items-center gap-2.5 min-w-0">
                        <div className="flex h-6.5 w-6.5 shrink-0 items-center justify-center rounded-lg bg-white text-[#087F73] border border-[#DCE7E4] group-hover:border-[#087F73]">
                          <item.icon className="h-3.5 w-3.5" />
                        </div>
                        <span className="text-xs font-semibold text-[#172B29] group-hover:text-[#087F73] truncate">
                          {item.title}
                        </span>
                      </div>
                      <ArrowUpRight className="h-3.5 w-3.5 shrink-0 text-[#647C79] transition-transform group-hover:translate-x-0.5 group-hover:-translate-y-0.5 group-hover:text-[#087F73]" />
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              /* KHI CÓ HỘI THOẠI: ƯU TIÊN DIỆN TÍCH CHO NỘI DUNG CÂU TRẢ LỜI */
              <div className="space-y-6 pb-4">
                {conversation.messages.map((m) => {
                  const isUser = m.role === "user"
                  const { mainContent, suggestions } = isUser
                    ? { mainContent: m.content, suggestions: [] }
                    : parseMessageSuggestions(m.content)
                  const attachedDocsForMsg = documents.filter((d) =>
                    m.attachedDocumentIds?.includes(d.id),
                  )
                  const scopeNb = notebooks.find((n) => n.id === m.notebookScopeId)
                  const vote = feedbackMap[m.id]

                  return (
                    <article
                      key={m.id}
                      className={
                        isUser
                          ? "ml-auto max-w-[80%] rounded-xl bg-[#F1F6F5] border border-[#DCE7E4] px-3.5 py-2.5 text-[#172B29]"
                          : "border-b border-[#DCE7E4]/80 pb-5 last:border-b-0"
                      }
                    >
                      {!isUser ? (
                        <div className="mb-2 flex items-center justify-between gap-2 text-xs">
                          <div className="flex items-center gap-1.5">
                            <span className="flex h-4.5 w-4.5 items-center justify-center rounded bg-[#087F73] text-[9.5px] font-bold text-white">
                              M
                            </span>
                            <span className="font-semibold text-[#172B29] text-xs">Motivo AI</span>
                          </div>
                          <span className="text-[10.5px] text-[#647C79]">
                            {formatDate(m.createdAt)}
                          </span>
                        </div>
                      ) : null}

                      {isUser && (attachedDocsForMsg.length > 0 || scopeNb) ? (
                        <div className="mb-1 flex flex-wrap items-center gap-1">
                          {scopeNb ? (
                            <span className="inline-flex items-center gap-1 rounded border border-[#DCE7E4] bg-white px-1.5 py-0.2 text-[10.5px] text-[#172B29]">
                              <BookOpen className="h-2.5 w-2.5 text-[#087F73]" />
                              {scopeNb.name}
                            </span>
                          ) : null}
                          {attachedDocsForMsg.map((d) => (
                            <span
                              key={d.id}
                              className="inline-flex items-center gap-1 rounded border border-[#DCE7E4] bg-white px-1.5 py-0.2 text-[10.5px] text-[#172B29]"
                            >
                              <FileText className="h-2.5 w-2.5 text-[#087F73]" />
                              {d.fileName}
                            </span>
                          ))}
                        </div>
                      ) : null}

                      {isUser ? (
                        <p className="whitespace-pre-wrap text-[13.5px] leading-relaxed text-[#172B29]">
                          {m.content}
                        </p>
                      ) : m.error ? (
                        <div className="space-y-2.5">
                          <Alert
                            tone="error"
                            title="Không thể tạo câu trả lời"
                            description={m.error}
                          />
                          <Button
                            variant="outline"
                            size="sm"
                            leftIcon={<RefreshCw className="h-3 w-3" />}
                            disabled={busy}
                            onClick={() => {
                              const prompt = findPrecedingUserPrompt(m.id)
                              if (prompt) void sendQuery(prompt, m.id)
                            }}
                          >
                            Thử lại
                          </Button>
                        </div>
                      ) : m.streaming && !m.content ? (
                        <div className="space-y-1.5 py-1.5" aria-live="polite">
                          <div className="flex items-center gap-2 text-xs text-[#647C79]">
                            <span className="h-1.5 w-1.5 animate-ping rounded-full bg-[#087F73]" />
                            <span>Đang truy xuất tài liệu...</span>
                          </div>
                          <div className="h-2.5 w-1/2 animate-pulse rounded bg-[#F1F6F5]" />
                        </div>
                      ) : (
                        <div className="text-[#172B29]">
                          <CitationMarkdown content={mainContent} />
                        </div>
                      )}

                      {/* Gợi ý câu hỏi tiếp theo chuẩn NotebookLM */}
                      {!isUser && suggestions.length > 0 && !m.streaming ? (
                        <div className="mt-3.5 space-y-2 border-t border-[#DCE7E4]/70 pt-3">
                          <div className="flex items-center gap-1.5 text-xs font-medium text-[#087F73]">
                            <Sparkles className="h-3.5 w-3.5" />
                            <span>Gợi ý tìm hiểu tiếp:</span>
                          </div>
                          <div className="flex flex-wrap gap-1.5">
                            {suggestions.map((sug, sIdx) => (
                              <button
                                key={sIdx}
                                type="button"
                                disabled={busy}
                                onClick={() => void sendQuery(sug)}
                                className="group inline-flex items-center gap-1.5 rounded-full border border-[#DCE7E4] bg-white px-3 py-1.5 text-left text-xs text-[#172B29] shadow-xs transition hover:border-[#087F73] hover:bg-[#F1F6F5] hover:text-[#087F73] disabled:opacity-50"
                              >
                                <span>{sug}</span>
                                <ArrowUpRight className="h-3 w-3 text-[#647C79] transition group-hover:text-[#087F73]" />
                              </button>
                            ))}
                          </div>
                        </div>
                      ) : null}

                      {/* Thanh công cụ dưới mỗi câu trả lời AI */}
                      {!isUser && !m.streaming && !m.error ? (
                        <div className="mt-3 pt-1">
                          <div className="flex flex-wrap items-center justify-between gap-2">
                            <div className="flex items-center gap-1">
                              <button
                                type="button"
                                onClick={() => void handleCopyMessage(m)}
                                className="inline-flex h-6.5 items-center gap-1 rounded px-1.5 text-xs text-[#647C79] transition-colors hover:bg-[#F1F6F5] hover:text-[#172B29]"
                              >
                                {copiedMsgId === m.id ? (
                                  <Check className="h-3 w-3 text-[#087F73]" />
                                ) : (
                                  <Copy className="h-3 w-3" />
                                )}
                                <span className="text-[11px]">{copiedMsgId === m.id ? "Đã chép" : "Copy"}</span>
                              </button>

                              <button
                                type="button"
                                disabled={busy}
                                onClick={() => {
                                  const prompt = findPrecedingUserPrompt(m.id)
                                  if (prompt) void sendQuery(prompt, m.id)
                                }}
                                className="inline-flex h-6.5 items-center gap-1 rounded px-1.5 text-xs text-[#647C79] transition-colors hover:bg-[#F1F6F5] hover:text-[#172B29] disabled:opacity-40"
                              >
                                <RefreshCw className="h-3 w-3" />
                                <span className="text-[11px]">Tạo lại</span>
                              </button>

                              <div className="mx-1 h-3 w-px bg-[#DCE7E4]" />

                              <Tooltip content="Hữu ích" side="bottom">
                                <button
                                  type="button"
                                  onClick={() => handleFeedback(m.id, "up")}
                                  aria-label="Hữu ích"
                                  className={cn(
                                    "inline-flex h-6.5 w-6.5 items-center justify-center rounded transition-colors",
                                    vote === "up"
                                      ? "text-[#087F73]"
                                      : "text-[#647C79] hover:bg-[#F1F6F5] hover:text-[#172B29]",
                                  )}
                                >
                                  <ThumbsUp className="h-3 w-3" />
                                </button>
                              </Tooltip>

                              <Tooltip content="Chưa chính xác" side="bottom">
                                <button
                                  type="button"
                                  onClick={() => handleFeedback(m.id, "down")}
                                  aria-label="Chưa chính xác"
                                  className={cn(
                                    "inline-flex h-6.5 w-6.5 items-center justify-center rounded transition-colors",
                                    vote === "down"
                                      ? "text-rose-600"
                                      : "text-[#647C79] hover:bg-[#F1F6F5] hover:text-[#172B29]",
                                  )}
                                >
                                  <ThumbsDown className="h-3 w-3" />
                                </button>
                              </Tooltip>
                            </div>

                            <DropdownMenu
                              align="end"
                              trigger={
                                <button
                                  type="button"
                                  className="inline-flex h-6.5 items-center gap-1 rounded border border-[#DCE7E4] bg-white px-2 text-[11px] font-medium text-[#172B29] transition-colors hover:border-[#087F73] hover:text-[#087F73]"
                                >
                                  <GraduationCap className="h-3 w-3 text-[#087F73]" />
                                  <span>Tạo học liệu</span>
                                </button>
                              }
                            >
                              <DropdownMenuLabel>Tạo học liệu từ câu trả lời</DropdownMenuLabel>
                              <DropdownMenuItem
                                icon={<FileText className="h-3.5 w-3.5" />}
                                onClick={() => handleCreateStudyFromMessage(m, "summary")}
                              >
                                Lưu Tóm tắt / Ghi chú
                              </DropdownMenuItem>
                              <DropdownMenuItem
                                icon={<Sparkles className="h-3.5 w-3.5" />}
                                onClick={() => handleCreateStudyFromMessage(m, "quiz")}
                              >
                                Tạo Quiz trắc nghiệm
                              </DropdownMenuItem>
                              <DropdownMenuItem
                                icon={<Layers className="h-3.5 w-3.5" />}
                                onClick={() => handleCreateStudyFromMessage(m, "flashcards")}
                              >
                                Tạo thẻ nhớ Flashcards
                              </DropdownMenuItem>
                              <DropdownMenuItem
                                icon={<Network className="h-3.5 w-3.5" />}
                                onClick={() => handleCreateStudyFromMessage(m, "mindmap")}
                              >
                                Tạo Sơ đồ tư duy (Mindmap)
                              </DropdownMenuItem>
                              <DropdownMenuItem
                                icon={<Calendar className="h-3.5 w-3.5" />}
                                onClick={() => handleCreateStudyFromMessage(m, "plan")}
                              >
                                Tạo Lộ trình học tập (Plan)
                              </DropdownMenuItem>
                            </DropdownMenu>
                          </div>
                        </div>
                      ) : null}
                    </article>
                  )
                })}
              </div>
            )}
            <div ref={bottomRef} />
          </div>
        </div>

        {/* Khung Composer cố định ở cuối */}
        <div className="shrink-0">
          <ChatComposer
            value={input}
            onChange={setInput}
            onSend={() => void sendQuery(input)}
            onCancel={handleCancelRequest}
            busy={busy}
            aiMode={aiMode}
            onModeChange={handleModeChange}
            modelId={localLlmModel}
            onModelChange={handleModelChange}
            currentWorkspace={currentWorkspace}
            notebooks={workspaceNotebooks}
            selectedNotebookId={selectedNotebookId}
            onSelectNotebook={setSelectedNotebookId}
            workspaceDocuments={workspaceDocuments}
            attachedDocIds={scopedAttachedDocIds}
            onToggleAttachDoc={toggleAttachDoc}
            onClearAttachedDocs={() => setAttachedDocIds([])}
            onUploadAttachment={(files) => void handleUploadAttachment(files)}
            uploadingAttachment={uploadingAttachment}
            backendOnline={status.backendOnline}
          />
        </div>
      </div>

      {/* =====================================================================
          CONTEXT PANEL BÊN PHẢI (20% chiều rộng - Nền #F1F6F5)
      ===================================================================== */}
      {citationOpen ? (
        <>
          <div className="hidden h-full w-[24%] min-w-[260px] max-w-[320px] shrink-0 xl:flex">
            <CitationPanel
              citations={lastAssistant?.citations ?? []}
              workspaceDocuments={workspaceDocuments}
              attachedDocIds={scopedAttachedDocIds}
              onToggleAttachDoc={toggleAttachDoc}
              onClose={() => setCitationOpen(false)}
            />
          </div>

          <div className="fixed inset-0 z-40 flex justify-end xl:hidden">
            <button
              type="button"
              aria-label="Đóng bảng ngữ cảnh"
              className="fixed inset-0 bg-[#172B29]/30"
              onClick={() => setCitationOpen(false)}
            />
            <div className="relative z-10 h-full w-80 max-w-[88vw] bg-[#F1F6F5]">
              <CitationPanel
                citations={lastAssistant?.citations ?? []}
                workspaceDocuments={workspaceDocuments}
                attachedDocIds={scopedAttachedDocIds}
                onToggleAttachDoc={toggleAttachDoc}
                onClose={() => setCitationOpen(false)}
              />
            </div>
          </div>
        </>
      ) : (
        <aside className="hidden h-full w-9 shrink-0 flex-col items-center border-l border-[#DCE7E4] bg-[#F1F6F5] py-2.5 xl:flex">
          <Tooltip content="Mở bảng Ngữ cảnh" side="left">
            <button
              type="button"
              onClick={() => setCitationOpen(true)}
              className="flex h-7 w-7 items-center justify-center rounded-lg border border-[#DCE7E4] bg-white text-[#172B29] transition-colors hover:border-[#087F73] hover:text-[#087F73]"
              aria-label="Mở rộng Context Panel"
            >
              <PanelRightOpen className="h-3.5 w-3.5" />
            </button>
          </Tooltip>
        </aside>
      )}

      <NameDialog
        open={Boolean(renameTarget)}
        title="Đổi tên cuộc trò chuyện"
        initialName={renameTarget?.title ?? ""}
        onClose={() => setRenameTarget(null)}
        onSubmit={(name) => {
          if (renameTarget) {
            void handleRenameConversation(renameTarget.id, name)
            toast({ title: "Đã đổi tên hội thoại", description: name, tone: "success" })
            setRenameTarget(null)
          }
        }}
      />

      <ConfirmDialog
        open={Boolean(deleteTarget)}
        title="Xóa cuộc trò chuyện?"
        description={
          deleteTarget
            ? `Bạn có chắc muốn xóa cuộc trò chuyện "${deleteTarget.title}"?`
            : undefined
        }
        onClose={() => setDeleteTarget(null)}
        onConfirm={handleConfirmDeleteConversation}
      />
    </div>
  )
}
