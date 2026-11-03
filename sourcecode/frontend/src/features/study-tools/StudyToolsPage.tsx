import { useMemo, useState } from "react"
import { useSearchParams } from "react-router-dom"
import Markdown from "react-markdown"
import remarkGfm from "remark-gfm"
import {
  BookmarkPlus,
  Check,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Copy,
  FilePlus2,
  Plus,
  RefreshCw,
  RotateCcw,
  Sparkles,
  Trash2,
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
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
  Textarea,
} from "@/components/ui"
import {
  buildMindmapFromContext,
  generateStudyFlashcards,
  generateStudyPlanTasks,
  generateStudyQuiz,
  generateStudySummary,
  type StudySourceContext,
  type StudyToolId,
} from "@/services/study-service"
import { useAppStore } from "@/store/app-store"
import { nowIso, relativeTime, uid } from "@/utils/format"
import type { MindmapNode, Note } from "@/types"

const VALID_TABS: StudyToolId[] = ["summary", "notes", "quiz", "flashcards", "mindmap", "plan"]

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
    <div className={depth > 0 ? "ml-5 border-l border-line pl-3" : ""}>
      <div className="group flex items-start justify-between gap-2 rounded-md px-2 py-1.5 transition-colors hover:bg-bg-hover">
        <div className="flex min-w-0 flex-1 items-start gap-1.5">
          {hasChildren ? (
            <button
              type="button"
              onClick={() => setExpanded((v) => !v)}
              className="mt-0.5 rounded p-0.5 text-muted hover:text-ink"
              aria-label={expanded ? "Thu gọn nhánh" : "Mở rộng nhánh"}
            >
              {expanded ? (
                <ChevronDown className="h-3.5 w-3.5" />
              ) : (
                <ChevronRight className="h-3.5 w-3.5" />
              )}
            </button>
          ) : (
            <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-muted/60" />
          )}

          <div className="min-w-0 flex-1">
            <p className={depth === 0 ? "text-base font-semibold text-ink" : "text-sm font-medium text-ink"}>
              {node.label}
            </p>
            {node.detail ? (
              <p className="mt-0.5 text-xs leading-relaxed text-muted">{node.detail}</p>
            ) : null}
          </div>
        </div>

        <button
          type="button"
          onClick={() => onAddChild(node.id)}
          className="shrink-0 rounded px-1.5 py-0.5 text-xs text-muted opacity-0 transition-opacity hover:bg-bg hover:text-ink group-hover:opacity-100 focus:opacity-100"
        >
          + Nhánh con
        </button>
      </div>

      {hasChildren && expanded ? (
        <div className="mt-1 space-y-1">
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
  const notebooks = useAppStore((s) => s.notebooks)
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
  const wsNotebooks = useMemo(
    () => notebooks.filter((n) => n.workspaceId === wsId),
    [notebooks, wsId],
  )
  const wsDocs = useMemo(
    () => documents.filter((d) => d.workspaceId === wsId),
    [documents, wsId],
  )

  // Chọn nguồn học tập (Notebook hoặc Tài liệu cụ thể)
  const [selectedNotebookId, setSelectedNotebookId] = useState<string>("")
  const [selectedDocId, setSelectedDocId] = useState<string>(() => wsDocs[0]?.id ?? "")

  const scopedDocs = useMemo(() => {
    if (!selectedNotebookId) return wsDocs
    return wsDocs.filter((d) => d.notebookId === selectedNotebookId)
  }, [wsDocs, selectedNotebookId])

  const activeDoc =
    scopedDocs.find((d) => d.id === selectedDocId) ?? scopedDocs[0] ?? null
  const activeNotebook =
    wsNotebooks.find((n) => n.id === selectedNotebookId) ?? null

  const sourceContext: StudySourceContext = useMemo(
    () => ({
      workspaceId: wsId,
      notebook: activeNotebook,
      document: activeDoc,
      documentsInScope: scopedDocs,
    }),
    [wsId, activeNotebook, activeDoc, scopedDocs],
  )

  // 1. Summary State
  const [focusPrompt, setFocusPrompt] = useState("")
  const [customSummary, setCustomSummary] = useState<string | null>(null)
  const generatedSummary = useMemo(
    () => generateStudySummary(sourceContext, focusPrompt),
    [sourceContext, focusPrompt],
  )
  const summaryMarkdown = customSummary ?? generatedSummary.markdown

  // 2. Notes State
  const wsNotes = useMemo(
    () =>
      notes
        .filter((n) => n.workspaceId === wsId)
        .filter((n) => (!selectedNotebookId ? true : n.notebookId === selectedNotebookId)),
    [notes, wsId, selectedNotebookId],
  )
  const [editingNote, setEditingNote] = useState<Note | null>(null)
  const [noteToDelete, setNoteToDelete] = useState<Note | null>(null)

  // 3. Quiz State (chỉ trong workspace hiện tại)
  const [difficulty, setDifficulty] = useState<"easy" | "medium" | "hard">("medium")
  const [questionCount, setQuestionCount] = useState<number>(3)
  const [activeQuizId, setActiveQuizId] = useState<string | null>(null)

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

  const safeCardIndex = wsCards.length > 0 ? cardIndex % wsCards.length : 0
  const currentCard = wsCards[safeCardIndex] ?? null
  const rememberedCount = wsCards.filter((f) => f.status === "remembered").length
  const reviewCount = wsCards.filter((f) => f.status === "review").length

  // 5. Mindmap State
  const [customMindmap, setCustomMindmap] = useState<MindmapNode | null>(null)
  const mindmapRoot = useMemo(
    () => customMindmap ?? buildMindmapFromContext(sourceContext),
    [customMindmap, sourceContext],
  )
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
  const [editingTaskId, setEditingTaskId] = useState<string | null>(null)
  const [editingTaskTitle, setEditingTaskTitle] = useState("")

  // Handlers
  const handleSaveSummaryAsNote = () => {
    const note: Note = {
      id: uid("note"),
      workspaceId: wsId,
      notebookId: activeNotebook?.id ?? activeDoc?.notebookId ?? null,
      documentId: activeDoc?.id ?? null,
      title: generatedSummary.title,
      content: summaryMarkdown,
      updatedAt: nowIso(),
    }
    saveNote(note)
    toast({ title: "Đã lưu bản tóm tắt vào Ghi chú", tone: "success" })
  }

  const handleGenerateQuiz = () => {
    const nextQuiz = generateStudyQuiz(sourceContext, difficulty, questionCount)
    upsertQuiz(nextQuiz)
    setActiveQuizId(nextQuiz.id)
    toast({
      title: "Đã tạo bài Quiz mới (Mô phỏng)",
      description: `${nextQuiz.questions.length} câu hỏi từ nguồn đã chọn.`,
      tone: "info",
    })
  }

  const handleGenerateFlashcards = () => {
    const created = generateStudyFlashcards(sourceContext)
    addFlashcards(created)
    setCardIndex(0)
    setFlipped(false)
    toast({
      title: `Đã tạo ${created.length} thẻ Flashcard (Mô phỏng)`,
      tone: "info",
    })
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
    if (!addBranchParentId || !branchLabel.trim()) return
    const nextTree = insertBranchIntoTree(mindmapRoot, addBranchParentId, {
      id: uid("mm"),
      label: branchLabel.trim(),
      detail: branchDetail.trim() || undefined,
    })
    setCustomMindmap(nextTree)
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

  const handleGenerateStudyPlan = () => {
    const generated = generateStudyPlanTasks(sourceContext)
    for (const item of generated) {
      addStudyTask(item)
    }
    toast({
      title: `Đã tạo ${generated.length} nhiệm vụ học tập (Mô phỏng)`,
      tone: "info",
    })
  }

  return (
    <div className="mx-auto max-w-4xl px-4 py-8 md:px-8">
      <PageHeader
        title="Công cụ học tập"
        actions={
          !status.backendOnline ? (
            <Badge tone="neutral">Kết quả tạo tự động đang dùng dịch vụ mô phỏng</Badge>
          ) : null
        }
      />

      {/* Thanh chọn Nguồn học tập chung (Notebook / Tài liệu) */}
      <div className="mb-6 flex flex-wrap items-center gap-3 rounded-lg border border-line bg-bg-secondary/50 px-3.5 py-2.5 text-xs">
        <div className="flex items-center gap-2">
          <span className="font-medium text-muted">Notebook:</span>
          <Select
            aria-label="Chọn Notebook làm nguồn"
            value={selectedNotebookId}
            onChange={(e) => {
              setSelectedNotebookId(e.target.value)
              setCustomSummary(null)
              setCustomMindmap(null)
            }}
            className="h-7 w-44 text-xs"
          >
            <option value="">Tất cả trong Workspace</option>
            {wsNotebooks.map((nb) => (
              <option key={nb.id} value={nb.id}>
                {nb.name}
              </option>
            ))}
          </Select>
        </div>

        <div className="flex items-center gap-2">
          <span className="font-medium text-muted">Tài liệu nguồn:</span>
          <Select
            aria-label="Chọn tài liệu làm nguồn"
            value={activeDoc?.id ?? ""}
            onChange={(e) => {
              setSelectedDocId(e.target.value)
              setCustomSummary(null)
              setCustomMindmap(null)
            }}
            className="h-7 w-56 text-xs"
          >
            {scopedDocs.length === 0 ? (
              <option value="">-- Chưa có tài liệu --</option>
            ) : (
              scopedDocs.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.fileName}
                </option>
              ))
            )}
          </Select>
        </div>
      </div>

      {/* Tabs chuyển đổi 6 công cụ */}
      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="summary">1. Tóm tắt</TabsTrigger>
          <TabsTrigger value="notes">
            2. Ghi chú <span className="text-xs text-muted">{wsNotes.length}</span>
          </TabsTrigger>
          <TabsTrigger value="quiz">3. Quiz</TabsTrigger>
          <TabsTrigger value="flashcards">
            4. Flashcards <span className="text-xs text-muted">{wsCards.length}</span>
          </TabsTrigger>
          <TabsTrigger value="mindmap">5. Mindmap</TabsTrigger>
          <TabsTrigger value="plan">
            6. Kế hoạch <span className="text-xs text-muted">{wsTasks.length}</span>
          </TabsTrigger>
        </TabsList>

        {/* 1. SUMMARY */}
        <TabsContent value="summary" className="space-y-4">
          <div className="flex flex-wrap items-center gap-2">
            <Input
              value={focusPrompt}
              onChange={(e) => {
                setFocusPrompt(e.target.value)
                setCustomSummary(null)
              }}
              placeholder="Nhập trọng tâm muốn tóm tắt (tuỳ chọn)..."
              className="max-w-sm"
            />
            <Button
              variant="outline"
              size="sm"
              leftIcon={<Sparkles className="h-3.5 w-3.5" />}
              onClick={() => {
                setCustomSummary(null)
                toast({ title: "Đã tạo lại bản tóm tắt (Mô phỏng)", tone: "info" })
              }}
            >
              Tạo tóm tắt
            </Button>
            <Button
              variant="outline"
              size="sm"
              leftIcon={<BookmarkPlus className="h-3.5 w-3.5" />}
              onClick={handleSaveSummaryAsNote}
            >
              Lưu thành Ghi chú
            </Button>
            <Button
              variant="ghost"
              size="sm"
              leftIcon={<Copy className="h-3.5 w-3.5" />}
              onClick={async () => {
                await navigator.clipboard.writeText(summaryMarkdown)
                toast({ title: "Đã sao chép bản tóm tắt", tone: "success" })
              }}
            >
              Sao chép
            </Button>
          </div>

          <article className="markdown-body rounded-lg border border-line bg-bg p-5 text-[14px] leading-7">
            <Markdown remarkPlugins={[remarkGfm]}>{summaryMarkdown}</Markdown>
          </article>
        </TabsContent>

        {/* 2. NOTES */}
        <TabsContent value="notes" className="space-y-4">
          <div className="flex items-center justify-between">
            <span className="text-xs text-muted">
              Lưu trữ ghi chú gắn với notebook và tài liệu đang chọn.
            </span>
            <Button
              size="sm"
              leftIcon={<FilePlus2 className="h-3.5 w-3.5" />}
              onClick={() =>
                setEditingNote({
                  id: uid("note"),
                  workspaceId: wsId,
                  notebookId: activeNotebook?.id ?? activeDoc?.notebookId ?? null,
                  documentId: activeDoc?.id ?? null,
                  title: "",
                  content: "",
                  updatedAt: nowIso(),
                })
              }
            >
              Ghi chú mới
            </Button>
          </div>

          {wsNotes.length === 0 ? (
            <EmptyState
              compact
              title="Chưa có ghi chú nào"
              description="Bấm Ghi chú mới để lưu lại ý chính từ tài liệu."
            />
          ) : (
            <div className="divide-y divide-line border-y border-line">
              {wsNotes.map((n) => {
                const nb = notebooks.find((x) => x.id === n.notebookId)
                const doc = documents.find((x) => x.id === n.documentId)
                return (
                  <div key={n.id} className="py-3.5">
                    <div className="flex items-start justify-between gap-2">
                      <button
                        type="button"
                        onClick={() => setEditingNote(n)}
                        className="min-w-0 flex-1 text-left"
                      >
                        <p className="text-sm font-semibold text-ink hover:underline">
                          {n.title || "Ghi chú không tiêu đề"}
                        </p>
                        <p className="mt-1 whitespace-pre-line text-[13px] leading-relaxed text-muted">
                          {n.content || "Chưa có nội dung"}
                        </p>
                      </button>

                      <div className="flex shrink-0 items-center gap-1">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => setEditingNote(n)}
                        >
                          Sửa
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-7 w-7 text-muted hover:text-error"
                          onClick={() => setNoteToDelete(n)}
                          aria-label={`Xóa ghi chú ${n.title}`}
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </Button>
                      </div>
                    </div>

                    <div className="mt-2 flex flex-wrap items-center gap-2 text-[11px] text-muted">
                      {nb ? <span>Notebook: {nb.name}</span> : null}
                      {doc ? <span>· Tài liệu: {doc.fileName}</span> : null}
                      <span>· Cập nhật {relativeTime(n.updatedAt)}</span>
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </TabsContent>

        {/* 3. QUIZ */}
        <TabsContent value="quiz" className="space-y-5">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line pb-3">
            <div className="flex flex-wrap items-center gap-2">
              <Select
                aria-label="Độ khó Quiz"
                value={difficulty}
                onChange={(e) => setDifficulty(e.target.value as typeof difficulty)}
                className="h-8 w-36 text-xs"
              >
                <option value="easy">Độ khó: Dễ</option>
                <option value="medium">Độ khó: Trung bình</option>
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
                variant="outline"
                size="sm"
                leftIcon={<Sparkles className="h-3.5 w-3.5" />}
                onClick={handleGenerateQuiz}
              >
                Tạo Quiz từ nguồn
              </Button>
            </div>

            {quiz ? (
              <span className="text-xs text-muted">
                {quiz.title} · {quiz.questions.length} câu {quiz.isMock ? "(Mô phỏng)" : ""}
              </span>
            ) : null}
          </div>

          {!quiz ? (
            <EmptyState
              compact
              title="Chưa có bài Quiz"
              description="Bấm Tạo Quiz từ nguồn để bắt đầu tự kiểm tra kiến thức."
              action={
                <Button size="sm" onClick={handleGenerateQuiz}>
                  Tạo Quiz
                </Button>
              }
            />
          ) : (
            <div className="space-y-5">
              {quiz.questions.map((q, idx) => {
                const selectedOpt = quiz.answers[q.id]
                const isCorrect = selectedOpt === q.answerIndex
                return (
                  <fieldset
                    key={q.id}
                    className="rounded-lg border border-line bg-bg p-4"
                  >
                    <legend className="px-1 text-sm font-semibold text-ink">
                      Câu {idx + 1}: {q.prompt}
                    </legend>
                    <div className="mt-2 space-y-1.5">
                      {q.options.map((opt, optIdx) => {
                        const checked = selectedOpt === optIdx
                        return (
                          <label
                            key={opt}
                            className={`flex cursor-pointer items-center gap-2.5 rounded-md border px-3 py-2 text-[13px] transition-colors ${
                              checked
                                ? "border-ink bg-bg-secondary font-medium text-ink"
                                : "border-line bg-bg text-ink hover:bg-bg-hover"
                            }`}
                          >
                            <input
                              type="radio"
                              name={q.id}
                              checked={checked}
                              disabled={quiz.submitted}
                              onChange={() =>
                                upsertQuiz({
                                  ...quiz,
                                  answers: { ...quiz.answers, [q.id]: optIdx },
                                })
                              }
                            />
                            <span>{opt}</span>
                          </label>
                        )
                      })}
                    </div>

                    {quiz.submitted ? (
                      <div
                        className={`mt-3 rounded-md px-3 py-2 text-xs ${
                          isCorrect
                            ? "bg-success-soft text-success"
                            : "bg-error-soft text-error"
                        }`}
                      >
                        <strong>{isCorrect ? "Chính xác." : "Chưa chính xác."}</strong>{" "}
                        {q.explanation}
                      </div>
                    ) : null}
                  </fieldset>
                )
              })}

              <div className="flex flex-wrap items-center justify-between gap-3 border-t border-line pt-4">
                <div className="flex items-center gap-2">
                  <Button
                    disabled={quiz.submitted}
                    onClick={() => {
                      upsertQuiz({ ...quiz, submitted: true })
                      toast({ title: "Đã nộp bài Quiz", tone: "success" })
                    }}
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

                {quiz.submitted ? (
                  <div className="text-sm font-semibold text-ink">
                    Kết quả: {quizScore} / {quiz.questions.length} câu đúng
                  </div>
                ) : null}
              </div>
            </div>
          )}
        </TabsContent>

        {/* 4. FLASHCARDS */}
        <TabsContent value="flashcards" className="space-y-5">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line pb-3">
            <div className="flex items-center gap-2 text-xs text-muted">
              <span>
                Đã nhớ: <strong className="text-ink">{rememberedCount}</strong>
              </span>
              <span>·</span>
              <span>
                Cần ôn: <strong className="text-ink">{reviewCount}</strong>
              </span>
              <span>·</span>
              <span>
                Tổng số: <strong className="text-ink">{wsCards.length}</strong>
              </span>
            </div>

            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                leftIcon={<Sparkles className="h-3.5 w-3.5" />}
                onClick={handleGenerateFlashcards}
              >
                Tạo thẻ từ nguồn
              </Button>
              <Button
                size="sm"
                leftIcon={<Plus className="h-3.5 w-3.5" />}
                onClick={() => setNewCardOpen(true)}
              >
                Thêm thẻ
              </Button>
            </div>
          </div>

          {!currentCard ? (
            <EmptyState
              compact
              title="Chưa có thẻ Flashcard"
              description="Tạo thẻ tự động từ tài liệu hoặc tự thêm thẻ mới."
              action={
                <Button size="sm" onClick={handleGenerateFlashcards}>
                  Tạo Flashcard
                </Button>
              }
            />
          ) : (
            <div className="mx-auto max-w-lg space-y-4">
              <button
                type="button"
                onClick={() => setFlipped((v) => !v)}
                className="flex min-h-[210px] w-full flex-col items-center justify-center rounded-xl border border-line bg-bg p-6 text-center transition-colors hover:bg-bg-secondary/50"
              >
                <span className="mb-2 text-[11px] uppercase tracking-wide text-muted">
                  {flipped ? "Mặt sau (Đáp án)" : "Mặt trước (Câu hỏi)"} · Thẻ {safeCardIndex + 1}/{wsCards.length}
                </span>
                <p className="text-base font-medium leading-relaxed text-ink">
                  {flipped ? currentCard.back : currentCard.front}
                </p>
                <span className="mt-4 text-xs text-muted">Nhấn vào thẻ để lật</span>
              </button>

              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex items-center gap-1">
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
                  >
                    Đã nhớ
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-8 w-8 text-muted hover:text-error"
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
        </TabsContent>

        {/* 5. MINDMAP */}
        <TabsContent value="mindmap" className="space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line pb-3">
            <span className="text-xs text-muted">
              Sơ đồ phân cấp khái niệm. Bấm vào từng mục để thu gọn/mở rộng hoặc thêm nhánh con.
            </span>
            <Button
              variant="outline"
              size="sm"
              leftIcon={<RefreshCw className="h-3.5 w-3.5" />}
              onClick={() => {
                setCustomMindmap(null)
                toast({ title: "Đã làm mới Mindmap theo tài liệu nguồn", tone: "info" })
              }}
            >
              Tạo lại từ nguồn
            </Button>
          </div>

          <div className="rounded-lg border border-line bg-bg p-4">
            <MindmapTreeItem
              node={mindmapRoot}
              onAddChild={(parentId) => setAddBranchParentId(parentId)}
            />
          </div>
        </TabsContent>

        {/* 6. STUDY PLAN */}
        <TabsContent value="plan" className="space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line pb-3">
            <span className="text-xs text-muted">
              Hoàn thành{" "}
              <strong className="text-ink">
                {wsTasks.filter((t) => t.completed).length}/{wsTasks.length}
              </strong>{" "}
              nhiệm vụ học tập
            </span>
            <Button
              variant="outline"
              size="sm"
              leftIcon={<Sparkles className="h-3.5 w-3.5" />}
              onClick={handleGenerateStudyPlan}
            >
              Tạo lộ trình từ nguồn
            </Button>
          </div>

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
              className="w-40"
              aria-label="Hạn hoàn thành"
            />
            <Button type="submit" size="sm" disabled={!newTaskTitle.trim()}>
              Thêm nhiệm vụ
            </Button>
          </form>

          {wsTasks.length === 0 ? (
            <EmptyState
              compact
              title="Chưa có nhiệm vụ trong kế hoạch"
              description="Thêm nhiệm vụ mới hoặc tạo tự động từ tài liệu nguồn."
            />
          ) : (
            <ul className="divide-y divide-line border-y border-line">
              {wsTasks.map((task) => {
                const doc = documents.find((d) => d.id === task.documentId)
                const isEditing = editingTaskId === task.id
                return (
                  <li
                    key={task.id}
                    className="flex items-center justify-between gap-3 py-2.5"
                  >
                    <div className="flex min-w-0 flex-1 items-center gap-2.5">
                      <input
                        type="checkbox"
                        checked={task.completed}
                        onChange={() => toggleStudyTask(task.id)}
                        aria-label={`Đánh dấu hoàn thành ${task.title}`}
                        className="h-4 w-4 rounded border-line"
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
                                updateStudyTask(task.id, { title: editingTaskTitle.trim() })
                              }
                              setEditingTaskId(null)
                            }}
                          >
                            Lưu
                          </Button>
                        </div>
                      ) : (
                        <div className="min-w-0 flex-1">
                          <p
                            className={`text-sm ${
                              task.completed ? "text-muted line-through" : "text-ink"
                            }`}
                          >
                            {task.title}
                          </p>
                          <p className="text-[11px] text-muted">
                            Hạn: {task.dueDate}
                            {doc ? ` · Nguồn: ${doc.fileName}` : ""}
                          </p>
                        </div>
                      )}
                    </div>

                    <div className="flex shrink-0 items-center gap-1">
                      {!isEditing ? (
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => {
                            setEditingTaskId(task.id)
                            setEditingTaskTitle(task.title)
                          }}
                        >
                          Sửa
                        </Button>
                      ) : null}
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-7 w-7 text-muted hover:text-error"
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
        </TabsContent>
      </Tabs>

      {/* Dialog chỉnh sửa / tạo Ghi chú */}
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

            <FormField label="Notebook">
              <Select
                value={editingNote.notebookId ?? ""}
                onChange={(e) =>
                  setEditingNote({
                    ...editingNote,
                    notebookId: e.target.value || null,
                  })
                }
              >
                <option value="">-- Chưa phân loại --</option>
                {wsNotebooks.map((nb) => (
                  <option key={nb.id} value={nb.id}>
                    {nb.name}
                  </option>
                ))}
              </Select>
            </FormField>

            <FormField label="Nội dung">
              <Textarea
                rows={5}
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
              <Button type="submit">Lưu ghi chú</Button>
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
          <FormField label="Mặt sau (Đáp án / Giải thích)">
            <Textarea
              rows={3}
              value={newCardBack}
              onChange={(e) => setNewCardBack(e.target.value)}
              placeholder="Ví dụ: Reciprocal Rank Fusion — phương pháp gộp bảng xếp hạng."
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
            <Button type="submit" disabled={!branchLabel.trim()}>
              Thêm nhánh
            </Button>
          </div>
        </form>
      </Dialog>

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
