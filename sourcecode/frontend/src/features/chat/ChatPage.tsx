import { useEffect, useMemo, useRef, useState } from "react"
import { useNavigate, useParams } from "react-router-dom"
import {
  ArrowUpRight,
  BookOpen,
  Check,
  Copy,
  FileText,
  GraduationCap,
  Layers,
  MessageSquare,
  MoreHorizontal,
  PanelRightOpen,
  Pencil,
  Plus,
  Quote,
  RefreshCw,
  Sparkles,
  ThumbsDown,
  ThumbsUp,
  Trash2,
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
  getModeDescriptor,
  sendChatMessageService,
} from "@/services/chat-service"
import {
  generateStudyFlashcards,
  generateStudyQuiz,
  type StudySourceContext,
} from "@/services/study-service"
import { useAppStore } from "@/store/app-store"
import { formatDate, nowIso, uid } from "@/utils/format"
import type { AIMode, ChatMessage, Conversation, Flashcard } from "@/types"
import { cn } from "@/utils/cn"
import { ModeSelector } from "./ModeSelector"
import { CitationPanel } from "./CitationPanel"
import { ChatComposer } from "./ChatComposer"

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
  const appendMessage = useAppStore((s) => s.appendMessage)
  const updateMessage = useAppStore((s) => s.updateMessage)

  const saveNote = useAppStore((s) => s.saveNote)
  const upsertQuiz = useAppStore((s) => s.upsertQuiz)
  const addFlashcards = useAppStore((s) => s.addFlashcards)

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
  const [copiedMsgId, setCopiedMsgId] = useState<string | null>(null)
  const [feedbackMap, setFeedbackMap] = useState<Record<string, "up" | "down">>({})

  // Phạm vi tri thức & đính kèm tài liệu trong Composer
  const [selectedNotebookId, setSelectedNotebookId] = useState<string | null>(null)
  const [attachedDocIds, setAttachedDocIds] = useState<string[]>([])

  // Dialog đổi tên & xóa hội thoại
  const [renameTarget, setRenameTarget] = useState<Conversation | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<Conversation | null>(null)

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

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [conversation?.messages.length, busy])

  const lastAssistant = useMemo(
    () => [...(conversation?.messages ?? [])].reverse().find((m) => m.role === "assistant"),
    [conversation?.messages],
  )

  // Sinh các prompt gợi ý dựa trên chính tài liệu thực tế có trong Workspace hiện tại
  const suggestedPrompts = useMemo(() => {
    const firstDoc = workspaceDocuments[0]
    const secondDoc = workspaceDocuments[1]
    if (firstDoc && secondDoc) {
      return [
        {
          title: "Tóm tắt luận điểm chính",
          prompt: `Tóm tắt các nội dung cốt lõi trong tài liệu "${firstDoc.fileName}" kèm trích dẫn trang cụ thể.`,
        },
        {
          title: "So sánh & Đối chiếu nguồn",
          prompt: `So sánh các điểm chính giữa "${firstDoc.fileName}" và "${secondDoc.fileName}".`,
        },
        {
          title: "Giải thích khái niệm trọng tâm",
          prompt: `Liệt kê và giải thích các thuật ngữ hoặc công thức quan trọng nhất trong kho tài liệu "${currentWorkspace?.name ?? "Workspace"}".`,
        },
        {
          title: "Tổng hợp câu hỏi ôn tập",
          prompt: `Tạo 5 câu hỏi ôn tập trọng tâm kèm đáp án trích xuất từ các tài liệu trong "${currentWorkspace?.name ?? "Workspace"}".`,
        },
      ]
    }
    if (firstDoc) {
      return [
        {
          title: "Tóm tắt tài liệu",
          prompt: `Tóm tắt có cấu trúc các ý chính trong "${firstDoc.fileName}" kèm trích dẫn.`,
        },
        {
          title: "Phân tích chi tiết",
          prompt: `Những phát hiện hoặc phương pháp quan trọng nhất được trình bày trong "${firstDoc.fileName}" là gì?`,
        },
        {
          title: "Trích xuất khái niệm",
          prompt: `Liệt kê các thuật ngữ chuyên ngành và định nghĩa của chúng từ "${firstDoc.fileName}".`,
        },
        {
          title: "Câu hỏi kiểm tra",
          prompt: `Đặt 5 câu hỏi kiểm tra mức độ hiểu bài dựa trên nội dung của "${firstDoc.fileName}".`,
        },
      ]
    }
    return [
      {
        title: "Khám phá chủ đề",
        prompt: `Tổng quan các khái niệm cốt lõi cần nắm vững trong "${currentWorkspace?.name ?? "Workspace"}".`,
      },
      {
        title: "So sánh kiến trúc Hybrid RAG",
        prompt: "Phân tích sự kết hợp giữa Dense Retrieval, BM25 và Reciprocal Rank Fusion (RRF) trong hệ thống RAG.",
      },
      {
        title: "Kiểm chứng trích dẫn",
        prompt: "Làm thế nào để đối chiếu từng câu trả lời AI với đoạn trích gốc trong tài liệu?",
      },
      {
        title: "Lập đề cương nghiên cứu",
        prompt: `Gợi ý lộ trình đọc hiểu và ghi chú cho chủ đề "${currentWorkspace?.name ?? "nghiên cứu"}".`,
      },
    ]
  }, [workspaceDocuments, currentWorkspace?.name])

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

  const handleCreateConversation = () => {
    const created = createConversation(currentWsId, "Cuộc trò chuyện mới")
    navigate(`/chat/${created.id}`)
  }

  const handleConfirmDeleteConversation = () => {
    if (!deleteTarget) return
    const targetId = deleteTarget.id
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

  const sendQuery = async (queryText: string, regenerateAssistantId?: string) => {
    const trimmed = queryText.trim()
    if (!trimmed || busy) return

    let activeConv = conversation
    if (!activeConv) {
      activeConv = createConversation(currentWsId, trimmed.slice(0, 68))
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
        attachedDocumentIds: attachedDocIds.length ? [...attachedDocIds] : undefined,
        notebookScopeId: selectedNotebookId,
      })
      if (activeConv.title === "Cuộc trò chuyện mới") {
        renameConversation(convId, trimmed.slice(0, 68))
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
    try {
      await navigator.clipboard.writeText(msg.content)
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
      title: vote === "up" ? "Cảm ơn phản hồi tích cực của bạn" : "Đã ghi nhận phản hồi để cải thiện",
      tone: "info",
    })
  }

  // Tạo học liệu trực tiếp từ câu trả lời AI (Summary / Note, Quiz, Flashcards)
  const handleCreateStudyFromMessage = (
    msg: ChatMessage,
    kind: "summary" | "quiz" | "flashcards",
  ) => {
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
        content: msg.content,
        updatedAt: nowIso(),
      })
      toast({
        title: "Đã lưu vào Học liệu (Ghi chú & Tóm tắt)",
        description: "Đang mở công cụ Học liệu...",
        tone: "success",
      })
      navigate("/study?tab=notes")
      return
    }

    if (kind === "quiz") {
      const quiz = generateStudyQuiz(ctx, "medium", 5)
      upsertQuiz({
        ...quiz,
        title: `Quiz từ hội thoại: ${promptTitle.slice(0, 40)}`,
      })
      toast({
        title: "Đã tạo bộ câu hỏi Quiz từ câu trả lời",
        description: "Đang chuyển tới tab Quiz...",
        tone: "success",
      })
      navigate("/study?tab=quiz")
      return
    }

    if (kind === "flashcards") {
      const lines = msg.content
        .split(/\n+/)
        .map((l) => l.replace(/^[-*•\d.)\s]+/, "").trim())
        .filter((l) => l.length > 24)

      let cards: Flashcard[]
      if (lines.length >= 2) {
        cards = lines.slice(0, 4).map((line, i) => ({
          id: uid("fc"),
          workspaceId: currentWsId,
          documentId: citedDocId,
          front: `${promptTitle.slice(0, 52)} — Ý trọng tâm #${i + 1}`,
          back: line,
          status: "new",
          isMock: true,
        }))
      } else {
        cards = generateStudyFlashcards(ctx)
      }

      addFlashcards(cards)
      toast({
        title: `Đã tạo ${cards.length} thẻ Flashcards từ câu trả lời`,
        description: "Đang chuyển tới tab Flashcards...",
        tone: "success",
      })
      navigate("/study?tab=flashcards")
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
          3. MAIN CHAT AREA (Chiếm 65-70% trung tâm màn hình)
      ===================================================================== */}
      <div className="flex h-full min-w-0 flex-1 flex-col overflow-hidden">
        {/* Thanh Sub-header của phiên hội thoại */}
        <header className="flex h-12 shrink-0 items-center justify-between gap-2 border-b border-[#DCECE8] bg-white px-4 md:px-6">
          <div className="flex min-w-0 flex-1 items-center gap-2">
            <MessageSquare className="h-4 w-4 shrink-0 text-[#0F766E]" />
            {conversation ? (
              <div className="min-w-0 max-w-md flex-1">
                <InlineEdit
                  value={conversation.title}
                  ariaLabel="Tiêu đề cuộc trò chuyện"
                  validate={(next) => (!next.trim() ? "Tiêu đề không được để trống." : null)}
                  onSave={(next) => {
                    renameConversation(conversation.id, next)
                    toast({ title: "Đã đổi tên hội thoại", tone: "success" })
                  }}
                  className="truncate text-sm font-semibold text-[#0B1716]"
                />
              </div>
            ) : (
              <span className="truncate text-sm font-semibold text-[#0B1716]">
                Phiên làm việc mới
              </span>
            )}
          </div>

          <div className="flex items-center gap-2">
            {/* Chọn chế độ Hybrid RAG */}
            <ModeSelector value={aiMode} onChange={handleModeChange} />

            {/* Nút mở Context Panel khi đang thu gọn hoặc trên màn hình nhỏ */}
            <Tooltip
              content={
                citationOpen
                  ? "Ẩn bảng Ngữ cảnh & Nguồn trích dẫn"
                  : "Mở bảng Ngữ cảnh & Nguồn trích dẫn"
              }
              side="bottom"
            >
              <button
                type="button"
                onClick={() => setCitationOpen(!citationOpen)}
                className={cn(
                  "inline-flex h-8 items-center gap-1.5 rounded-lg border px-2.5 text-xs font-medium transition-colors",
                  citationOpen
                    ? "border-[#0F766E]/40 bg-[#E2F3EF] text-[#0F766E]"
                    : "border-[#D5E6E2] bg-white text-[#37524F] hover:bg-[#F1F8F6]",
                )}
                aria-label="Đóng/mở Context Panel"
              >
                <PanelRightOpen className="h-3.5 w-3.5" />
                <span className="hidden sm:inline">
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
                    className="h-8 w-8 text-[#647D7A] hover:bg-[#F1F8F6] hover:text-[#0B1716]"
                    aria-label="Tùy chọn hội thoại"
                  >
                    <MoreHorizontal className="h-4 w-4" />
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

        {/* Vùng cuộn nội dung Chat */}
        <div className="min-h-0 flex-1 overflow-y-auto px-4 py-6 md:px-8">
          <div className="mx-auto flex min-h-full w-full max-w-3xl flex-col">
            {!conversation || conversation.messages.length === 0 ? (
              /* EMPTY STATE: Lời chào, mô tả ngắn & các Prompt gợi ý theo ngữ cảnh Workspace */
              <div className="my-auto flex flex-col items-center justify-center py-8 text-center">
                <span className="mb-3 inline-flex items-center gap-1.5 rounded-full border border-[#CBE4DF] bg-[#F2F9F7] px-3 py-1 text-xs font-medium text-[#0F766E]">
                  <Sparkles className="h-3.5 w-3.5" />
                  <span>Workspace Studio · {currentWorkspace?.name ?? "Kho tri thức"}</span>
                </span>

                <h1 className="font-editorial-serif text-3xl font-medium tracking-tight text-[#0B1716] sm:text-4xl">
                  Hỏi đáp chuyên sâu trên{" "}
                  <span className="italic text-[#0F766E]">tài liệu của bạn.</span>
                </h1>

                <p className="mt-2 max-w-lg text-sm leading-relaxed text-[#526B68]">
                  Mọi câu trả lời đều được tổng hợp bằng Hybrid RAG và đính kèm trích dẫn đối chiếu
                  trực tiếp tới từng trang tài liệu trong không gian làm việc này.
                </p>

                {/* Các Prompt gợi ý */}
                <div className="mt-7 grid w-full max-w-2xl grid-cols-1 gap-3 text-left sm:grid-cols-2">
                  {suggestedPrompts.map((item) => (
                    <button
                      key={item.title}
                      type="button"
                      onClick={() => void sendQuery(item.prompt)}
                      className="group flex flex-col justify-between rounded-2xl border border-[#D5E6E2] bg-[#FAFDFC] p-3.5 text-left transition-all duration-150 hover:border-[#0F766E] hover:bg-white hover:shadow-sm"
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-xs font-semibold text-[#0B1716] group-hover:text-[#0F766E]">
                          {item.title}
                        </span>
                        <ArrowUpRight className="h-3.5 w-3.5 text-[#7A9490] transition-transform group-hover:translate-x-0.5 group-hover:-translate-y-0.5 group-hover:text-[#0F766E]" />
                      </div>
                      <p className="mt-1 line-clamp-2 text-xs leading-relaxed text-[#58726F]">
                        {item.prompt}
                      </p>
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              /* LUỒNG HỘI THOẠI GIỮA NGƯỜI DÙNG & AI */
              <div className="space-y-6 pb-4">
                {conversation.messages.map((m) => {
                  const isUser = m.role === "user"
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
                          ? "ml-auto max-w-[85%] rounded-2xl border border-[#DCECE8] bg-[#F2F9F7] px-4 py-3 text-[#0B1716]"
                          : "rounded-2xl border border-[#E6F0EE] bg-white p-5 shadow-[0_2px_12px_-4px_rgba(11,25,23,0.04)]"
                      }
                    >
                      {!isUser ? (
                        <div className="mb-3 flex items-center justify-between gap-2 border-b border-[#F0F6F5] pb-2.5 text-xs">
                          <div className="flex items-center gap-2">
                            <span className="flex h-6 w-6 items-center justify-center rounded-lg bg-[#0F766E] text-[11px] font-bold text-white">
                              M
                            </span>
                            <span className="font-semibold text-[#0B1716]">Motivo RAG</span>
                            {m.modeRequested ? (
                              <span className="rounded-md bg-[#F0F7F5] px-1.5 py-0.5 text-[10px] font-medium text-[#526B68]">
                                {getModeDescriptor(m.modeRequested).label}
                              </span>
                            ) : null}
                          </div>
                          <span className="text-[11px] text-[#7A9490]">
                            {formatDate(m.createdAt)}
                          </span>
                        </div>
                      ) : null}

                      {isUser && (attachedDocsForMsg.length > 0 || scopeNb) ? (
                        <div className="mb-1.5 flex flex-wrap items-center gap-1">
                          {scopeNb ? (
                            <span className="inline-flex items-center gap-1 rounded-md border border-[#CBE4DF] bg-white px-2 py-0.5 text-[11px] text-[#37524F]">
                              <BookOpen className="h-3 w-3 text-[#0F766E]" />
                              {scopeNb.name}
                            </span>
                          ) : null}
                          {attachedDocsForMsg.map((d) => (
                            <span
                              key={d.id}
                              className="inline-flex items-center gap-1 rounded-md border border-[#CBE4DF] bg-white px-2 py-0.5 text-[11px] text-[#37524F]"
                            >
                              <FileText className="h-3 w-3 text-[#0F766E]" />
                              {d.fileName}
                            </span>
                          ))}
                        </div>
                      ) : null}

                      {isUser ? (
                        <p className="whitespace-pre-wrap text-[14px] leading-relaxed text-[#0B1716]">
                          {m.content}
                        </p>
                      ) : m.error ? (
                        <div className="space-y-3">
                          <Alert
                            tone="error"
                            title="Không thể tạo câu trả lời"
                            description={m.error}
                          />
                          <Button
                            variant="outline"
                            size="sm"
                            leftIcon={<RefreshCw className="h-3.5 w-3.5" />}
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
                        <div className="space-y-2 py-2" aria-live="polite">
                          <div className="flex items-center gap-2 text-xs text-[#526B68]">
                            <span className="h-2 w-2 animate-ping rounded-full bg-[#0F766E]" />
                            <span>Đang truy xuất tài liệu &amp; tổng hợp câu trả lời...</span>
                          </div>
                          <div className="h-3 w-2/3 animate-pulse rounded bg-[#EFF6F5]" />
                        </div>
                      ) : (
                        <CitationMarkdown content={m.content} />
                      )}

                      {/* Thanh công cụ dưới mỗi câu trả lời AI: Copy, Regenerate, Feedback, Tạo Học liệu & Chips Citation */}
                      {!isUser && !m.streaming && !m.error ? (
                        <div className="mt-4 space-y-2.5 border-t border-[#F0F6F5] pt-3">
                          {/* Dải các nguồn trích dẫn inline của câu trả lời */}
                          {m.citations.length > 0 ? (
                            <div className="flex flex-wrap items-center gap-1.5">
                              <span className="inline-flex items-center gap-1 text-[11px] font-medium text-[#647D7A]">
                                <Quote className="h-3 w-3 text-[#0F766E]" />
                                Nguồn:
                              </span>
                              {m.citations.map((c) => (
                                <button
                                  key={c.refId}
                                  type="button"
                                  onClick={() => {
                                    setActiveCitation(c.refId)
                                    setCitationOpen(true)
                                    window.dispatchEvent(
                                      new CustomEvent("studio-context-tab", { detail: "citations" }),
                                    )
                                  }}
                                  className="inline-flex items-center gap-1 rounded-lg border border-[#D5E6E2] bg-[#F6FBF9] px-2 py-0.5 text-[11px] font-medium text-[#0F766E] transition-colors hover:border-[#0F766E] hover:bg-[#E2F3EF]"
                                >
                                  <span className="font-mono font-bold">[{c.refId}]</span>
                                  <span className="max-w-[160px] truncate">{c.documentName}</span>
                                  {c.pageNumber != null ? (
                                    <span className="text-[10px] text-[#647D7A]">· Tr.{c.pageNumber}</span>
                                  ) : null}
                                </button>
                              ))}
                            </div>
                          ) : null}

                          {/* Hàng nút thao tác: Copy, Regenerate, Feedback & Tạo học liệu trực tiếp */}
                          <div className="flex flex-wrap items-center justify-between gap-2">
                            <div className="flex items-center gap-1">
                              <Tooltip content="Sao chép câu trả lời" side="bottom">
                                <button
                                  type="button"
                                  onClick={() => void handleCopyMessage(m)}
                                  className="inline-flex h-7 items-center gap-1 rounded-lg px-2 text-xs text-[#526B68] transition-colors hover:bg-[#F0F7F5] hover:text-[#0B1716]"
                                >
                                  {copiedMsgId === m.id ? (
                                    <Check className="h-3.5 w-3.5 text-[#10B981]" />
                                  ) : (
                                    <Copy className="h-3.5 w-3.5" />
                                  )}
                                  <span>{copiedMsgId === m.id ? "Đã chép" : "Copy"}</span>
                                </button>
                              </Tooltip>

                              <Tooltip content="Tạo lại câu trả lời" side="bottom">
                                <button
                                  type="button"
                                  disabled={busy}
                                  onClick={() => {
                                    const prompt = findPrecedingUserPrompt(m.id)
                                    if (prompt) void sendQuery(prompt, m.id)
                                  }}
                                  className="inline-flex h-7 items-center gap-1 rounded-lg px-2 text-xs text-[#526B68] transition-colors hover:bg-[#F0F7F5] hover:text-[#0B1716] disabled:opacity-40"
                                >
                                  <RefreshCw className="h-3.5 w-3.5" />
                                  <span>Regenerate</span>
                                </button>
                              </Tooltip>

                              <div className="mx-1 h-3.5 w-px bg-[#E4EFECE0]" />

                              <Tooltip content="Câu trả lời hữu ích" side="bottom">
                                <button
                                  type="button"
                                  onClick={() => handleFeedback(m.id, "up")}
                                  aria-label="Hữu ích"
                                  className={cn(
                                    "inline-flex h-7 w-7 items-center justify-center rounded-lg transition-colors",
                                    vote === "up"
                                      ? "bg-[#E2F3EF] text-[#0F766E]"
                                      : "text-[#647D7A] hover:bg-[#F0F7F5] hover:text-[#0B1716]",
                                  )}
                                >
                                  <ThumbsUp className="h-3.5 w-3.5" />
                                </button>
                              </Tooltip>

                              <Tooltip content="Câu trả lời cần cải thiện" side="bottom">
                                <button
                                  type="button"
                                  onClick={() => handleFeedback(m.id, "down")}
                                  aria-label="Chưa chính xác"
                                  className={cn(
                                    "inline-flex h-7 w-7 items-center justify-center rounded-lg transition-colors",
                                    vote === "down"
                                      ? "bg-rose-50 text-rose-600"
                                      : "text-[#647D7A] hover:bg-[#F0F7F5] hover:text-[#0B1716]",
                                  )}
                                >
                                  <ThumbsDown className="h-3.5 w-3.5" />
                                </button>
                              </Tooltip>
                            </div>

                            {/* Nút tạo học liệu trực tiếp từ câu trả lời AI */}
                            <DropdownMenu
                              align="end"
                              trigger={
                                <button
                                  type="button"
                                  className="inline-flex h-7 items-center gap-1.5 rounded-lg border border-[#CBE4DF] bg-[#F4FAF8] px-2.5 text-xs font-semibold text-[#0F766E] transition-colors hover:bg-[#E2F3EF]"
                                >
                                  <GraduationCap className="h-3.5 w-3.5" />
                                  <span>Tạo học liệu</span>
                                </button>
                              }
                            >
                              <DropdownMenuLabel>Tạo học liệu từ câu trả lời này</DropdownMenuLabel>
                              <DropdownMenuItem
                                icon={<FileText className="h-3.5 w-3.5" />}
                                onClick={() => handleCreateStudyFromMessage(m, "summary")}
                              >
                                Lưu làm Tóm tắt / Ghi chú
                              </DropdownMenuItem>
                              <DropdownMenuItem
                                icon={<Sparkles className="h-3.5 w-3.5" />}
                                onClick={() => handleCreateStudyFromMessage(m, "quiz")}
                              >
                                Tạo bộ câu hỏi Quiz
                              </DropdownMenuItem>
                              <DropdownMenuItem
                                icon={<Layers className="h-3.5 w-3.5" />}
                                onClick={() => handleCreateStudyFromMessage(m, "flashcards")}
                              >
                                Tạo thẻ nhớ Flashcards
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
            attachedDocIds={attachedDocIds}
            onToggleAttachDoc={toggleAttachDoc}
            onClearAttachedDocs={() => setAttachedDocIds([])}
            backendOnline={status.backendOnline}
          />
        </div>
      </div>

      {/* =====================================================================
          4. CONTEXT PANEL BÊN PHẢI (Thu gọn / Mở rộng, Drawer trên màn hình nhỏ)
      ===================================================================== */}
      {citationOpen ? (
        <>
          <div className="hidden h-full w-80 shrink-0 xl:flex">
            <CitationPanel
              citations={lastAssistant?.citations ?? []}
              workspaceDocuments={workspaceDocuments}
              attachedDocIds={attachedDocIds}
              onToggleAttachDoc={toggleAttachDoc}
              onClose={() => setCitationOpen(false)}
            />
          </div>

          {/* Drawer trên màn hình nhỏ (< xl) */}
          <div className="fixed inset-0 z-40 flex justify-end xl:hidden">
            <button
              type="button"
              aria-label="Đóng bảng ngữ cảnh"
              className="fixed inset-0 bg-[#0B1716]/30"
              onClick={() => setCitationOpen(false)}
            />
            <div className="relative z-10 h-full w-80 max-w-[88vw] bg-white">
              <CitationPanel
                citations={lastAssistant?.citations ?? []}
                workspaceDocuments={workspaceDocuments}
                attachedDocIds={attachedDocIds}
                onToggleAttachDoc={toggleAttachDoc}
                onClose={() => setCitationOpen(false)}
              />
            </div>
          </div>
        </>
      ) : (
        /* Thanh thu gọn của Context Panel bên phải trên màn hình lớn */
        <aside className="hidden h-full w-10 shrink-0 flex-col items-center border-l border-[#DCECE8] bg-[#F7FAF9] py-3 xl:flex">
          <Tooltip content="Mở rộng bảng Ngữ cảnh & Nguồn trích dẫn" side="left">
            <button
              type="button"
              onClick={() => setCitationOpen(true)}
              className="flex h-8 w-8 items-center justify-center rounded-lg border border-[#D5E6E2] bg-white text-[#0F766E] transition-colors hover:border-[#0F766E] hover:bg-[#E2F3EF]"
              aria-label="Mở rộng Context Panel"
            >
              <PanelRightOpen className="h-4 w-4" />
            </button>
          </Tooltip>
        </aside>
      )}

      {/* Dialog đổi tên hội thoại */}
      <NameDialog
        open={Boolean(renameTarget)}
        title="Đổi tên cuộc trò chuyện"
        initialName={renameTarget?.title ?? ""}
        onClose={() => setRenameTarget(null)}
        onSubmit={(name) => {
          if (renameTarget) {
            renameConversation(renameTarget.id, name)
            toast({ title: "Đã đổi tên hội thoại", description: name, tone: "success" })
            setRenameTarget(null)
          }
        }}
      />

      {/* Dialog xác nhận xóa hội thoại */}
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
