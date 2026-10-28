import { useNavigate, useParams } from "react-router-dom"
import { AlertCircle, ExternalLink, FileText, Globe, X } from "lucide-react"
import type { Citation } from "@/types"
import { Button, Badge } from "@/components/ui"
import { useAppStore } from "@/store/app-store"
import { buildSourceViewerHref, resolveCitationEvidence } from "@/services/source-service"

export function CitationPanel({
  citations,
  onClose,
}: {
  citations: Citation[]
  onClose: () => void
}) {
  const { conversationId } = useParams()
  const active = useAppStore((s) => s.activeCitation)
  const setActive = useAppStore((s) => s.setActiveCitation)
  const documents = useAppStore((s) => s.documents)
  const navigate = useNavigate()

  const selectedCitation =
    citations.find((c) => c.refId === active) ?? citations[0] ?? null
  const evidence = selectedCitation
    ? resolveCitationEvidence(selectedCitation, documents)
    : null

  return (
    <aside className="flex h-full w-full flex-col border-l border-line bg-bg text-[13px]">
      <div className="flex h-12 shrink-0 items-center justify-between border-b border-line px-3.5">
        <span className="font-semibold text-ink">Nguồn trích dẫn ({citations.length})</span>
        <Button
          variant="ghost"
          size="icon"
          className="h-7 w-7"
          onClick={onClose}
          aria-label="Đóng bảng nguồn"
        >
          <X className="h-4 w-4" />
        </Button>
      </div>

      {citations.length === 0 ? (
        <div className="p-4 text-muted">
          Không có bằng chứng trích dẫn cho câu trả lời này.
        </div>
      ) : (
        <>
          {/* Danh sách chọn nhanh Citation theo refId ổn định */}
          <div className="flex shrink-0 gap-1 overflow-x-auto border-b border-line px-3 py-2">
            {citations.map((c) => {
              const isSelected = selectedCitation?.refId === c.refId
              return (
                <button
                  key={`${c.sourceId ?? c.documentId ?? "web"}-${c.refId}`}
                  type="button"
                  onClick={() => setActive(c.refId)}
                  className={`rounded px-2 py-1 text-xs transition-colors ${
                    isSelected
                      ? "bg-bg-active font-semibold text-ink"
                      : "text-muted hover:bg-bg-hover hover:text-ink"
                  }`}
                >
                  [{c.refId}]
                </button>
              )
            })}
          </div>

          {evidence ? (
            <div className="flex-1 space-y-4 overflow-y-auto p-4">
              {/* Tên nguồn & Metadata tối thiểu */}
              <div>
                <div className="flex items-start gap-2">
                  {evidence.source.kind === "web" ? (
                    <Globe className="mt-0.5 h-4 w-4 shrink-0 text-muted" />
                  ) : (
                    <FileText className="mt-0.5 h-4 w-4 shrink-0 text-muted" />
                  )}
                  <p className="font-semibold leading-snug text-ink">{evidence.source.title}</p>
                </div>

                <div className="mt-2 flex flex-wrap items-center gap-1.5">
                  <Badge tone="neutral">
                    {evidence.source.kind === "web" ? "Nguồn: Web" : "Nguồn: Local"}
                  </Badge>
                  {evidence.pageNumber != null ? (
                    <Badge tone="neutral">Trang {evidence.pageNumber}</Badge>
                  ) : null}
                  {evidence.chunkId ? (
                    <Badge tone="neutral">{evidence.chunkId}</Badge>
                  ) : null}
                  {evidence.source.isMock ? (
                    <Badge tone="warning">Dữ liệu demo</Badge>
                  ) : null}
                </div>
              </div>

              {/* Cảnh báo nếu tài liệu gốc đã bị xóa */}
              {!evidence.source.exists && evidence.source.kind === "local" ? (
                <div className="flex items-start gap-2 rounded-md border border-error/40 bg-error-soft/40 p-2.5 text-xs text-error">
                  <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                  <span>
                    Tài liệu nguồn này đã bị xóa hoặc không còn tồn tại trong kho tri thức.
                  </span>
                </div>
              ) : null}

              {/* URL nếu là nguồn Web */}
              {evidence.source.url ? (
                <div>
                  <p className="mb-1 text-[11px] uppercase tracking-wide text-muted">Địa chỉ URL</p>
                  <a
                    href={evidence.source.url}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center gap-1 break-all text-xs text-ink underline hover:text-muted"
                  >
                    <span>{evidence.source.url}</span>
                    <ExternalLink className="h-3 w-3 shrink-0" />
                  </a>
                </div>
              ) : null}

              {/* Đoạn trích liên quan */}
              <div>
                <p className="mb-1.5 text-[11px] uppercase tracking-wide text-muted">
                  Đoạn trích liên quan
                </p>
                <blockquote className="rounded-r-md border-l-2 border-ink bg-bg-secondary/60 px-3 py-2.5 text-[13px] leading-relaxed text-ink">
                  {evidence.snippet || "Không có đoạn trích đính kèm."}
                </blockquote>
                {!evidence.hasExactOffset ? (
                  <p className="mt-1.5 text-[11px] text-muted">
                    Định vị theo đoạn văn (chunk/trang); chưa có dữ liệu byte-offset từ parser.
                  </p>
                ) : null}
              </div>

              {/* Hành động mở Source Viewer */}
              {evidence.source.kind === "local" && evidence.citation.documentId ? (
                <div className="pt-1">
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={!evidence.source.exists}
                    onClick={() => {
                      const href = buildSourceViewerHref(evidence.citation, conversationId)
                      if (href) navigate(href)
                    }}
                  >
                    {evidence.source.exists ? "Mở trong Source Viewer" : "Nguồn không khả dụng"}
                  </Button>
                </div>
              ) : null}
            </div>
          ) : null}
        </>
      )}
    </aside>
  )
}
