import { useMemo, useState } from "react"
import { useSearchParams } from "react-router-dom"
import Markdown from "react-markdown"
import remarkGfm from "remark-gfm"
import {
  BookmarkPlus,
  CalendarCheck,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Copy,
  FilePlus2,
  FileText,
  GitFork,
  HelpCircle,
  Layers,
  PenSquare,
  Plus,
  RotateCcw,
  Sparkles,
  Trash2,
  XCircle,
} from "lucide-react"
import { PageHeader } from "@/components/common/PageHeader"
import { ConfirmDialog } from "@/components/common/NameDialog"
import {
  Badge,
  Button,
  Dialog,
  EmptyState,
  FormField,
  Input,
  Select,
  Textarea,
} from "@/components/ui"
import {
  generateStudyFlashcardsAsync,
  generateStudyMindmapAsync,
  generateStudyNotesAsync,
  generateStudyPlanAsync,
  generateStudyQuizAsync,
  generateStudySummaryAsync,
  type StudySourceContext,
  type StudyToolId,
} from "@/services/study-service"
import { useAppStore } from "@/store/app-store"
import { nowIso, relativeTime, uid } from "@/utils/format"
import { cn } from "@/utils/cn"
import type { MindmapNode, Note } from "@/types"

const VALID_TABS: StudyToolId[] = ["summary", "notes", "quiz", "flashcards", "mindmap", "plan"]

interface ToolItem {
  id: StudyToolId
  label: string
  sublabel: string
  icon: React.ComponentType<{ className?: string }>
  badgeText: string | null
}

function MindmapTreeItem({
  node,
  depth = 0,
  onAddChild,
}: {
  node: MindmapNode
  depth?: number
  onAddChild: (parentId: string) => void
}) {
  const [expanded, setExpanded] = useState(true)
  const hasChildren = Boolean(node.children && node.children.length > 0)

  return (
    <div className={depth > 0 ? "ml-3 sm:ml-5 border-l-2 border-[#DCE7E4] pl-3 sm:pl-4 mt-2" : ""}>
      <div className="group flex items-start justify-between gap-2 rounded-xl p-2.5 transition-colors hover:bg-[#F1F6F5]">
        <div className="flex min-w-0 flex-1 items-start gap-2">
          {hasChildren ? (
            <button
              type="button"
              onClick={() => setExpanded((v) => !v)}
              className="mt-0.5 rounded-md p-1 text-[#647C79] hover:bg-white hover:text-[#172B29] transition-colors"
              aria-label={expanded ? "Thu gọn nhánh" : "Mở rộng nhánh"}
            >
              {expanded ? (
                <ChevronDown className="h-4 w-4" />
              ) : (
                <ChevronRight className="h-4 w-4" />
              )}
            </button>
          ) : (
            <span className="mt-2 h-2 w-2 shrink-0 rounded-full bg-[#087F73]/70" />
          )}

          <div className="min-w-0 flex-1">
            <p className={depth === 0 ? "text-base font-bold text-[#172B29]" : "text-sm font-semibold text-[#172B29]"}>
              {node.label}
            </p>
            {node.detail ? (
              <p className="mt-0.5 text-xs leading-relaxed text-[#647C79]">{node.detail}</p>
            ) : null}
          </div>
        </div>

        <button
          type="button"
          onClick={() => onAddChild(node.id)}
          className="shrink-0 rounded-lg border border-[#DCE7E4] bg-white px-2 py-1 text-xs font-medium text-[#647C79] opacity-0 transition-all hover:border-[#087F73] hover:text-[#087F73] group-hover:opacity-100 focus:opacity-100"
        >
          + Nhánh con
        </button>
      </div>

      {hasChildren && expanded ? (
        <div className="space-y-1">
          {node.children?.map((child) => (
            <MindmapTreeItem
              key={child.id}
              node={child}
              depth={depth + 1}
              onAddChild={onAddChild}
            />
          ))}
        </div>
      ) : null}
    </div>
  )
}

export function StudyToolsPage() {
  const [params, setParams] = useSearchParams()
  const rawTab = params.get("tab") as StudyToolId | null
  const tab: StudyToolId = rawTab && VALID_TABS.includes(rawTab) ? rawTab : "summary"
  const setTab = (next: string) => setParams({ tab: next }, { replace: true })

  const workspaces = useAppStore((s) => s.workspaces)
  const documents = useAppStore((s) => s.documents)
  const notes = useAppStore((s) => s.notes)
  const quizzes = useAppStore((s) => s.quizzes)
  const flashcards = useAppStore((s) => s.flashcards)
  const studyTasks = useAppStore((s) => s.studyTasks)
  const current = useAppStore((s) => s.currentWorkspaceId)
  const status = useAppStore((s) => s.status)

  const saveNote = useAppStore((s) => s.saveNote)
  const deleteNote = useAppStore((s) => s.deleteNote)
  const upsertQuiz = useAppStore((s) => s.upsertQuiz)
  const setFlashStatus = useAppStore((s) => s.setFlashStatus)
  const addFlashcards = useAppStore((s) => s.addFlashcards)
  const deleteFlashcard = useAppStore((s) => s.deleteFlashcard)
  const addStudyTask = useAppStore((s) => s.addStudyTask)
  const updateStudyTask = useAppStore((s) => s.updateStudyTask)
  const toggleStudyTask = useAppStore((s) => s.toggleStudyTask)
  const deleteStudyTask = useAppStore((s) => s.deleteStudyTask)
  const toast = useAppStore((s) => s.toast)

  const currentWs = workspaces.find((w) => w.id === current) ?? workspaces[0]
  const wsId = currentWs?.id ?? "ws_research"

  // Toàn bộ tài liệu thuộc workspace hiện tại
  const wsDocs = useMemo(
    () => documents.filter((d) => d.workspaceId === wsId),
    [documents, wsId],
  )

  // Chọn nguồn tài liệu (rỗng = toàn bộ tài liệu trong workspace)
  const [selectedDocId, setSelectedDocId] = useState<string>("")

  const activeDoc = useMemo(
    () => (selectedDocId ? wsDocs.find((d) => d.id === selectedDocId) ?? null : null),
    [selectedDocId, wsDocs],
  )

  const scopedDocs = useMemo(
    () => (activeDoc ? [activeDoc] : wsDocs),
    [activeDoc, wsDocs],
  )

  const sourceContext: StudySourceContext = useMemo(
    () => ({
      workspaceId: wsId,
      notebook: null,
      document: activeDoc,
      documentsInScope: scopedDocs,
    }),
    [wsId, activeDoc, scopedDocs],
  )

  // 1. Summary State
  const [focusPrompt, setFocusPrompt] = useState("")
  const [customSummary, setCustomSummary] = useState<string | null>(null)
  const [summaryTitle, setSummaryTitle] = useState("")
  const [summaryIsMock, setSummaryIsMock] = useState(false)
  const [isGeneratingSummary, setIsGeneratingSummary] = useState(false)
  const summaryMarkdown = customSummary

  // 2. Notes State
  const wsNotes = useMemo(
    () => notes.filter((n) => n.workspaceId === wsId),
    [notes, wsId],
  )
  const [isGeneratingNotes, setIsGeneratingNotes] = useState(false)
  const [editingNote, setEditingNote] = useState<Note | null>(null)
  const [noteToDelete, setNoteToDelete] = useState<Note | null>(null)

  // 3. Quiz State
  const [difficulty, setDifficulty] = useState<"easy" | "medium" | "hard">("medium")
  const [questionCount, setQuestionCount] = useState<number>(3)
  const [activeQuizId, setActiveQuizId] = useState<string | null>(null)
  const [isGeneratingQuiz, setIsGeneratingQuiz] = useState(false)

  const wsQuizzes = useMemo(
    () => quizzes.filter((q) => q.workspaceId === wsId),
    [quizzes, wsId],
  )
  const quiz =
    wsQuizzes.find((q) => q.id === activeQuizId) ??
    wsQuizzes[0] ??
    null

  const quizScore = quiz
    ? quiz.questions.filter((q) => quiz.answers[q.id] === q.answerIndex).length
    : 0

  // 4. Flashcards State
  const wsCards = useMemo(
    () => flashcards.filter((f) => f.workspaceId === wsId),
    [flashcards, wsId],
  )
  const [cardIndex, setCardIndex] = useState(0)
  const [flipped, setFlipped] = useState(false)
  const [newCardOpen, setNewCardOpen] = useState(false)
  const [newCardFront, setNewCardFront] = useState("")
  const [newCardBack, setNewCardBack] = useState("")
  const [isGeneratingFlashcards, setIsGeneratingFlashcards] = useState(false)

  const safeCardIndex = wsCards.length > 0 ? cardIndex % wsCards.length : 0
  const currentCard = wsCards[safeCardIndex] ?? null
  const rememberedCount = wsCards.filter((f) => f.status === "remembered").length
  const reviewCount = wsCards.filter((f) => f.status === "review").length

  // 5. Mindmap State
  const [mindmapRoot, setMindmapRoot] = useState<MindmapNode | null>(null)
  const [mindmapIsMock, setMindmapIsMock] = useState(false)
  const [isGeneratingMindmap, setIsGeneratingMindmap] = useState(false)
  const [addBranchParentId, setAddBranchParentId] = useState<string | null>(null)
  const [branchLabel, setBranchLabel] = useState("")
  const [branchDetail, setBranchDetail] = useState("")

  // 6. Study Plan State
  const wsTasks = useMemo(
    () => studyTasks.filter((t) => t.workspaceId === wsId),
    [studyTasks, wsId],
  )
  const [newTaskTitle, setNewTaskTitle] = useState("")
  const [newTaskDue, setNewTaskDue] = useState("2026-11-05")
  const [isGeneratingPlan, setIsGeneratingPlan] = useState(false)
  const [editingTaskId, setEditingTaskId] = useState<string | null>(null)
  const [editingTaskTitle, setEditingTaskTitle] = useState("")

  // Handlers
  const handleSaveSummaryAsNote = () => {
    if (!summaryMarkdown) {
      toast({ title: "Chưa có bản tóm tắt để lưu", tone: "info" })
      return
    }
    const note: Note = {
      id: uid("note"),
      workspaceId: wsId,
      notebookId: null,
      documentId: activeDoc?.id ?? null,
      title: summaryTitle || "Tóm tắt học tập",
      content: summaryMarkdown,
      updatedAt: nowIso(),
    }
    saveNote(note)
    toast({ title: "Đã lưu bản tóm tắt vào Ghi chú", tone: "success" })
  }

  const handleGenerateSummary = async () => {
    setIsGeneratingSummary(true)
    try {
      const res = await generateStudySummaryAsync(sourceContext, focusPrompt)
      setCustomSummary(res.markdown)
      setSummaryTitle(res.title)
      setSummaryIsMock(res.isMock)
      toast({
        title: res.isMock ? "Đã tạo bản tóm tắt (Mô phỏng)" : "Đã tạo bản tóm tắt bằng AI thành công",
        description: res.isMock ? "Dịch vụ AI cục bộ chưa chạy." : "Nội dung đã được AI đọc hiểu và tổng hợp.",
        tone: res.isMock ? "info" : "success",
      })
    } catch {
      toast({ title: "Không thể tạo tóm tắt", tone: "error" })
    } finally {
      setIsGeneratingSummary(false)
    }
  }

  const handleGenerateNotes = async () => {
    setIsGeneratingNotes(true)
    try {
      const res = await generateStudyNotesAsync(sourceContext)
      setEditingNote({
        id: uid("note"),
        workspaceId: wsId,
        notebookId: null,
        documentId: activeDoc?.id ?? null,
        title: res.title,
        content: res.markdown,
        updatedAt: nowIso(),
      })
      toast({
        title: res.isMock ? "Đã tạo ghi chú (Mô phỏng)" : "Đã tạo ghi chú bằng AI thành công",
        description: res.isMock
          ? "Dịch vụ AI chưa sẵn sàng, đang dùng dữ liệu mô phỏng."
          : "Bạn có thể chỉnh sửa nội dung trước khi lưu.",
        tone: res.isMock ? "info" : "success",
      })
    } catch {
      toast({ title: "Không thể tạo ghi chú AI", tone: "error" })
    } finally {
      setIsGeneratingNotes(false)
    }
  }

  const handleGenerateQuiz = async () => {
    setIsGeneratingQuiz(true)
    try {
      const nextQuiz = await generateStudyQuizAsync(sourceContext, difficulty, questionCount)
      upsertQuiz(nextQuiz)
      setActiveQuizId(nextQuiz.id)
      toast({
        title: nextQuiz.isMock ? "Đã tạo bài Quiz (Mô phỏng)" : "Đã tạo bài Quiz bằng AI thành công",
        description: `${nextQuiz.questions.length} câu hỏi từ nguồn tài liệu đã chọn.`,
        tone: nextQuiz.isMock ? "info" : "success",
      })
    } catch {
      toast({ title: "Không thể tạo Quiz", tone: "error" })
    } finally {
      setIsGeneratingQuiz(false)
    }
  }

  const handleGenerateFlashcards = async () => {
    setIsGeneratingFlashcards(true)
    try {
      const created = await generateStudyFlashcardsAsync(sourceContext, 6)
      addFlashcards(created)
      setCardIndex(0)
      setFlipped(false)
      const hasRealAi = created.some((c) => !c.isMock)
      toast({
        title: hasRealAi
          ? `Đã tạo ${created.length} thẻ Flashcards bằng AI thành công`
          : `Đã tạo ${created.length} thẻ Flashcards (Mô phỏng)`,
        tone: hasRealAi ? "success" : "info",
      })
    } catch {
      toast({ title: "Không thể tạo Flashcards", tone: "error" })
    } finally {
      setIsGeneratingFlashcards(false)
    }
  }

  const handleAddCustomFlashcard = (e: React.FormEvent) => {
    e.preventDefault()
    if (!newCardFront.trim() || !newCardBack.trim()) return
    addFlashcards([
      {
        id: uid("fc"),
        workspaceId: wsId,
        documentId: activeDoc?.id ?? null,
        front: newCardFront.trim(),
        back: newCardBack.trim(),
        status: "new",
        isMock: false,
      },
    ])
    setNewCardFront("")
    setNewCardBack("")
    setNewCardOpen(false)
    setCardIndex(0)
    toast({ title: "Đã thêm thẻ ghi nhớ mới", tone: "success" })
  }

  const insertBranchIntoTree = (
    node: MindmapNode,
    parentId: string,
    child: MindmapNode,
  ): MindmapNode => {
    if (node.id === parentId) {
      return {
        ...node,
        children: [...(node.children ?? []), child],
      }
    }
    if (!node.children) return node
    return {
      ...node,
      children: node.children.map((c) => insertBranchIntoTree(c, parentId, child)),
    }
  }

  const handleConfirmAddBranch = (e: React.FormEvent) => {
    e.preventDefault()
    if (!mindmapRoot || !addBranchParentId || !branchLabel.trim()) return
    const nextTree = insertBranchIntoTree(mindmapRoot, addBranchParentId, {
      id: uid("mm"),
      label: branchLabel.trim(),
      detail: branchDetail.trim() || undefined,
    })
    setMindmapRoot(nextTree)
    setAddBranchParentId(null)
    setBranchLabel("")
    setBranchDetail("")
    toast({ title: "Đã thêm nhánh vào Mindmap", tone: "success" })
  }

  const handleAddStudyTask = (e: React.FormEvent) => {
    e.preventDefault()
    if (!newTaskTitle.trim()) return
    addStudyTask({
      id: uid("st"),
      workspaceId: wsId,
      documentId: activeDoc?.id ?? null,
      title: newTaskTitle.trim(),
      dueDate: newTaskDue || "2026-11-05",
      completed: false,
      isMock: false,
    })
    setNewTaskTitle("")
    toast({ title: "Đã thêm nhiệm vụ học tập", tone: "success" })
  }

  const handleGenerateMindmap = async () => {
    setIsGeneratingMindmap(true)
    try {
      const res = await generateStudyMindmapAsync(sourceContext)
      setMindmapRoot(res.root)
      setMindmapIsMock(res.isMock)
      toast({
        title: res.isMock ? "Đã tạo Mindmap (Mô phỏng)" : "Đã tạo Mindmap bằng AI thành công",
        tone: res.isMock ? "info" : "success",
      })
    } catch {
      toast({ title: "Không thể tạo Mindmap", tone: "error" })
    } finally {
      setIsGeneratingMindmap(false)
    }
  }

  const handleGenerateStudyPlan = async () => {
    setIsGeneratingPlan(true)
    try {
      const today = new Date().toISOString().slice(0, 10)
      const res = await generateStudyPlanAsync(sourceContext, today, 7)
      for (const item of res.tasks) {
        addStudyTask(item)
      }
      toast({
        title: res.isMock
          ? `Đã tạo ${res.tasks.length} nhiệm vụ học tập (Mô phỏng)`
          : `Đã tạo ${res.tasks.length} nhiệm vụ học tập bằng AI`,
        tone: res.isMock ? "info" : "success",
      })
    } catch {
      toast({ title: "Không thể tạo lộ trình học tập", tone: "error" })
    } finally {
      setIsGeneratingPlan(false)
    }
  }

  // Cấu hình 6 ô vuông công cụ học tập nổi bật
  const tools: ToolItem[] = [
    {
      id: "summary",
      label: "Tóm tắt AI",
      sublabel: "Tổng hợp cốt lõi",
      icon: FileText,
      badgeText: summaryMarkdown ? "Sẵn sàng" : null,
    },
    {
      id: "notes",
      label: "Ghi chú",
      sublabel: "Trích lược & sổ tay",
      icon: PenSquare,
      badgeText: wsNotes.length > 0 ? `${wsNotes.length}` : null,
    },
    {
      id: "quiz",
      label: "Trắc nghiệm",
      sublabel: "Kiểm tra phản xạ",
      icon: HelpCircle,
      badgeText: quiz
        ? quiz.submitted
          ? `${quizScore}/${quiz.questions.length}đ`
          : `${quiz.questions.length} câu`
        : null,
    },
    {
      id: "flashcards",
      label: "Flashcards",
      sublabel: "Ghi nhớ ngắt quãng",
      icon: Layers,
      badgeText: wsCards.length > 0 ? `${wsCards.length}` : null,
    },
    {
      id: "mindmap",
      label: "Sơ đồ tư duy",
      sublabel: "Phân cấp khái niệm",
      icon: GitFork,
      badgeText: mindmapRoot ? "Sẵn sàng" : null,
    },
    {
      id: "plan",
      label: "Lộ trình",
      sublabel: "Kế hoạch học tập",
      icon: CalendarCheck,
      badgeText:
        wsTasks.length > 0
          ? `${wsTasks.filter((t) => t.completed).length}/${wsTasks.length}`
          : null,
    },
  ]

  return (
    <div className="mx-auto max-w-5xl space-y-6 px-4 py-8 md:px-8">
      {/* Tiêu đề trang */}
      <PageHeader
        title="Công cụ học tập"
        description="Bộ công cụ AI phân tích, tổng hợp tri thức, trắc nghiệm và lập lộ trình học tập từ tài liệu trong Không gian làm việc."
        actions={
          !status.backendOnline ? (
            <Badge tone="neutral">Kết quả tạo tự động đang dùng dịch vụ mô phỏng</Badge>
          ) : null
        }
      />

      {/* Thanh chọn Nguồn tài liệu (Loại bỏ Notebook theo thiết kế mới) */}
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-[#DCE7E4] bg-white px-4 py-3 shadow-xs">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-[#F1F6F5] text-[#087F73]">
            <FileText className="h-4 w-4" />
          </div>
          <div>
            <p className="text-[10px] font-bold uppercase tracking-wider text-[#647C79]">
              Phạm vi tài liệu nguồn
            </p>
            <div className="mt-0.5 flex items-center gap-2">
              <Select
                aria-label="Chọn tài liệu làm nguồn học tập"
                value={selectedDocId}
                onChange={(e) => {
                  setSelectedDocId(e.target.value)
                  setCustomSummary(null)
                  setSummaryTitle("")
                  setSummaryIsMock(false)
                  setMindmapRoot(null)
                  setMindmapIsMock(false)
                }}
                className="h-8 max-w-md border-0 bg-transparent p-0 font-medium text-[#172B29] focus:ring-0 text-xs sm:text-sm"
              >
                <option value="">Tất cả tài liệu trong Không gian ({wsDocs.length})</option>
                {wsDocs.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.fileName}
                  </option>
                ))}
              </Select>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2 text-xs text-[#647C79]">
          <span className="inline-flex items-center gap-1.5 rounded-full bg-[#F1F6F5] px-2.5 py-1 text-xs font-medium text-[#172B29]">
            <span className="h-1.5 w-1.5 rounded-full bg-[#087F73]" />
            {scopedDocs.length} tài liệu trong phạm vi
          </span>
        </div>
      </div>

      {/* 6 Ô vuông công cụ học tập nổi bật */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 sm:gap-4 lg:grid-cols-6">
        {tools.map((item) => {
          const isActive = tab === item.id
          const Icon = item.icon
          return (
            <button
              key={item.id}
              type="button"
              onClick={() => setTab(item.id)}
              className={cn(
                "group relative flex aspect-square flex-col items-center justify-between rounded-2xl p-3 sm:p-4 text-center transition-all duration-200 select-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#087F73] focus-visible:ring-offset-2",
                isActive
                  ? "border-2 border-[#087F73] bg-[#F0FDFA] shadow-sm text-[#087F73]"
                  : "border border-[#DCE7E4] bg-white text-[#172B29] hover:border-[#087F73]/40 hover:bg-[#F9FCFB] hover:shadow-xs",
              )}
            >
              {/* Badge trên cùng */}
              <div className="flex h-5 w-full items-center justify-between text-[11px]">
                {item.badgeText ? (
                  <span
                    className={cn(
                      "inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-semibold tracking-tight transition-colors",
                      isActive
                        ? "bg-[#087F73] text-white"
                        : "bg-[#F1F6F5] text-[#647C79] group-hover:bg-[#E6F3F1] group-hover:text-[#087F73]",
                    )}
                  >
                    {item.badgeText}
                  </span>
                ) : (
                  <span />
                )}

                {isActive && (
                  <span className="flex h-2 w-2 rounded-full bg-[#087F73] ring-2 ring-[#087F73]/20" />
                )}
              </div>

              {/* Icon trung tâm */}
              <div
                className={cn(
                  "flex h-11 w-11 sm:h-13 sm:w-13 items-center justify-center rounded-xl sm:rounded-2xl transition-all duration-200",
                  isActive
                    ? "bg-[#087F73] text-white shadow-md shadow-[#087F73]/20 scale-105"
                    : "bg-[#F1F6F5] text-[#172B29] group-hover:bg-[#E6F3F1] group-hover:text-[#087F73] group-hover:scale-105",
                )}
              >
                <Icon className="h-5 w-5 sm:h-6 sm:w-6" />
              </div>

              {/* Nhãn và mô tả ngắn dưới cùng */}
              <div className="w-full min-w-0">
                <p
                  className={cn(
                    "truncate text-xs sm:text-[13px] font-semibold",
                    isActive ? "text-[#087F73]" : "text-[#172B29] group-hover:text-[#087F73]",
                  )}
                >
                  {item.label}
                </p>
                <p
                  className={cn(
                    "hidden sm:block truncate text-[11px] leading-tight",
                    isActive ? "text-[#087F73]/80 font-medium" : "text-[#647C79]",
                  )}
                >
                  {item.sublabel}
                </p>
              </div>
            </button>
          )
        })}
      </div>

      {/* Giao diện nội dung chi tiết tương ứng từng chức năng */}
      <div className="rounded-2xl border border-[#DCE7E4] bg-white p-5 sm:p-7 shadow-xs">
        {/* 1. TÓM TẮT AI */}
        {tab === "summary" && (
          <div className="space-y-5">
            {/* Thanh tiêu đề & hành động */}
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between border-b border-[#DCE7E4] pb-4">
              <div>
                <h2 className="text-lg font-bold text-[#172B29]">Tóm tắt nội dung tài liệu</h2>
                <p className="mt-0.5 text-xs text-[#647C79]">
                  AI đọc hiểu toàn bộ tài liệu trong phạm vi và rút trích các luận điểm cốt lõi.
                </p>
              </div>

              <div className="flex flex-wrap items-center gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  leftIcon={<BookmarkPlus className="h-3.5 w-3.5" />}
                  disabled={!summaryMarkdown}
                  onClick={handleSaveSummaryAsNote}
                >
                  Lưu vào Ghi chú
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  leftIcon={<Copy className="h-3.5 w-3.5" />}
                  disabled={!summaryMarkdown}
                  onClick={async () => {
                    if (!summaryMarkdown) return
                    await navigator.clipboard.writeText(summaryMarkdown)
                    toast({ title: "Đã sao chép bản tóm tắt", tone: "success" })
                  }}
                >
                  Sao chép
                </Button>
              </div>
            </div>

            {/* Ô nhập trọng tâm & nút sinh tóm tắt */}
            <div className="flex flex-col gap-2.5 sm:flex-row sm:items-center">
              <Input
                value={focusPrompt}
                onChange={(e) => {
                  setFocusPrompt(e.target.value)
                  setCustomSummary(null)
                  setSummaryTitle("")
                  setSummaryIsMock(false)
                }}
                placeholder="Nhập trọng tâm cần tóm tắt (hoặc để trống để tóm tắt tổng thể)..."
                className="flex-1"
              />
              <Button
                size="sm"
                leftIcon={<Sparkles className="h-3.5 w-3.5" />}
                loading={isGeneratingSummary}
                onClick={handleGenerateSummary}
                className="bg-[#087F73] hover:bg-[#076b61] text-white shrink-0"
              >
                Tạo tóm tắt AI
              </Button>
            </div>

            {/* Vùng hiển thị kết quả */}
            {!summaryMarkdown ? (
              <EmptyState
                compact
                icon={<Sparkles className="h-5 w-5 text-[#087F73]" />}
                title="Chưa có bản tóm tắt AI"
                description="Bấm Tạo tóm tắt AI để hệ thống phân tích và rút trích các luận điểm quan trọng từ tài liệu đã chọn."
                action={
                  <Button
                    size="sm"
                    loading={isGeneratingSummary}
                    onClick={handleGenerateSummary}
                    className="bg-[#087F73] hover:bg-[#076b61] text-white"
                  >
                    Bắt đầu tóm tắt AI
                  </Button>
                }
              />
            ) : (
              <div className="space-y-3">
                <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl bg-[#F1F6F5] px-4 py-2 text-xs">
                  <span className="font-semibold text-[#172B29]">
                    {summaryTitle || "Bản tóm tắt học tập"}
                  </span>
                  <div className="flex items-center gap-2">
                    {summaryIsMock ? (
                      <Badge tone="neutral">Mô phỏng</Badge>
                    ) : (
                      <Badge tone="success">AI cục bộ</Badge>
                    )}
                  </div>
                </div>
                <article className="markdown-body rounded-xl border border-[#DCE7E4] bg-[#FBFDFC] p-6 text-[14px] leading-relaxed text-[#172B29]">
                  <Markdown remarkPlugins={[remarkGfm]}>{summaryMarkdown}</Markdown>
                </article>
              </div>
            )}
          </div>
        )}

        {/* 2. GHI CHÚ */}
        {tab === "notes" && (
          <div className="space-y-5">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between border-b border-[#DCE7E4] pb-4">
              <div>
                <h2 className="text-lg font-bold text-[#172B29]">
                  Sổ tay ghi chú ({wsNotes.length})
                </h2>
                <p className="mt-0.5 text-xs text-[#647C79]">
                  Lưu trữ các kiến thức trọng tâm, trích lược và ghi chép cá nhân từ tài liệu.
                </p>
              </div>

              <div className="flex flex-wrap items-center gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  leftIcon={<Sparkles className="h-3.5 w-3.5" />}
                  loading={isGeneratingNotes}
                  onClick={handleGenerateNotes}
                >
                  Trích xuất ghi chú AI
                </Button>
                <Button
                  size="sm"
                  leftIcon={<FilePlus2 className="h-3.5 w-3.5" />}
                  onClick={() =>
                    setEditingNote({
                      id: uid("note"),
                      workspaceId: wsId,
                      notebookId: null,
                      documentId: activeDoc?.id ?? null,
                      title: "",
                      content: "",
                      updatedAt: nowIso(),
                    })
                  }
                  className="bg-[#087F73] hover:bg-[#076b61] text-white"
                >
                  + Ghi chú mới
                </Button>
              </div>
            </div>

            {wsNotes.length === 0 ? (
              <EmptyState
                compact
                icon={<PenSquare className="h-5 w-5 text-[#087F73]" />}
                title="Chưa có ghi chú nào"
                description="Tạo ghi chú thủ công hoặc dùng AI trích xuất các ý chính quan trọng từ tài liệu."
                action={
                  <div className="flex items-center gap-2">
                    <Button
                      size="sm"
                      onClick={() =>
                        setEditingNote({
                          id: uid("note"),
                          workspaceId: wsId,
                          notebookId: null,
                          documentId: activeDoc?.id ?? null,
                          title: "",
                          content: "",
                          updatedAt: nowIso(),
                        })
                      }
                      className="bg-[#087F73] hover:bg-[#076b61] text-white"
                    >
                      Tạo ghi chú mới
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      leftIcon={<Sparkles className="h-3.5 w-3.5" />}
                      loading={isGeneratingNotes}
                      onClick={handleGenerateNotes}
                    >
                      AI Trích xuất
                    </Button>
                  </div>
                }
              />
            ) : (
              <div className="grid grid-cols-1 gap-3.5 md:grid-cols-2">
                {wsNotes.map((n) => {
                  const doc = documents.find((x) => x.id === n.documentId)
                  return (
                    <div
                      key={n.id}
                      className="group flex flex-col justify-between rounded-xl border border-[#DCE7E4] bg-white p-4 transition-all hover:border-[#087F73]/40 hover:shadow-xs"
                    >
                      <div>
                        <div className="flex items-start justify-between gap-2">
                          <button
                            type="button"
                            onClick={() => setEditingNote(n)}
                            className="min-w-0 flex-1 text-left"
                          >
                            <h3 className="text-sm font-bold text-[#172B29] group-hover:text-[#087F73] transition-colors line-clamp-1">
                              {n.title || "Ghi chú không tiêu đề"}
                            </h3>
                          </button>
                          <div className="flex shrink-0 items-center gap-1">
                            <Button
                              variant="ghost"
                              size="sm"
                              className="h-7 px-2 text-xs text-[#647C79] hover:text-[#172B29]"
                              onClick={() => setEditingNote(n)}
                            >
                              Sửa
                            </Button>
                            <Button
                              variant="ghost"
                              size="icon"
                              className="h-7 w-7 text-[#647C79] hover:text-red-600"
                              onClick={() => setNoteToDelete(n)}
                              aria-label={`Xóa ghi chú ${n.title}`}
                            >
                              <Trash2 className="h-3.5 w-3.5" />
                            </Button>
                          </div>
                        </div>

                        <p className="mt-2 line-clamp-3 whitespace-pre-line text-xs leading-relaxed text-[#647C79]">
                          {n.content || "Chưa có nội dung"}
                        </p>
                      </div>

                      <div className="mt-4 flex flex-wrap items-center justify-between gap-2 border-t border-[#DCE7E4]/60 pt-2.5 text-[11px] text-[#647C79]">
                        {doc ? (
                          <span className="truncate max-w-[180px] font-medium text-[#172B29]">
                            {doc.fileName}
                          </span>
                        ) : (
                          <span>Ghi chép tự do</span>
                        )}
                        <span>{relativeTime(n.updatedAt)}</span>
                      </div>
                    </div>
                  )
                })}
              </div>
            )}
          </div>
        )}

        {/* 3. TRẮC NGHIỆM / QUIZ */}
        {tab === "quiz" && (
          <div className="space-y-5">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between border-b border-[#DCE7E4] pb-4">
              <div>
                <h2 className="text-lg font-bold text-[#172B29]">
                  Bộ câu hỏi trắc nghiệm tự kiểm tra
                </h2>
                <p className="mt-0.5 text-xs text-[#647C79]">
                  Tự động kiểm tra mức độ hiểu sâu kiến thức với câu hỏi đối chiếu từ tài liệu.
                </p>
              </div>

              <div className="flex flex-wrap items-center gap-2">
                <Select
                  aria-label="Độ khó Quiz"
                  value={difficulty}
                  onChange={(e) => setDifficulty(e.target.value as typeof difficulty)}
                  className="h-8 w-32 text-xs"
                >
                  <option value="easy">Độ khó: Dễ</option>
                  <option value="medium">Độ khó: Vừa</option>
                  <option value="hard">Độ khó: Khó</option>
                </Select>

                <Select
                  aria-label="Số lượng câu hỏi"
                  value={String(questionCount)}
                  onChange={(e) => setQuestionCount(Number(e.target.value))}
                  className="h-8 w-28 text-xs"
                >
                  <option value="3">3 câu hỏi</option>
                  <option value="5">5 câu hỏi</option>
                </Select>

                <Button
                  size="sm"
                  leftIcon={<Sparkles className="h-3.5 w-3.5" />}
                  loading={isGeneratingQuiz}
                  onClick={handleGenerateQuiz}
                  className="bg-[#087F73] hover:bg-[#076b61] text-white shrink-0"
                >
                  Tạo Quiz AI
                </Button>
              </div>
            </div>

            {!quiz ? (
              <EmptyState
                compact
                icon={<HelpCircle className="h-5 w-5 text-[#087F73]" />}
                title="Chưa có bài trắc nghiệm"
                description="Bấm nút Tạo Quiz AI để hệ thống phân tích tài liệu và dựng bộ câu hỏi ôn tập kèm đáp án đối chiếu."
                action={
                  <Button
                    size="sm"
                    loading={isGeneratingQuiz}
                    onClick={handleGenerateQuiz}
                    className="bg-[#087F73] hover:bg-[#076b61] text-white"
                  >
                    Tạo bài Quiz AI
                  </Button>
                }
              />
            ) : (
              <div className="space-y-5">
                {/* Banner kết quả nếu đã nộp */}
                {quiz.submitted && (
                  <div className="flex items-center justify-between rounded-xl border border-[#DCE7E4] bg-[#F0FDFA] p-4 text-[#172B29]">
                    <div className="flex items-center gap-3">
                      <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-[#087F73] text-white">
                        <Check className="h-5 w-5" />
                      </div>
                      <div>
                        <p className="text-sm font-bold text-[#087F73]">
                          Điểm số của bạn: {quizScore} / {quiz.questions.length} câu đúng (
                          {Math.round((quizScore / quiz.questions.length) * 100)}%)
                        </p>
                        <p className="text-xs text-[#647C79]">
                          {quizScore === quiz.questions.length
                            ? "Xuất sắc! Bạn đã nắm rất vững kiến thức tài liệu."
                            : "Hãy xem lại phần giải thích chi tiết dưới mỗi câu để củng cố kiến thức."}
                        </p>
                      </div>
                    </div>
                    <Button
                      variant="outline"
                      size="sm"
                      leftIcon={<RotateCcw className="h-3.5 w-3.5" />}
                      onClick={() => upsertQuiz({ ...quiz, answers: {}, submitted: false })}
                    >
                      Làm lại
                    </Button>
                  </div>
                )}

                {/* Danh sách câu hỏi */}
                <div className="space-y-4">
                  {quiz.questions.map((q, idx) => {
                    const selectedOpt = quiz.answers[q.id]
                    const isCorrect = selectedOpt === q.answerIndex
                    const letters = ["A", "B", "C", "D", "E"]

                    return (
                      <div
                        key={q.id}
                        className="rounded-xl border border-[#DCE7E4] bg-white p-5 space-y-3"
                      >
                        <div className="flex items-start gap-2.5">
                          <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-[#F1F6F5] text-xs font-bold text-[#087F73]">
                            {idx + 1}
                          </span>
                          <p className="text-sm font-bold text-[#172B29] leading-snug">
                            {q.prompt}
                          </p>
                        </div>

                        <div className="space-y-2 pt-1">
                          {q.options.map((opt, optIdx) => {
                            const isChosen = selectedOpt === optIdx
                            const isRightAnswer = q.answerIndex === optIdx

                            let optionStyle =
                              "border-[#DCE7E4] bg-white text-[#172B29] hover:bg-[#F9FCFB]"

                            if (quiz.submitted) {
                              if (isRightAnswer) {
                                optionStyle = "border-emerald-500 bg-emerald-50/70 text-emerald-950 font-semibold"
                              } else if (isChosen && !isRightAnswer) {
                                optionStyle = "border-rose-400 bg-rose-50/70 text-rose-950 line-through"
                              } else {
                                optionStyle = "border-[#DCE7E4] opacity-60"
                              }
                            } else if (isChosen) {
                              optionStyle =
                                "border-[#087F73] bg-[#F0FDFA] font-semibold text-[#087F73]"
                            }

                            return (
                              <button
                                key={opt}
                                type="button"
                                disabled={quiz.submitted}
                                onClick={() =>
                                  upsertQuiz({
                                    ...quiz,
                                    answers: { ...quiz.answers, [q.id]: optIdx },
                                  })
                                }
                                className={cn(
                                  "flex w-full items-center gap-3 rounded-xl border p-3 text-left text-xs sm:text-[13px] transition-all",
                                  optionStyle,
                                )}
                              >
                                <span
                                  className={cn(
                                    "flex h-6 w-6 shrink-0 items-center justify-center rounded-lg text-xs font-bold",
                                    isChosen
                                      ? "bg-[#087F73] text-white"
                                      : "bg-[#F1F6F5] text-[#647C79]",
                                  )}
                                >
                                  {letters[optIdx] ?? optIdx + 1}
                                </span>
                                <span className="flex-1">{opt}</span>
                                {quiz.submitted && isRightAnswer && (
                                  <CheckCircle2 className="h-4 w-4 text-emerald-600 shrink-0" />
                                )}
                                {quiz.submitted && isChosen && !isRightAnswer && (
                                  <XCircle className="h-4 w-4 text-rose-500 shrink-0" />
                                )}
                              </button>
                            )
                          })}
                        </div>

                        {quiz.submitted && (
                          <div
                            className={cn(
                              "mt-3 rounded-xl p-3 text-xs leading-relaxed",
                              isCorrect
                                ? "bg-emerald-50 text-emerald-900 border border-emerald-200"
                                : "bg-rose-50 text-rose-900 border border-rose-200",
                            )}
                          >
                            <strong>{isCorrect ? "✓ Chính xác:" : "✕ Chưa chính xác:"}</strong>{" "}
                            {q.explanation}
                          </div>
                        )}
                      </div>
                    )
                  })}
                </div>

                {/* Thanh hành động nộp bài */}
                <div className="flex flex-wrap items-center justify-between gap-3 border-t border-[#DCE7E4] pt-4">
                  <div className="flex items-center gap-2">
                    <Button
                      disabled={quiz.submitted}
                      onClick={() => {
                        upsertQuiz({ ...quiz, submitted: true })
                        toast({ title: "Đã nộp bài Quiz", tone: "success" })
                      }}
                      className="bg-[#087F73] hover:bg-[#076b61] text-white"
                    >
                      Nộp bài
                    </Button>
                    {quiz.submitted ? (
                      <Button
                        variant="outline"
                        leftIcon={<RotateCcw className="h-3.5 w-3.5" />}
                        onClick={() =>
                          upsertQuiz({ ...quiz, answers: {}, submitted: false })
                        }
                      >
                        Làm lại
                      </Button>
                    ) : null}
                  </div>

                  <span className="text-xs text-[#647C79]">
                    Đã trả lời {Object.keys(quiz.answers).length} / {quiz.questions.length} câu
                  </span>
                </div>
              </div>
            )}
          </div>
        )}

        {/* 4. FLASHCARDS */}
        {tab === "flashcards" && (
          <div className="space-y-5">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between border-b border-[#DCE7E4] pb-4">
              <div>
                <h2 className="text-lg font-bold text-[#172B29]">Bộ thẻ ghi nhớ Flashcards</h2>
                <div className="mt-1 flex items-center gap-2 text-xs text-[#647C79]">
                  <span>
                    Tổng: <strong className="text-[#172B29]">{wsCards.length}</strong>
                  </span>
                  <span>·</span>
                  <span className="text-emerald-700 font-medium">
                    Đã nhớ: {rememberedCount}
                  </span>
                  <span>·</span>
                  <span className="text-amber-700 font-medium">
                    Cần ôn: {reviewCount}
                  </span>
                </div>
              </div>

              <div className="flex flex-wrap items-center gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  leftIcon={<Sparkles className="h-3.5 w-3.5" />}
                  loading={isGeneratingFlashcards}
                  onClick={handleGenerateFlashcards}
                >
                  Tạo thẻ AI từ nguồn
                </Button>
                <Button
                  size="sm"
                  leftIcon={<Plus className="h-3.5 w-3.5" />}
                  onClick={() => setNewCardOpen(true)}
                  className="bg-[#087F73] hover:bg-[#076b61] text-white"
                >
                  + Thêm thẻ
                </Button>
              </div>
            </div>

            {!currentCard ? (
              <EmptyState
                compact
                icon={<Layers className="h-5 w-5 text-[#087F73]" />}
                title="Chưa có thẻ Flashcard nào"
                description="Tạo bộ thẻ ghi nhớ tự động từ tài liệu bằng AI hoặc tự tạo thẻ theo ý bạn."
                action={
                  <div className="flex items-center gap-2">
                    <Button
                      size="sm"
                      loading={isGeneratingFlashcards}
                      onClick={handleGenerateFlashcards}
                      className="bg-[#087F73] hover:bg-[#076b61] text-white"
                    >
                      Tạo Flashcard AI
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => setNewCardOpen(true)}
                    >
                      Thêm thẻ mới
                    </Button>
                  </div>
                }
              />
            ) : (
              <div className="mx-auto max-w-xl space-y-4">
                {/* Chỉ số tiến độ */}
                <div className="flex items-center justify-between text-xs text-[#647C79]">
                  <span>
                    Thẻ{" "}
                    <strong className="text-[#172B29]">
                      {safeCardIndex + 1} / {wsCards.length}
                    </strong>
                  </span>
                  <span className="text-[11px]">Nhấp chuột vào thẻ để lật</span>
                </div>

                {/* Khung thẻ Flashcard lật */}
                <button
                  type="button"
                  onClick={() => setFlipped((v) => !v)}
                  className={cn(
                    "flex min-h-[220px] sm:min-h-[250px] w-full flex-col items-center justify-between rounded-2xl border-2 p-6 sm:p-8 text-center transition-all duration-200 select-none shadow-xs",
                    flipped
                      ? "border-[#087F73] bg-[#F4FAF9]"
                      : "border-[#DCE7E4] bg-white hover:border-[#087F73]/50",
                  )}
                >
                  <span
                    className={cn(
                      "rounded-full px-3 py-1 text-[11px] font-bold uppercase tracking-wider",
                      flipped
                        ? "bg-[#087F73] text-white"
                        : "bg-[#F1F6F5] text-[#647C79]",
                    )}
                  >
                    {flipped ? "Mặt sau (Đáp án & Luận giải)" : "Mặt trước (Câu hỏi / Thuật ngữ)"}
                  </span>

                  <p className="my-auto text-base sm:text-lg font-semibold leading-relaxed text-[#172B29]">
                    {flipped ? currentCard.back : currentCard.front}
                  </p>

                  <span className="text-[11px] text-[#647C79]">
                    {flipped ? "Nhấp để xem câu hỏi" : "Nhấp để xem đáp án"}
                  </span>
                </button>

                {/* Điều hướng & đánh giá thẻ */}
                <div className="flex flex-wrap items-center justify-between gap-2 pt-2">
                  <div className="flex items-center gap-1.5">
                    <Button
                      variant="outline"
                      size="sm"
                      leftIcon={<ChevronLeft className="h-3.5 w-3.5" />}
                      onClick={() => {
                        setFlipped(false)
                        setCardIndex((i) => (i - 1 + wsCards.length) % wsCards.length)
                      }}
                    >
                      Trước
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => {
                        setFlipped(false)
                        setCardIndex((i) => (i + 1) % wsCards.length)
                      }}
                    >
                      Tiếp
                      <ChevronRight className="ml-1 h-3.5 w-3.5" />
                    </Button>
                  </div>

                  <div className="flex items-center gap-1.5">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => {
                        setFlashStatus(currentCard.id, "review")
                        setFlipped(false)
                        setCardIndex((i) => (i + 1) % wsCards.length)
                      }}
                      className="border-amber-300 text-amber-800 hover:bg-amber-50"
                    >
                      Cần ôn tập
                    </Button>
                    <Button
                      size="sm"
                      leftIcon={<Check className="h-3.5 w-3.5" />}
                      onClick={() => {
                        setFlashStatus(currentCard.id, "remembered")
                        setFlipped(false)
                        setCardIndex((i) => (i + 1) % wsCards.length)
                      }}
                      className="bg-[#087F73] hover:bg-[#076b61] text-white"
                    >
                      Đã nhớ
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-8 w-8 text-[#647C79] hover:text-red-600"
                      onClick={() => {
                        deleteFlashcard(currentCard.id)
                        setCardIndex(0)
                      }}
                      aria-label="Xóa thẻ này"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </Button>
                  </div>
                </div>
              </div>
            )}
          </div>
        )}

        {/* 5. MINDMAP */}
        {tab === "mindmap" && (
          <div className="space-y-5">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between border-b border-[#DCE7E4] pb-4">
              <div>
                <h2 className="text-lg font-bold text-[#172B29]">Sơ đồ tư duy phân cấp</h2>
                <p className="mt-0.5 text-xs text-[#647C79]">
                  Cấu trúc cây khái niệm mô hình hoá các chủ đề, ý chính và luận điểm từ tài liệu.
                </p>
              </div>

              <div className="flex items-center gap-2">
                {mindmapRoot ? (
                  mindmapIsMock ? (
                    <Badge tone="neutral">Mô phỏng</Badge>
                  ) : (
                    <Badge tone="success">AI cục bộ</Badge>
                  )
                ) : null}
                <Button
                  size="sm"
                  leftIcon={<Sparkles className="h-3.5 w-3.5" />}
                  loading={isGeneratingMindmap}
                  onClick={handleGenerateMindmap}
                  className="bg-[#087F73] hover:bg-[#076b61] text-white shrink-0"
                >
                  Tạo Mindmap AI
                </Button>
              </div>
            </div>

            {!mindmapRoot ? (
              <EmptyState
                compact
                icon={<GitFork className="h-5 w-5 text-[#087F73]" />}
                title="Chưa có Sơ đồ tư duy"
                description="Bấm Tạo Mindmap AI để hệ thống phân tích tài liệu và cấu trúc hóa các chủ đề thành sơ đồ phân nhánh trực quan."
                action={
                  <Button
                    size="sm"
                    loading={isGeneratingMindmap}
                    onClick={handleGenerateMindmap}
                    className="bg-[#087F73] hover:bg-[#076b61] text-white"
                  >
                    Tạo Mindmap AI
                  </Button>
                }
              />
            ) : (
              <div className="rounded-xl border border-[#DCE7E4] bg-[#FBFDFC] p-4 sm:p-5">
                <MindmapTreeItem
                  node={mindmapRoot}
                  onAddChild={(parentId) => setAddBranchParentId(parentId)}
                />
              </div>
            )}
          </div>
        )}

        {/* 6. LỘ TRÌNH HỌC TẬP */}
        {tab === "plan" && (
          <div className="space-y-5">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between border-b border-[#DCE7E4] pb-4">
              <div>
                <h2 className="text-lg font-bold text-[#172B29]">Lộ trình & Kế hoạch học tập</h2>
                <p className="mt-0.5 text-xs text-[#647C79]">
                  Hoàn thành{" "}
                  <strong className="text-[#172B29]">
                    {wsTasks.filter((t) => t.completed).length}/{wsTasks.length}
                  </strong>{" "}
                  nhiệm vụ học tập
                </p>
              </div>

              <Button
                size="sm"
                leftIcon={<Sparkles className="h-3.5 w-3.5" />}
                loading={isGeneratingPlan}
                onClick={handleGenerateStudyPlan}
                className="bg-[#087F73] hover:bg-[#076b61] text-white shrink-0"
              >
                Tạo lộ trình AI
              </Button>
            </div>

            {/* Form thêm nhiệm vụ mới nhanh */}
            <form onSubmit={handleAddStudyTask} className="flex flex-wrap items-center gap-2">
              <Input
                value={newTaskTitle}
                onChange={(e) => setNewTaskTitle(e.target.value)}
                placeholder="Thêm nhiệm vụ học tập mới..."
                className="min-w-[240px] flex-1"
              />
              <Input
                type="date"
                value={newTaskDue}
                onChange={(e) => setNewTaskDue(e.target.value)}
                className="w-36 text-xs"
                aria-label="Hạn hoàn thành"
              />
              <Button
                type="submit"
                size="sm"
                disabled={!newTaskTitle.trim()}
                className="bg-[#087F73] hover:bg-[#076b61] text-white shrink-0"
              >
                Thêm nhiệm vụ
              </Button>
            </form>

            {wsTasks.length === 0 ? (
              <EmptyState
                compact
                icon={<CalendarCheck className="h-5 w-5 text-[#087F73]" />}
                title="Chưa có nhiệm vụ trong kế hoạch"
                description="Tạo lộ trình tự động bằng AI từ tài liệu hoặc tự thêm các mục tiêu học tập của bạn."
                action={
                  <Button
                    size="sm"
                    loading={isGeneratingPlan}
                    onClick={handleGenerateStudyPlan}
                    className="bg-[#087F73] hover:bg-[#076b61] text-white"
                  >
                    Tạo lộ trình AI
                  </Button>
                }
              />
            ) : (
              <ul className="divide-y divide-[#DCE7E4] rounded-xl border border-[#DCE7E4] bg-white">
                {wsTasks.map((task) => {
                  const doc = documents.find((d) => d.id === task.documentId)
                  const isEditing = editingTaskId === task.id

                  return (
                    <li
                      key={task.id}
                      className="flex items-center justify-between gap-3 p-3.5 hover:bg-[#F9FCFB] transition-colors"
                    >
                      <div className="flex min-w-0 flex-1 items-center gap-3">
                        <input
                          type="checkbox"
                          checked={task.completed}
                          onChange={() => toggleStudyTask(task.id)}
                          aria-label={`Đánh dấu hoàn thành ${task.title}`}
                          className="h-4 w-4 rounded border-[#DCE7E4] text-[#087F73] focus:ring-[#087F73]"
                        />

                        {isEditing ? (
                          <div className="flex flex-1 items-center gap-2">
                            <Input
                              autoFocus
                              value={editingTaskTitle}
                              onChange={(e) => setEditingTaskTitle(e.target.value)}
                              className="h-8 text-xs"
                            />
                            <Button
                              size="sm"
                              onClick={() => {
                                if (editingTaskTitle.trim()) {
                                  updateStudyTask(task.id, {
                                    title: editingTaskTitle.trim(),
                                  })
                                }
                                setEditingTaskId(null)
                              }}
                              className="bg-[#087F73] text-white h-8 text-xs px-2.5"
                            >
                              Lưu
                            </Button>
                          </div>
                        ) : (
                          <div className="min-w-0 flex-1">
                            <p
                              className={cn(
                                "text-sm font-medium",
                                task.completed
                                  ? "text-[#647C79] line-through"
                                  : "text-[#172B29]",
                              )}
                            >
                              {task.title}
                            </p>
                            <p className="text-[11px] text-[#647C79]">
                              Hạn: {task.dueDate}
                              {doc ? ` · Nguồn: ${doc.fileName}` : ""}
                            </p>
                          </div>
                        )}
                      </div>

                      <div className="flex shrink-0 items-center gap-1">
                        {!isEditing && (
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-7 px-2 text-xs text-[#647C79] hover:text-[#172B29]"
                            onClick={() => {
                              setEditingTaskId(task.id)
                              setEditingTaskTitle(task.title)
                            }}
                          >
                            Sửa
                          </Button>
                        )}
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-7 w-7 text-[#647C79] hover:text-red-600"
                          onClick={() => deleteStudyTask(task.id)}
                          aria-label={`Xóa nhiệm vụ ${task.title}`}
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </Button>
                      </div>
                    </li>
                  )
                })}
              </ul>
            )}
          </div>
        )}
      </div>

      {/* Dialog chỉnh sửa / tạo Ghi chú (Đã loại bỏ Notebook) */}
      <Dialog
        open={Boolean(editingNote)}
        title={editingNote?.title ? "Chỉnh sửa ghi chú" : "Ghi chú mới"}
        onClose={() => setEditingNote(null)}
      >
        {editingNote ? (
          <form
            onSubmit={(e) => {
              e.preventDefault()
              saveNote({
                ...editingNote,
                title: editingNote.title.trim() || "Ghi chú mới",
                updatedAt: nowIso(),
              })
              setEditingNote(null)
              toast({ title: "Đã lưu ghi chú", tone: "success" })
            }}
            className="space-y-3"
          >
            <FormField label="Tiêu đề">
              <Input
                autoFocus
                value={editingNote.title}
                onChange={(e) =>
                  setEditingNote({ ...editingNote, title: e.target.value })
                }
                placeholder="Nhập tiêu đề ghi chú..."
              />
            </FormField>

            <FormField label="Nội dung">
              <Textarea
                rows={6}
                value={editingNote.content}
                onChange={(e) =>
                  setEditingNote({ ...editingNote, content: e.target.value })
                }
                placeholder="Nhập nội dung ghi chú..."
              />
            </FormField>

            <div className="flex justify-end gap-2 pt-2">
              <Button
                type="button"
                variant="outline"
                onClick={() => setEditingNote(null)}
              >
                Hủy
              </Button>
              <Button type="submit" className="bg-[#087F73] hover:bg-[#076b61] text-white">
                Lưu ghi chú
              </Button>
            </div>
          </form>
        ) : null}
      </Dialog>

      {/* Dialog thêm thẻ Flashcard */}
      <Dialog
        open={newCardOpen}
        title="Thêm thẻ Flashcard"
        onClose={() => setNewCardOpen(false)}
      >
        <form onSubmit={handleAddCustomFlashcard} className="space-y-3">
          <FormField label="Mặt trước (Câu hỏi / Thuật ngữ)">
            <Input
              autoFocus
              value={newCardFront}
              onChange={(e) => setNewCardFront(e.target.value)}
              placeholder="Ví dụ: RRF là viết tắt của thuật ngữ gì?"
            />
          </FormField>
          <FormField label="Mặt sau (Đáp án / Luận giải)">
            <Textarea
              rows={4}
              value={newCardBack}
              onChange={(e) => setNewCardBack(e.target.value)}
              placeholder="Ví dụ: Reciprocal Rank Fusion — phương pháp gộp và tái xếp hạng kết quả từ BM25 và Vector Search."
            />
          </FormField>
          <div className="flex justify-end gap-2 pt-2">
            <Button
              type="button"
              variant="outline"
              onClick={() => setNewCardOpen(false)}
            >
              Hủy
            </Button>
            <Button
              type="submit"
              disabled={!newCardFront.trim() || !newCardBack.trim()}
              className="bg-[#087F73] hover:bg-[#076b61] text-white"
            >
              Thêm thẻ
            </Button>
          </div>
        </form>
      </Dialog>

      {/* Dialog thêm nhánh Mindmap */}
      <Dialog
        open={Boolean(addBranchParentId)}
        title="Thêm nhánh con vào Mindmap"
        onClose={() => setAddBranchParentId(null)}
      >
        <form onSubmit={handleConfirmAddBranch} className="space-y-3">
          <FormField label="Tên nhánh">
            <Input
              autoFocus
              value={branchLabel}
              onChange={(e) => setBranchLabel(e.target.value)}
              placeholder="Nhập tên khái niệm / ý chính..."
            />
          </FormField>
          <FormField label="Chi tiết bổ sung (tuỳ chọn)">
            <Input
              value={branchDetail}
              onChange={(e) => setBranchDetail(e.target.value)}
              placeholder="Mô tả ngắn gọn..."
            />
          </FormField>
          <div className="flex justify-end gap-2 pt-2">
            <Button
              type="button"
              variant="outline"
              onClick={() => setAddBranchParentId(null)}
            >
              Hủy
            </Button>
            <Button
              type="submit"
              disabled={!branchLabel.trim()}
              className="bg-[#087F73] hover:bg-[#076b61] text-white"
            >
              Thêm nhánh
            </Button>
          </div>
        </form>
      </Dialog>

      {/* Xác nhận xóa ghi chú */}
      <ConfirmDialog
        open={Boolean(noteToDelete)}
        title="Xóa ghi chú?"
        description={`Xóa "${noteToDelete?.title ?? ""}"?`}
        onClose={() => setNoteToDelete(null)}
        onConfirm={() => {
          if (noteToDelete) {
            deleteNote(noteToDelete.id)
            setNoteToDelete(null)
            toast({ title: "Đã xóa ghi chú", tone: "info" })
          }
        }}
      />
    </div>
  )
}
