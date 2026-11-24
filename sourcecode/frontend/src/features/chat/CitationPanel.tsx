import { useEffect, useState } from "react"
import { useNavigate } from "react-router-dom"
import Markdown from "react-markdown"
import remarkGfm from "remark-gfm"
import {
  BookOpenCheck,
  Check,
  ChevronDown,
  ChevronUp,
  Copy,
  ExternalLink,
  FileText,
  Globe,
  Loader2,
  NotebookPen,
  PanelRightClose,
  Quote,
  StickyNote,
  Trash2,
  X,
} from "lucide-react"
import { Badge, Button, EmptyState, Tooltip } from "@/components/ui"
import { ExportFormatMenu } from "@/components/common/ExportFormatMenu"
import { fetchDocumentChunks, type DocumentChunkRecord } from "@/services/api"
import { buildSourceViewerHref, resolveCitationEvidence } from "@/services/source-service"
import { useAppStore } from "@/store/app-store"
import type { Citation, EvidenceItem, KnowledgeDocument, Note } from "@/types"
import { formatDate } from "@/utils/format"
import { cn } from "@/utils/cn"

export function CitationPanel({
  citations,
  workspaceDocuments,
  notes = [],
  activeTab: controlledTab,
  onTabChange,
  onDeleteNote,
  onClose,
}: {
  citations: Citation[]
  workspaceDocuments: KnowledgeDocument[]
  attachedDocIds?: string[]
  onToggleAttachDoc?: (docId: string) => void
  notes?: Note[]
  activeTab?: "citations" | "notes"
  onTabChange?: (tab: "citations" | "notes") => void
  onDeleteNote?: (noteId: string) => void
  onClose: () => void
}) {
  const navigate = useNavigate()
  const activeCitation = useAppStore((s) => s.activeCitation)
  const setActiveCitation = useAppStore((s) => s.setActiveCitation)
  const toast = useAppStore((s) => s.toast)

  const [internalTab, setInternalTab] = useState<"citations" | "notes">("citations")
  const tab = controlledTab ?? internalTab
  const setTab = (next: "citations" | "notes") => {
    if (onTabChange) onTabChange(next)
    setInternalTab(next)
  }

  const [expandedRefIds, setExpandedRefIds] = useState<Record<number, boolean>>({})
  const [copiedKey, setCopiedKey] = useState<string | null>(null)

  // In-place Context Reader Drawer (xem ngữ cảnh cả trang/chunk kế bên mà không rời Chat)
  const [contextEvidence, setContextEvidence] = useState<EvidenceItem | null>(null)
  const [contextChunks, setContextChunks] = useState<DocumentChunkRecord[]>([])
  const [contextLoading, setContextLoading] = useState(false)

  useEffect(() => {
    if (activeCitation != null) {
      setExpandedRefIds((prev) => ({ ...prev, [activeCitation]: true }))
      setTab("citations")
      const el = document.getElementById(`citation-card-${activeCitation}`)
      if (el) {
        el.scrollIntoView({ behavior: "smooth", block: "nearest" })
      }
    }
  }, [activeCitation])

  const evidences = citations.map((c) => resolveCitationEvidence(c, workspaceDocuments))

  const handleToggleExpand = (refId: number) => {
    setExpandedRefIds((prev) => ({ ...prev, [refId]: !prev[refId] }))
  }

  const handleCopyText = async (key: string, text: string) => {
    try {
      await navigator.clipboard.writeText(text)
      setCopiedKey(key)
      window.setTimeout(() => setCopiedKey(null), 1600)
      toast({ title: "Đã sao chép nội dung", tone: "success" })
    } catch {
      toast({ title: "Không thể sao chép tự động", tone: "warning" })
    }
  }

  const handleOpenInPlaceReader = async (evidence: EvidenceItem) => {
    if (!evidence.citation.documentId) return
    setContextEvidence(evidence)
    setContextLoading(true)
    setContextChunks([])
    try {
      const pageNum = evidence.pageNumber ?? undefined
      const res = await fetchDocumentChunks(evidence.citation.documentId, pageNum)
      setContextChunks(res.chunks ?? [])
    } catch {
      setContextChunks([])
    } finally {
      setContextLoading(false)
    }
  }

  return (
    <aside className="flex h-full w-full flex-col border-l border-[#DCE7E4] bg-[#F7FAF9] text-[#172B29]">
      {/* Header + Tabs Bằng chứng / Ghi chú Studio */}
      <div className="flex h-11 shrink-0 items-center justify-between gap-2 border-b border-[#DCE7E4] px-3">
        <div className="flex items-center gap-1 rounded-lg bg-[#E9F1EF] p-0.5">
          <button
            type="button"
            onClick={() => setTab("citations")}
            className={cn(
              "inline-flex items-center gap-1.5 rounded-md px-2.5 py-1 text-[11px] font-semibold transition-all",
              tab === "citations"
                ? "bg-white text-[#087F73] shadow-2xs"
                : "text-[#647C79] hover:text-[#172B29]",
            )}
          >
            <Quote className="h-3 w-3" />
            <span>Trích dẫn ({evidences.length})</span>
          </button>
          <button
            type="button"
            onClick={() => setTab("notes")}
            className={cn(
              "inline-flex items-center gap-1.5 rounded-md px-2.5 py-1 text-[11px] font-semibold transition-all",
              tab === "notes"
                ? "bg-white text-[#087F73] shadow-2xs"
                : "text-[#647C79] hover:text-[#172B29]",
            )}
          >
            <StickyNote className="h-3 w-3" />
            <span>Ghi chú ({notes.length})</span>
          </button>
        </div>

        <Tooltip content="Đóng bảng bên phải" side="left">
          <button
            type="button"
            onClick={onClose}
            aria-label="Đóng bảng bằng chứng"
            className="inline-flex h-7 w-7 items-center justify-center rounded-md text-[#647C79] transition hover:bg-white hover:text-[#172B29]"
          >
            <PanelRightClose className="h-3.5 w-3.5" />
          </button>
        </Tooltip>
      </div>

      {/* Nội dung Panel */}
      <div className="min-h-0 flex-1 overflow-y-auto p-3">
        {tab === "citations" ? (
          evidences.length === 0 ? (
            <div className="py-8">
              <EmptyState
                compact
                icon={<Quote className="h-5 w-5 text-[#087F73]" />}
                title="Chưa có đoạn trích dẫn"
                description="Khi bạn đặt câu hỏi và AI trích xuất thông tin từ tài liệu, toàn bộ đoạn gốc kèm số trang sẽ hiển thị đầy đủ tại đây để bạn đối chiếu."
              />
            </div>
          ) : (
            <div className="space-y-2.5">
              {evidences.map((ev) => {
                const refId = ev.citation.refId
                const isActive = activeCitation === refId
                const fullText = (ev.fullText || ev.citation.fullText || ev.snippet || "").trim()
                const hasLongContent = fullText.length > ev.snippet.length + 20 || fullText.length > 260
                const isExpanded = Boolean(expandedRefIds[refId] ?? (isActive || evidences.length === 1))
                const isWeb = ev.source.kind === "web"

                return (
                  <article
                    key={refId}
                    id={`citation-card-${refId}`}
                    className={cn(
                      "rounded-xl border bg-white p-3 transition-all",
                      isActive
                        ? "border-[#087F73] ring-2 ring-[#087F73]/15 shadow-xs"
                        : "border-[#DCE7E4] hover:border-[#B4CDC7]",
                    )}
                  >
                    {/* Header thẻ nguồn */}
                    <div
                      role="button"
                      tabIndex={0}
                      onClick={() => setActiveCitation(refId)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" || e.key === " ") setActiveCitation(refId)
                      }}
                      className="flex cursor-pointer items-start justify-between gap-2"
                    >
                      <div className="flex min-w-0 items-start gap-2">
                        <span
                          className={cn(
                            "mt-0.5 inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[11px] font-bold",
                            isActive
                              ? "bg-[#087F73] text-white"
                              : "bg-[#E8F4F2] text-[#087F73]",
                          )}
                        >
                          {refId}
                        </span>
                        <div className="min-w-0">
                          <div className="flex items-center gap-1.5">
                            {isWeb ? (
                              <Globe className="h-3.5 w-3.5 shrink-0 text-[#087F73]" />
                            ) : (
                              <FileText className="h-3.5 w-3.5 shrink-0 text-[#087F73]" />
                            )}
                            <span className="truncate text-[12px] font-semibold text-[#172B29]">
                              {ev.source.title}
                            </span>
                          </div>
                          <div className="mt-0.5 flex flex-wrap items-center gap-1.5 text-[10.5px] text-[#647C79]">
                            {ev.pageLabel ? (
                              <Badge tone="neutral" className="px-1.5 py-0 text-[10px]">
                                {ev.pageLabel}
                              </Badge>
                            ) : null}
                            {ev.citation.chunkIndex != null ? (
                              <span>Đoạn #{ev.citation.chunkIndex}</span>
                            ) : null}
                          </div>
                        </div>
                      </div>

                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation()
                          void handleCopyText(`cite-${refId}`, fullText)
                        }}
                        title="Chép đoạn trích dẫn"
                        className="inline-flex h-6 w-6 shrink-0 items-center justify-center rounded text-[#647C79] hover:bg-[#F1F6F5] hover:text-[#172B29]"
                      >
                        {copiedKey === `cite-${refId}` ? (
                          <Check className="h-3 w-3 text-[#087F73]" />
                        ) : (
                          <Copy className="h-3 w-3" />
                        )}
                      </button>
                    </div>

                    {/* Đoạn bằng chứng đầy đủ (không còn bị cắt cụt 200 ký tự!) */}
                    <div className="mt-2.5 rounded-lg border border-[#DCE7E4]/80 bg-[#F9FCFB] px-2.5 py-2">
                      {isExpanded ? (
                        <div className="markdown-body max-h-[340px] overflow-y-auto pr-1 text-[12.5px] leading-relaxed text-[#172B29]">
                          <Markdown remarkPlugins={[remarkGfm]}>{fullText}</Markdown>
                        </div>
                      ) : (
                        <p className="text-[12px] leading-relaxed text-[#172B29]/90 whitespace-pre-line">
                          {ev.snippet}
                        </p>
                      )}
                    </div>

                    {/* Thanh hành động thẻ trích dẫn */}
                    <div className="mt-2 flex flex-wrap items-center justify-between gap-1.5 pt-0.5">
                      <div className="flex items-center gap-1.5">
                        {hasLongContent ? (
                          <button
                            type="button"
                            onClick={() => handleToggleExpand(refId)}
                            className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[11px] font-medium text-[#087F73] hover:bg-[#E8F4F2]"
                          >
                            {isExpanded ? (
                              <>
                                <ChevronUp className="h-3 w-3" />
                                <span>Thu gọn</span>
                              </>
                            ) : (
                              <>
                                <ChevronDown className="h-3 w-3" />
                                <span>Đọc toàn đoạn</span>
                              </>
                            )}
                          </button>
                        ) : null}

                        {!isWeb && ev.citation.documentId ? (
                          <button
                            type="button"
                            onClick={() => void handleOpenInPlaceReader(ev)}
                            className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[11px] font-medium text-[#172B29] hover:bg-[#F1F6F5] hover:text-[#087F73]"
                          >
                            <BookOpenCheck className="h-3 w-3 text-[#087F73]" />
                            <span>Xem ngữ cảnh trang</span>
                          </button>
                        ) : null}
                      </div>

                      {isWeb && ev.source.url ? (
                        <a
                          href={ev.source.url}
                          target="_blank"
                          rel="noreferrer"
                          className="inline-flex items-center gap-1 text-[11px] font-medium text-[#087F73] hover:underline"
                        >
                          <span>Mở liên kết</span>
                          <ExternalLink className="h-3 w-3" />
                        </a>
                      ) : !isWeb && ev.citation.documentId && ev.source.exists ? (
                        <button
                          type="button"
                          onClick={() => {
                            const href = buildSourceViewerHref(ev.citation)
                            if (href) navigate(href)
                          }}
                          className="inline-flex items-center gap-1 text-[11px] font-medium text-[#647C79] hover:text-[#087F73]"
                        >
                          <span>Mở tệp</span>
                          <ExternalLink className="h-3 w-3" />
                        </button>
                      ) : null}
                    </div>
                  </article>
                )
              })}
            </div>
          )
        ) : (
          /* Tab Ghi chú Studio (NotebookLM Studio Notes) */
          <div className="space-y-2.5">
            {notes.length === 0 ? (
              <div className="py-8">
                <EmptyState
                  compact
                  icon={<NotebookPen className="h-5 w-5 text-[#087F73]" />}
                  title="Chưa có ghi chú đã lưu"
                  description="Bấm 'Lưu ghi chú' ngay dưới mỗi câu trả lời AI để ghim các tổng hợp, công thức và lập luận quan trọng vào Studio tại đây."
                />
              </div>
            ) : (
              notes.map((note) => (
                <article
                  key={note.id}
                  className="rounded-xl border border-[#DCE7E4] bg-white p-3 shadow-2xs"
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <h4 className="truncate text-[12.5px] font-semibold text-[#172B29]">
                        {note.title}
                      </h4>
                      <span className="text-[10.5px] text-[#647C79]">
                        {formatDate(note.updatedAt)}
                      </span>
                    </div>
                    <div className="flex items-center gap-1 shrink-0">
                      <button
                        type="button"
                        onClick={() => void handleCopyText(`note-${note.id}`, note.content)}
                        title="Sao chép ghi chú"
                        className="inline-flex h-6 w-6 items-center justify-center rounded text-[#647C79] hover:bg-[#F1F6F5] hover:text-[#172B29]"
                      >
                        {copiedKey === `note-${note.id}` ? (
                          <Check className="h-3 w-3 text-[#087F73]" />
                        ) : (
                          <Copy className="h-3 w-3" />
                        )}
                      </button>
                      <ExportFormatMenu
                        title={note.title}
                        content={note.content}
                        label=""
                        size="sm"
                        variant="ghost"
                      />
                      {onDeleteNote ? (
                        <button
                          type="button"
                          onClick={() => onDeleteNote(note.id)}
                          title="Xóa ghi chú"
                          className="inline-flex h-6 w-6 items-center justify-center rounded text-[#647C79] hover:bg-rose-50 hover:text-rose-600"
                        >
                          <Trash2 className="h-3 w-3" />
                        </button>
                      ) : null}
                    </div>
                  </div>
                  <div className="markdown-body mt-2 max-h-44 overflow-y-auto border-t border-[#DCE7E4]/70 pt-2 text-[12px] leading-relaxed text-[#172B29]">
                    <Markdown remarkPlugins={[remarkGfm]}>{note.content}</Markdown>
                  </div>
                </article>
              ))
            )}
          </div>
        )}
      </div>

      {/* Modal In-Place Context Reader (Đọc nguyên trang/đoạn lân cận mà không rời Chat) */}
      {contextEvidence ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-[#172B29]/40 p-4 backdrop-blur-[1px]">
          <div className="flex max-h-[85vh] w-full max-w-2xl flex-col overflow-hidden rounded-2xl border border-[#DCE7E4] bg-white shadow-2xl">
            <div className="flex items-center justify-between border-b border-[#DCE7E4] bg-[#F7FAF9] px-4 py-3">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span className="inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-[#087F73] text-[11px] font-bold text-white">
                    {contextEvidence.citation.refId}
                  </span>
                  <h3 className="truncate text-sm font-semibold text-[#172B29]">
                    {contextEvidence.source.title}
                  </h3>
                </div>
                <p className="mt-0.5 text-xs text-[#647C79]">
                  {contextEvidence.pageLabel || "Toàn tài liệu"}
                  {contextEvidence.citation.chunkIndex != null
                    ? ` · Đang tô sáng Đoạn #${contextEvidence.citation.chunkIndex}`
                    : ""}
                </p>
              </div>
              <div className="flex items-center gap-1.5">
                {contextEvidence.citation.documentId && contextEvidence.source.exists ? (
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => {
                      const url = buildSourceViewerHref(contextEvidence.citation)
                      setContextEvidence(null)
                      if (url) navigate(url)
                    }}
                  >
                    <ExternalLink className="mr-1 h-3.5 w-3.5" />
                    Mở trang tài liệu
                  </Button>
                ) : null}
                <button
                  type="button"
                  onClick={() => setContextEvidence(null)}
                  className="inline-flex h-8 w-8 items-center justify-center rounded-lg text-[#647C79] hover:bg-white hover:text-[#172B29]"
                  aria-label="Đóng khung đọc ngữ cảnh"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
            </div>

            <div className="min-h-0 flex-1 space-y-3 overflow-y-auto p-4">
              {contextLoading ? (
                <div className="flex items-center justify-center gap-2 py-12 text-xs text-[#647C79]">
                  <Loader2 className="h-4 w-4 animate-spin text-[#087F73]" />
                  <span>Đang tải nguyên văn trang gốc từ tài liệu...</span>
                </div>
              ) : contextChunks.length === 0 ? (
                <div className="rounded-xl border border-[#DCE7E4] bg-[#F9FCFB] p-4">
                  <div className="markdown-body text-[13.5px] leading-relaxed">
                    <Markdown remarkPlugins={[remarkGfm]}>
                      {contextEvidence.fullText || contextEvidence.snippet}
                    </Markdown>
                  </div>
                </div>
              ) : (
                contextChunks.map((chunk) => {
                  const isTarget =
                    contextEvidence.citation.chunkIndex != null &&
                    chunk.chunk_index === contextEvidence.citation.chunkIndex
                  return (
                    <div
                      key={chunk.id}
                      className={cn(
                        "rounded-xl border p-3.5 transition-all",
                        isTarget
                          ? "border-[#087F73] bg-[#E8F4F2]/75 ring-2 ring-[#087F73]/25"
                          : "border-[#DCE7E4] bg-white",
                      )}
                    >
                      <div className="mb-1.5 flex items-center justify-between text-[11px] text-[#647C79]">
                        <span className="font-semibold text-[#172B29]">
                          Đoạn #{chunk.chunk_index} · Trang {chunk.page_number}
                        </span>
                        {isTarget ? (
                          <span className="rounded bg-[#087F73] px-2 py-0.5 text-[10px] font-semibold text-white">
                            Trích dẫn đang xem
                          </span>
                        ) : null}
                      </div>
                      <div className="markdown-body text-[13.5px] leading-relaxed text-[#172B29]">
                        <Markdown remarkPlugins={[remarkGfm]}>{chunk.content}</Markdown>
                      </div>
                    </div>
                  )
                })
              )}
            </div>
          </div>
        </div>
      ) : null}
    </aside>
  )
}
