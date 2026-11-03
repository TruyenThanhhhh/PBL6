import { useEffect, useState } from "react"
import { useNavigate, useParams } from "react-router-dom"
import {
  AlertCircle,
  ArrowUpRight,
  Check,
  ExternalLink,
  FileText,
  FileUp,
  Globe,
  PanelRightClose,
  Paperclip,
  Quote,
} from "lucide-react"
import type { Citation, KnowledgeDocument } from "@/types"
import { Button, Tooltip } from "@/components/ui"
import { useAppStore } from "@/store/app-store"
import { buildSourceViewerHref, resolveCitationEvidence } from "@/services/source-service"
import { formatBytes } from "@/utils/format"
import { cn } from "@/utils/cn"

export function CitationPanel({
  citations,
  workspaceDocuments = [],
  attachedDocIds = [],
  onToggleAttachDoc,
  onClose,
}: {
  citations: Citation[]
  workspaceDocuments?: KnowledgeDocument[]
  attachedDocIds?: string[]
  onToggleAttachDoc?: (docId: string) => void
  onClose: () => void
}) {
  const { conversationId } = useParams()
  const active = useAppStore((s) => s.activeCitation)
  const setActive = useAppStore((s) => s.setActiveCitation)
  const allDocuments = useAppStore((s) => s.documents)
  const navigate = useNavigate()

  const [manualTab, setManualTab] = useState<"citations" | "overview" | null>(null)
  const activeTab: "citations" | "overview" =
    manualTab ?? (citations.length > 0 ? "citations" : "overview")

  useEffect(() => {
    const onSwitchTab = (e: Event) => {
      const custom = e as CustomEvent<"citations" | "overview">
      if (custom.detail) setManualTab(custom.detail)
    }
    window.addEventListener("studio-context-tab", onSwitchTab)
    return () => window.removeEventListener("studio-context-tab", onSwitchTab)
  }, [])

  const readyDocs = workspaceDocuments.filter((d) => d.status === "ready")
  const totalChunks = workspaceDocuments.reduce((acc, d) => acc + (d.totalChunks || 0), 0)

  return (
    <aside
      aria-label="Context Panel"
      className="flex h-full w-full flex-col border-l border-[#D4E2DF] bg-[#F5F8F7] text-[13px]"
    >
      {/* Header của Context Panel: Tab Nguồn và Kho tài liệu có trạng thái active rõ ràng */}
      <div className="flex h-12 shrink-0 items-center justify-between gap-2 border-b border-[#D4E2DF] bg-[#F5F8F7] px-3">
        <div className="flex items-center gap-1 rounded-lg border border-[#D4E2DF] bg-[#E8EFEE] p-0.5">
          <button
            type="button"
            onClick={() => setManualTab("citations")}
            className={cn(
              "inline-flex items-center gap-1.5 rounded-md px-3 py-1 text-xs transition-all",
              activeTab === "citations"
                ? "bg-[#087F73] font-semibold text-white shadow-2xs"
                : "font-medium text-[#647C79] hover:text-[#172B29]",
            )}
          >
            <span>Nguồn ({citations.length})</span>
          </button>

          <button
            type="button"
            onClick={() => setManualTab("overview")}
            className={cn(
              "inline-flex items-center gap-1.5 rounded-md px-3 py-1 text-xs transition-all",
              activeTab === "overview"
                ? "bg-[#087F73] font-semibold text-white shadow-2xs"
                : "font-medium text-[#647C79] hover:text-[#172B29]",
            )}
          >
            <span>Kho tài liệu ({workspaceDocuments.length})</span>
          </button>
        </div>

        <Tooltip content="Thu gọn bảng ngữ cảnh" side="left">
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7 text-[#647C79] hover:bg-[#E4ECEA] hover:text-[#172B29]"
            onClick={onClose}
            aria-label="Thu gọn Context Panel"
          >
            <PanelRightClose className="h-4 w-4" />
          </Button>
        </Tooltip>
      </div>

      {/* TAB 1: NGUỒN CITATION ĐƯỢC SỬ DỤNG */}
      {activeTab === "citations" ? (
        citations.length === 0 ? (
          <div className="flex flex-1 flex-col items-center justify-center p-6 text-center">
            <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-xl border border-[#D4E2DF] bg-white text-[#087F73]">
              <Quote className="h-4.5 w-4.5" />
            </div>
            <p className="text-sm font-semibold text-[#172B29]">Chưa có trích dẫn</p>
            <p className="mt-1 max-w-[210px] text-xs leading-relaxed text-[#647C79]">
              Các đoạn trích từ tài liệu của câu trả lời sẽ hiển thị tại đây.
            </p>
            <button
              type="button"
              onClick={() => setManualTab("overview")}
              className="mt-4 inline-flex items-center gap-1 rounded-lg border border-[#D4E2DF] bg-white px-3 py-1.5 text-xs font-semibold text-[#172B29] transition-colors hover:border-[#087F73] hover:text-[#087F73]"
            >
              <span>Xem Kho tài liệu</span>
            </button>
          </div>
        ) : (
          <div className="flex-1 space-y-3 overflow-y-auto p-3.5">
            {citations.map((c) => {
              const evidence = resolveCitationEvidence(c, allDocuments)
              const isSelected = active === c.refId || (!active && citations[0]?.refId === c.refId)

              return (
                <article
                  key={`${c.sourceId ?? c.documentId ?? "web"}-${c.refId}`}
                  onClick={() => setActive(c.refId)}
                  className={cn(
                    "cursor-pointer rounded-xl border bg-white p-3.5 transition-all",
                    isSelected
                      ? "border-[#087F73] ring-1 ring-[#087F73]"
                      : "border-[#D4E2DF] hover:border-[#087F73]/60",
                  )}
                >
                  {/* 1. Tên tài liệu & Số trang phân biệt rõ ràng */}
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex min-w-0 items-center gap-2">
                      <span
                        className={cn(
                          "inline-flex h-5 shrink-0 items-center justify-center rounded px-1.5 font-mono text-[11px] font-bold",
                          isSelected
                            ? "bg-[#087F73] text-white"
                            : "border border-[#D4E2DF] bg-[#F5F8F7] text-[#172B29]",
                        )}
                      >
                        [{c.refId}]
                      </span>

                      {evidence.source.kind === "web" ? (
                        <Globe className="h-3.5 w-3.5 shrink-0 text-[#647C79]" />
                      ) : (
                        <FileText className="h-3.5 w-3.5 shrink-0 text-[#087F73]" />
                      )}

                      <h4 className="truncate text-xs font-semibold text-[#172B29]">
                        {evidence.source.title}
                      </h4>
                    </div>

                    {evidence.pageNumber != null ? (
                      <span className="shrink-0 rounded border border-[#D4E2DF] bg-[#F5F8F7] px-2 py-0.5 text-[11px] font-semibold text-[#172B29]">
                        Trang {evidence.pageNumber}
                      </span>
                    ) : null}
                  </div>

                  {/* Cảnh báo nếu tài liệu gốc đã bị xóa */}
                  {!evidence.source.exists && evidence.source.kind === "local" ? (
                    <div className="mt-2.5 flex items-start gap-1.5 rounded-lg border border-rose-200 bg-rose-50 p-2 text-[11px] text-rose-700">
                      <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                      <span>Tài liệu gốc đã bị xóa khỏi Workspace.</span>
                    </div>
                  ) : null}

                  {/* 2. Đoạn trích (Snippet) trong khung riêng biệt */}
                  <blockquote className="mt-2.5 rounded-r-lg border-l-2 border-[#087F73] bg-[#F5F8F7] px-3 py-2 text-xs leading-relaxed text-[#172B29]">
                    &ldquo;{evidence.snippet || "Không có đoạn trích đính kèm."}&rdquo;
                  </blockquote>

                  {/* 3. Nút xem chi tiết */}
                  <div className="mt-2.5 flex items-center justify-between">
                    <span className="text-[11px] text-[#647C79]">
                      {evidence.chunkId ?? (evidence.source.kind === "web" ? "Nguồn Web" : "Tài liệu cục bộ")}
                    </span>

                    {evidence.source.kind === "web" && evidence.source.url ? (
                      <a
                        href={evidence.source.url}
                        target="_blank"
                        rel="noreferrer"
                        onClick={(e) => e.stopPropagation()}
                        className="inline-flex items-center gap-1 text-xs font-semibold text-[#087F73] hover:underline"
                      >
                        <span>Mở liên kết</span>
                        <ExternalLink className="h-3 w-3" />
                      </a>
                    ) : evidence.citation.documentId ? (
                      <button
                        type="button"
                        disabled={!evidence.source.exists}
                        onClick={(e) => {
                          e.stopPropagation()
                          const href = buildSourceViewerHref(evidence.citation, conversationId)
                          if (href) navigate(href)
                        }}
                        className="inline-flex items-center gap-1 text-xs font-semibold text-[#087F73] hover:underline disabled:opacity-50"
                      >
                        <span>Xem chi tiết</span>
                        <ArrowUpRight className="h-3.5 w-3.5" />
                      </button>
                    ) : null}
                  </div>
                </article>
              )
            })}
          </div>
        )
      ) : (
        /* TAB 2: KHO TÀI LIỆU (Statistics card riêng + Nút Upload nổi bật + Danh sách gọn) */
        <div className="flex-1 space-y-4 overflow-y-auto p-3.5">
          {/* Statistics được trình bày thành 2 card riêng biệt */}
          <div className="grid grid-cols-2 gap-2.5">
            <div className="rounded-xl border border-[#D4E2DF] bg-white p-3">
              <div className="text-lg font-bold text-[#172B29]">
                {readyDocs.length}/{workspaceDocuments.length}
              </div>
              <div className="mt-0.5 text-[11px] font-medium text-[#647C79]">
                Tài liệu sẵn sàng
              </div>
            </div>

            <div className="rounded-xl border border-[#D4E2DF] bg-white p-3">
              <div className="text-lg font-bold text-[#172B29]">{totalChunks}</div>
              <div className="mt-0.5 text-[11px] font-medium text-[#647C79]">
                Đoạn trích (Chunks)
              </div>
            </div>
          </div>

          {/* Nút Upload nổi bật (Primary CTA #087F73) */}
          <button
            type="button"
            onClick={() => navigate("/documents")}
            className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-[#087F73] py-2.5 text-xs font-semibold text-white transition-colors hover:bg-[#06665C]"
          >
            <FileUp className="h-4 w-4" />
            <span>Tải lên tài liệu</span>
          </button>

          {/* Danh sách tài liệu */}
          <div className="space-y-2 pt-1">
            <div className="flex items-center justify-between px-0.5">
              <span className="text-[11px] font-semibold text-[#647C79]">
                Tài liệu ({workspaceDocuments.length})
              </span>
              {attachedDocIds.length > 0 ? (
                <span className="text-[11px] font-semibold text-[#087F73]">
                  Đã chọn {attachedDocIds.length}
                </span>
              ) : null}
            </div>

            {workspaceDocuments.length === 0 ? (
              <div className="rounded-xl border border-dashed border-[#D4E2DF] bg-white p-5 text-center">
                <p className="text-xs text-[#647C79]">Chưa có tài liệu nào.</p>
              </div>
            ) : (
              <div className="space-y-1.5">
                {workspaceDocuments.map((doc) => {
                  const isAttached = attachedDocIds.includes(doc.id)
                  return (
                    <div
                      key={doc.id}
                      className={cn(
                        "group flex items-center justify-between gap-2 rounded-xl border bg-white px-3 py-2.5 transition-colors",
                        isAttached
                          ? "border-[#087F73]"
                          : "border-[#D4E2DF] hover:border-[#087F73]/50",
                      )}
                    >
                      <button
                        type="button"
                        onClick={() => navigate(`/documents/${doc.id}`)}
                        className="flex min-w-0 flex-1 items-center gap-2.5 text-left"
                      >
                        <FileText className="h-4 w-4 shrink-0 text-[#087F73]" />
                        <div className="min-w-0 flex-1">
                          <p className="truncate text-xs font-semibold text-[#172B29] group-hover:text-[#087F73]">
                            {doc.fileName}
                          </p>
                          <p className="mt-0.5 text-[11px] text-[#647C79]">
                            {doc.pageCount ? `${doc.pageCount} trang · ` : ""}
                            {formatBytes(doc.fileSize)}
                          </p>
                        </div>
                      </button>

                      {onToggleAttachDoc ? (
                        <Tooltip
                          content={
                            isAttached
                              ? "Bỏ đính kèm"
                              : "Đính kèm vào câu hỏi"
                          }
                          side="left"
                        >
                          <button
                            type="button"
                            onClick={() => onToggleAttachDoc(doc.id)}
                            className={cn(
                              "inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-lg border text-xs transition-colors",
                              isAttached
                                ? "border-[#087F73] bg-[#087F73] text-white"
                                : "border-[#D4E2DF] bg-white text-[#647C79] hover:border-[#087F73] hover:text-[#087F73]",
                            )}
                            aria-label={`Đính kèm ${doc.fileName}`}
                          >
                            {isAttached ? (
                              <Check className="h-3.5 w-3.5" />
                            ) : (
                              <Paperclip className="h-3.5 w-3.5" />
                            )}
                          </button>
                        </Tooltip>
                      ) : null}
                    </div>
                  )
                })}
              </div>
            )}
          </div>
        </div>
      )}
    </aside>
  )
}
