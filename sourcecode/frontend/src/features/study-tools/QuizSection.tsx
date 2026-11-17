import { useEffect, useMemo, useRef, useState } from "react"
import { Link } from "react-router-dom"
import {
  ArrowLeft,
  ArrowRight,
  BookOpen,
  Check,
  CheckCircle2,
  ClipboardList,
  Clock,
  ExternalLink,
  History,
  ListChecks,
  RotateCcw,
  Sparkles,
  Target,
  Trash2,
  X,
  XCircle,
} from "lucide-react"
import { ConfirmDialog } from "@/components/common/NameDialog"
import { Badge, Button, Input, Select } from "@/components/ui"
import {
  deleteStudyArtifactApi,
  fetchStudyArtifactsApi,
  saveStudyArtifactApi,
  updateStudyArtifactApi,
  type StudyArtifactRecord,
} from "@/services/api"
import { generateStudyQuizAsync, type StudySourceContext } from "@/services/study-service"
import { useAppStore } from "@/store/app-store"
import { cn } from "@/utils/cn"
import { formatDateTime, nowIso, relativeTime, uid } from "@/utils/format"
import type { KnowledgeDocument, Quiz, QuizAttempt, QuizQuestion } from "@/types"

const LETTERS = ["A", "B", "C", "D", "E"]
const DIFFICULTY_LABEL: Record<Quiz["difficulty"], string> = {
  easy: "Dễ",
  medium: "Vừa",
  hard: "Khó",
}

function formatDuration(seconds: number): string {
  const safe = Math.max(0, Math.floor(seconds))
  const m = Math.floor(safe / 60)
  const s = safe % 60
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`
}

function mapArtifactToQuiz(record: StudyArtifactRecord): Quiz | null {
  if (record.artifact_type !== "quiz") return null
  const data = (record.data ?? {}) as Record<string, unknown>
  const rawQuestions = Array.isArray(data.questions) ? (data.questions as QuizQuestion[]) : []
  if (rawQuestions.length === 0) return null

  const diffRaw = String(data.difficulty ?? "medium")
  const difficulty: Quiz["difficulty"] =
    diffRaw === "easy" || diffRaw === "hard" ? diffRaw : "medium"
  const attempts = Array.isArray(data.attempts) ? (data.attempts as QuizAttempt[]) : []
  const answers =
    data.answers && typeof data.answers === "object"
      ? (data.answers as Record<string, number>)
      : {}

  return {
    id: record.id,
    workspaceId: record.workspace_id,
    documentId: record.document_id ?? null,
    documentName: typeof data.documentName === "string" ? data.documentName : null,
    focusPrompt: typeof data.focusPrompt === "string" ? data.focusPrompt : undefined,
    title: record.title || "Bài kiểm tra Quiz",
    difficulty,
    questions: rawQuestions,
    answers,
    submitted: Boolean(data.submitted),
    timeLimitMinutes:
      typeof data.timeLimitMinutes === "number" ? data.timeLimitMinutes : null,
    createdAt: record.created_at || nowIso(),
    attempts,
    isMock: Boolean(data.isMock),
  }
}

function buildQuizArtifactPayload(quiz: Quiz) {
  return {
    documentName: quiz.documentName ?? null,
    focusPrompt: quiz.focusPrompt ?? "",
    difficulty: quiz.difficulty,
    questions: quiz.questions,
    answers: quiz.answers,
    submitted: quiz.submitted,
    timeLimitMinutes: quiz.timeLimitMinutes ?? null,
    attempts: quiz.attempts ?? [],
    isMock: Boolean(quiz.isMock),
  }
}

function buildWeakTopicsPrompt(wrongQuestions: QuizQuestion[]): string {
  const snippet = wrongQuestions
    .slice(0, 3)
    .map((q) => q.prompt.replace(/[?？]+$/g, "").trim())
    .filter(Boolean)
    .join("; ")
  return snippet.slice(0, 140)
}

function QuestionCard({
  question,
  index,
  selectedOption,
  submitted,
  documents,
  onSelect,
}: {
  question: QuizQuestion
  index: number
  selectedOption: number | undefined
  submitted: boolean
  documents: KnowledgeDocument[]
  onSelect: (optionIndex: number) => void
}) {
  const isCorrect = selectedOption === question.answerIndex
  const matchedDoc = question.citation?.documentId
    ? documents.find((d) => d.id === question.citation?.documentId)
    : undefined

  const sourceHref = (() => {
    if (!question.citation?.documentId || !matchedDoc || matchedDoc.mock) return null
    const params = new URLSearchParams()
    if (question.citation.pageNumber != null) {
      params.set("page", String(question.citation.pageNumber))
    }
    if (question.citation.chunkIndex != null) {
      params.set("chunk", String(question.citation.chunkIndex))
    }
    const qs = params.toString()
    return `/documents/${question.citation.documentId}${qs ? `?${qs}` : ""}`
  })()

  return (
    <div
      id={`quiz-q-${question.id}`}
      className="rounded-xl border border-[#DCE7E4] bg-white p-5 space-y-3"
    >
      <div className="flex items-start gap-2.5">
        <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-[#F1F6F5] text-xs font-bold text-[#087F73]">
          {index + 1}
        </span>
        <p className="text-sm font-bold text-[#172B29] leading-snug">{question.prompt}</p>
      </div>

      <div className="space-y-2 pt-1">
        {question.options.map((opt, optIdx) => {
          const isChosen = selectedOption === optIdx
          const isRightAnswer = question.answerIndex === optIdx

          let optionStyle = "border-[#DCE7E4] bg-white text-[#172B29] hover:bg-[#F9FCFB]"
          if (submitted) {
            if (isRightAnswer) {
              optionStyle = "border-emerald-500 bg-emerald-50/70 text-emerald-950 font-semibold"
            } else if (isChosen && !isRightAnswer) {
              optionStyle = "border-rose-400 bg-rose-50/70 text-rose-950 line-through"
            } else {
              optionStyle = "border-[#DCE7E4] opacity-60"
            }
          } else if (isChosen) {
            optionStyle = "border-[#087F73] bg-[#F0FDFA] font-semibold text-[#087F73]"
          }

          return (
            <button
              key={`${question.id}-opt-${optIdx}`}
              type="button"
              disabled={submitted}
              onClick={() => onSelect(optIdx)}
              className={cn(
                "flex w-full items-center gap-3 rounded-xl border p-3 text-left text-xs sm:text-[13px] transition-all",
                optionStyle,
              )}
            >
              <span
                className={cn(
                  "flex h-6 w-6 shrink-0 items-center justify-center rounded-lg text-xs font-bold",
                  isChosen ? "bg-[#087F73] text-white" : "bg-[#F1F6F5] text-[#647C79]",
                )}
              >
                {LETTERS[optIdx] ?? optIdx + 1}
              </span>
              <span className="flex-1">{opt}</span>
              {submitted && isRightAnswer ? (
                <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-600" />
              ) : null}
              {submitted && isChosen && !isRightAnswer ? (
                <XCircle className="h-4 w-4 shrink-0 text-rose-500" />
              ) : null}
            </button>
          )
        })}
      </div>

      {submitted ? (
        <div className="space-y-2 pt-1">
          <div
            className={cn(
              "rounded-xl p-3 text-xs leading-relaxed border",
              isCorrect
                ? "bg-emerald-50 text-emerald-900 border-emerald-200"
                : "bg-rose-50 text-rose-900 border-rose-200",
            )}
          >
            <p>
              <strong>
                {isCorrect
                  ? "✓ Chính xác:"
                  : `✕ Chưa chính xác (Đáp án đúng: ${LETTERS[question.answerIndex] ?? question.answerIndex + 1}):`}
              </strong>{" "}
              {question.explanation}
            </p>
          </div>

          {question.citation ? (
            <div className="rounded-xl border border-[#DCE7E4] bg-[#F9FCFB] p-3 text-xs space-y-1.5">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="inline-flex items-center gap-1.5 font-semibold text-[#172B29]">
                  <BookOpen className="h-3.5 w-3.5 text-[#087F73]" />
                  <span>Nguồn đối chiếu: {question.citation.documentName}</span>
                  {question.citation.pageNumber != null ? (
                    <Badge tone="neutral">Trang {question.citation.pageNumber}</Badge>
                  ) : null}
                </span>

                {sourceHref ? (
                  <Link
                    to={sourceHref}
                    className="inline-flex items-center gap-1 font-semibold text-[#087F73] hover:underline"
                  >
                    <span>Mở tài liệu gốc</span>
                    <ExternalLink className="h-3 w-3" />
                  </Link>
                ) : null}
              </div>

              {question.citation.snippet ? (
                <p className="line-clamp-2 italic text-[11.5px] leading-relaxed text-[#647C79]">
                  &ldquo;{question.citation.snippet}&rdquo;
                </p>
              ) : null}
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  )
}

export function QuizSection({
  workspaceId,
  documents,
  selectedDocId,
  onSelectDocId,
  quizzes,
  activeQuizId,
  onSelectQuizId,
  useBackendHistory,
}: {
  workspaceId: string
  documents: KnowledgeDocument[]
  selectedDocId: string
  onSelectDocId: (docId: string) => void
  quizzes: Quiz[]
  activeQuizId: string | null
  onSelectQuizId: (id: string | null) => void
  useBackendHistory: boolean
}) {
  const upsertQuiz = useAppStore((s) => s.upsertQuiz)
  const deleteQuiz = useAppStore((s) => s.deleteQuiz)
  const replaceWorkspaceQuizzes = useAppStore((s) => s.replaceWorkspaceQuizzes)
  const toast = useAppStore((s) => s.toast)

  // Form tạo Quiz
  const [focusPrompt, setFocusPrompt] = useState("")
  const [difficulty, setDifficulty] = useState<"easy" | "medium" | "hard">("medium")
  const [questionCount, setQuestionCount] = useState<number>(10)
  const [timeLimitMinutes, setTimeLimitMinutes] = useState<number>(0)
  const [isGenerating, setIsGenerating] = useState(false)
  const quizAbortRef = useRef<AbortController | null>(null)

  // Danh sách bộ đề
  const [listFilter, setListFilter] = useState<"all" | "todo" | "done">("all")
  const [quizToDelete, setQuizToDelete] = useState<Quiz | null>(null)

  // Chế độ làm bài / xem kết quả
  const [displayMode, setDisplayMode] = useState<"single" | "all">("single")
  const [currentIdx, setCurrentIdx] = useState(0)
  const [reviewFilter, setReviewFilter] = useState<"all" | "wrong">("all")
  const [inspectAttemptId, setInspectAttemptId] = useState<string | null>(null)
  const [showAttemptHistory, setShowAttemptHistory] = useState(false)

  // Timer làm bài
  const [secondsLeft, setSecondsLeft] = useState<number | null>(null)
  const [elapsedSeconds, setElapsedSeconds] = useState(0)

  // Chế độ luyện lại câu sai (không sửa đề gốc)
  const [drillState, setDrillState] = useState<{
    quizId: string
    questions: QuizQuestion[]
    answers: Record<string, number>
    submitted: boolean
  } | null>(null)

  useEffect(() => {
    return () => {
      quizAbortRef.current?.abort()
    }
  }, [])

  // Đồng bộ lịch sử bộ Quiz từ SQLite khi đăng nhập
  useEffect(() => {
    if (!useBackendHistory) return
    let active = true
    fetchStudyArtifactsApi(workspaceId, "quiz")
      .then((res) => {
        if (!active) return
        const mapped = (res.artifacts ?? [])
          .map(mapArtifactToQuiz)
          .filter((item): item is Quiz => item !== null)
        replaceWorkspaceQuizzes(workspaceId, mapped)
      })
      .catch(() => {
        // Giữ nguyên state hiện có nếu mạng tạm lỗi
      })
    return () => {
      active = false
    }
  }, [workspaceId, useBackendHistory, replaceWorkspaceQuizzes])

  const activeQuiz = useMemo(
    () => (activeQuizId ? quizzes.find((q) => q.id === activeQuizId) ?? null : null),
    [quizzes, activeQuizId],
  )

  const filteredQuizzes = useMemo(() => {
    return quizzes.filter((q) => {
      const done = q.submitted || (q.attempts?.length ?? 0) > 0
      if (listFilter === "todo") return !done
      if (listFilter === "done") return done
      return true
    })
  }, [quizzes, listFilter])

  const todoCount = useMemo(
    () => quizzes.filter((q) => !q.submitted && (q.attempts?.length ?? 0) === 0).length,
    [quizzes],
  )
  const doneCount = quizzes.length - todoCount

  const persistUpdateQuiz = async (updated: Quiz) => {
    upsertQuiz(updated)
    if (!useBackendHistory) return
    try {
      await updateStudyArtifactApi(workspaceId, updated.id, {
        title: updated.title,
        data: buildQuizArtifactPayload(updated),
      })
    } catch {
      // Nếu bộ đề được tạo offline/seed chưa tồn tại trong DB, tự lưu mới
      try {
        const res = await saveStudyArtifactApi(workspaceId, {
          document_id: updated.documentId,
          artifact_type: "quiz",
          title: updated.title,
          data: buildQuizArtifactPayload(updated),
        })
        const synced = mapArtifactToQuiz(res.artifact)
        if (synced) {
          deleteQuiz(updated.id)
          upsertQuiz(synced)
          onSelectQuizId(synced.id)
        }
      } catch {
        // Giữ trạng thái local
      }
    }
  }

  const handleSubmitQuiz = async (quiz: Quiz) => {
    if (quiz.submitted) return
    const total = quiz.questions.length
    const wrongQuestionIds = quiz.questions
      .filter((q) => quiz.answers[q.id] !== q.answerIndex)
      .map((q) => q.id)
    const score = total - wrongQuestionIds.length
    const percentage = total > 0 ? Math.round((score / total) * 100) : 0

    const attempt: QuizAttempt = {
      id: uid("att"),
      submittedAt: nowIso(),
      score,
      total,
      percentage,
      durationSeconds: elapsedSeconds,
      answers: { ...quiz.answers },
      wrongQuestionIds,
    }

    const updated: Quiz = {
      ...quiz,
      submitted: true,
      attempts: [attempt, ...(quiz.attempts ?? [])],
    }

    setInspectAttemptId(attempt.id)
    setReviewFilter("all")
    setSecondsLeft(null)
    await persistUpdateQuiz(updated)
    toast({
      title: `Hoàn thành: ${score}/${total} câu đúng (${percentage}%)`,
      tone: percentage >= 70 ? "success" : "info",
    })
  }

  const autoSubmitRef = useRef<() => void>(() => {})
  useEffect(() => {
    autoSubmitRef.current = () => {
      if (activeQuiz && !activeQuiz.submitted) {
        toast({ title: "Hết thời gian làm bài — hệ thống tự động nộp bài", tone: "warning" })
        void handleSubmitQuiz(activeQuiz)
      }
    }
  })

  // Bộ đếm thời gian làm bài
  useEffect(() => {
    if (!activeQuiz || activeQuiz.submitted || drillState) return
    const id = window.setInterval(() => {
      setElapsedSeconds((prev) => prev + 1)
      setSecondsLeft((prev) => {
        if (prev === null) return null
        if (prev <= 1) {
          autoSubmitRef.current()
          return 0
        }
        return prev - 1
      })
    }, 1000)
    return () => window.clearInterval(id)
  }, [activeQuiz, drillState])

  const runGenerateQuiz = async (customFocus?: string) => {
    const usedFocus = customFocus !== undefined ? customFocus : focusPrompt
    quizAbortRef.current?.abort()
    const controller = new AbortController()
    quizAbortRef.current = controller
    setIsGenerating(true)

    const activeDoc = selectedDocId
      ? documents.find((d) => d.id === selectedDocId) ?? null
      : null
    const ctx: StudySourceContext = {
      workspaceId,
      notebook: null,
      document: activeDoc,
      documentsInScope: activeDoc ? [activeDoc] : documents,
    }

    try {
      const generated = await generateStudyQuizAsync(
        ctx,
        difficulty,
        questionCount,
        usedFocus,
        controller.signal,
      )
      if (controller.signal.aborted) return

      const enriched: Quiz = {
        ...generated,
        timeLimitMinutes: timeLimitMinutes > 0 ? timeLimitMinutes : null,
      }

      let savedQuiz = enriched
      if (useBackendHistory) {
        try {
          const res = await saveStudyArtifactApi(workspaceId, {
            document_id: enriched.documentId,
            artifact_type: "quiz",
            title: enriched.title,
            data: buildQuizArtifactPayload(enriched),
          })
          const mapped = mapArtifactToQuiz(res.artifact)
          if (mapped) savedQuiz = mapped
        } catch {
          // Fallback local store
        }
      }

      upsertQuiz(savedQuiz)
      onSelectQuizId(savedQuiz.id)
      setDrillState(null)
      setInspectAttemptId(null)
      setReviewFilter("all")
      setCurrentIdx(0)
      setElapsedSeconds(0)
      setSecondsLeft(
        savedQuiz.timeLimitMinutes && savedQuiz.timeLimitMinutes > 0
          ? savedQuiz.timeLimitMinutes * 60
          : null,
      )

      toast({
        title: savedQuiz.isMock
          ? "Đã tạo bộ Quiz (Mô phỏng)"
          : "Đã tạo bộ Quiz bằng AI thành công",
        description: `${savedQuiz.questions.length} câu hỏi sẵn sàng làm bài.`,
        tone: savedQuiz.isMock ? "info" : "success",
      })
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") return
      const msg = err instanceof Error && err.message ? err.message : "Vui lòng thử lại sau."
      toast({ title: "Không thể tạo Quiz", description: msg, tone: "error" })
    } finally {
      if (quizAbortRef.current === controller) {
        quizAbortRef.current = null
        setIsGenerating(false)
      }
    }
  }

  const handleOpenQuiz = (q: Quiz) => {
    setDrillState(null)
    setInspectAttemptId(q.attempts?.[0]?.id ?? null)
    setReviewFilter("all")
    setCurrentIdx(0)
    setElapsedSeconds(0)
    setShowAttemptHistory(false)
    setSecondsLeft(
      !q.submitted && q.timeLimitMinutes && q.timeLimitMinutes > 0
        ? q.timeLimitMinutes * 60
        : null,
    )
    onSelectQuizId(q.id)
  }

  const handleRetakeQuiz = async (q: Quiz) => {
    const resetQuiz: Quiz = {
      ...q,
      answers: {},
      submitted: false,
    }
    setDrillState(null)
    setInspectAttemptId(null)
    setReviewFilter("all")
    setCurrentIdx(0)
    setElapsedSeconds(0)
    setShowAttemptHistory(false)
    setSecondsLeft(
      q.timeLimitMinutes && q.timeLimitMinutes > 0 ? q.timeLimitMinutes * 60 : null,
    )
    onSelectQuizId(resetQuiz.id)
    await persistUpdateQuiz(resetQuiz)
  }

  const handleConfirmDeleteQuiz = async () => {
    if (!quizToDelete) return
    const target = quizToDelete
    try {
      if (useBackendHistory) {
        try {
          await deleteStudyArtifactApi(workspaceId, target.id)
        } catch {
          // Bỏ qua nếu bản ghi chưa lưu trên server
        }
      }
      deleteQuiz(target.id)
      if (activeQuizId === target.id) {
        onSelectQuizId(null)
        setDrillState(null)
      }
      setQuizToDelete(null)
      toast({ title: "Đã xóa bộ câu hỏi", tone: "info" })
    } catch {
      toast({ title: "Không thể xóa bộ câu hỏi", tone: "error" })
    }
  }

  // ============================================================================
  // CHẾ ĐỘ LUYỆN TẬP CÂU TRẢ LỜI SAI
  // ============================================================================
  if (activeQuiz && drillState && drillState.quizId === activeQuiz.id) {
    const drillScore = drillState.questions.filter(
      (q) => drillState.answers[q.id] === q.answerIndex,
    ).length
    const answeredCount = Object.keys(drillState.answers).length

    return (
      <div className="space-y-5">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[#DCE7E4] pb-4">
          <div className="space-y-1">
            <button
              type="button"
              onClick={() => setDrillState(null)}
              className="inline-flex items-center gap-1 text-xs font-semibold text-[#087F73] hover:underline"
            >
              <ArrowLeft className="h-3.5 w-3.5" />
              <span>Quay lại kết quả đầy đủ</span>
            </button>
            <h2 className="text-lg font-bold text-[#172B29]">
              Ôn tập câu sai · {activeQuiz.title}
            </h2>
            <p className="text-xs text-[#647C79]">
              Luyện tập lại {drillState.questions.length} câu hỏi bạn đã trả lời chưa đúng ở lần trước.
            </p>
          </div>

          <Button
            variant="outline"
            size="sm"
            leftIcon={<RotateCcw className="h-3.5 w-3.5" />}
            onClick={() =>
              setDrillState({ ...drillState, answers: {}, submitted: false })
            }
          >
            Làm lại lượt ôn
          </Button>
        </div>

        {drillState.submitted ? (
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-emerald-200 bg-[#F0FDFA] p-4">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-[#087F73] text-white">
                <Target className="h-5 w-5" />
              </div>
              <div>
                <p className="text-sm font-bold text-[#087F73]">
                  Kết quả ôn tập: {drillScore} / {drillState.questions.length} câu đúng
                </p>
                <p className="text-xs text-[#647C79]">
                  {drillScore === drillState.questions.length
                    ? "Tuyệt vời! Bạn đã khắc phục toàn bộ các câu sai trước đó."
                    : "Tiếp tục xem giải thích và tài liệu gốc để ghi nhớ sâu hơn."}
                </p>
              </div>
            </div>
            <Button
              size="sm"
              className="bg-[#087F73] text-white hover:bg-[#076b61]"
              onClick={() => setDrillState(null)}
            >
              Xong, quay lại kết quả
            </Button>
          </div>
        ) : null}

        <div className="space-y-4">
          {drillState.questions.map((q, idx) => (
            <QuestionCard
              key={q.id}
              question={q}
              index={idx}
              selectedOption={drillState.answers[q.id]}
              submitted={drillState.submitted}
              documents={documents}
              onSelect={(optIdx) =>
                setDrillState({
                  ...drillState,
                  answers: { ...drillState.answers, [q.id]: optIdx },
                })
              }
            />
          ))}
        </div>

        <div className="flex items-center justify-between border-t border-[#DCE7E4] pt-4">
          <Button
            disabled={drillState.submitted}
            className="bg-[#087F73] text-white hover:bg-[#076b61]"
            onClick={() => setDrillState({ ...drillState, submitted: true })}
          >
            Kiểm tra đáp án
          </Button>
          <span className="text-xs text-[#647C79]">
            Đã chọn {answeredCount} / {drillState.questions.length} câu
          </span>
        </div>
      </div>
    )
  }

  // ============================================================================
  // CHẾ ĐỘ LÀM BÀI / XEM KẾT QUẢ BỘ ĐỀ ĐANG CHỌN
  // ============================================================================
  if (activeQuiz) {
    const attempts = activeQuiz.attempts ?? []
    const inspectedAttempt =
      activeQuiz.submitted && inspectAttemptId
        ? attempts.find((a) => a.id === inspectAttemptId) ?? null
        : null
    const effectiveAnswers = inspectedAttempt ? inspectedAttempt.answers : activeQuiz.answers
    const wrongQuestions = activeQuiz.submitted
      ? activeQuiz.questions.filter((q) => effectiveAnswers[q.id] !== q.answerIndex)
      : []
    const correctCount = activeQuiz.questions.length - wrongQuestions.length
    const scorePct =
      activeQuiz.questions.length > 0
        ? Math.round((correctCount / activeQuiz.questions.length) * 100)
        : 0

    const visibleQuestions =
      activeQuiz.submitted && reviewFilter === "wrong"
        ? wrongQuestions
        : activeQuiz.questions

    const safeIdx =
      visibleQuestions.length > 0 ? Math.min(currentIdx, visibleQuestions.length - 1) : 0
    const singleQuestion = visibleQuestions[safeIdx] ?? null
    const answeredCount = Object.keys(activeQuiz.answers).length

    return (
      <div className="space-y-5">
        {/* Header thanh điều khiển bài làm */}
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between border-b border-[#DCE7E4] pb-4">
          <div className="space-y-1">
            <button
              type="button"
              onClick={() => {
                onSelectQuizId(null)
                setSecondsLeft(null)
              }}
              className="inline-flex items-center gap-1 text-xs font-semibold text-[#087F73] hover:underline"
            >
              <ArrowLeft className="h-3.5 w-3.5" />
              <span>Danh sách bộ đề</span>
            </button>
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-lg font-bold text-[#172B29]">{activeQuiz.title}</h2>
              <Badge tone="neutral">{DIFFICULTY_LABEL[activeQuiz.difficulty]}</Badge>
              {activeQuiz.isMock ? <Badge tone="neutral">Mô phỏng</Badge> : null}
            </div>
            <p className="text-xs text-[#647C79]">
              {activeQuiz.questions.length} câu ·{" "}
              {activeQuiz.documentName || "Toàn bộ tài liệu workspace"} ·{" "}
              {attempts.length} lần làm
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            {/* Đồng hồ đếm ngược hoặc thời gian đã làm */}
            {!activeQuiz.submitted ? (
              <span
                className={cn(
                  "inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-semibold",
                  secondsLeft !== null && secondsLeft <= 60
                    ? "border-amber-300 bg-amber-50 text-amber-800"
                    : "border-[#DCE7E4] bg-[#F1F6F5] text-[#172B29]",
                )}
              >
                <Clock className="h-3.5 w-3.5 text-[#087F73]" />
                {secondsLeft !== null
                  ? `Còn ${formatDuration(secondsLeft)}`
                  : formatDuration(elapsedSeconds)}
              </span>
            ) : null}

            {/* Chuyển chế độ Từng câu / Toàn bộ đề */}
            <div className="inline-flex rounded-lg border border-[#DCE7E4] bg-[#F1F6F5] p-0.5 text-xs">
              <button
                type="button"
                onClick={() => setDisplayMode("single")}
                className={cn(
                  "rounded-md px-2.5 py-1 font-medium transition-colors",
                  displayMode === "single"
                    ? "bg-white text-[#087F73] shadow-2xs"
                    : "text-[#647C79] hover:text-[#172B29]",
                )}
              >
                Từng câu
              </button>
              <button
                type="button"
                onClick={() => setDisplayMode("all")}
                className={cn(
                  "rounded-md px-2.5 py-1 font-medium transition-colors",
                  displayMode === "all"
                    ? "bg-white text-[#087F73] shadow-2xs"
                    : "text-[#647C79] hover:text-[#172B29]",
                )}
              >
                Toàn bộ đề
              </button>
            </div>

            {activeQuiz.submitted ? (
              <Button
                variant="outline"
                size="sm"
                leftIcon={<RotateCcw className="h-3.5 w-3.5" />}
                onClick={() => void handleRetakeQuiz(activeQuiz)}
              >
                Làm lại
              </Button>
            ) : null}
          </div>
        </div>

        {/* Banner kết quả & Ôn tập câu sai sau khi nộp bài */}
        {activeQuiz.submitted ? (
          <div className="space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-[#DCE7E4] bg-[#F0FDFA] p-4 text-[#172B29]">
              <div className="flex items-center gap-3">
                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-[#087F73] text-white">
                  <Check className="h-5 w-5" />
                </div>
                <div>
                  <p className="text-sm font-bold text-[#087F73]">
                    Kết quả: {correctCount} / {activeQuiz.questions.length} câu đúng ({scorePct}%)
                  </p>
                  <p className="text-xs text-[#647C79]">
                    {inspectedAttempt
                      ? `Lần làm lúc ${formatDateTime(inspectedAttempt.submittedAt)}${
                          inspectedAttempt.durationSeconds
                            ? ` · Thời gian ${formatDuration(inspectedAttempt.durationSeconds)}`
                            : ""
                        }`
                      : null}
                  </p>
                </div>
              </div>

              <div className="flex flex-wrap items-center gap-2">
                {attempts.length > 0 ? (
                  <Button
                    variant="outline"
                    size="sm"
                    leftIcon={<History className="h-3.5 w-3.5" />}
                    onClick={() => setShowAttemptHistory((v) => !v)}
                  >
                    Lịch sử ({attempts.length})
                  </Button>
                ) : null}
                <Button
                  size="sm"
                  leftIcon={<RotateCcw className="h-3.5 w-3.5" />}
                  className="bg-[#087F73] text-white hover:bg-[#076b61]"
                  onClick={() => void handleRetakeQuiz(activeQuiz)}
                >
                  Làm lại bộ đề
                </Button>
              </div>
            </div>

            {/* Lịch sử các lần làm bài */}
            {showAttemptHistory && attempts.length > 0 ? (
              <div className="rounded-xl border border-[#DCE7E4] bg-white p-4 space-y-2.5">
                <h4 className="text-xs font-bold uppercase tracking-wider text-[#647C79]">
                  Lịch sử các lần làm ({attempts.length})
                </h4>
                <div className="divide-y divide-[#DCE7E4]/70">
                  {attempts.map((att, idx) => {
                    const isInspecting = (inspectedAttempt?.id ?? attempts[0]?.id) === att.id
                    return (
                      <div
                        key={att.id}
                        className="flex flex-wrap items-center justify-between gap-2 py-2 text-xs"
                      >
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="font-semibold text-[#172B29]">
                            Lần {attempts.length - idx}
                          </span>
                          <Badge tone={att.percentage >= 70 ? "success" : "neutral"}>
                            {att.score}/{att.total} điểm ({att.percentage}%)
                          </Badge>
                          {att.durationSeconds != null ? (
                            <span className="text-[#647C79]">
                              · {formatDuration(att.durationSeconds)}
                            </span>
                          ) : null}
                          <span className="text-[#647C79]">
                            · {relativeTime(att.submittedAt)}
                          </span>
                        </div>
                        <Button
                          variant={isInspecting ? "outline" : "ghost"}
                          size="sm"
                          className="h-7 text-xs"
                          onClick={() => {
                            setInspectAttemptId(att.id)
                            setReviewFilter("all")
                            setCurrentIdx(0)
                          }}
                        >
                          {isInspecting ? "Đang xem" : "Xem bài làm này"}
                        </Button>
                      </div>
                    )
                  })}
                </div>
              </div>
            ) : null}

            {/* Tổng hợp và ôn tập câu trả lời sai */}
            {wrongQuestions.length > 0 ? (
              <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between rounded-xl border border-amber-200 bg-amber-50/70 p-4">
                <div className="space-y-1">
                  <div className="flex items-center gap-1.5 text-sm font-bold text-amber-950">
                    <Target className="h-4 w-4 text-amber-700" />
                    <span>Ôn tập {wrongQuestions.length} câu trả lời chưa đúng</span>
                  </div>
                  <p className="text-xs text-amber-900/80">
                    Luyện tập lại ngay những câu sai hoặc để AI tạo bộ Quiz mới tập trung vào các chủ đề còn yếu.
                  </p>
                </div>

                <div className="flex flex-wrap items-center gap-2 shrink-0">
                  <Button
                    variant="outline"
                    size="sm"
                    leftIcon={<ListChecks className="h-3.5 w-3.5" />}
                    className="border-amber-300 bg-white text-amber-950 hover:bg-amber-100/70"
                    onClick={() =>
                      setDrillState({
                        quizId: activeQuiz.id,
                        questions: wrongQuestions,
                        answers: {},
                        submitted: false,
                      })
                    }
                  >
                    Luyện lại {wrongQuestions.length} câu sai
                  </Button>
                  <Button
                    size="sm"
                    loading={isGenerating}
                    leftIcon={<Sparkles className="h-3.5 w-3.5" />}
                    className="bg-[#087F73] text-white hover:bg-[#076b61]"
                    onClick={() => {
                      const weakTopic = buildWeakTopicsPrompt(wrongQuestions)
                      setFocusPrompt(weakTopic)
                      void runGenerateQuiz(weakTopic)
                    }}
                  >
                    Tạo Quiz mới phần còn yếu
                  </Button>
                </div>
              </div>
            ) : null}

            {/* Thanh lọc xem tất cả / chỉ câu sai */}
            {wrongQuestions.length > 0 ? (
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => {
                    setReviewFilter("all")
                    setCurrentIdx(0)
                  }}
                  className={cn(
                    "rounded-full px-3 py-1 text-xs font-medium border transition-colors",
                    reviewFilter === "all"
                      ? "border-[#087F73] bg-[#087F73] text-white"
                      : "border-[#DCE7E4] bg-white text-[#647C79] hover:text-[#172B29]",
                  )}
                >
                  Tất cả câu ({activeQuiz.questions.length})
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setReviewFilter("wrong")
                    setCurrentIdx(0)
                  }}
                  className={cn(
                    "rounded-full px-3 py-1 text-xs font-medium border transition-colors",
                    reviewFilter === "wrong"
                      ? "border-rose-600 bg-rose-600 text-white"
                      : "border-[#DCE7E4] bg-white text-rose-700 hover:border-rose-400",
                  )}
                >
                  Chỉ câu sai ({wrongQuestions.length})
                </button>
              </div>
            ) : null}
          </div>
        ) : null}

        {/* Thanh điều hướng số câu hỏi */}
        {visibleQuestions.length > 1 ? (
          <div className="flex flex-wrap items-center gap-1.5">
            {visibleQuestions.map((q, idx) => {
              const sel = effectiveAnswers[q.id]
              const isAnswered = sel !== undefined
              const isRight = sel === q.answerIndex
              const isCurrent = displayMode === "single" && idx === safeIdx

              let pillStyle = "border-[#DCE7E4] bg-white text-[#647C79]"
              if (activeQuiz.submitted) {
                pillStyle = isRight
                  ? "border-emerald-300 bg-emerald-50 text-emerald-800"
                  : "border-rose-300 bg-rose-50 text-rose-800"
              } else if (isAnswered) {
                pillStyle = "border-[#087F73]/40 bg-[#E6F3F1] text-[#087F73]"
              }

              return (
                <button
                  key={`nav-${q.id}`}
                  type="button"
                  onClick={() => {
                    setCurrentIdx(idx)
                    if (displayMode === "all") {
                      document
                        .getElementById(`quiz-q-${q.id}`)
                        ?.scrollIntoView({ behavior: "smooth", block: "nearest" })
                    }
                  }}
                  className={cn(
                    "h-7 min-w-7 rounded-lg border px-2 text-xs font-semibold transition-all",
                    pillStyle,
                    isCurrent ? "ring-2 ring-[#087F73] ring-offset-1" : "",
                  )}
                >
                  {idx + 1}
                </button>
              )
            })}
          </div>
        ) : null}

        {/* Hiển thị câu hỏi (Từng câu hoặc Toàn bộ đề) */}
        {displayMode === "single" && singleQuestion ? (
          <div className="space-y-4">
            <QuestionCard
              question={singleQuestion}
              index={safeIdx}
              selectedOption={effectiveAnswers[singleQuestion.id]}
              submitted={activeQuiz.submitted}
              documents={documents}
              onSelect={(optIdx) =>
                upsertQuiz({
                  ...activeQuiz,
                  answers: { ...activeQuiz.answers, [singleQuestion.id]: optIdx },
                })
              }
            />

            <div className="flex flex-wrap items-center justify-between gap-2 border-t border-[#DCE7E4] pt-4">
              <div className="flex items-center gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  disabled={safeIdx === 0}
                  leftIcon={<ArrowLeft className="h-3.5 w-3.5" />}
                  onClick={() => setCurrentIdx((i) => Math.max(0, i - 1))}
                >
                  Câu trước
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={safeIdx >= visibleQuestions.length - 1}
                  onClick={() =>
                    setCurrentIdx((i) => Math.min(visibleQuestions.length - 1, i + 1))
                  }
                >
                  <span>Câu tiếp</span>
                  <ArrowRight className="h-3.5 w-3.5" />
                </Button>
              </div>

              <div className="flex items-center gap-3">
                <span className="text-xs text-[#647C79]">
                  {activeQuiz.submitted
                    ? `Câu ${safeIdx + 1} / ${visibleQuestions.length}`
                    : `Đã chọn ${answeredCount} / ${activeQuiz.questions.length} câu`}
                </span>
                {!activeQuiz.submitted ? (
                  <Button
                    className="bg-[#087F73] text-white hover:bg-[#076b61]"
                    onClick={() => void handleSubmitQuiz(activeQuiz)}
                  >
                    Nộp bài
                  </Button>
                ) : null}
              </div>
            </div>
          </div>
        ) : (
          <div className="space-y-4">
            {visibleQuestions.map((q, idx) => (
              <QuestionCard
                key={q.id}
                question={q}
                index={idx}
                selectedOption={effectiveAnswers[q.id]}
                submitted={activeQuiz.submitted}
                documents={documents}
                onSelect={(optIdx) =>
                  upsertQuiz({
                    ...activeQuiz,
                    answers: { ...activeQuiz.answers, [q.id]: optIdx },
                  })
                }
              />
            ))}

            {!activeQuiz.submitted ? (
              <div className="flex flex-wrap items-center justify-between gap-3 border-t border-[#DCE7E4] pt-4">
                <Button
                  className="bg-[#087F73] text-white hover:bg-[#076b61]"
                  onClick={() => void handleSubmitQuiz(activeQuiz)}
                >
                  Nộp bài
                </Button>
                <span className="text-xs text-[#647C79]">
                  Đã trả lời {answeredCount} / {activeQuiz.questions.length} câu
                </span>
              </div>
            ) : null}
          </div>
        )}
      </div>
    )
  }

  // ============================================================================
  // CHẾ ĐỘ MẶC ĐỊNH: FORM TẠO QUIZ NHÓM RÕ RÀNG + "BỘ ĐỀ CỦA TÔI"
  // ============================================================================
  return (
    <div className="space-y-6">
      {/* Tiêu đề mục Trắc nghiệm AI */}
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-bold text-[#172B29]">Trắc nghiệm AI</h2>
          <p className="mt-0.5 text-xs text-[#647C79]">
            Tạo bài kiểm tra từ tài liệu của bạn với đáp án, giải thích và trích dẫn nguồn gốc.
          </p>
        </div>
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-[#F1F6F5] text-[#087F73]">
          <ClipboardList className="h-4.5 w-4.5" />
        </div>
      </div>

      {/* Form tạo bộ câu hỏi mới được nhóm thành khung rõ ràng (1 nút CTA duy nhất) */}
      <div className="rounded-2xl border border-[#DCE7E4] bg-[#FBFDFC] p-5 space-y-4">
        <h3 className="text-sm font-bold text-[#172B29]">Tạo bộ câu hỏi mới</h3>

        <div className="space-y-1.5">
          <label
            htmlFor="quiz-focus-input"
            className="block text-xs font-medium text-[#647C79]"
          >
            Chủ đề (không bắt buộc)
          </label>
          <Input
            id="quiz-focus-input"
            value={focusPrompt}
            disabled={isGenerating}
            onChange={(e) => setFocusPrompt(e.target.value)}
            placeholder="VD: Ngữ pháp JLPT N3, chương 2..."
            className="bg-white"
          />
        </div>

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <div className="space-y-1.5">
            <label
              htmlFor="quiz-doc-select"
              className="block text-xs font-medium text-[#647C79]"
            >
              Tài liệu nguồn
            </label>
            <Select
              id="quiz-doc-select"
              disabled={isGenerating}
              value={selectedDocId}
              onChange={(e) => onSelectDocId(e.target.value)}
              className="bg-white text-xs"
            >
              <option value="">Tất cả tài liệu ({documents.length})</option>
              {documents.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.fileName}
                </option>
              ))}
            </Select>
          </div>

          <div className="space-y-1.5">
            <label
              htmlFor="quiz-difficulty-select"
              className="block text-xs font-medium text-[#647C79]"
            >
              Độ khó
            </label>
            <Select
              id="quiz-difficulty-select"
              disabled={isGenerating}
              value={difficulty}
              onChange={(e) => setDifficulty(e.target.value as typeof difficulty)}
              className="bg-white text-xs"
            >
              <option value="easy">Dễ</option>
              <option value="medium">Vừa</option>
              <option value="hard">Khó</option>
            </Select>
          </div>

          <div className="space-y-1.5">
            <label
              htmlFor="quiz-count-select"
              className="block text-xs font-medium text-[#647C79]"
            >
              Số câu hỏi
            </label>
            <Select
              id="quiz-count-select"
              disabled={isGenerating}
              value={String(questionCount)}
              onChange={(e) => setQuestionCount(Number(e.target.value))}
              className="bg-white text-xs"
            >
              <option value="3">3 câu</option>
              <option value="5">5 câu</option>
              <option value="10">10 câu</option>
              <option value="15">15 câu</option>
              <option value="20">20 câu</option>
            </Select>
          </div>

          <div className="space-y-1.5">
            <label
              htmlFor="quiz-timer-select"
              className="block text-xs font-medium text-[#647C79]"
            >
              Giới hạn thời gian
            </label>
            <Select
              id="quiz-timer-select"
              disabled={isGenerating}
              value={String(timeLimitMinutes)}
              onChange={(e) => setTimeLimitMinutes(Number(e.target.value))}
              className="bg-white text-xs"
            >
              <option value="0">Không giới hạn</option>
              <option value="5">5 phút</option>
              <option value="10">10 phút</option>
              <option value="15">15 phút</option>
              <option value="30">30 phút</option>
            </Select>
          </div>
        </div>

        <div className="flex items-center justify-end gap-2 pt-1">
          {isGenerating ? (
            <Button
              type="button"
              variant="outline"
              size="sm"
              leftIcon={<X className="h-3.5 w-3.5" />}
              onClick={() => {
                quizAbortRef.current?.abort()
                quizAbortRef.current = null
                setIsGenerating(false)
                toast({ title: "Đã hủy tạo Quiz AI", tone: "info" })
              }}
            >
              Hủy
            </Button>
          ) : null}
          <Button
            size="sm"
            leftIcon={<Sparkles className="h-3.5 w-3.5" />}
            loading={isGenerating}
            onClick={() => void runGenerateQuiz()}
            className="bg-[#087F73] hover:bg-[#076b61] text-white"
          >
            {isGenerating ? "Đang tạo Quiz..." : "Tạo Quiz AI"}
          </Button>
        </div>
      </div>

      {/* Danh sách bộ đề đã tạo & lịch sử làm bài */}
      <div className="space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 className="text-sm font-bold text-[#172B29]">
            Bộ đề của tôi ({quizzes.length})
          </h3>

          <div className="inline-flex rounded-full border border-[#DCE7E4] bg-white p-0.5 text-xs">
            <button
              type="button"
              onClick={() => setListFilter("all")}
              className={cn(
                "rounded-full px-3 py-1 font-medium transition-colors",
                listFilter === "all"
                  ? "bg-[#172B29] text-white"
                  : "text-[#647C79] hover:text-[#172B29]",
              )}
            >
              Tất cả ({quizzes.length})
            </button>
            <button
              type="button"
              onClick={() => setListFilter("todo")}
              className={cn(
                "rounded-full px-3 py-1 font-medium transition-colors",
                listFilter === "todo"
                  ? "bg-[#172B29] text-white"
                  : "text-[#647C79] hover:text-[#172B29]",
              )}
            >
              Chưa làm ({todoCount})
            </button>
            <button
              type="button"
              onClick={() => setListFilter("done")}
              className={cn(
                "rounded-full px-3 py-1 font-medium transition-colors",
                listFilter === "done"
                  ? "bg-[#172B29] text-white"
                  : "text-[#647C79] hover:text-[#172B29]",
              )}
            >
              Đã làm ({doneCount})
            </button>
          </div>
        </div>

        {quizzes.length === 0 ? (
          <p className="rounded-xl border border-dashed border-[#DCE7E4] bg-[#F9FCFB] px-4 py-5 text-center text-xs text-[#647C79]">
            Chưa có bộ đề nào trong workspace này. Hãy thiết lập ở khung phía trên và bấm{" "}
            <strong className="text-[#172B29]">Tạo Quiz AI</strong> để bắt đầu.
          </p>
        ) : filteredQuizzes.length === 0 ? (
          <p className="rounded-xl border border-dashed border-[#DCE7E4] bg-[#F9FCFB] px-4 py-5 text-center text-xs text-[#647C79]">
            Không có bộ đề nào ở trạng thái này.
          </p>
        ) : (
          <div className="space-y-3">
            {filteredQuizzes.map((q) => {
              const attempts = q.attempts ?? []
              const latestAttempt = attempts[0] ?? null
              const correctFallback = q.questions.filter(
                (item) => q.answers[item.id] === item.answerIndex,
              ).length
              const hasScore = q.submitted || latestAttempt !== null
              const displayScore = latestAttempt ? latestAttempt.score : correctFallback
              const displayTotal = latestAttempt ? latestAttempt.total : q.questions.length

              return (
                <div
                  key={q.id}
                  className="rounded-2xl border border-[#DCE7E4] bg-white p-4 transition-all hover:border-[#087F73]/40 hover:shadow-xs space-y-3"
                >
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <div className="min-w-0 space-y-1">
                      <h4 className="text-sm font-bold text-[#172B29]">{q.title}</h4>
                      <p className="text-xs text-[#647C79]">
                        {q.questions.length} câu · Độ khó {DIFFICULTY_LABEL[q.difficulty].toLowerCase()}{" "}
                        · {q.documentName || "Toàn bộ workspace"}
                        {q.timeLimitMinutes ? ` · ${q.timeLimitMinutes} phút` : ""}
                        {attempts.length > 0 ? ` · ${attempts.length} lần làm` : ""}
                      </p>
                    </div>

                    <div className="flex flex-col items-end gap-1 shrink-0">
                      <Badge tone={hasScore ? "success" : "neutral"}>
                        {hasScore ? "Đã làm" : "Chưa làm"}
                      </Badge>
                      {hasScore ? (
                        <span className="text-xs font-bold text-[#087F73]">
                          {displayScore}/{displayTotal} điểm
                        </span>
                      ) : null}
                    </div>
                  </div>

                  <div className="flex flex-wrap items-center justify-between gap-2 pt-1">
                    <span className="text-[11px] text-[#647C79]">
                      {q.createdAt ? `Tạo ${relativeTime(q.createdAt)}` : "Bộ đề có sẵn"}
                    </span>

                    <div className="flex flex-wrap items-center gap-1.5">
                      <Button
                        type="button"
                        variant="ghost"
                        size="icon"
                        className="h-8 w-8 text-[#647C79] hover:text-red-600"
                        onClick={() => setQuizToDelete(q)}
                        aria-label={`Xóa bộ đề ${q.title}`}
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>

                      {hasScore ? (
                        <>
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => handleOpenQuiz(q)}
                          >
                            Xem kết quả
                          </Button>
                          <Button
                            variant="outline"
                            size="sm"
                            leftIcon={<RotateCcw className="h-3.5 w-3.5" />}
                            onClick={() => void handleRetakeQuiz(q)}
                          >
                            Làm lại
                          </Button>
                        </>
                      ) : (
                        <Button
                          size="sm"
                          onClick={() => handleOpenQuiz(q)}
                          className="bg-[#087F73] text-white hover:bg-[#076b61]"
                        >
                          <span>Làm bài</span>
                          <ArrowRight className="h-3.5 w-3.5" />
                        </Button>
                      )}
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>

      <ConfirmDialog
        open={Boolean(quizToDelete)}
        title="Xóa bộ câu hỏi?"
        description={`Bạn có chắc muốn xóa "${quizToDelete?.title ?? ""}" cùng lịch sử làm bài?`}
        onClose={() => setQuizToDelete(null)}
        onConfirm={() => void handleConfirmDeleteQuiz()}
      />
    </div>
  )
}
