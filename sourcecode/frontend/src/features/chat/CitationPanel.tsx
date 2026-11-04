import { useEffect, useState } from "react"
import { useNavigate, useParams } from "react-router-dom"
import {
  AlertCircle,
  ArrowUpRight,
  Check,
  ExternalLink,
  FileText,
  Globe,
  PanelRightClose,
  Paperclip,
  Plus,
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

  const [manualTab, setManualTab] = useState<"overview" | "citations" | null>(null)
  const activeTab: "overview" | "citations" =
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
      className="flex h-full w-full flex-col border-l border-[#DCE7E4] bg-[#F1F6F5] text-[13px]"
    >
      {/* 1. Header: Tabs tinh giản, giảm độ nổi bật theo phong cách SaaS tối giản */}
      <div className="flex h-11 shrink-0 items-center justify-between border-b border-[#DCE7E4] bg-white px-3">
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={() => setManualTab("overview")}
            className={cn(
              "relative py-3 text-xs font-medium transition-colors",
              activeTab === "overview"
                ? "font-semibold text-[#087F73]"
                : "text-[#647C79] hover:text-[#172B29]",
            )}
          >
            <span>Tài liệu ({workspaceDocuments.length})</span>
            {activeTab === "overview" ? (
              <span className="absolute bottom-0 inset-x-0 h-0.5 bg-[#087F73]" />
            ) : null}
          </button>

          <button
            type="button"
            onClick={() => setManualTab("citations")}
            className={cn(
              "relative py-3 text-xs font-medium transition-colors",
              activeTab === "citations"
                ? "font-semibold text-[#087F73]"
                : "text-[#647C79] hover:text-[#172B29]",
            )}
          >
            <span>Nguồn ({citations.length})</span>
            {activeTab === "citations" ? (
              <span className="absolute bottom-0 inset-x-0 h-0.5 bg-[#087F73]" />
            ) : null}
          </button>
        </div>

        <Tooltip content="Thu gọn bảng" side="left">
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7 text-[#647C79] hover:bg-[#F1F6F5] hover:text-[#172B29]"
            onClick={onClose}
            aria-label="Thu gọn Context Panel"
          >
            <PanelRightClose className="h-4 w-4" />
          </Button>
        </Tooltip>
      </div>

      {/* 2. TAB 1: DANH SÁCH TÀI LIỆU LÀ THÀNH PHẦN CHÍNH */}
      {activeTab === "overview" ? (
        <div className="flex flex-1 flex-col overflow-hidden p-3 space-y-3">
          {/* Statistics nhỏ gọn: 1 dòng súc tích */}
          <div className="flex items-center justify-between rounded-lg border border-[#DCE7E4] bg-white px-3 py-2 text-xs">
            <div className="flex items-center gap-1.5">
              <span className="h-1.5 w-1.5 rounded-full bg-[#087F73]" />
              <span className="font-semibold text-[#172B29]">
                {readyDocs.length}/{workspaceDocuments.length}
              </span>
              <span className="text-[#647C79]">sẵn sàng</span>
            </div>
            <div className="text-[11px] text-[#647C79]">
              <span className="font-semibold text-[#172B29]">{totalChunks}</span> chunks
            </div>
          </div>

          {/* Nút thêm tài liệu (Kiểu Secondary Button, không lạm dụng Primary CTA) */}
          <button
            type="button"
            onClick={() => navigate("/documents")}
            className="inline-flex w-full items-center justify-center gap-1.5 rounded-lg border border-[#DCE7E4] bg-white py-1.5 text-xs font-medium text-[#172B29] transition-colors hover:bg-white/80 hover:border-[#647C79] shadow-2xs"
          >
            <Plus className="h-3.5 w-3.5 text-[#647C79]" />
            <span>Thêm tài liệu</span>
          </button>

          {/* Danh sách tài liệu (Thành phần chính) */}
          <div className="flex-1 overflow-y-auto space-y-1">
            {workspaceDocuments.length === 0 ? (
              <div className="rounded-lg border border-dashed border-[#DCE7E4] p-4 text-center">
                <p className="text-xs text-[#647C79]">Chưa có tài liệu trong không gian này.</p>
              </div>
            ) : (
              workspaceDocuments.map((doc) => {
                const isAttached = attachedDocIds.includes(doc.id)
                const isReady = doc.status === "ready"
                return (
                  <div
                    key={doc.id}
                    className={cn(
                      "group flex items-center justify-between gap-2 rounded-lg border bg-white px-2.5 py-2 transition-colors",
                      isAttached
                        ? "border-[#087F73] ring-1 ring-[#087F73]/20"
                        : "border-[#DCE7E4] hover:border-[#087F73]/50",
                    )}
                  >
                    <button
                      type="button"
                      onClick={() => navigate(`/documents/${doc.id}`)}
                      className="flex min-w-0 flex-1 items-center gap-2 text-left"
                    >
                      <FileText className="h-4 w-4 shrink-0 text-[#647C79] group-hover:text-[#087F73]" />
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-xs font-medium text-[#172B29] group-hover:text-[#087F73]">
                          {doc.fileName}
                        </p>
                        <div className="mt-0.5 flex items-center gap-1.5 text-[10.5px] text-[#647C79]">
                          <span>{formatBytes(doc.fileSize)}</span>
                          <span>·</span>
                          <span className={cn(isReady ? "text-[#087F73]" : "text-amber-600")}>
                            {isReady ? "Đã index" : "Đang xử lý"}
                          </span>
                        </div>
                      </div>
                    </button>

                    {onToggleAttachDoc ? (
                      <Tooltip
                        content={isAttached ? "Bỏ đính kèm" : "Đính kèm vào câu hỏi"}
                        side="left"
                      >
                        <button
                          type="button"
                          onClick={() => onToggleAttachDoc(doc.id)}
                          className={cn(
                            "inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-md border text-xs transition-colors",
                            isAttached
                              ? "border-[#087F73] bg-[#087F73] text-white"
                              : "border-[#DCE7E4] bg-white text-[#647C79] hover:border-[#087F73] hover:text-[#087F73]",
                          )}
                          aria-label={`Đính kèm ${doc.fileName}`}
                        >
                          {isAttached ? (
                            <Check className="h-3 w-3" />
                          ) : (
                            <Paperclip className="h-3 w-3" />
                          )}
                        </button>
                      </Tooltip>
                    ) : null}
                  </div>
                )
              })
            )}
          </div>
        </div>
      ) : (
        /* 3. TAB 2: NGUỒN CITATION CỦA CÂU TRẢ LỜI HIỆN TẠI */
        <div className="flex-1 overflow-y-auto p-3 space-y-2.5">
          {citations.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-10 text-center">
              <Quote className="h-5 w-5 text-[#647C79] mb-1.5" />
              <p className="text-xs font-semibold text-[#172B29]">Chưa có trích dẫn</p>
              <p className="mt-0.5 max-w-[200px] text-[11px] text-[#647C79]">
                Câu trả lời AI có đối chiếu tài liệu sẽ hiển thị trích dẫn tại đây.
              </p>
            </div>
          ) : (
            citations.map((c) => {
              const evidence = resolveCitationEvidence(c, allDocuments)
              const isSelected = active === c.refId || (!active && citations[0]?.refId === c.refId)

              return (
                <article
                  key={`${c.sourceId ?? c.documentId ?? "web"}-${c.refId}`}
                  onClick={() => setActive(c.refId)}
                  className={cn(
                    "cursor-pointer rounded-lg border bg-white p-2.5 transition-all",
                    isSelected
                      ? "border-[#087F73] ring-1 ring-[#087F73]/30 shadow-2xs"
                      : "border-[#DCE7E4] hover:border-[#087F73]/50",
                  )}
                >
                  {/* Tên tài liệu & Trang */}
                  <div className="flex items-start justify-between gap-1.5">
                    <div className="flex min-w-0 items-center gap-1.5">
                      <span
                        className={cn(
                          "inline-flex h-4.5 px-1 items-center justify-center rounded text-[10px] font-mono font-bold",
                          isSelected
                            ? "bg-[#087F73] text-white"
                            : "border border-[#DCE7E4] bg-[#F1F6F5] text-[#172B29]",
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
                      <span className="shrink-0 rounded border border-[#DCE7E4] bg-[#F1F6F5] px-1.5 py-0.5 text-[10px] font-medium text-[#172B29]">
                        Trang {evidence.pageNumber}
                      </span>
                    ) : null}
                  </div>

                  {/* Cảnh báo nếu tài liệu bị xóa */}
                  {!evidence.source.exists && evidence.source.kind === "local" ? (
                    <div className="mt-2 flex items-center gap-1 rounded bg-rose-50 p-1.5 text-[11px] text-rose-700">
                      <AlertCircle className="h-3 w-3 shrink-0" />
                      <span>Tài liệu đã bị xóa khỏi không gian.</span>
                    </div>
                  ) : null}

                  {/* Đoạn trích (Snippet) */}
                  <blockquote className="mt-2 rounded border-l-2 border-[#087F73] bg-[#F1F6F5] px-2 py-1.5 text-[11.5px] leading-relaxed text-[#172B29]">
                    &ldquo;{evidence.snippet || "Không có đoạn trích đính kèm."}&rdquo;
                  </blockquote>

                  {/* Nút xem chi tiết */}
                  <div className="mt-2 flex items-center justify-end">
                    {evidence.source.kind === "web" && evidence.source.url ? (
                      <a
                        href={evidence.source.url}
                        target="_blank"
                        rel="noreferrer"
                        onClick={(e) => e.stopPropagation()}
                        className="inline-flex items-center gap-1 text-[11px] font-semibold text-[#087F73] hover:underline"
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
                        className="inline-flex items-center gap-1 text-[11px] font-semibold text-[#087F73] hover:underline disabled:opacity-50"
                      >
                        <span>Xem chi tiết</span>
                        <ArrowUpRight className="h-3 w-3" />
                      </button>
                    ) : null}
                  </div>
                </article>
              )
            })
          )}
        </div>
      )}
    </aside>
  )
}
