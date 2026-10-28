import { useState } from "react"
import { useNavigate } from "react-router-dom"
import {
  ArrowRight,
  BookOpen,
  ChevronRight,
  Clock,
  FilePlus2,
  FileText,
  FileUp,
  FolderOpen,
  FolderPlus,
  GraduationCap,
  MessageSquare,
  MoreHorizontal,
  TrendingUp,
} from "lucide-react"
import { NameDialog } from "@/components/common/NameDialog"
import {
  Button,
  Dialog,
  DropdownMenu,
  DropdownMenuItem,
  DropdownMenuSeparator,
  EmptyState,
  FormField,
  Input,
  Select,
  StatusBadge,
  Textarea,
  Tooltip,
} from "@/components/ui"
import { useAppStore } from "@/store/app-store"
import {
  formatBytes,
  greeting,
  nowIso,
  relativeTime,
  todayFullLabel,
  uid,
} from "@/utils/format"

export function DashboardPage() {
  const navigate = useNavigate()
  const [wsOpen, setWsOpen] = useState(false)
  const [noteOpen, setNoteOpen] = useState(false)

  const [noteTitle, setNoteTitle] = useState("")
  const [noteContent, setNoteContent] = useState("")
  const [noteDocId, setNoteDocId] = useState<string>("")

  const workspaces = useAppStore((s) => s.workspaces)
  const documents = useAppStore((s) => s.documents)
  const notes = useAppStore((s) => s.notes)
  const flashcards = useAppStore((s) => s.flashcards)
  const studyTasks = useAppStore((s) => s.studyTasks)
  const conversations = useAppStore((s) => s.conversations)
  const current = useAppStore((s) => s.currentWorkspaceId)
  const createWorkspace = useAppStore((s) => s.createWorkspace)
  const createConversation = useAppStore((s) => s.createConversation)
  const saveNote = useAppStore((s) => s.saveNote)
  const log = useAppStore((s) => s.log)
  const toast = useAppStore((s) => s.toast)

  const activeWorkspace = workspaces.find((w) => w.id === current) ?? workspaces[0]
  const activeWsId = activeWorkspace?.id ?? "ws_default"

  // Dữ liệu cô lập nghiêm ngặt theo workspace đang chọn
  const wsDocs = documents.filter((d) => d.workspaceId === activeWsId)
  const wsConversations = conversations.filter((c) => c.workspaceId === activeWsId)
  const wsNotes = notes.filter((n) => n.workspaceId === activeWsId)
  const wsFlashcards = flashcards.filter((f) => f.workspaceId === activeWsId)
  const wsStudyTasks = studyTasks.filter((t) => t.workspaceId === activeWsId)

  const readyDocsCount = wsDocs.filter((d) => d.status === "ready").length
  const totalDocs = Math.max(wsDocs.length, 1)
  const readyPct = wsDocs.length > 0 ? Math.round((readyDocsCount / totalDocs) * 100) : 0

  const completedTasks = wsStudyTasks.filter((t) => t.completed).length
  const totalTasks = Math.max(wsStudyTasks.length, 1)
  const progressPct =
    wsStudyTasks.length > 0
      ? Math.round(((readyDocsCount + completedTasks) / (totalDocs + totalTasks)) * 100)
      : wsDocs.length > 0
        ? readyPct
        : 0

  // Vòng tròn Donut Chart tiến độ
  const radius = 30
  const circumference = 2 * Math.PI * radius
  const strokeDashoffset = circumference - (progressPct / 100) * circumference

  const handleCreateQuickNote = (e: React.FormEvent) => {
    e.preventDefault()
    if (!noteTitle.trim()) return
    saveNote({
      id: uid("note"),
      workspaceId: activeWsId,
      notebookId: null,
      documentId: noteDocId || null,
      title: noteTitle.trim(),
      content: noteContent.trim(),
      updatedAt: nowIso(),
    })
    log(`Tạo ghi chú "${noteTitle.trim()}"`, "study")
    toast({ title: "Đã lưu ghi chú", tone: "success" })
    setNoteTitle("")
    setNoteContent("")
    setNoteDocId("")
    setNoteOpen(false)
  }

  const handleStartChat = () => {
    if (wsConversations[0]) {
      navigate(`/chat/${wsConversations[0].id}`)
    } else {
      const c = createConversation(activeWsId)
      navigate(`/chat/${c.id}`)
    }
  }

  return (
    <div className="mx-auto max-w-5xl px-4 py-6 md:px-8">
      {/* 1. Phần Chào mừng & Hành động chính: Gọn gàng, thoáng mắt */}
      <section className="mb-6 flex flex-col justify-between gap-3 sm:flex-row sm:items-end">
        <div className="min-w-0 max-w-xl">
          <h1 className="text-2xl font-bold tracking-tight text-ink sm:text-[26px]">
            {greeting()} 👋{" "}
            <span className="font-editorial text-[28px] font-normal sm:text-[30px]">
              tri thức hôm nay.
            </span>
          </h1>
          <p className="mt-1 text-xs text-muted sm:text-[13px]">
            {todayFullLabel()} — Tiếp tục các câu hỏi hoặc xem tài liệu.
          </p>
        </div>

        {/* 2 nút hành động chính + menu thao tác phụ */}
        <div className="flex shrink-0 items-center gap-2">
          <button
            type="button"
            onClick={handleStartChat}
            className="inline-flex h-9 items-center gap-2 rounded-full bg-primary px-4 text-xs font-semibold text-primary-fg shadow-xs transition-opacity hover:opacity-90"
          >
            <MessageSquare className="h-3.5 w-3.5" />
            <span>Hỏi đáp AI</span>
            <ArrowRight className="h-3 w-3 opacity-70" />
          </button>

          <Button
            variant="outline"
            size="sm"
            className="h-9 rounded-full bg-bg px-3.5 text-xs font-medium text-ink"
            leftIcon={<FileUp className="h-3.5 w-3.5 text-brand" />}
            onClick={() => navigate("/documents")}
          >
            Tải tài liệu
          </Button>

          <DropdownMenu
            align="end"
            trigger={
              <span>
                <Tooltip content="Thao tác khác" side="bottom">
                  <Button
                    variant="outline"
                    size="icon"
                    className="h-9 w-9 rounded-full bg-bg text-muted hover:text-ink"
                    aria-label="Thao tác khác"
                  >
                    <MoreHorizontal className="h-4 w-4" />
                  </Button>
                </Tooltip>
              </span>
            }
          >
            <DropdownMenuItem
              icon={<FilePlus2 className="h-3.5 w-3.5 text-brand" />}
              onClick={() => setNoteOpen(true)}
            >
              Tạo ghi chú nhanh
            </DropdownMenuItem>
            <DropdownMenuItem
              icon={<FolderPlus className="h-3.5 w-3.5 text-brand" />}
              onClick={() => setWsOpen(true)}
            >
              Tạo không gian mới
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem
              icon={<GraduationCap className="h-3.5 w-3.5 text-muted" />}
              onClick={() => navigate("/study")}
            >
              Công cụ học tập
            </DropdownMenuItem>
          </DropdownMenu>
        </div>
      </section>

      {/* 2. Dải 4 số liệu tối giản: Thanh mảnh, không cồng kềnh */}
      <section
        aria-label="Chỉ số tổng quan"
        className="motivo-card mb-6 grid grid-cols-2 divide-y divide-line p-2 sm:grid-cols-4 sm:divide-x sm:divide-y-0 sm:p-3"
      >
        <div className="flex items-center gap-3 p-2 sm:px-3">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-brand-soft text-brand">
            <FolderOpen className="h-4 w-4" />
          </div>
          <div className="min-w-0">
            <div className="text-lg font-bold tracking-tight text-ink sm:text-xl">
              {workspaces.length}
            </div>
            <div className="truncate text-xs text-muted">Không gian</div>
          </div>
        </div>

        <div className="flex items-center gap-3 p-2 sm:px-3">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-brand-soft text-brand">
            <FileText className="h-4 w-4" />
          </div>
          <div className="min-w-0">
            <div className="text-lg font-bold tracking-tight text-ink sm:text-xl">
              {readyPct}%
            </div>
            <div className="truncate text-xs text-muted">
              Tài liệu sẵn sàng ({readyDocsCount}/{wsDocs.length})
            </div>
          </div>
        </div>

        <div className="flex items-center gap-3 p-2 sm:px-3">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-brand-soft text-brand">
            <TrendingUp className="h-4 w-4" />
          </div>
          <div className="min-w-0">
            <div className="text-lg font-bold tracking-tight text-ink sm:text-xl">
              {wsConversations.length}
            </div>
            <div className="truncate text-xs text-muted">Cuộc trò chuyện</div>
          </div>
        </div>

        <div className="flex items-center gap-3 p-2 sm:px-3">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-brand-soft text-brand">
            <Clock className="h-4 w-4" />
          </div>
          <div className="min-w-0">
            <div className="text-lg font-bold tracking-tight text-ink sm:text-xl">
              {wsNotes.length + wsFlashcards.length}
            </div>
            <div className="truncate text-xs text-muted">Ghi chú & Thẻ ôn tập</div>
          </div>
        </div>
      </section>

      {/* 3. Bố cục chính 2 cột: Cân đối, tập trung vào công việc quan trọng */}
      <div className="grid gap-5 lg:grid-cols-12">
        {/* Cột trái (7/12): Hoạt động gần đây (Hội thoại & Tài liệu) */}
        <div className="space-y-4 lg:col-span-7">
          {/* Nhóm 1: Cuộc trò chuyện gần đây trong workspace này */}
          <div className="motivo-card p-4 sm:p-5">
            <div className="mb-3 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="flex h-6 w-6 items-center justify-center rounded-lg bg-brand-soft text-brand">
                  <MessageSquare className="h-3.5 w-3.5" />
                </span>
                <h2 className="text-sm font-semibold text-ink">Cuộc trò chuyện gần đây</h2>
              </div>
              <button
                type="button"
                onClick={() => navigate("/chat")}
                className="inline-flex items-center gap-0.5 text-xs font-medium text-muted hover:text-brand"
              >
                <span>Xem tất cả</span>
                <ChevronRight className="h-3.5 w-3.5" />
              </button>
            </div>

            {wsConversations.length === 0 ? (
              <EmptyState
                compact
                icon={<MessageSquare className="h-4 w-4" />}
                title="Chưa có cuộc trò chuyện"
                description={`Không gian "${activeWorkspace?.name}" chưa có hội thoại nào.`}
                action={
                  <Button size="sm" variant="outline" onClick={handleStartChat}>
                    Hỏi đáp AI
                  </Button>
                }
              />
            ) : (
              <div className="divide-y divide-line/60">
                {wsConversations.slice(0, 3).map((c) => (
                  <button
                    key={c.id}
                    type="button"
                    onClick={() => navigate(`/chat/${c.id}`)}
                    className="group flex w-full items-center justify-between gap-3 py-2.5 text-left transition-colors hover:bg-bg-hover/70"
                  >
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-xs font-semibold text-ink group-hover:text-brand">
                        {c.title}
                      </p>
                      <p className="mt-0.5 truncate text-[11px] text-muted">
                        {c.messages.length} tin nhắn · {relativeTime(c.updatedAt)}
                      </p>
                    </div>
                    <ChevronRight className="h-3.5 w-3.5 shrink-0 text-muted/50 transition-transform group-hover:translate-x-0.5 group-hover:text-brand" />
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* Nhóm 2: Tài liệu gần đây trong workspace này */}
          <div className="motivo-card p-4 sm:p-5">
            <div className="mb-3 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="flex h-6 w-6 items-center justify-center rounded-lg bg-brand-soft text-brand">
                  <BookOpen className="h-3.5 w-3.5" />
                </span>
                <h2 className="text-sm font-semibold text-ink">Tài liệu trong không gian</h2>
              </div>
              <button
                type="button"
                onClick={() => navigate("/documents")}
                className="inline-flex items-center gap-0.5 text-xs font-medium text-muted hover:text-brand"
              >
                <span>Xem tất cả</span>
                <ChevronRight className="h-3.5 w-3.5" />
              </button>
            </div>

            {wsDocs.length === 0 ? (
              <EmptyState
                compact
                icon={<BookOpen className="h-4 w-4" />}
                title="Chưa có tài liệu nào"
                description={`Không gian "${activeWorkspace?.name}" chưa có tài liệu nào.`}
                action={
                  <Button size="sm" variant="outline" onClick={() => navigate("/documents")}>
                    Tải tài liệu
                  </Button>
                }
              />
            ) : (
              <div className="divide-y divide-line/60">
                {wsDocs.slice(0, 3).map((d) => (
                  <button
                    key={d.id}
                    type="button"
                    onClick={() => navigate(`/documents/${d.id}`)}
                    className="group flex w-full items-center justify-between gap-3 py-2.5 text-left transition-colors hover:bg-bg-hover/70"
                  >
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-xs font-semibold text-ink group-hover:text-brand">
                        {d.fileName}
                      </p>
                      <p className="mt-0.5 truncate text-[11px] text-muted">
                        {d.fileType.toUpperCase()} · {d.fileSize ? formatBytes(d.fileSize) : `${d.pageCount} trang`} · {relativeTime(d.createdAt)}
                      </p>
                    </div>
                    <div className="shrink-0">
                      <StatusBadge status={d.status} />
                    </div>
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Cột phải (5/12): Tiến độ tri thức & Thao tác nhanh */}
        <div className="space-y-4 lg:col-span-5">
          {/* Card: Tiến độ tri thức tinh gọn */}
          <div className="motivo-card p-4 sm:p-5">
            <div className="mb-2 flex items-center justify-between">
              <h2 className="text-sm font-semibold text-ink">Tiến độ tri thức</h2>
              <button
                type="button"
                onClick={() => navigate("/study")}
                className="inline-flex items-center gap-0.5 text-xs font-medium text-muted hover:text-brand"
              >
                <span>Học tập</span>
                <ChevronRight className="h-3 w-3" />
              </button>
            </div>

            <div className="flex items-center gap-4 py-1.5">
              <div className="relative flex h-16 w-16 shrink-0 items-center justify-center">
                <svg className="h-16 w-16 -rotate-90" viewBox="0 0 72 72">
                  <circle
                    cx="36"
                    cy="36"
                    r={radius}
                    stroke="currentColor"
                    strokeWidth="5"
                    fill="transparent"
                    className="text-brand-soft"
                  />
                  <circle
                    cx="36"
                    cy="36"
                    r={radius}
                    stroke="currentColor"
                    strokeWidth="5"
                    strokeDasharray={circumference}
                    strokeDashoffset={strokeDashoffset}
                    strokeLinecap="round"
                    fill="transparent"
                    className="text-brand transition-all duration-500"
                  />
                </svg>
                <span className="absolute text-xs font-bold text-ink">{progressPct}%</span>
              </div>

              <div className="min-w-0 space-y-1">
                <p className="text-xs font-semibold text-ink">
                  {readyDocsCount}/{wsDocs.length} tài liệu đã sẵn sàng
                </p>
                <p className="text-[11px] leading-relaxed text-muted">
                  {completedTasks}/{wsStudyTasks.length} nhiệm vụ học tập hoàn thành.
                </p>
              </div>
            </div>
          </div>

          {/* Card: Thao tác nhanh */}
          <div className="motivo-card p-4 sm:p-5">
            <h2 className="mb-3 text-sm font-semibold text-ink">Thao tác nhanh</h2>
            <div className="space-y-2">
              <button
                type="button"
                onClick={() => setNoteOpen(true)}
                className="flex w-full items-center justify-between rounded-xl border border-line/60 bg-bg p-2.5 text-left text-xs font-medium text-ink transition-colors hover:border-brand/30 hover:bg-bg-hover"
              >
                <div className="flex items-center gap-2">
                  <span className="flex h-6 w-6 items-center justify-center rounded-lg bg-brand-soft text-brand">
                    <FilePlus2 className="h-3.5 w-3.5" />
                  </span>
                  <span>Tạo ghi chú nhanh</span>
                </div>
                <ChevronRight className="h-3.5 w-3.5 text-muted" />
              </button>

              <button
                type="button"
                onClick={() => navigate("/documents")}
                className="flex w-full items-center justify-between rounded-xl border border-line/60 bg-bg p-2.5 text-left text-xs font-medium text-ink transition-colors hover:border-brand/30 hover:bg-bg-hover"
              >
                <div className="flex items-center gap-2">
                  <span className="flex h-6 w-6 items-center justify-center rounded-lg bg-brand-soft text-brand">
                    <FileUp className="h-3.5 w-3.5" />
                  </span>
                  <span>Tải lên tài liệu mới</span>
                </div>
                <ChevronRight className="h-3.5 w-3.5 text-muted" />
              </button>

              <button
                type="button"
                onClick={() => navigate("/study")}
                className="flex w-full items-center justify-between rounded-xl border border-line/60 bg-bg p-2.5 text-left text-xs font-medium text-ink transition-colors hover:border-brand/30 hover:bg-bg-hover"
              >
                <div className="flex items-center gap-2">
                  <span className="flex h-6 w-6 items-center justify-center rounded-lg bg-brand-soft text-brand">
                    <GraduationCap className="h-3.5 w-3.5" />
                  </span>
                  <span>Ôn tập với Flashcard & Quiz</span>
                </div>
                <ChevronRight className="h-3.5 w-3.5 text-muted" />
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Dialog tạo Không gian làm việc mới */}
      <NameDialog
        open={wsOpen}
        title="Tạo không gian làm việc mới"
        confirmLabel="Tạo"
        showDescription
        onClose={() => setWsOpen(false)}
        onSubmit={(name, description) => {
          const ws = createWorkspace(name, description)
          toast({ title: "Đã tạo không gian mới", description: ws.name, tone: "success" })
          navigate(`/knowledge/${ws.id}`)
        }}
      />

      {/* Dialog tạo Ghi chú nhanh */}
      <Dialog
        open={noteOpen}
        title="Tạo ghi chú nhanh"
        onClose={() => setNoteOpen(false)}
      >
        <form onSubmit={handleCreateQuickNote} className="space-y-3">
          <FormField label="Tiêu đề">
            <Input
              autoFocus
              value={noteTitle}
              onChange={(e) => setNoteTitle(e.target.value)}
              placeholder="Nhập tiêu đề ghi chú..."
            />
          </FormField>

          <FormField label="Tài liệu liên quan (tuỳ chọn)">
            <Select value={noteDocId} onChange={(e) => setNoteDocId(e.target.value)}>
              <option value="">-- Không chọn --</option>
              {documents
                .filter((d) => d.workspaceId === current)
                .map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.fileName}
                  </option>
                ))}
            </Select>
          </FormField>

          <FormField label="Nội dung">
            <Textarea
              rows={4}
              value={noteContent}
              onChange={(e) => setNoteContent(e.target.value)}
              placeholder="Nội dung ghi chú..."
            />
          </FormField>

          <div className="flex justify-end gap-2 pt-2">
            <Button type="button" variant="outline" onClick={() => setNoteOpen(false)}>
              Hủy
            </Button>
            <Button type="submit" disabled={!noteTitle.trim()}>
              Lưu ghi chú
            </Button>
          </div>
        </form>
      </Dialog>
    </div>
  )
}
