import { useEffect, useRef, useState } from "react"
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
  Loader2,
  PanelRightClose,
  Quote,
  UploadCloud,
} from "lucide-react"
import type { Citation, KnowledgeDocument } from "@/types"
import { Badge, Button, Tooltip } from "@/components/ui"
import { readPlainTextIfPossible } from "@/features/documents/document-utils"
import { fetchDocuments, uploadDocumentWithProgress } from "@/services/api"
import {
  buildSourceViewerHref,
  parseDocumentChunks,
  resolveCitationEvidence,
} from "@/services/source-service"
import { buildUploadedDocument, useAppStore } from "@/store/app-store"
import { ACCEPTED_EXTENSIONS, formatBytes } from "@/utils/format"
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
  const currentWorkspaceId = useAppStore((s) => s.currentWorkspaceId)
  const addDocument = useAppStore((s) => s.addDocument)
  const replaceDocs = useAppStore((s) => s.replaceDocumentsFromBackend)
  const status = useAppStore((s) => s.status)
  const toast = useAppStore((s) => s.toast)
  const navigate = useNavigate()

  const fileInputRef = useRef<HTMLInputElement>(null)
  const [uploading, setUploading] = useState(false)

  // Mặc định: Khi chưa có câu trả lời (citations rỗng) -> hiển thị "overview" (Kho tài liệu)
  // Khi có câu trả lời có citations -> tự động hiển thị "citations" (Nguồn trích dẫn)
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

  const handleQuickUploadFiles = async (files: FileList | File[]) => {
    const list = Array.from(files)
    if (!list.length || uploading) return
    setUploading(true)
    const wsId = currentWorkspaceId || "ws_default"
    let uploadedCount = 0

    for (const file of list) {
      try {
        if (status.backendOnline) {
          await uploadDocumentWithProgress(wsId, file, { notebookId: null })
          uploadedCount += 1
        } else {
          const localDoc = buildUploadedDocument(file, wsId, null)
          const plain = await readPlainTextIfPossible(file)
          if (plain) {
            localDoc.extractedText = plain
            localDoc.pageCount = Math.max(1, Math.ceil(plain.length / 1200))
            localDoc.totalChunks = Math.max(1, Math.ceil(plain.length / 400))
          } else {
            localDoc.extractedText = `Nội dung trích xuất từ tài liệu "${file.name}". Hệ thống Hybrid RAG sử dụng văn bản này để chia đoạn (chunking) và đối chiếu trích dẫn theo từng trang.`
          }
          addDocument(localDoc)
          uploadedCount += 1
        }
      } catch (err) {
        toast({
          title: `Không thể tải tệp ${file.name}`,
          description: err instanceof Error ? err.message : String(err),
          tone: "error",
        })
      }
    }

    if (status.backendOnline && uploadedCount > 0) {
      try {
        const refreshed = await fetchDocuments(wsId)
        replaceDocs(refreshed)
      } catch {
        // Giữ nguyên nếu gọi lại lỗi
      }
    }

    if (uploadedCount > 0) {
      toast({
        title: `Đã thêm ${uploadedCount} tài liệu vào Kho tài liệu`,
        description: "Tài liệu đã sẵn sàng để truy xuất và hỏi đáp.",
        tone: "success",
      })
    }
    setUploading(false)
  }

  const readyDocs = workspaceDocuments.filter((d) => d.status === "ready")
  const totalChunks = workspaceDocuments.reduce((acc, d) => acc + (d.totalChunks || 0), 0)
  const totalBytes = workspaceDocuments.reduce((acc, d) => acc + (d.fileSize || 0), 0)

  const selectedCitation =
    citations.find((c) => c.refId === active) ?? citations[0] ?? null
  const activeEvidence = selectedCitation
    ? resolveCitationEvidence(selectedCitation, allDocuments)
    : null
  const activeDocObj = activeEvidence?.citation.documentId
    ? allDocuments.find((d) => d.id === activeEvidence.citation.documentId)
    : undefined
  const activeDocChunks = parseDocumentChunks(activeDocObj)

  return (
    <aside
      aria-label="Trung tâm Nguồn và Kho tài liệu"
      className="flex h-full w-full flex-col border-l border-slate-200/80 bg-[#F8FAFC] text-[13px]"
    >
      {/* Header của Cột Phải: 2 Tab Nguồn (Citation) & Kho tài liệu + Nút thu gọn */}
      <div className="flex h-12 shrink-0 items-center justify-between gap-2 border-b border-slate-200/80 bg-white px-3">
        <div className="flex items-center gap-1 rounded-xl bg-slate-100 p-0.5">
          <button
            type="button"
            onClick={() => setManualTab("citations")}
            className={cn(
              "inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1 text-xs font-medium transition-all",
              activeTab === "citations"
                ? "bg-white font-semibold text-[#2563EB] shadow-2xs"
                : "text-slate-600 hover:text-slate-900",
            )}
          >
            <Quote className="h-3 w-3" />
            <span>Nguồn ({citations.length})</span>
          </button>

          <button
            type="button"
            onClick={() => setManualTab("overview")}
            className={cn(
              "inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1 text-xs font-medium transition-all",
              activeTab === "overview"
                ? "bg-white font-semibold text-[#2563EB] shadow-2xs"
                : "text-slate-600 hover:text-slate-900",
            )}
          >
            <Layers className="h-3 w-3" />
            <span>Kho tài liệu ({workspaceDocuments.length})</span>
          </button>
        </div>

        <Tooltip content="Thu gọn cột phải" side="left">
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7 text-slate-500 hover:bg-slate-100 hover:text-slate-900"
            onClick={onClose}
            aria-label="Thu gọn Context Panel"
          >
            <PanelRightClose className="h-4 w-4" />
          </Button>
        </Tooltip>
      </div>

      {/* =====================================================================
          TAB 1: NGUỒN (CITATION) — Hiển thị trang PDF & Highlight đoạn Chunk
      ===================================================================== */}
      {activeTab === "citations" ? (
        citations.length === 0 ? (
          <div className="flex flex-1 flex-col items-center justify-center p-6 text-center">
            <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-xl border border-blue-100 bg-[#EFF6FF] text-[#2563EB]">
              <Quote className="h-4.5 w-4.5" />
            </div>
            <p className="text-sm font-semibold text-slate-900">
              Chưa có trích dẫn đang chọn
            </p>
            <p className="mt-1 max-w-[230px] text-xs leading-relaxed text-slate-500">
              Khi bấm vào số trích dẫn <span className="font-mono font-semibold text-[#2563EB]">[1]</span> trong câu trả lời, trang tài liệu và đoạn chunk tương ứng sẽ được highlight tại đây.
            </p>
            <button
              type="button"
              onClick={() => setManualTab("overview")}
              className="mt-4 inline-flex items-center gap-1.5 rounded-full border border-[#BFDBFE] bg-[#EFF6FF] px-3.5 py-1.5 text-xs font-semibold text-[#2563EB] transition-colors hover:bg-blue-100"
            >
              <span>Mở Kho tài liệu ({workspaceDocuments.length})</span>
            </button>
          </div>
        ) : (
          <div className="studio-scroll flex-1 space-y-3.5 overflow-y-auto p-3.5">
            {/* Thanh chọn nhanh các số trích dẫn [1], [2]... */}
            <div className="flex flex-wrap items-center gap-1.5">
              {citations.map((c) => {
                const isSelected = selectedCitation?.refId === c.refId
                return (
                  <button
                    key={`${c.sourceId ?? c.documentId ?? "web"}-${c.refId}`}
                    type="button"
                    onClick={() => setActive(c.refId)}
                    className={cn(
                      "inline-flex items-center gap-1 rounded-lg border px-2.5 py-1 text-xs font-semibold transition-all",
                      isSelected
                        ? "border-[#2563EB] bg-[#2563EB] text-white shadow-2xs"
                        : "border-slate-200 bg-white text-slate-700 hover:border-[#2563EB]/50 hover:text-[#2563EB]",
                    )}
                  >
                    <span className="font-mono">[{c.refId}]</span>
                    {c.pageNumber != null ? (
                      <span className={cn("text-[10px]", isSelected ? "text-blue-100" : "text-slate-400")}>
                        Tr.{c.pageNumber}
                      </span>
                    ) : null}
                  </button>
                )
              })}
            </div>

            {/* Chi tiết Nguồn & Highlight đoạn Chunk trên trang PDF */}
            {activeEvidence ? (
              <div className="space-y-3 rounded-2xl border border-slate-200 bg-white p-3.5 shadow-2xs">
                <div className="flex items-start justify-between gap-2">
                  <div className="flex min-w-0 items-start gap-2">
                    {activeEvidence.source.kind === "web" ? (
                      <Globe className="mt-0.5 h-4 w-4 shrink-0 text-[#2563EB]" />
                    ) : (
                      <FileText className="mt-0.5 h-4 w-4 shrink-0 text-[#2563EB]" />
                    )}
                    <div className="min-w-0">
                      <h4 className="truncate text-xs font-bold text-slate-900">
                        {activeEvidence.source.title}
                      </h4>
                      <div className="mt-1 flex flex-wrap items-center gap-1.5">
                        {activeEvidence.pageNumber != null ? (
                          <span className="rounded-md bg-[#EFF6FF] px-2 py-0.5 text-[11px] font-semibold text-[#2563EB]">
                            Trang {activeEvidence.pageNumber}
                          </span>
                        ) : null}
                        {activeEvidence.chunkId ? (
                          <Badge tone="neutral">{activeEvidence.chunkId}</Badge>
                        ) : null}
                      </div>
                    </div>
                  </div>
                </div>

                {!activeEvidence.source.exists && activeEvidence.source.kind === "local" ? (
                  <div className="flex items-start gap-1.5 rounded-lg border border-rose-200 bg-rose-50 p-2 text-[11px] text-rose-700">
                    <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                    <span>Tài liệu gốc đã bị xóa khỏi Workspace.</span>
                  </div>
                ) : null}

                {/* Đoạn Chunk được Highlight */}
                <div>
                  <div className="mb-1 flex items-center justify-between text-[11px] font-semibold text-[#2563EB]">
                    <span>Đoạn trích được highlight</span>
                    {activeEvidence.pageNumber != null ? (
                      <span>PDF · Trang {activeEvidence.pageNumber}</span>
                    ) : null}
                  </div>
                  <blockquote className="rounded-xl border border-[#BFDBFE] border-l-4 border-l-[#2563EB] bg-[#EFF6FF]/70 px-3 py-2.5 text-xs leading-relaxed text-slate-800">
                    &ldquo;{activeEvidence.snippet || "Không có đoạn trích đính kèm."}&rdquo;
                  </blockquote>
                </div>

                {/* Khung xem ngữ cảnh các đoạn (chunks) trên trang tài liệu */}
                {activeDocChunks.length > 0 ? (
                  <div className="space-y-1.5 border-t border-slate-100 pt-2.5">
                    <span className="text-[11px] font-semibold text-slate-500">
                      Ngữ cảnh trong tài liệu ({activeDocChunks.length} đoạn)
                    </span>
                    <div className="max-h-48 space-y-1.5 overflow-y-auto rounded-xl border border-slate-100 bg-slate-50/70 p-2">
                      {activeDocChunks.slice(0, 6).map((chunk) => {
                        const isMatchedChunk =
                          chunk.index === selectedCitation?.chunkIndex ||
                          chunk.page === activeEvidence.pageNumber
                        return (
                          <div
                            key={chunk.id}
                            className={cn(
                              "rounded-lg p-2 text-[11px] leading-relaxed transition-colors",
                              isMatchedChunk
                                ? "border border-[#BFDBFE] bg-[#EFF6FF] font-medium text-slate-900"
                                : "bg-white text-slate-500",
                            )}
                          >
                            <div className="mb-0.5 flex items-center justify-between font-mono text-[10px] text-slate-400">
                              <span>{chunk.id}</span>
                              <span>Trang {chunk.page}</span>
                            </div>
                            <p className="line-clamp-3">{chunk.content}</p>
                          </div>
                        )
                      })}
                    </div>
                  </div>
                ) : null}

                {/* Nút mở Source Viewer toàn màn hình */}
                <div className="flex items-center justify-end pt-1">
                  {activeEvidence.source.kind === "web" && activeEvidence.source.url ? (
                    <a
                      href={activeEvidence.source.url}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-flex items-center gap-1 rounded-lg bg-[#2563EB] px-3 py-1.5 text-xs font-semibold text-white transition-colors hover:bg-[#1D4ED8]"
                    >
                      <span>Mở trang Web</span>
                      <ExternalLink className="h-3 w-3" />
                    </a>
                  ) : activeEvidence.citation.documentId ? (
                    <button
                      type="button"
                      disabled={!activeEvidence.source.exists}
                      onClick={() => {
                        const href = buildSourceViewerHref(
                          activeEvidence.citation,
                          conversationId,
                        )
                        if (href) navigate(href)
                      }}
                      className="inline-flex items-center gap-1 rounded-lg bg-[#2563EB] px-3 py-1.5 text-xs font-semibold text-white transition-colors hover:bg-[#1D4ED8] disabled:opacity-50"
                    >
                      <span>Mở trang PDF chi tiết</span>
                      <ArrowUpRight className="h-3.5 w-3.5" />
                    </button>
                  ) : null}
                </div>
              </div>
            ) : null}
          </div>
        )
      ) : (
        /* ===================================================================
            TAB 2: KHO TÀI LIỆU — Upload nhanh & Tích chọn file để hỏi đáp
        =================================================================== */
        <div className="studio-scroll flex-1 space-y-4 overflow-y-auto p-3.5">
          {/* Input file ẩn cho nút Upload nhanh */}
          <input
            ref={fileInputRef}
            type="file"
            multiple
            accept={ACCEPTED_EXTENSIONS.join(",")}
            className="hidden"
            onChange={(e) => {
              if (e.target.files) {
                void handleQuickUploadFiles(e.target.files)
                e.target.value = ""
              }
            }}
          />

          {/* Thẻ tóm tắt + Nút tải lên tài liệu trực tiếp */}
          <div className="rounded-2xl border border-slate-200 bg-white p-3.5 shadow-2xs">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-slate-900">Kho tài liệu Workspace</span>
              <span className="inline-flex items-center gap-1.5 rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-semibold text-slate-700">
                <span className="h-1.5 w-1.5 rounded-full bg-[#10B981]" />
                {readyDocs.length}/{workspaceDocuments.length} sẵn sàng
              </span>
            </div>

            <div className="mt-2.5 grid grid-cols-2 gap-2">
              <div className="rounded-xl bg-slate-50 px-3 py-2">
                <div className="text-base font-bold text-slate-900">{totalChunks}</div>
                <div className="text-[11px] text-slate-500">Chunks chỉ mục</div>
              </div>
              <div className="rounded-xl bg-slate-50 px-3 py-2">
                <div className="text-base font-bold text-slate-900">
                  {totalBytes > 0 ? formatBytes(totalBytes) : "0 B"}
                </div>
                <div className="text-[11px] text-slate-500">Dung lượng</div>
              </div>
            </div>

            <div className="mt-3 flex items-center gap-2">
              <button
                type="button"
                disabled={uploading}
                onClick={() => fileInputRef.current?.click()}
                className="inline-flex flex-1 items-center justify-center gap-1.5 rounded-xl bg-[#2563EB] py-2 text-xs font-semibold text-white transition-colors hover:bg-[#1D4ED8] disabled:opacity-60"
              >
                {uploading ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <UploadCloud className="h-3.5 w-3.5" />
                )}
                <span>{uploading ? "Đang tải lên..." : "Tải tài liệu lên"}</span>
              </button>

              <Tooltip content="Mở trình quản lý tài liệu đầy đủ" side="bottom">
                <button
                  type="button"
                  onClick={() => navigate("/documents")}
                  className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-xl border border-slate-200 bg-white text-slate-600 transition-colors hover:border-[#2563EB] hover:text-[#2563EB]"
                  aria-label="Quản lý tài liệu"
                >
                  <FileUp className="h-3.5 w-3.5" />
                </button>
              </Tooltip>
            </div>
          </div>

          {/* Danh sách tài liệu kèm ô tích chọn (Checkbox) để giới hạn phạm vi hỏi */}
          <div className="space-y-2">
            <div className="flex items-center justify-between px-0.5">
              <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">
                Tích chọn file để hỏi ({attachedDocIds.length || "Tất cả"})
              </span>
              { workspaceDocuments.length > 0 ? (
                <button
                  type="button"
                  onClick={() => navigate("/documents")}
                  className="text-[11px] font-semibold text-[#2563EB] hover:underline"
                >
                  Quản lý
                </button>
              ) : null }
            </div>

            {workspaceDocuments.length === 0 ? (
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                className="flex w-full flex-col items-center justify-center rounded-2xl border-2 border-dashed border-slate-200 bg-white p-6 text-center transition-colors hover:border-[#2563EB] hover:bg-[#EFF6FF]/40"
              >
                <UploadCloud className="mb-2 h-6 w-6 text-[#2563EB]" />
                <p className="text-xs font-semibold text-slate-800">
                  Chưa có tài liệu trong Workspace
                </p>
                <p className="mt-0.5 text-[11px] text-slate-500">
                  Bấm để chọn tệp PDF, DOCX, TXT, MD
                </p>
              </button>
            ) : (
              <div className="space-y-2">
                {workspaceDocuments.map((doc) => {
                  const isAttached = attachedDocIds.includes(doc.id)
                  return (
                    <div
                      key={doc.id}
                      className={cn(
                        "group flex items-start gap-2.5 rounded-xl border bg-white p-2.5 transition-all",
                        isAttached
                          ? "border-[#2563EB] bg-[#EFF6FF]/50 ring-1 ring-[#BFDBFE]"
                          : "border-slate-200/90 hover:border-[#2563EB]/40",
                      )}
                    >
                      {/* Checkbox tích chọn tài liệu vào phạm vi câu hỏi */}
                      {onToggleAttachDoc ? (
                        <button
                          type="button"
                          onClick={() => onToggleAttachDoc(doc.id)}
                          aria-label={`Chọn ${doc.fileName} để hỏi`}
                          className={cn(
                            "mt-0.5 flex h-4.5 w-4.5 shrink-0 items-center justify-center rounded border transition-colors",
                            isAttached
                              ? "border-[#2563EB] bg-[#2563EB] text-white"
                              : "border-slate-300 bg-white hover:border-[#2563EB]",
                          )}
                        >
                          {isAttached ? <Check className="h-3 w-3 stroke-[2.5]" /> : null}
                        </button>
                      ) : null}

                      <button
                        type="button"
                        onClick={() => navigate(`/documents/${doc.id}`)}
                        className="min-w-0 flex-1 text-left"
                      >
                        <div className="flex items-center gap-1.5">
                          <span
                            className={cn(
                              "h-1.5 w-1.5 shrink-0 rounded-full",
                              doc.status === "ready"
                                ? "bg-[#10B981]"
                                : doc.status === "failed"
                                  ? "bg-rose-500"
                                  : "bg-amber-400",
                            )}
                          />
                          <p className="truncate text-xs font-semibold text-slate-900 group-hover:text-[#2563EB]">
                            {doc.fileName}
                          </p>
                        </div>
                        <p className="mt-0.5 pl-3 text-[11px] text-slate-500">
                          {doc.pageCount ? `${doc.pageCount} trang · ` : ""}
                          {doc.totalChunks ?? 0} chunks · {formatBytes(doc.fileSize)}
                        </p>
                      </button>
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
