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
  Layers,
  PanelRightClose,
  Paperclip,
  Quote,
} from "lucide-react"
import type { Citation, KnowledgeDocument } from "@/types"
import { Badge, Button, Tooltip } from "@/components/ui"
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

  // Mặc định: Khi chưa có câu trả lời (citations rỗng) -> hiển thị "overview" (Tổng quan kho tài liệu)
  // Khi có câu trả lời có citations -> tự động hiển thị "citations" (Danh sách nguồn Citation)
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
  const totalBytes = workspaceDocuments.reduce((acc, d) => acc + (d.fileSize || 0), 0)

  return (
    <aside
      aria-label="Context Panel"
      className="flex h-full w-full flex-col border-l border-[#DCECE8] bg-[#FBFDFC] text-[13px]"
    >
      {/* Header của Context Panel: Chuyển tab Nguồn Citation / Kho tài liệu + Nút thu gọn */}
      <div className="flex h-12 shrink-0 items-center justify-between gap-2 border-b border-[#DCECE8] bg-white px-3">
        <div className="flex items-center gap-1 rounded-xl bg-[#F0F7F5] p-0.5">
          <button
            type="button"
            onClick={() => setManualTab("citations")}
            className={cn(
              "inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1 text-xs font-medium transition-all",
              activeTab === "citations"
                ? "bg-white font-semibold text-[#0B1716] shadow-2xs"
                : "text-[#526B68] hover:text-[#0B1716]",
            )}
          >
            <Quote className="h-3 w-3 text-[#0F766E]" />
            <span>Nguồn ({citations.length})</span>
          </button>

          <button
            type="button"
            onClick={() => setManualTab("overview")}
            className={cn(
              "inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1 text-xs font-medium transition-all",
              activeTab === "overview"
                ? "bg-white font-semibold text-[#0B1716] shadow-2xs"
                : "text-[#526B68] hover:text-[#0B1716]",
            )}
          >
            <Layers className="h-3 w-3 text-[#0F766E]" />
            <span>Kho tài liệu ({workspaceDocuments.length})</span>
          </button>
        </div>

        <Tooltip content="Thu gọn bảng ngữ cảnh" side="left">
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7 text-[#647D7A] hover:bg-[#EDF6F4] hover:text-[#0B1716]"
            onClick={onClose}
            aria-label="Thu gọn Context Panel"
          >
            <PanelRightClose className="h-4 w-4" />
          </Button>
        </Tooltip>
      </div>

      {/* NỘI DUNG TAB 1: DANH SÁCH NGUỒN CITATION ĐƯỢC SỬ DỤNG */}
      {activeTab === "citations" ? (
        citations.length === 0 ? (
          <div className="flex flex-1 flex-col items-center justify-center p-6 text-center">
            <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-xl border border-[#D5E6E2] bg-white text-[#0F766E]">
              <Quote className="h-4.5 w-4.5" />
            </div>
            <p className="text-sm font-semibold text-[#0B1716]">Chưa có trích dẫn trong câu trả lời</p>
            <p className="mt-1 max-w-[230px] text-xs leading-relaxed text-[#647D7A]">
              Khi bạn đặt câu hỏi, các đoạn trích dẫn từ tài liệu sẽ xuất hiện tại đây kèm số trang và liên kết đối chiếu.
            </p>
            <button
              type="button"
              onClick={() => setManualTab("overview")}
              className="mt-4 inline-flex items-center gap-1.5 rounded-full border border-[#CBE4DF] bg-white px-3 py-1.5 text-xs font-semibold text-[#0F766E] transition-colors hover:bg-[#F0F9F7]"
            >
              <span>Xem tổng quan kho tài liệu</span>
            </button>
          </div>
        ) : (
          <div className="flex-1 space-y-3 overflow-y-auto p-3.5">
            <div className="flex items-center justify-between px-0.5 text-[11px] font-medium text-[#647D7A]">
              <span>Nguồn đối chiếu của câu trả lời</span>
              <span>{citations.length} trích dẫn</span>
            </div>

            {citations.map((c) => {
              const evidence = resolveCitationEvidence(c, allDocuments)
              const isSelected = active === c.refId || (!active && citations[0]?.refId === c.refId)

              return (
                <article
                  key={`${c.sourceId ?? c.documentId ?? "web"}-${c.refId}`}
                  onClick={() => setActive(c.refId)}
                  className={cn(
                    "cursor-pointer rounded-2xl border bg-white p-3.5 transition-all",
                    isSelected
                      ? "border-[#0F766E] ring-2 ring-[#0F766E]/12 shadow-xs"
                      : "border-[#DCECE8] hover:border-[#0F766E]/50",
                  )}
                >
                  {/* Đầu thẻ nguồn: Số hiệu [1], Tên tài liệu & Trang */}
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex min-w-0 items-start gap-2">
                      <span
                        className={cn(
                          "mt-0.5 inline-flex h-5 shrink-0 items-center justify-center rounded-md px-1.5 font-mono text-[11px] font-bold",
                          isSelected
                            ? "bg-[#0F766E] text-white"
                            : "bg-[#E2F3EF] text-[#0F766E]",
                        )}
                      >
                        [{c.refId}]
                      </span>

                      <div className="min-w-0">
                        <div className="flex items-center gap-1.5">
                          {evidence.source.kind === "web" ? (
                            <Globe className="h-3.5 w-3.5 shrink-0 text-[#0284C7]" />
                          ) : (
                            <FileText className="h-3.5 w-3.5 shrink-0 text-[#0F766E]" />
                          )}
                          <h4 className="truncate text-xs font-semibold text-[#0B1716]">
                            {evidence.source.title}
                          </h4>
                        </div>

                        <div className="mt-1 flex flex-wrap items-center gap-1.5">
                          {evidence.pageNumber != null ? (
                            <Badge tone="neutral">Trang {evidence.pageNumber}</Badge>
                          ) : null}
                          {evidence.chunkId ? (
                            <Badge tone="neutral">{evidence.chunkId}</Badge>
                          ) : null}
                          <span className="text-[10px] text-[#647D7A]">
                            {evidence.source.kind === "web" ? "Web" : "Tài liệu cá nhân"}
                          </span>
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Cảnh báo nếu tài liệu gốc đã bị xóa */}
                  {!evidence.source.exists && evidence.source.kind === "local" ? (
                    <div className="mt-2.5 flex items-start gap-1.5 rounded-lg border border-rose-200 bg-rose-50 p-2 text-[11px] text-rose-700">
                      <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                      <span>Tài liệu gốc đã bị xóa khỏi Workspace.</span>
                    </div>
                  ) : null}

                  {/* Đoạn trích (Snippet) */}
                  <blockquote className="mt-2.5 rounded-xl border-l-2 border-[#0F766E] bg-[#F4FAF8] px-3 py-2 text-xs leading-relaxed text-[#1E3A37]">
                    &ldquo;{evidence.snippet || "Không có đoạn trích đính kèm."}&rdquo;
                  </blockquote>

                  {/* Nút xem chi tiết */}
                  <div className="mt-3 flex items-center justify-end">
                    {evidence.source.kind === "web" && evidence.source.url ? (
                      <a
                        href={evidence.source.url}
                        target="_blank"
                        rel="noreferrer"
                        onClick={(e) => e.stopPropagation()}
                        className="inline-flex items-center gap-1 rounded-lg border border-[#D5E6E2] bg-white px-2.5 py-1 text-[11px] font-semibold text-[#0F766E] transition-colors hover:bg-[#F0F9F7]"
                      >
                        <span>Mở nguồn Web</span>
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
                        className="inline-flex items-center gap-1 rounded-lg border border-[#D5E6E2] bg-white px-2.5 py-1 text-[11px] font-semibold text-[#0F766E] transition-colors hover:border-[#0F766E] hover:bg-[#F0F9F7] disabled:opacity-50"
                      >
                        <span>Xem chi tiết</span>
                        <ArrowUpRight className="h-3 w-3" />
                      </button>
                    ) : null}
                  </div>
                </article>
              )
            })}
          </div>
        )
      ) : (
        /* NỘI DUNG TAB 2: TỔNG QUAN KHO TÀI LIỆU KHI CHƯA HỎI */
        <div className="flex-1 space-y-4 overflow-y-auto p-3.5">
          {/* Thẻ tóm tắt trạng thái kho tri thức của Workspace */}
          <div className="rounded-2xl border border-[#DCECE8] bg-white p-3.5">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-[#0B1716]">Tổng quan kho tài liệu</span>
              <span className="inline-flex items-center gap-1 rounded-full bg-[#E2F3EF] px-2 py-0.5 text-[10px] font-bold text-[#0F766E]">
                {readyDocs.length}/{workspaceDocuments.length} sẵn sàng
              </span>
            </div>

            <div className="mt-3 grid grid-cols-2 gap-2">
              <div className="rounded-xl bg-[#F5FAF9] px-3 py-2">
                <div className="text-base font-bold text-[#0B1716]">{totalChunks}</div>
                <div className="text-[11px] text-[#647D7A]">Chunks đã lập chỉ mục</div>
              </div>
              <div className="rounded-xl bg-[#F5FAF9] px-3 py-2">
                <div className="text-base font-bold text-[#0B1716]">
                  {totalBytes > 0 ? formatBytes(totalBytes) : "0 B"}
                </div>
                <div className="text-[11px] text-[#647D7A]">Dung lượng tài liệu</div>
              </div>
            </div>

            <button
              type="button"
              onClick={() => navigate("/documents")}
              className="mt-3 inline-flex w-full items-center justify-center gap-1.5 rounded-xl border border-[#CBE4DF] bg-[#F4FAF8] py-1.5 text-xs font-semibold text-[#0F766E] transition-colors hover:bg-[#E2F3EF]"
            >
              <FileUp className="h-3.5 w-3.5" />
              <span>Tải lên / Quản lý tài liệu</span>
            </button>
          </div>

          {/* Danh sách tài liệu trong Workspace */}
          <div className="space-y-2">
            <div className="flex items-center justify-between px-0.5">
              <span className="text-[11px] font-semibold uppercase tracking-wider text-[#647D7A]">
                Tài liệu trong Workspace
              </span>
              {attachedDocIds.length > 0 ? (
                <span className="text-[11px] font-semibold text-[#0F766E]">
                  Đang chọn {attachedDocIds.length}
                </span>
              ) : null}
            </div>

            {workspaceDocuments.length === 0 ? (
              <div className="rounded-2xl border border-dashed border-[#CBE4DF] bg-white p-5 text-center">
                <p className="text-xs font-medium text-[#526B68]">
                  Workspace này chưa có tài liệu nào.
                </p>
                <button
                  type="button"
                  onClick={() => navigate("/documents")}
                  className="mt-2 inline-flex items-center gap-1 text-xs font-semibold text-[#0F766E] hover:underline"
                >
                  <span>+ Tải tài liệu đầu tiên</span>
                </button>
              </div>
            ) : (
              <div className="space-y-2">
                {workspaceDocuments.map((doc) => {
                  const isAttached = attachedDocIds.includes(doc.id)
                  return (
                    <div
                      key={doc.id}
                      className={cn(
                        "group flex items-start justify-between gap-2 rounded-xl border bg-white p-2.5 transition-all",
                        isAttached
                          ? "border-[#0F766E] bg-[#F4FAF8]"
                          : "border-[#DCECE8] hover:border-[#0F766E]/40",
                      )}
                    >
                      <button
                        type="button"
                        onClick={() => navigate(`/documents/${doc.id}`)}
                        className="flex min-w-0 flex-1 items-start gap-2.5 text-left"
                      >
                        <div className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-[#EFF7F5] text-[#0F766E]">
                          <FileText className="h-3.5 w-3.5" />
                        </div>
                        <div className="min-w-0 flex-1">
                          <p className="truncate text-xs font-semibold text-[#0B1716] group-hover:text-[#0F766E]">
                            {doc.fileName}
                          </p>
                          <p className="mt-0.5 text-[11px] text-[#647D7A]">
                            {doc.pageCount ? `${doc.pageCount} trang · ` : ""}
                            {doc.totalChunks ?? 0} chunks · {formatBytes(doc.fileSize)}
                          </p>
                        </div>
                      </button>

                      {onToggleAttachDoc ? (
                        <Tooltip
                          content={
                            isAttached
                              ? "Bỏ ghim tài liệu này khỏi câu hỏi"
                              : "Ghim tài liệu này làm ngữ cảnh ưu tiên"
                          }
                          side="left"
                        >
                          <button
                            type="button"
                            onClick={() => onToggleAttachDoc(doc.id)}
                            className={cn(
                              "inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-lg border text-xs transition-colors",
                              isAttached
                                ? "border-[#0F766E] bg-[#0F766E] text-white"
                                : "border-[#DCECE8] bg-white text-[#647D7A] hover:border-[#0F766E] hover:text-[#0F766E]",
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
