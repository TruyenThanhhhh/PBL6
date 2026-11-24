import { useEffect, useMemo, useRef, useState, type ReactNode } from "react"
import { useNavigate, useParams } from "react-router-dom"
import Markdown from "react-markdown"
import remarkGfm from "remark-gfm"
import {
  ArrowLeft,
  Check,
  ChevronDown,
  ChevronRight,
  Copy,
  ExternalLink,
  FileText,
  MoreHorizontal,
  Pencil,
  Plus,
  Search,
  Telescope,
  Trash2,
} from "lucide-react"
import { ExportFormatMenu } from "@/components/common/ExportFormatMenu"
import { InlineEdit } from "@/components/common/InlineEdit"
import { ConfirmDialog, NameDialog } from "@/components/common/NameDialog"
import { PageHeader } from "@/components/common/PageHeader"
import {
  Badge,
  Button,
  DropdownMenu,
  DropdownMenuItem,
  DropdownMenuSeparator,
  EmptyState,
  FormField,
  Input,
  Select,
  Textarea,
} from "@/components/ui"
import { ModeSelector } from "@/features/chat/ModeSelector"
import {
  deleteResearchProjectApi,
  fetchResearchProjectsApi,
  streamResearchProjectApi,
  updateResearchProjectApi,
} from "@/services/api"
import { getAuthToken } from "@/services/auth-service"
import {
  buildSimulatedResearchReport,
  REPORT_SECTIONS,
  RESEARCH_PIPELINE_STEPS,
} from "@/services/research-service"
import { useAppStore } from "@/store/app-store"
import { nowIso, relativeTime, uid } from "@/utils/format"
import type { AIMode, Citation, ResearchProject } from "@/types"

function sectionIdFromHeading(text: string): string | undefined {
  const lower = text.toLowerCase()
  if (lower.includes("executive") || lower.includes("tóm tắt điều hành")) {
    return "sec-executive-summary"
  }
  if (lower.includes("research question") || lower.includes("câu hỏi nghiên cứu")) {
    return "sec-research-question"
  }
  if (lower.includes("key findings") || lower.includes("phát hiện chính")) {
    return "sec-key-findings"
  }
  if (lower.includes("comparison") || lower.includes("so sánh")) {
    return "sec-comparison"
  }
  if (lower.includes("contradiction") || lower.includes("mâu thuẫn")) {
    return "sec-contradictions"
  }
  if (lower.includes("gap")) {
    return "sec-research-gaps"
  }
  if (lower.includes("conclusion") || lower.includes("kết luận")) {
    return "sec-conclusion"
  }
  if (lower.includes("reference") || lower.includes("tham khảo")) {
    return "sec-references"
  }
  return undefined
}

function renderReportTextWithCitations(
  children: ReactNode,
  projectCitations: Citation[] | undefined,
  projectDocs: Array<{ id: string; fileName: string }>,
  onOpenLocal: (docId: string, refId: number, page?: number | null) => void,
): ReactNode {
  const items = Array.isArray(children) ? children : [children]
  return items.map((child, idx) => {
    if (typeof child !== "string") return child
    const parts = child.split(/(\[\d+\])/)
    return parts.map((part, pIdx) => {
      const m = part.match(/^\[(\d+)\]$/)
      if (!m) return <span key={`${idx}-${pIdx}`}>{part}</span>
      const refNum = Number(m[1])
      const cite = projectCitations?.find((c) => c.refId === refNum) ?? projectCitations?.[refNum - 1]
      if (cite?.url && cite.sourceKind === "web") {
        return (
          <a
            key={`${idx}-${pIdx}`}
            href={cite.url}
            target="_blank"
            rel="noopener noreferrer"
            title={`Mở nguồn web [${refNum}]: ${cite.documentName}`}
            className="citation-chip"
          >
            {refNum}
          </a>
        )
      }
      const docId = cite?.documentId ?? (projectDocs[refNum - 1] ?? projectDocs[0])?.id
      const docName = cite?.documentName ?? (projectDocs[refNum - 1] ?? projectDocs[0])?.fileName
      if (!docId) {
        return (
          <span key={`${idx}-${pIdx}`} className="citation-chip">
            {refNum}
          </span>
        )
      }
      return (
        <button
          key={`${idx}-${pIdx}`}
          type="button"
          title={`Mở nguồn [${refNum}]: ${docName ?? "Tài liệu"}`}
          onClick={() => onOpenLocal(docId, refNum, cite?.pageNumber)}
          className="citation-chip"
        >
          {refNum}
        </button>
      )
    })
  })
}

export function ResearchPage() {
  const { projectId } = useParams()
  const navigate = useNavigate()

  const projects = useAppStore((s) => s.researchProjects)
  const workspaces = useAppStore((s) => s.workspaces)
  const notebooks = useAppStore((s) => s.notebooks)
  const documents = useAppStore((s) => s.documents)
  const current = useAppStore((s) => s.currentWorkspaceId)
  const status = useAppStore((s) => s.status)

  const upsert = useAppStore((s) => s.upsertResearch)
  const renameResearch = useAppStore((s) => s.renameResearch)
  const deleteResearch = useAppStore((s) => s.deleteResearch)
  const replaceResearch = useAppStore((s) => s.replaceResearchFromBackend)
  const toast = useAppStore((s) => s.toast)

  const selected = projects.find((p) => p.id === projectId) ?? null
  const abortRef = useRef<AbortController | null>(null)

  // Danh sách dự án & tìm kiếm
  const [searchQuery, setSearchQuery] = useState("")
  const [renameTarget, setRenameTarget] = useState<ResearchProject | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<ResearchProject | null>(null)

  // Form tạo nghiên cứu mới
  const [createExpanded, setCreateExpanded] = useState(false)
  const [advancedOpen, setAdvancedOpen] = useState(false)
  const [question, setQuestion] = useState("")
  const [title, setTitle] = useState("")
  const [sourceWsId, setSourceWsId] = useState<string>(current || workspaces[0]?.id || "ws_research")
  const [sourceNbId, setSourceNbId] = useState<string>("")
  const [selectedDocIds, setSelectedDocIds] = useState<string[]>([])
  const [allowWeb, setAllowWeb] = useState(false)
  const [mode, setMode] = useState<AIMode>("local")
  const [running, setRunning] = useState(false)
  const [liveStepDetail, setLiveStepDetail] = useState("")

  useEffect(() => {
    if (current && !workspaces.some((w) => w.id === sourceWsId)) {
      setSourceWsId(current)
    }
  }, [current, sourceWsId, workspaces])

  useEffect(() => {
    const wsId = current || sourceWsId
    if (!status.backendOnline || !getAuthToken() || !wsId) return
    fetchResearchProjectsApi(wsId)
      .then((rows) => replaceResearch(wsId, rows))
      .catch(() => {})
  }, [current, sourceWsId, status.backendOnline, replaceResearch])

  useEffect(() => {
    return () => {
      abortRef.current?.abort()
    }
  }, [])

  // Trạng thái trên trang chi tiết báo cáo
  const [editingReport, setEditingReport] = useState(false)
  const [reportDraft, setReportDraft] = useState("")
  const [copied, setCopied] = useState(false)

  const availableNotebooks = useMemo(
    () => notebooks.filter((n) => n.workspaceId === sourceWsId),
    [notebooks, sourceWsId],
  )

  const availableDocs = useMemo(() => {
    const wsDocs = documents.filter((d) => d.workspaceId === sourceWsId)
    if (!sourceNbId) return wsDocs
    return wsDocs.filter((d) => d.notebookId === sourceNbId)
  }, [documents, sourceWsId, sourceNbId])

  const filteredProjects = useMemo(() => {
    const kw = searchQuery.trim().toLowerCase()
    if (!kw) return projects
    return projects.filter(
      (p) =>
        p.title.toLowerCase().includes(kw) || p.question.toLowerCase().includes(kw),
    )
  }, [projects, searchQuery])

  const toggleDocSelection = (docId: string) => {
    setSelectedDocIds((prev) =>
      prev.includes(docId) ? prev.filter((id) => id !== docId) : [...prev, docId],
    )
  }

  const handleRunResearch = async (existingProject?: ResearchProject) => {
    const qText = existingProject ? existingProject.question : question.trim()
    if (!qText || running) return

    const useBackend = status.backendOnline && Boolean(getAuthToken())
    const docIdsToUse = existingProject
      ? existingProject.documentIds
      : selectedDocIds.length > 0
        ? selectedDocIds
        : availableDocs.map((d) => d.id)

    const initialProject: ResearchProject = existingProject
      ? {
          ...existingProject,
          status: "running",
          step: 1,
          report: "",
          isMock: !useBackend,
          updatedAt: nowIso(),
        }
      : {
          id: uid("rs"),
          workspaceId: sourceWsId,
          notebookId: sourceNbId || null,
          title: title.trim() || qText.slice(0, 64),
          question: qText,
          documentIds: docIdsToUse,
          allowWeb,
          mode,
          status: "running",
          step: 1,
          report: "",
          citations: [],
          isMock: !useBackend,
          createdAt: nowIso(),
          updatedAt: nowIso(),
        }

    setRunning(true)
    setLiveStepDetail("Đang khởi tạo pipeline nghiên cứu...")
    upsert(initialProject)
    navigate(`/research/${initialProject.id}`)

    if (useBackend) {
      abortRef.current?.abort()
      const controller = new AbortController()
      abortRef.current = controller
      let workingProject: ResearchProject = { ...initialProject }
      let accumulatedReport = ""

      try {
        const finalProject = await streamResearchProjectApi(
          workingProject.workspaceId,
          {
            project_id: existingProject ? existingProject.id : undefined,
            notebook_id: workingProject.notebookId,
            title: workingProject.title,
            question: workingProject.question,
            document_ids: workingProject.documentIds,
            allow_web: workingProject.allowWeb,
            mode: workingProject.mode,
          },
          {
            onMeta: (serverProj) => {
              const oldId = workingProject.id
              workingProject = { ...serverProj, status: "running", step: 1, report: "" }
              upsert(workingProject)
              if (oldId !== serverProj.id) {
                deleteResearch(oldId)
                navigate(`/research/${serverProj.id}`, { replace: true })
              }
            },
            onStep: (step, label, detail) => {
              setLiveStepDetail(detail || label)
              workingProject = { ...workingProject, status: "running", step, updatedAt: nowIso() }
              upsert(workingProject)
            },
            onCitations: (citations) => {
              workingProject = { ...workingProject, citations }
              upsert(workingProject)
            },
            onDelta: (deltaText) => {
              accumulatedReport += deltaText
              workingProject = { ...workingProject, report: accumulatedReport, updatedAt: nowIso() }
              upsert(workingProject)
            },
            onDone: (completedProj) => {
              workingProject = completedProj
              upsert(completedProj)
            },
          },
          controller.signal,
        )

        if (finalProject) {
          upsert(finalProject)
        }
        setRunning(false)
        setLiveStepDetail("")
        setQuestion("")
        setTitle("")
        setCreateExpanded(false)
        toast({
          title: "Đã hoàn thành báo cáo nghiên cứu AI",
          description: workingProject.title,
          tone: "success",
        })
        return
      } catch (err) {
        if (err instanceof DOMException && err.name === "AbortError") {
          setRunning(false)
          setLiveStepDetail("")
          return
        }
        const msg = err instanceof Error ? err.message : "Không thể chạy pipeline nghiên cứu từ Backend."
        upsert({ ...workingProject, status: "completed", isMock: true })
        setRunning(false)
        setLiveStepDetail("")
        toast({
          title: "Nghiên cứu sâu gặp lỗi",
          description: msg,
          tone: "error",
        })
        return
      }
    }

    for (let step = 1; step <= RESEARCH_PIPELINE_STEPS.length; step += 1) {
      await new Promise((r) => setTimeout(r, 320))
      upsert({
        ...initialProject,
        status: "running",
        step,
        updatedAt: nowIso(),
      })
    }

    const chosenDocs = documents.filter((d) => docIdsToUse.includes(d.id))
    const generatedReport = buildSimulatedResearchReport({
      question: initialProject.question,
      selectedDocs: chosenDocs,
      allowWeb: initialProject.allowWeb,
      mode: initialProject.mode,
    })

    const completed: ResearchProject = {
      ...initialProject,
      status: "completed",
      step: RESEARCH_PIPELINE_STEPS.length,
      report: generatedReport,
      isMock: true,
      updatedAt: nowIso(),
    }

    upsert(completed)
    setRunning(false)
    setLiveStepDetail("")
    setQuestion("")
    setTitle("")
    setCreateExpanded(false)
    toast({
      title: "Đã hoàn thành báo cáo nghiên cứu (Mô phỏng)",
      description: completed.title,
      tone: "info",
    })
  }

  const handleRenameProject = async (project: ResearchProject, nextTitle: string) => {
    renameResearch(project.id, nextTitle)
    if (status.backendOnline && getAuthToken() && !project.isMock) {
      try {
        const updated = await updateResearchProjectApi(project.id, { title: nextTitle })
        upsert(updated)
      } catch {
        // giữ tên cục bộ nếu sync lỗi tạm thời
      }
    }
    toast({ title: "Đã đổi tên dự án", tone: "success" })
  }

  const handleSaveEditedReport = async (project: ResearchProject, nextReport: string) => {
    upsert({ ...project, report: nextReport, updatedAt: nowIso() })
    setEditingReport(false)
    if (status.backendOnline && getAuthToken() && !project.isMock) {
      try {
        const updated = await updateResearchProjectApi(project.id, { report: nextReport })
        upsert(updated)
      } catch {
        toast({ title: "Đã lưu cục bộ (chưa đồng bộ được server)", tone: "warning" })
        return
      }
    }
    toast({ title: "Đã lưu nội dung báo cáo", tone: "success" })
  }

  const handleDeleteProject = async (project: ResearchProject, goBack: boolean) => {
    if (status.backendOnline && getAuthToken() && !project.isMock) {
      try {
        await deleteResearchProjectApi(project.id)
      } catch {
        // vẫn xóa state cục bộ
      }
    }
    deleteResearch(project.id)
    setDeleteTarget(null)
    toast({ title: "Đã xóa dự án nghiên cứu", tone: "info" })
    if (goBack) navigate("/research")
  }

  const handleCopyReport = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 1800)
      toast({ title: "Đã sao chép báo cáo vào bộ nhớ tạm", tone: "success" })
    } catch {
      toast({ title: "Không thể sao chép tự động", tone: "warning" })
    }
  }

  const scrollToSection = (sectionId: string) => {
    const el = document.getElementById(sectionId)
    if (el) {
      el.scrollIntoView({ behavior: "smooth", block: "start" })
    }
  }

  // ============================================================================
  // CHI TIẾT DỰ ÁN & BÁO CÁO NGHIÊN CỨU
  // ============================================================================
  if (selected) {
    const projectDocs = documents.filter((d) => selected.documentIds.includes(d.id))
    const ws = workspaces.find((w) => w.id === selected.workspaceId)

    return (
      <div className="mx-auto max-w-5xl px-4 py-6 md:px-8">
        {/* Thanh điều hướng quay lại */}
        <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
          <Button
            variant="ghost"
            size="sm"
            leftIcon={<ArrowLeft className="h-3.5 w-3.5" />}
            onClick={() => navigate("/research")}
          >
            Tất cả dự án nghiên cứu
          </Button>

          <div className="flex flex-wrap items-center gap-1.5">
            <Button
              variant="ghost"
              size="sm"
              leftIcon={
                copied ? (
                  <Check className="h-3.5 w-3.5 text-success" />
                ) : (
                  <Copy className="h-3.5 w-3.5" />
                )
              }
              onClick={() => void handleCopyReport(selected.report)}
            >
              {copied ? "Đã chép" : "Sao chép"}
            </Button>
            <ExportFormatMenu
              title={selected.title}
              content={selected.report}
              label="Xuất file"
            />
            <Button
              variant="outline"
              size="sm"
              leftIcon={<Pencil className="h-3.5 w-3.5" />}
              onClick={() => {
                setReportDraft(selected.report)
                setEditingReport((v) => !v)
              }}
            >
              {editingReport ? "Đóng chỉnh sửa" : "Sửa báo cáo"}
            </Button>
            <DropdownMenu
              align="end"
              trigger={
                <Button variant="ghost" size="icon" className="h-8 w-8" aria-label="Tùy chọn dự án">
                  <MoreHorizontal className="h-4 w-4" />
                </Button>
              }
            >
              <DropdownMenuItem
                icon={<Pencil className="h-3.5 w-3.5" />}
                onClick={() => setRenameTarget(selected)}
              >
                Đổi tên dự án
              </DropdownMenuItem>
              <DropdownMenuItem
                onClick={() => void handleRunResearch(selected)}
              >
                Chạy lại pipeline tổng hợp
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem
                tone="danger"
                icon={<Trash2 className="h-3.5 w-3.5" />}
                onClick={() => setDeleteTarget(selected)}
              >
                Xóa dự án nghiên cứu
              </DropdownMenuItem>
            </DropdownMenu>
          </div>
        </div>

        {/* Tiêu đề & Câu hỏi nghiên cứu */}
        <div className="mb-5 border-b border-line pb-4">
          <div className="flex flex-wrap items-center gap-2">
            <div className="min-w-0 flex-1">
              <InlineEdit
                value={selected.title}
                ariaLabel="Tên dự án nghiên cứu"
                validate={(next) => (!next.trim() ? "Tên không được để trống." : null)}
                onSave={(next) => {
                  void handleRenameProject(selected, next)
                }}
                className="text-2xl font-semibold tracking-tight text-ink"
                inputClassName="text-xl font-semibold"
              />
            </div>
            <Badge tone="neutral">
              {selected.status === "completed" ? "Hoàn thành" : "Đang tổng hợp"}
            </Badge>
            {selected.isMock ? (
              <Badge tone="warning">Báo cáo mô phỏng</Badge>
            ) : (
              <Badge tone="success">Báo cáo AI thực tế</Badge>
            )}
          </div>

          <p className="mt-1.5 text-sm text-muted">
            <strong className="font-medium text-ink">Câu hỏi:</strong> {selected.question}
          </p>

          <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted">
            <span>Workspace: {ws?.name ?? "—"}</span>
            <span>·</span>
            <span>Chế độ: {selected.mode.toUpperCase()}</span>
            <span>·</span>
            <span>Nguồn: {projectDocs.length} tài liệu</span>
            <span>·</span>
            <span>Cập nhật {relativeTime(selected.updatedAt)}</span>
          </div>
        </div>

        {/* Thanh tiến trình Research Pipeline 5 bước */}
        <section
          aria-label="Tiến trình nghiên cứu 5 bước"
          className="mb-6 rounded-lg border border-line bg-bg-secondary/40 p-3.5"
        >
          <div className="mb-2 flex items-center justify-between text-xs">
            <span className="font-semibold text-ink">Pipeline nghiên cứu (5 bước)</span>
            <span className="text-muted">
              {selected.status === "running" && liveStepDetail
                ? liveStepDetail
                : selected.isMock
                  ? "Tiến trình mô phỏng trên giao diện · Chưa kết nối Backend"
                  : "Pipeline RAG + LLM đa nguồn thực tế từ Backend"}
            </span>
          </div>
          <ol className="grid gap-2 sm:grid-cols-5">
            {RESEARCH_PIPELINE_STEPS.map((st) => {
              const done = selected.step >= st.step && selected.status === "completed"
              const currentStep = selected.status === "running" && selected.step === st.step
              return (
                <li
                  key={st.step}
                  title={st.description}
                  className={`rounded-md border px-2.5 py-2 text-xs ${
                    done
                      ? "border-success/30 bg-success-soft/40 text-ink"
                      : currentStep
                        ? "border-warning/40 bg-warning-soft/50 font-medium text-ink"
                        : "border-line bg-bg text-muted"
                  }`}
                >
                  <p className="font-medium">
                    {st.step}. {st.label}
                  </p>
                </li>
              )
            })}
          </ol>
        </section>

        {/* Bố cục 2 cột: Báo cáo học thuật & Mục lục điều hướng */}
        <div className="flex flex-col gap-8 lg:flex-row">
          <div className="min-w-0 flex-1">
            {editingReport ? (
              <div className="space-y-3">
                <Textarea
                  rows={18}
                  value={reportDraft}
                  onChange={(e) => setReportDraft(e.target.value)}
                  className="font-mono text-xs leading-6"
                />
                <div className="flex justify-end gap-2">
                  <Button variant="outline" size="sm" onClick={() => setEditingReport(false)}>
                    Hủy
                  </Button>
                  <Button
                    size="sm"
                    onClick={() => void handleSaveEditedReport(selected, reportDraft)}
                  >
                    Lưu báo cáo
                  </Button>
                </div>
              </div>
            ) : (
              <article className="markdown-body max-w-3xl text-[14px] leading-7 text-ink">
                <Markdown
                  remarkPlugins={[remarkGfm]}
                  components={{
                    h2({ children }) {
                      const text = String(children ?? "")
                      const secId = sectionIdFromHeading(text)
                      return (
                        <h2 id={secId} className="scroll-mt-16 border-b border-line pb-1.5 pt-2">
                          {children}
                        </h2>
                      )
                    },
                    p({ children }) {
                      return (
                        <p>
                          {renderReportTextWithCitations(
                            children,
                            selected.citations,
                            projectDocs,
                            (docId, refId, page) =>
                              navigate(`/documents/${docId}?${page ? `page=${page}&` : ""}cite=${refId}`),
                          )}
                        </p>
                      )
                    },
                    li({ children }) {
                      return (
                        <li>
                          {renderReportTextWithCitations(
                            children,
                            selected.citations,
                            projectDocs,
                            (docId, refId, page) =>
                              navigate(`/documents/${docId}?${page ? `page=${page}&` : ""}cite=${refId}`),
                          )}
                        </li>
                      )
                    },
                  }}
                >
                  {selected.report}
                </Markdown>
              </article>
            )}
          </div>

          {/* Cột phải: Mục lục (Table of Contents) & Nguồn tài liệu liên kết */}
          <aside className="w-full shrink-0 border-t border-line pt-4 lg:w-64 lg:border-l lg:border-t-0 lg:pl-6 lg:pt-0">
            <div className="sticky top-4 space-y-6">
              <div>
                <p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-muted">
                  Mục lục báo cáo
                </p>
                <nav aria-label="Mục lục báo cáo" className="space-y-0.5">
                  {REPORT_SECTIONS.map((sec) => (
                    <button
                      key={sec.id}
                      type="button"
                      onClick={() => scrollToSection(sec.id)}
                      className="block w-full truncate rounded-md px-2 py-1 text-left text-xs text-muted transition-colors hover:bg-bg-hover hover:text-ink"
                    >
                      {sec.title}
                    </button>
                  ))}
                </nav>
              </div>

              <div>
                <p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-muted">
                  Nguồn tham chiếu ({selected.citations?.length || projectDocs.length})
                </p>
                {selected.citations && selected.citations.length > 0 ? (
                  <ul className="space-y-1.5">
                    {selected.citations.map((cite) =>
                      cite.sourceKind === "web" && cite.url ? (
                        <li key={`cite-${cite.refId}`}>
                          <a
                            href={cite.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="flex w-full items-start gap-2 rounded-md border border-line bg-bg px-2.5 py-1.5 text-left text-xs transition-colors hover:bg-bg-hover"
                          >
                            <span className="font-semibold text-ink">[{cite.refId}]</span>
                            <span className="min-w-0 flex-1 truncate text-ink">{cite.documentName}</span>
                            <ExternalLink className="mt-0.5 h-3 w-3 shrink-0 text-muted" />
                          </a>
                        </li>
                      ) : (
                        <li key={`cite-${cite.refId}`}>
                          <button
                            type="button"
                            onClick={() =>
                              cite.documentId &&
                              navigate(
                                `/documents/${cite.documentId}?${cite.pageNumber ? `page=${cite.pageNumber}&` : ""}cite=${cite.refId}`,
                              )
                            }
                            className="flex w-full items-start gap-2 rounded-md border border-line bg-bg px-2.5 py-1.5 text-left text-xs transition-colors hover:bg-bg-hover"
                          >
                            <span className="font-semibold text-ink">[{cite.refId}]</span>
                            <div className="min-w-0 flex-1">
                              <p className="truncate text-ink">{cite.documentName}</p>
                              {cite.pageLabel ? (
                                <p className="text-[10.5px] text-muted">{cite.pageLabel}</p>
                              ) : null}
                            </div>
                          </button>
                        </li>
                      ),
                    )}
                  </ul>
                ) : projectDocs.length === 0 ? (
                  <p className="text-xs text-muted">Chưa gắn tài liệu cụ thể.</p>
                ) : (
                  <ul className="space-y-1.5">
                    {projectDocs.map((doc, idx) => (
                      <li key={doc.id}>
                        <button
                          type="button"
                          onClick={() => navigate(`/documents/${doc.id}?cite=${idx + 1}`)}
                          className="flex w-full items-start gap-2 rounded-md border border-line bg-bg px-2.5 py-1.5 text-left text-xs transition-colors hover:bg-bg-hover"
                        >
                          <span className="font-semibold text-ink">[{idx + 1}]</span>
                          <span className="truncate text-ink">{doc.fileName}</span>
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </div>
          </aside>
        </div>

        <NameDialog
          open={Boolean(renameTarget)}
          title="Đổi tên dự án nghiên cứu"
          initialName={renameTarget?.title ?? ""}
          onClose={() => setRenameTarget(null)}
          onSubmit={(name) => {
            if (renameTarget) {
              void handleRenameProject(renameTarget, name)
            }
          }}
        />

        <ConfirmDialog
          open={Boolean(deleteTarget)}
          title="Xóa dự án nghiên cứu?"
          description={`Xóa dự án "${deleteTarget?.title ?? ""}" và báo cáo đi kèm?`}
          onClose={() => setDeleteTarget(null)}
          onConfirm={() => {
            if (deleteTarget) {
              void handleDeleteProject(deleteTarget, true)
            }
          }}
        />
      </div>
    )
  }

  // ============================================================================
  // DANH SÁCH DỰ ÁN & FORM KHỞI TẠO NGHIÊN CỨU
  // ============================================================================
  return (
    <div className="mx-auto max-w-4xl px-4 py-8 md:px-8">
      <PageHeader
        title="Trợ lý nghiên cứu"
        actions={
          <Button
            size="sm"
            leftIcon={<Plus className="h-3.5 w-3.5" />}
            onClick={() => setCreateExpanded((v) => !v)}
          >
            {createExpanded ? "Đóng khung tạo" : "Nghiên cứu mới"}
          </Button>
        }
      />

      {/* Khung khởi tạo nghiên cứu gọn gàng */}
      {createExpanded || projects.length === 0 ? (
        <section
          aria-label="Khởi tạo nghiên cứu mới"
          className="mb-8 rounded-lg border border-line bg-bg p-4"
        >
          <h2 className="mb-3 text-sm font-semibold text-ink">Khởi tạo nghiên cứu mới</h2>

          <div className="space-y-3">
            <FormField label="Câu hỏi nghiên cứu">
              <Textarea
                rows={3}
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                placeholder="Nhập câu hỏi nghiên cứu cần tổng hợp bằng chứng từ tài liệu..."
              />
            </FormField>

            <div className="grid gap-3 sm:grid-cols-2">
              <FormField label="Workspace nguồn">
                <Select
                  value={sourceWsId}
                  onChange={(e) => {
                    setSourceWsId(e.target.value)
                    setSourceNbId("")
                    setSelectedDocIds([])
                  }}
                >
                  {workspaces.map((w) => (
                    <option key={w.id} value={w.id}>
                      {w.name}
                    </option>
                  ))}
                </Select>
              </FormField>

              <FormField label="Notebook (tuỳ chọn)">
                <Select
                  value={sourceNbId}
                  onChange={(e) => {
                    setSourceNbId(e.target.value)
                    setSelectedDocIds([])
                  }}
                >
                  <option value="">Tất cả trong Workspace</option>
                  {availableNotebooks.map((nb) => (
                    <option key={nb.id} value={nb.id}>
                      {nb.name}
                    </option>
                  ))}
                </Select>
              </FormField>
            </div>

            {/* Chọn tài liệu nguồn */}
            <div>
              <p className="mb-1.5 text-xs font-medium text-ink">
                Tài liệu nguồn ({selectedDocIds.length}/{availableDocs.length} đã chọn)
              </p>
              {availableDocs.length === 0 ? (
                <p className="text-xs text-muted">Chưa có tài liệu trong phạm vi này.</p>
              ) : (
                <div className="flex flex-wrap gap-1.5">
                  {availableDocs.map((d) => {
                    const checked = selectedDocIds.includes(d.id)
                    return (
                      <button
                        key={d.id}
                        type="button"
                        onClick={() => toggleDocSelection(d.id)}
                        className={`inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1 text-xs transition-colors ${
                          checked
                            ? "border-ink bg-bg-active font-medium text-ink"
                            : "border-line bg-bg text-muted hover:bg-bg-hover hover:text-ink"
                        }`}
                      >
                        <FileText className="h-3 w-3" />
                        <span>{d.fileName}</span>
                      </button>
                    )
                  })}
                </div>
              )}
            </div>

            {/* Tùy chọn nâng cao thu gọn */}
            <div className="border-t border-line pt-2">
              <button
                type="button"
                onClick={() => setAdvancedOpen((v) => !v)}
                className="inline-flex items-center gap-1 text-xs text-muted hover:text-ink"
              >
                {advancedOpen ? (
                  <ChevronDown className="h-3.5 w-3.5" />
                ) : (
                  <ChevronRight className="h-3.5 w-3.5" />
                )}
                <span>Tùy chọn nâng cao (Tên dự án, Chế độ AI & Web Search)</span>
              </button>

              {advancedOpen ? (
                <div className="mt-3 space-y-3 rounded-md bg-bg-secondary/50 p-3">
                  <FormField label="Tên dự án (để trống sẽ tự lấy theo câu hỏi)">
                    <Input
                      value={title}
                      onChange={(e) => setTitle(e.target.value)}
                      placeholder="Ví dụ: Đánh giá độ tin cậy của Citation trong RAG..."
                    />
                  </FormField>

                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div>
                      <p className="mb-1 text-xs font-medium text-ink">Chế độ AI</p>
                      <ModeSelector
                        value={mode}
                        onChange={setMode}
                        backendOnline={status.backendOnline}
                      />
                    </div>

                    <label className="flex cursor-pointer items-center gap-2 text-xs text-ink">
                      <input
                        type="checkbox"
                        checked={allowWeb}
                        onChange={(e) => setAllowWeb(e.target.checked)}
                      />
                      <span>Mở rộng đối chiếu từ Web Search (Internet)</span>
                    </label>
                  </div>
                </div>
              ) : null}
            </div>

            <div className="flex items-center justify-between pt-2">
              <span className="text-xs text-muted">
                {status.backendOnline && getAuthToken()
                  ? "Sử dụng Pipeline RAG + LLM đa nguồn thực tế (5 bước SSE)."
                  : "Pipeline 5 bước sẽ chạy ở chế độ mô phỏng khi chưa kết nối Backend."}
              </span>
              <Button
                loading={running}
                disabled={!question.trim()}
                onClick={() => void handleRunResearch()}
              >
                {running ? "Đang tổng hợp..." : "Bắt đầu nghiên cứu"}
              </Button>
            </div>
          </div>
        </section>
      ) : null}

      {/* Tìm kiếm & Danh sách dự án nghiên cứu */}
      <div className="mb-3 flex items-center justify-between gap-2">
        <div className="relative w-full max-w-xs">
          <Search className="pointer-events-none absolute left-2.5 top-2.5 h-3.5 w-3.5 text-muted" />
          <Input
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Tìm dự án nghiên cứu..."
            className="pl-8"
          />
        </div>
        <span className="text-xs text-muted">{filteredProjects.length} dự án</span>
      </div>

      {projects.length === 0 ? (
        <EmptyState
          compact
          icon={<Telescope className="h-4 w-4" />}
          title="Chưa có dự án nghiên cứu"
          description="Nhập câu hỏi nghiên cứu ở khung phía trên để tạo báo cáo tổng hợp đầu tiên."
        />
      ) : filteredProjects.length === 0 ? (
        <EmptyState
          compact
          title="Không tìm thấy dự án phù hợp"
          description="Thử từ khóa khác hoặc xóa bộ lọc tìm kiếm."
          action={
            <Button variant="outline" size="sm" onClick={() => setSearchQuery("")}>
              Xóa tìm kiếm
            </Button>
          }
        />
      ) : (
        <ul className="divide-y divide-line border-y border-line">
          {filteredProjects.map((p) => {
            const ws = workspaces.find((w) => w.id === p.workspaceId)
            return (
              <li
                key={p.id}
                className="group flex items-center justify-between gap-3 py-3 transition-colors hover:bg-bg-hover/60"
              >
                <button
                  type="button"
                  onClick={() => navigate(`/research/${p.id}`)}
                  className="min-w-0 flex-1 text-left"
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-sm font-semibold text-ink">{p.title}</span>
                    <Badge tone="neutral">
                      {p.status === "completed" ? "Hoàn thành" : "Đang chạy"}
                    </Badge>
                  </div>
                  <p className="mt-0.5 line-clamp-1 text-xs text-muted">{p.question}</p>
                  <p className="mt-1 text-[11px] text-muted">
                    {ws?.name ?? "Workspace"} · {p.documentIds.length} nguồn · {relativeTime(p.updatedAt)}
                  </p>
                </button>

                <div className="shrink-0 opacity-0 transition-opacity group-hover:opacity-100 focus-within:opacity-100">
                  <DropdownMenu
                    align="end"
                    trigger={
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-7 w-7"
                        aria-label={`Tùy chọn cho ${p.title}`}
                      >
                        <MoreHorizontal className="h-4 w-4 text-muted" />
                      </Button>
                    }
                  >
                    <DropdownMenuItem onClick={() => navigate(`/research/${p.id}`)}>
                      Mở báo cáo
                    </DropdownMenuItem>
                    <DropdownMenuItem
                      icon={<Pencil className="h-3.5 w-3.5" />}
                      onClick={() => setRenameTarget(p)}
                    >
                      Đổi tên dự án
                    </DropdownMenuItem>
                    <DropdownMenuSeparator />
                    <DropdownMenuItem
                      tone="danger"
                      icon={<Trash2 className="h-3.5 w-3.5" />}
                      onClick={() => setDeleteTarget(p)}
                    >
                      Xóa dự án
                    </DropdownMenuItem>
                  </DropdownMenu>
                </div>
              </li>
            )
          })}
        </ul>
      )}

      <NameDialog
        open={Boolean(renameTarget)}
        title="Đổi tên dự án nghiên cứu"
        initialName={renameTarget?.title ?? ""}
        onClose={() => setRenameTarget(null)}
        onSubmit={(name) => {
          if (renameTarget) {
            void handleRenameProject(renameTarget, name)
          }
        }}
      />

      <ConfirmDialog
        open={Boolean(deleteTarget)}
        title="Xóa dự án nghiên cứu?"
        description={`Xóa "${deleteTarget?.title ?? ""}"?`}
        onClose={() => setDeleteTarget(null)}
        onConfirm={() => {
          if (deleteTarget) {
            void handleDeleteProject(deleteTarget, false)
          }
        }}
      />
    </div>
  )
}
