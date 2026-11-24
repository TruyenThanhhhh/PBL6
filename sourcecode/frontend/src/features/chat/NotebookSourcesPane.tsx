import { useRef, useState } from "react"
import {
  BookOpen,
  Check,
  ChevronDown,
  ChevronRight,
  FileSpreadsheet,
  FileText,
  Loader2,
  PanelLeftClose,
  Plus,
  RefreshCw,
  Search,
  Sparkles,
  Wrench,
} from "lucide-react"
import Markdown from "react-markdown"
import remarkGfm from "remark-gfm"
import { Button, Tooltip } from "@/components/ui"
import {
  fetchDocumentGuideApi,
  fetchDocuments,
  rebuildDocumentApi,
  uploadDocumentWithProgress,
  type DocumentGuideResponse,
} from "@/services/api"
import { getAuthToken } from "@/services/auth-service"
import { useAppStore } from "@/store/app-store"
import type { KnowledgeDocument } from "@/types"
import { ACCEPTED_EXTENSIONS, fileKindFromName, formatBytes, nowIso, uid } from "@/utils/format"
import { cn } from "@/utils/cn"

interface NotebookSourcesPaneProps {
  workspaceId: string
  notebookId: string | null
  documents: KnowledgeDocument[]
  attachedDocIds: string[]
  onToggleDoc: (docId: string) => void
  onSelectAllDocs: () => void
  onClearDocs: () => void
  onAskQuestion: (prompt: string) => void
  onClose?: () => void
  busy?: boolean
}

export function NotebookSourcesPane({
  workspaceId,
  notebookId,
  documents,
  attachedDocIds,
  onToggleDoc,
  onSelectAllDocs,
  onClearDocs,
  onAskQuestion,
  onClose,
  busy = false,
}: NotebookSourcesPaneProps) {
  const fileInputRef = useRef<HTMLInputElement>(null)
  const addDocument = useAppStore((s) => s.addDocument)
  const replaceDocumentsFromBackend = useAppStore((s) => s.replaceDocumentsFromBackend)
  const updateSettings = useAppStore((s) => s.updateSettings)
  const toast = useAppStore((s) => s.toast)

  const [filterText, setFilterText] = useState("")
  const [uploadingName, setUploadingName] = useState<string | null>(null)
  const [uploadProgress, setUploadProgress] = useState<number>(0)
  const [expandedGuideId, setExpandedGuideId] = useState<string | null>(null)
  const [guideCache, setGuideCache] = useState<Record<string, DocumentGuideResponse>>({})
  const [loadingGuideId, setLoadingGuideId] = useState<string | null>(null)
  const [rebuildingDocId, setRebuildingDocId] = useState<string | null>(null)

  const filteredDocs = documents.filter((d) =>
    filterText.trim()
      ? d.fileName.toLowerCase().includes(filterText.trim().toLowerCase())
      : true,
  )

  const allSelected =
    documents.length > 0 && attachedDocIds.length === documents.length
  const usingAllImplicit = attachedDocIds.length === 0

  const handleToggleMaster = () => {
    if (allSelected) {
      onClearDocs()
    } else if (usingAllImplicit) {
      onSelectAllDocs()
    } else {
      onSelectAllDocs()
    }
  }

  const handleUploadFiles = async (fileList: FileList | null) => {
    if (!fileList || fileList.length === 0) return
    const files = Array.from(fileList)
    for (const file of files) {
      setUploadingName(file.name)
      setUploadProgress(5)
      try {
        if (getAuthToken()) {
          await uploadDocumentWithProgress(workspaceId, file, {
            notebookId,
            deferMetadata: files.length > 1,
            autoVersion: true,
            onProgress: (pct) => setUploadProgress(pct),
          })
          const freshDocs = await fetchDocuments(workspaceId)
          const otherDocs = useAppStore
            .getState()
            .documents.filter((d) => d.workspaceId !== workspaceId)
          replaceDocumentsFromBackend([...freshDocs, ...otherDocs])
          toast({
            title: "Đã thêm nguồn mới",
            description: `${file.name} đã sẵn sàng hỏi đáp ngay.`,
            tone: "success",
          })
        } else {
          addDocument({
            id: uid("doc"),
            workspaceId,
            notebookId,
            fileName: file.name,
            fileType: fileKindFromName(file.name),
            fileSize: file.size,
            status: "ready",
            createdAt: nowIso(),
            totalChunks: 1,
            pageCount: 1,
            extractedText: "",
            mock: true,
          })
          toast({
            title: "Đã thêm nguồn cục bộ",
            description: file.name,
            tone: "info",
          })
        }
      } catch (err) {
        toast({
          title: "Không thể tải tệp lên",
          description: err instanceof Error ? err.message : file.name,
          tone: "error",
        })
      } finally {
        setUploadingName(null)
        setUploadProgress(0)
      }
    }
    if (fileInputRef.current) {
      fileInputRef.current.value = ""
    }
    updateSettings({})
  }

  const handleToggleGuide = async (doc: KnowledgeDocument) => {
    if (expandedGuideId === doc.id) {
      setExpandedGuideId(null)
      return
    }
    setExpandedGuideId(doc.id)
    if (guideCache[doc.id] || doc.mock) return
    setLoadingGuideId(doc.id)
    try {
      const guide = await fetchDocumentGuideApi(doc.id)
      setGuideCache((prev) => ({ ...prev, [doc.id]: guide }))
    } catch {
      setGuideCache((prev) => ({
        ...prev,
        [doc.id]: {
          document_id: doc.id,
          file_name: doc.fileName,
          file_type: doc.fileType,
          total_pages: doc.pageCount,
          total_chunks: doc.totalChunks,
          doc_category: "general",
          summary: `Tài liệu **${doc.fileName}** (${doc.pageCount} trang · ${doc.totalChunks} phân đoạn).`,
          outline: [],
          suggested_questions: [
            `Tóm tắt các ý chính trong ${doc.fileName}`,
            `Liệt kê những định nghĩa hoặc công thức quan trọng nhất của ${doc.fileName}`,
          ],
        },
      }))
    } finally {
      setLoadingGuideId(null)
    }
  }

  const handleRebuildDoc = async (docId: string) => {
    setRebuildingDocId(docId)
    try {
      const res = await rebuildDocumentApi(docId)
      const freshGuide = await fetchDocumentGuideApi(docId)
      setGuideCache((prev) => ({ ...prev, [docId]: freshGuide }))
      toast({
        title: "Đã làm sạch & tối ưu chỉ mục",
        description: `${res.file_name}: ${res.total_chunks} phân đoạn sạch.`,
        tone: "success",
      })
    } catch (err) {
      toast({
        title: "Không thể tái tạo chỉ mục",
        description: err instanceof Error ? err.message : "Vui lòng thử lại",
        tone: "error",
      })
    } finally {
      setRebuildingDocId(null)
    }
  }

  return (
    <aside className="flex h-full w-full flex-col border-r border-[#DCE7E4] bg-[#F7FAF9] text-[#172B29]">
      {/* Header Nguồn tri thức (NotebookLM Sources Sidebar) */}
      <div className="flex h-11 shrink-0 items-center justify-between border-b border-[#DCE7E4] px-3">
        <div className="flex items-center gap-1.5 min-w-0">
          <BookOpen className="h-3.5 w-3.5 shrink-0 text-[#087F73]" />
          <span className="truncate text-xs font-semibold tracking-tight text-[#172B29]">
            Nguồn tri thức
          </span>
          <span className="rounded-full bg-[#E3F3EF] px-1.5 py-0.5 text-[10px] font-semibold text-[#087F73]">
            {documents.length}
          </span>
        </div>

        <div className="flex items-center gap-1">
          <input
            ref={fileInputRef}
            type="file"
            multiple
            accept={ACCEPTED_EXTENSIONS.join(",")}
            className="hidden"
            onChange={(e) => void handleUploadFiles(e.target.files)}
          />
          <Tooltip content="Thêm tài liệu mới vào Notebook" side="bottom">
            <Button
              type="button"
              size="sm"
              variant="outline"
              onClick={() => fileInputRef.current?.click()}
              disabled={Boolean(uploadingName)}
              className="h-7 gap-1 border-[#DCE7E4] bg-white px-2 text-[11px] font-medium text-[#087F73] hover:border-[#087F73] hover:bg-[#F1F6F5]"
            >
              {uploadingName ? (
                <Loader2 className="h-3 w-3 animate-spin" />
              ) : (
                <Plus className="h-3 w-3" />
              )}
              <span>Thêm nguồn</span>
            </Button>
          </Tooltip>
          {onClose ? (
            <button
              type="button"
              onClick={onClose}
              aria-label="Thu gọn cột nguồn"
              className="inline-flex h-7 w-7 items-center justify-center rounded-md text-[#647C79] transition hover:bg-white hover:text-[#172B29]"
            >
              <PanelLeftClose className="h-3.5 w-3.5" />
            </button>
          ) : null}
        </div>
      </div>

      {/* Thanh upload tiến trình */}
      {uploadingName ? (
        <div className="border-b border-[#DCE7E4] bg-[#E8F4F2] px-3 py-2">
          <div className="flex items-center justify-between text-[11px] font-medium text-[#087F73]">
            <span className="truncate">{uploadingName}</span>
            <span>{uploadProgress}%</span>
          </div>
          <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-white">
            <div
              className="h-full rounded-full bg-[#087F73] transition-all duration-200"
              style={{ width: `${uploadProgress}%` }}
            />
          </div>
        </div>
      ) : null}

      {/* Tìm nhanh & Checkbox chọn tất cả nguồn */}
      <div className="space-y-2 border-b border-[#DCE7E4] px-3 py-2.5">
        {documents.length > 3 ? (
          <div className="relative">
            <Search className="pointer-events-none absolute left-2.5 top-2 h-3 w-3 text-[#647C79]" />
            <input
              type="text"
              value={filterText}
              onChange={(e) => setFilterText(e.target.value)}
              placeholder="Lọc nhanh tên nguồn..."
              className="h-7 w-full rounded-md border border-[#DCE7E4] bg-white pr-2.5 pl-7 text-[11.5px] text-[#172B29] placeholder:text-[#647C79] focus:border-[#087F73] focus:outline-none"
            />
          </div>
        ) : null}

        <div className="flex items-center justify-between gap-2 text-[11px]">
          <button
            type="button"
            onClick={handleToggleMaster}
            disabled={documents.length === 0}
            className="flex items-center gap-1.5 font-medium text-[#172B29] hover:text-[#087F73] disabled:opacity-40"
          >
            <span
              className={cn(
                "flex h-3.5 w-3.5 items-center justify-center rounded border transition-colors",
                allSelected || usingAllImplicit
                  ? "border-[#087F73] bg-[#087F73] text-white"
                  : "border-[#B8CBC7] bg-white",
              )}
            >
              {allSelected || usingAllImplicit ? (
                <Check className="h-2.5 w-2.5 stroke-[3]" />
              ) : null}
            </span>
            <span>
              {usingAllImplicit
                ? `Tất cả nguồn (${documents.length})`
                : `Đang chọn ${attachedDocIds.length}/${documents.length} nguồn`}
            </span>
          </button>
          {attachedDocIds.length > 0 ? (
            <button
              type="button"
              onClick={onClearDocs}
              className="text-[10.5px] font-medium text-[#087F73] hover:underline"
            >
              Mặc định tất cả
            </button>
          ) : null}
        </div>
      </div>

      {/* Danh sách Nguồn + Source Guide mở rộng */}
      <div className="min-h-0 flex-1 space-y-1.5 overflow-y-auto p-2.5">
        {filteredDocs.length === 0 ? (
          <div className="rounded-xl border border-dashed border-[#DCE7E4] bg-white/70 p-4 text-center">
            <FileText className="mx-auto mb-1.5 h-6 w-6 text-[#647C79]/70" />
            <p className="text-xs font-medium text-[#172B29]">
              {documents.length === 0 ? "Chưa có nguồn nào" : "Không tìm thấy nguồn khớp"}
            </p>
            <p className="mt-1 text-[11px] leading-relaxed text-[#647C79]">
              Tải PDF, Word, Excel hoặc Markdown để AI đọc và trích dẫn chính xác.
            </p>
            {documents.length === 0 ? (
              <Button
                type="button"
                size="sm"
                onClick={() => fileInputRef.current?.click()}
                className="mt-2.5 h-7 bg-[#087F73] px-2.5 text-[11px] text-white hover:bg-[#076D63]"
              >
                <Plus className="mr-1 h-3 w-3" />
                Tải nguồn ngay
              </Button>
            ) : null}
          </div>
        ) : (
          filteredDocs.map((doc) => {
            const isChecked = usingAllImplicit || attachedDocIds.includes(doc.id)
            const isExpanded = expandedGuideId === doc.id
            const guide = guideCache[doc.id]
            const isLoadingGuide = loadingGuideId === doc.id
            const isSheet = doc.fileType === "xlsx" || doc.fileType === "xls" || doc.fileType === "csv"

            return (
              <div
                key={doc.id}
                className={cn(
                  "rounded-lg border bg-white transition-all",
                  attachedDocIds.includes(doc.id)
                    ? "border-[#087F73]/70 shadow-2xs ring-1 ring-[#087F73]/10"
                    : "border-[#DCE7E4] hover:border-[#B4CDC7]",
                )}
              >
                <div className="flex items-start gap-2 p-2">
                  <button
                    type="button"
                    onClick={() => onToggleDoc(doc.id)}
                    aria-label={`Chọn nguồn ${doc.fileName}`}
                    className={cn(
                      "mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded border transition-colors",
                      isChecked
                        ? "border-[#087F73] bg-[#087F73] text-white"
                        : "border-[#B8CBC7] bg-white hover:border-[#087F73]",
                    )}
                  >
                    {isChecked ? <Check className="h-2.5 w-2.5 stroke-[3]" /> : null}
                  </button>

                  <button
                    type="button"
                    onClick={() => void handleToggleGuide(doc)}
                    className="min-w-0 flex-1 text-left"
                  >
                    <div className="flex items-center gap-1.5">
                      {isSheet ? (
                        <FileSpreadsheet className="h-3.5 w-3.5 shrink-0 text-[#087F73]" />
                      ) : (
                        <FileText className="h-3.5 w-3.5 shrink-0 text-[#087F73]" />
                      )}
                      <span className="truncate text-[12px] font-medium text-[#172B29]">
                        {doc.fileName}
                      </span>
                    </div>
                    <div className="mt-0.5 flex items-center justify-between text-[10.5px] text-[#647C79]">
                      <span>
                        {doc.fileType.toUpperCase()} · {formatBytes(doc.fileSize)}
                        {doc.pageCount > 0 ? ` · ${doc.pageCount}tr` : ""}
                      </span>
                      <span className="inline-flex items-center gap-0.5 text-[10.5px] font-medium text-[#087F73]">
                        <span>Guide</span>
                        {isExpanded ? (
                          <ChevronDown className="h-3 w-3" />
                        ) : (
                          <ChevronRight className="h-3 w-3" />
                        )}
                      </span>
                    </div>
                  </button>
                </div>

                {/* Source Guide kiểu NotebookLM */}
                {isExpanded ? (
                  <div className="border-t border-[#DCE7E4] bg-[#F9FCFB] px-2.5 py-2.5 text-[11.5px]">
                    {isLoadingGuide ? (
                      <div className="flex items-center gap-1.5 py-2 text-[#647C79]">
                        <Loader2 className="h-3.5 w-3.5 animate-spin text-[#087F73]" />
                        <span>Đang tổng hợp Source Guide...</span>
                      </div>
                    ) : guide ? (
                      <div className="space-y-2.5">
                        <div className="markdown-body text-[11.5px] leading-relaxed text-[#172B29]">
                          <Markdown remarkPlugins={[remarkGfm]}>{guide.summary}</Markdown>
                        </div>

                        {guide.has_legacy_pua ? (
                          <div className="flex items-center justify-between gap-2 rounded-md border border-amber-300 bg-amber-50 px-2 py-1.5 text-[11px] text-amber-800">
                            <span>Phát hiện ký tự toán học cũ</span>
                            <button
                              type="button"
                              onClick={() => void handleRebuildDoc(doc.id)}
                              disabled={rebuildingDocId === doc.id}
                              className="inline-flex items-center gap-1 rounded bg-amber-600 px-2 py-0.5 text-[10.5px] font-semibold text-white hover:bg-amber-700 disabled:opacity-50"
                            >
                              {rebuildingDocId === doc.id ? (
                                <RefreshCw className="h-2.5 w-2.5 animate-spin" />
                              ) : (
                                <Wrench className="h-2.5 w-2.5" />
                              )}
                              <span>Làm sạch</span>
                            </button>
                          </div>
                        ) : null}

                        {guide.outline.length > 0 ? (
                          <div>
                            <p className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-[#647C79]">
                              Chủ đề / Chương trong nguồn
                            </p>
                            <div className="flex flex-wrap gap-1">
                              {guide.outline.slice(0, 8).map((sec, idx) => (
                                <button
                                  key={idx}
                                  type="button"
                                  disabled={busy}
                                  onClick={() =>
                                    onAskQuestion(`Nội dung chi tiết của ${sec} gồm những gì?`)
                                  }
                                  className="max-w-full truncate rounded-md border border-[#DCE7E4] bg-white px-2 py-1 text-left text-[10.5px] text-[#172B29] transition hover:border-[#087F73] hover:text-[#087F73] disabled:opacity-50"
                                  title={sec}
                                >
                                  {sec}
                                </button>
                              ))}
                            </div>
                          </div>
                        ) : null}

                        {guide.suggested_questions.length > 0 ? (
                          <div>
                            <p className="mb-1 flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wider text-[#087F73]">
                              <Sparkles className="h-2.5 w-2.5" />
                              <span>Gợi ý hỏi nhanh</span>
                            </p>
                            <div className="space-y-1">
                              {guide.suggested_questions.map((q, idx) => (
                                <button
                                  key={idx}
                                  type="button"
                                  disabled={busy}
                                  onClick={() => onAskQuestion(q)}
                                  className="block w-full rounded-md border border-[#DCE7E4]/80 bg-white px-2 py-1.5 text-left text-[11px] leading-snug text-[#172B29] transition hover:border-[#087F73] hover:bg-[#EBF6F3] disabled:opacity-50"
                                >
                                  {q}
                                </button>
                              ))}
                            </div>
                          </div>
                        ) : null}
                      </div>
                    ) : null}
                  </div>
                ) : null}
              </div>
            )
          })
        )}
      </div>

      {/* Footer nhanh kiểu NotebookLM */}
      {documents.length > 0 ? (
        <div className="shrink-0 border-t border-[#DCE7E4] bg-white/80 px-3 py-2 text-[10.5px] text-[#647C79]">
          Mẹo: Tick checkbox để khoanh vùng nguồn trả lời hoặc bấm <strong>Guide</strong> để xem mục lục nhanh.
        </div>
      ) : null}
    </aside>
  )
}
