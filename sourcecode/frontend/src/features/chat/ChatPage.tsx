import { useEffect, useMemo, useRef, useState } from "react"
import { useNavigate, useParams } from "react-router-dom"
import {
  BookOpen,
  Check,
  Copy,
  FileText,
  MessageSquare,
  MoreHorizontal,
  PanelLeft,
  PanelRight,
  Pencil,
  Plus,
  RefreshCw,
  Search,
  Trash2,
  X,
} from "lucide-react"
import { InlineEdit } from "@/components/common/InlineEdit"
import { ConfirmDialog, NameDialog } from "@/components/common/NameDialog"
import {
  Alert,
  Button,
  DropdownMenu,
  DropdownMenuItem,
  DropdownMenuSeparator,
  EmptyState,
  Input,
  Tooltip,
} from "@/components/ui"
import { CitationMarkdown } from "@/features/citations/CitationMarkdown"
import {
  getModeDescriptor,
  sendChatMessageService,
} from "@/services/chat-service"
import { useAppStore } from "@/store/app-store"
import { formatDate, nowIso, uid } from "@/utils/format"
import type { AIMode, ChatMessage, Conversation } from "@/types"
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

  // Mặc định đóng cột lịch sử phụ để tránh 2 cột bên trái cùng xuất hiện làm hẹp vùng đọc
  const [historyOpen, setHistoryOpen] = useState(false)
  const [mobileHistoryOpen, setMobileHistoryOpen] = useState(false)
  const [chatQuery, setChatQuery] = useState("")
  const [input, setInput] = useState("")
  const [busy, setBusy] = useState(false)
  const [copiedMsgId, setCopiedMsgId] = useState<string | null>(null)

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

  // Danh sách hội thoại độc lập nghiêm ngặt theo workspace đang chọn
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

  const filteredConversations = useMemo(() => {
    const q = chatQuery.trim().toLowerCase()
    if (!q) return wsConversations
    return wsConversations.filter((c) => c.title.toLowerCase().includes(q))
  }, [wsConversations, chatQuery])

  useEffect(() => {
    if (conversationId) {
      // Kiểm tra nếu conversationId trong URL thuộc workspace khác
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

  const handleModeChange = (nextMode: AIMode) => {
    setAiMode(nextMode)
    const desc = getModeDescriptor(nextMode)
    toast({
      title: `Chế độ tìm kiếm: ${desc.label}`,
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
    const created = createConversation(currentWs, "Cuộc trò chuyện mới")
    setMobileHistoryOpen(false)
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
      activeConv = createConversation(currentWs, trimmed.slice(0, 68))
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
        workspaceId: currentWs,
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

  const toggleAttachDoc = (docId: string) => {
    setAttachedDocIds((prev) =>
      prev.includes(docId) ? prev.filter((id) => id !== docId) : [...prev, docId],
    )
  }

  const renderConversationList = () => (
    <div className="flex h-full flex-col bg-bg-secondary/40">
      <div className="flex items-center justify-between border-b border-line px-3 py-2.5">
        <span className="text-xs font-semibold text-ink">
          Lịch sử ({wsConversations.length})
        </span>
        <Button
          variant="outline"
          size="sm"
          leftIcon={<Plus className="h-3.5 w-3.5" />}
          onClick={handleCreateConversation}
        >
          Mới
        </Button>
      </div>

      {wsConversations.length > 4 ? (
        <div className="p-2">
          <div className="relative">
            <Search className="pointer-events-none absolute left-2.5 top-2.5 h-3.5 w-3.5 text-muted" />
            <Input
              value={chatQuery}
              onChange={(e) => setChatQuery(e.target.value)}
              placeholder="Lọc hội thoại..."
              className="h-8 pl-8 text-xs"
            />
          </div>
        </div>
      ) : null}

      <div className="flex-1 overflow-y-auto px-2 py-2">
        {filteredConversations.length === 0 ? (
          <p className="px-2 py-4 text-center text-xs text-muted">
            Không tìm thấy cuộc trò chuyện.
          </p>
        ) : (
          <ul className="space-y-0.5">
            {filteredConversations.map((c) => {
              const isActive = c.id === conversation?.id
              return (
                <li
                  key={c.id}
                  className={`group flex items-center justify-between gap-1 rounded-md px-2.5 py-1.5 text-sm transition-colors ${
                    isActive
                      ? "bg-bg-active font-semibold text-ink"
                      : "text-muted hover:bg-bg-hover hover:text-ink"
                  }`}
                >
                  <button
                    type="button"
                    onClick={() => {
                      setMobileHistoryOpen(false)
                      navigate(`/chat/${c.id}`)
                    }}
                    className="min-w-0 flex-1 text-left"
                  >
                    <p className="truncate text-[13px]">{c.title}</p>
                  </button>

                  <DropdownMenu
                    align="end"
                    trigger={
                      <button
                        type="button"
                        aria-label={`Tùy chọn cho ${c.title}`}
                        className="rounded p-1 text-muted opacity-0 hover:bg-bg hover:text-ink group-hover:opacity-100 focus:opacity-100"
                      >
                        <MoreHorizontal className="h-3.5 w-3.5" />
                      </button>
                    }
                  >
                    <DropdownMenuItem
                      icon={<Pencil className="h-3.5 w-3.5" />}
                      onClick={() => setRenameTarget(c)}
                    >
                      Đổi tên
                    </DropdownMenuItem>
                    <DropdownMenuSeparator />
                    <DropdownMenuItem
                      tone="danger"
                      icon={<Trash2 className="h-3.5 w-3.5" />}
                      onClick={() => setDeleteTarget(c)}
                    >
                      Xóa
                    </DropdownMenuItem>
                  </DropdownMenu>
                </li>
              )
            })}
          </ul>
        )}
      </div>
    </div>
  )

  const citationCount = lastAssistant?.citations.length ?? 0

  return (
    <div className="relative flex h-full w-full min-w-0 overflow-hidden">
      {/* Panel danh sách hội thoại bên trái (chỉ mở khi người dùng bấm nút bật) */}
      {historyOpen ? (
        <aside
          aria-label="Danh sách hội thoại"
          className="hidden h-full w-60 shrink-0 border-r border-line lg:flex lg:flex-col"
        >
          {renderConversationList()}
        </aside>
      ) : null}

      {/* Ngăn kéo danh sách hội thoại trên Mobile / Tablet */}
      {mobileHistoryOpen ? (
        <div className="fixed inset-0 z-40 flex lg:hidden">
          <button
            type="button"
            aria-label="Đóng danh sách hội thoại"
            className="fixed inset-0 bg-ink/30"
            onClick={() => setMobileHistoryOpen(false)}
          />
          <div className="relative z-10 flex h-full w-72 max-w-[85vw] flex-col border-r border-line bg-bg">
            <div className="flex items-center justify-between border-b border-line px-3 py-2">
              <span className="text-xs font-semibold text-ink">Lịch sử hội thoại</span>
              <Button
                variant="ghost"
                size="icon"
                aria-label="Đóng"
                onClick={() => setMobileHistoryOpen(false)}
              >
                <X className="h-4 w-4" />
              </Button>
            </div>
            <div className="min-h-0 flex-1">{renderConversationList()}</div>
          </div>
        </div>
      ) : null}

      {/* Khu vực hội thoại chính */}
      <div className="flex h-full min-w-0 flex-1 flex-col overflow-hidden">
        {/* Thanh công cụ phía trên gọn gàng, một hàng duy nhất */}
        <header className="flex h-11 shrink-0 items-center justify-between gap-2 border-b border-line bg-bg px-3 md:px-6">
          <div className="flex min-w-0 flex-1 items-center gap-1.5">
            {/* Nút mở lịch sử hội thoại trên Mobile/Tablet */}
            <Button
              variant="ghost"
              size="icon"
              className="h-7 w-7 lg:hidden"
              aria-label="Mở lịch sử hội thoại"
              onClick={() => setMobileHistoryOpen(true)}
            >
              <PanelLeft className="h-4 w-4" />
            </Button>

            {/* Nút đóng/mở cột lịch sử hội thoại trên Desktop */}
            <Tooltip
              content={historyOpen ? "Ẩn cột lịch sử hội thoại" : "Hiện cột lịch sử hội thoại"}
              side="bottom"
            >
              <Button
                variant={historyOpen ? "secondary" : "ghost"}
                size="icon"
                className="hidden h-7 w-7 lg:inline-flex"
                aria-label={historyOpen ? "Ẩn cột lịch sử hội thoại" : "Hiện cột lịch sử hội thoại"}
                onClick={() => setHistoryOpen((o) => !o)}
              >
                <PanelLeft className="h-4 w-4" />
              </Button>
            </Tooltip>

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
                  className="truncate text-sm font-semibold text-ink"
                />
              </div>
            ) : (
              <span className="text-sm font-semibold text-ink">Hỏi đáp AI</span>
            )}
          </div>

          <div className="flex items-center gap-1.5">
            {/* Menu chọn chế độ tìm kiếm gọn gàng (mặc định: Tự động) */}
            <ModeSelector value={aiMode} onChange={handleModeChange} />

            {/* Nút mở/đóng bảng nguồn trích dẫn kèm Tooltip */}
            <Tooltip content="Xem các đoạn tài liệu trích dẫn" side="bottom">
              <Button
                variant={citationOpen ? "secondary" : "outline"}
                size="sm"
                leftIcon={<PanelRight className="h-3.5 w-3.5" />}
                onClick={() => setCitationOpen(!citationOpen)}
                aria-label="Đóng/mở bảng nguồn trích dẫn"
              >
                Nguồn{citationCount > 0 ? ` (${citationCount})` : ""}
              </Button>
            </Tooltip>

            {conversation ? (
              <DropdownMenu
                align="end"
                trigger={
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-8 w-8"
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
                  Cuộc trò chuyện mới
                </DropdownMenuItem>
                <DropdownMenuItem
                  icon={<Pencil className="h-3.5 w-3.5" />}
                  onClick={() => setRenameTarget(conversation)}
                >
                  Đổi tên
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

        {/* Vùng cuộn tin nhắn */}
        <div className="min-h-0 flex-1 overflow-y-auto px-4 py-6 md:px-8">
          <div className="mx-auto flex min-h-full w-full max-w-3xl flex-col">
            {!conversation ? (
              <div className="my-auto">
                <EmptyState
                  icon={<MessageSquare className="h-5 w-5" />}
                  title={`Không gian "${currentWorkspace?.name}" chưa có cuộc trò chuyện`}
                  description="Hãy nhập câu hỏi bên dưới hoặc bấm 'Cuộc trò chuyện mới' để bắt đầu tương tác với AI trong không gian này."
                  action={
                    <Button
                      leftIcon={<Plus className="h-4 w-4" />}
                      onClick={handleCreateConversation}
                    >
                      Cuộc trò chuyện mới
                    </Button>
                  }
                />
              </div>
            ) : conversation.messages.length === 0 ? (
              /* Trạng thái trống trẻ trung phong cách Motivo */
              <div className="my-auto flex flex-col items-center justify-center py-12 text-center">
                <span className="mb-3 inline-flex items-center gap-1.5 rounded-full border border-line bg-bg px-3 py-1 text-xs font-medium text-ink shadow-2xs">
                  <span className="rounded-full bg-brand-soft px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-brand">
                    AI
                  </span>
                  <span>{currentWorkspace?.name ?? "Không gian tri thức"}</span>
                </span>
                <h1 className="text-3xl font-bold tracking-tight text-ink sm:text-4xl">
                  Tra cứu nhanh hơn,{" "}
                  <span className="font-editorial text-[34px] sm:text-[42px]">
                    hiểu sâu hơn.
                  </span>
                </h1>
                <p className="mt-2 max-w-md text-sm text-muted">
                  Nhập câu hỏi bên dưới để nhận câu trả lời kèm trích dẫn trực tiếp từ tài liệu của bạn.
                </p>
              </div>
            ) : (
              <div className="space-y-6 pb-4">
                {conversation.messages.map((m) => {
                  const isUser = m.role === "user"
                  const attachedDocsForMsg = documents.filter((d) =>
                    m.attachedDocumentIds?.includes(d.id),
                  )
                  const scopeNb = notebooks.find((n) => n.id === m.notebookScopeId)

                  return (
                    <article
                      key={m.id}
                      className={
                        isUser
                          ? "ml-auto max-w-[85%] rounded-2xl bg-bg-secondary px-4 py-3 text-ink"
                          : "border-b border-line/70 pb-5 last:border-b-0"
                      }
                    >
                      {!isUser ? (
                        <div className="mb-2 flex items-center justify-between gap-2 text-xs">
                          <span className="font-semibold text-ink">Knowledge AI</span>
                          <Tooltip
                            content={`Thời gian: ${formatDate(m.createdAt)}${
                              m.modeRequested ? ` · Chế độ: ${getModeDescriptor(m.modeRequested).label}` : ""
                            }`}
                            side="left"
                          >
                            <span className="text-muted">{formatDate(m.createdAt)}</span>
                          </Tooltip>
                        </div>
                      ) : null}

                      {isUser && (attachedDocsForMsg.length > 0 || scopeNb) ? (
                        <div className="mb-1.5 flex flex-wrap items-center gap-1">
                          {scopeNb ? (
                            <span className="inline-flex items-center gap-1 rounded border border-line bg-bg px-1.5 py-0.5 text-[11px] text-muted">
                              <BookOpen className="h-3 w-3" />
                              {scopeNb.name}
                            </span>
                          ) : null}
                          {attachedDocsForMsg.map((d) => (
                            <span
                              key={d.id}
                              className="inline-flex items-center gap-1 rounded border border-line bg-bg px-1.5 py-0.5 text-[11px] text-muted"
                            >
                              <FileText className="h-3 w-3" />
                              {d.fileName}
                            </span>
                          ))}
                        </div>
                      ) : null}

                      {isUser ? (
                        <p className="whitespace-pre-wrap text-[14px] leading-relaxed text-ink">
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
                          <div className="flex items-center gap-2 text-xs text-muted">
                            <span className="h-2 w-2 animate-ping rounded-full bg-ink" />
                            <span>Đang tìm trong tài liệu...</span>
                          </div>
                          <div className="h-3 w-2/3 animate-pulse rounded bg-bg-secondary" />
                        </div>
                      ) : (
                        <CitationMarkdown content={m.content} />
                      )}

                      {!isUser && !m.streaming && !m.error ? (
                        <div className="mt-3 flex flex-wrap items-center justify-between gap-2 pt-1">
                          <div className="flex items-center gap-1">
                            <Tooltip content="Sao chép câu trả lời" side="bottom">
                              <Button
                                variant="ghost"
                                size="sm"
                                className="h-7 px-2 text-xs text-muted hover:text-ink"
                                leftIcon={
                                  copiedMsgId === m.id ? (
                                    <Check className="h-3.5 w-3.5 text-success" />
                                  ) : (
                                    <Copy className="h-3.5 w-3.5" />
                                  )
                                }
                                onClick={() => void handleCopyMessage(m)}
                              >
                                {copiedMsgId === m.id ? "Đã chép" : "Sao chép"}
                              </Button>
                            </Tooltip>

                            <Tooltip content="Tạo lại câu trả lời" side="bottom">
                              <Button
                                variant="ghost"
                                size="sm"
                                disabled={busy}
                                className="h-7 px-2 text-xs text-muted hover:text-ink"
                                leftIcon={<RefreshCw className="h-3.5 w-3.5" />}
                                onClick={() => {
                                  const prompt = findPrecedingUserPrompt(m.id)
                                  if (prompt) void sendQuery(prompt, m.id)
                                }}
                              >
                                Tạo lại
                              </Button>
                            </Tooltip>
                          </div>

                          {m.citations.length > 0 ? (
                            <div className="flex flex-wrap items-center gap-1">
                              {m.citations.map((c) => (
                                <Tooltip
                                  key={c.refId}
                                  content={`Xem đoạn trích từ "${c.documentName}"`}
                                  side="top"
                                >
                                  <button
                                    type="button"
                                    onClick={() => setActiveCitation(c.refId)}
                                    className="rounded border border-line bg-bg-secondary px-1.5 py-0.5 text-[11px] font-medium text-ink transition-colors hover:bg-bg-active"
                                  >
                                    [{c.refId}] {c.documentName}
                                  </button>
                                </Tooltip>
                              ))}
                            </div>
                          ) : null}
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

        {/* Khu vực Composer cố định ở cuối vùng chat */}
        <div className="shrink-0">
          <ChatComposer
            value={input}
            onChange={setInput}
            onSend={() => void sendQuery(input)}
            onCancel={handleCancelRequest}
            busy={busy}
            aiMode={aiMode}
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

      {/* Bảng Nguồn trích dẫn (CitationPanel) bên phải */}
      {citationOpen ? (
        <>
          <aside className="hidden h-full w-80 shrink-0 xl:flex">
            <CitationPanel
              citations={lastAssistant?.citations ?? []}
              onClose={() => setCitationOpen(false)}
            />
          </aside>

          <div className="fixed inset-0 z-40 flex justify-end xl:hidden">
            <button
              type="button"
              aria-label="Đóng bảng trích dẫn"
              className="fixed inset-0 bg-ink/30"
              onClick={() => setCitationOpen(false)}
            />
            <div className="relative z-10 h-full w-80 max-w-[88vw] bg-bg">
              <CitationPanel
                citations={lastAssistant?.citations ?? []}
                onClose={() => setCitationOpen(false)}
              />
            </div>
          </div>
        </>
      ) : null}

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
