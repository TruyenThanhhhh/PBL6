import { useMemo, useState } from "react"
import { useNavigate, useParams, useSearchParams } from "react-router-dom"
import Markdown from "react-markdown"
import remarkGfm from "remark-gfm"
import {
  ArrowLeft,
  Download,
  ExternalLink,
  FileText,
  Globe,
  MessageSquare,
  MoreHorizontal,
  Pencil,
  Search,
  Trash2,
} from "lucide-react"
import { InlineEdit } from "@/components/common/InlineEdit"
import { ConfirmDialog, NameDialog } from "@/components/common/NameDialog"
import {
  Badge,
  Button,
  DropdownMenu,
  DropdownMenuItem,
  DropdownMenuSeparator,
  EmptyState,
  Input,
  Select,
  StatusBadge,
} from "@/components/ui"
import { downloadExtractedText } from "@/features/documents/document-utils"
import { deleteDocumentApi } from "@/services/api"
import { parseDocumentChunks } from "@/services/source-service"
import { useAppStore } from "@/store/app-store"
import { formatBytes, formatDate } from "@/utils/format"

export function SourceViewerPage() {
  const { documentId } = useParams()
  const [params] = useSearchParams()
  const navigate = useNavigate()

  const documents = useAppStore((s) => s.documents)
  const conversations = useAppStore((s) => s.conversations)
  const workspaces = useAppStore((s) => s.workspaces)
  const notebooks = useAppStore((s) => s.notebooks)
  const updateDocument = useAppStore((s) => s.updateDocument)
  const deleteDocument = useAppStore((s) => s.deleteDocument)
  const status = useAppStore((s) => s.status)
  const toast = useAppStore((s) => s.toast)

  const doc = documents.find((d) => d.id === documentId)

  const citeParam = params.get("cite")
  const pageParam = params.get("page")
  const chunkParam = params.get("chunk")
  const fromChatId = params.get("fromChat")

  const [q, setQ] = useState("")
  const [selectedPage, setSelectedPage] = useState<number>(() => {
    const p = Number(pageParam)
    return Number.isFinite(p) && p > 0 ? p : 1
  })
  const [renameOpen, setRenameOpen] = useState(false)
  const [deleteOpen, setDeleteOpen] = useState(false)

  const citation = useMemo(() => {
    if (!citeParam) return undefined
    return conversations
      .flatMap((c) => c.messages.flatMap((m) => m.citations))
      .find(
        (c) =>
          String(c.refId) === citeParam &&
          (c.documentId === documentId || c.sourceId === documentId),
      )
  }, [conversations, citeParam, documentId])

  const chunks = useMemo(() => parseDocumentChunks(doc), [doc])

  const filteredChunks = useMemo(() => {
    const kw = q.trim().toLowerCase()
    if (!kw) return chunks
    return chunks.filter((c) => c.content.toLowerCase().includes(kw))
  }, [chunks, q])

  if (!doc) {
    // Trường hợp nguồn Web hoặc tài liệu đã bị xóa
    if (citation && citation.sourceKind === "web") {
      return (
        <div className="mx-auto max-w-3xl px-4 py-10 md:px-8">
          <div className="mb-4 flex items-center justify-between">
            <Button
              variant="ghost"
              size="sm"
              leftIcon={<ArrowLeft className="h-3.5 w-3.5" />}
              onClick={() => navigate(fromChatId ? `/chat/${fromChatId}` : "/chat")}
            >
              Quay lại hội thoại
            </Button>
          </div>
          <div className="rounded-lg border border-line bg-bg p-6">
            <div className="flex items-center gap-2">
              <Globe className="h-4 w-4 text-muted" />
              <h1 className="text-lg font-semibold text-ink">{citation.documentName}</h1>
              <Badge tone="neutral">Nguồn Web</Badge>
            </div>
            {citation.url ? (
              <a
                href={citation.url}
                target="_blank"
                rel="noreferrer"
                className="mt-2 inline-flex items-center gap-1 text-xs text-ink underline"
              >
                <span>{citation.url}</span>
                <ExternalLink className="h-3 w-3" />
              </a>
            ) : null}
            <blockquote className="mt-4 border-l-2 border-ink pl-3 text-sm text-ink">
              {citation.snippet}
            </blockquote>
          </div>
        </div>
      )
    }

    return (
      <div className="mx-auto max-w-3xl px-4 py-12 md:px-8">
        <EmptyState
          icon={<FileText className="h-5 w-5" />}
          title="Nguồn tài liệu không tồn tại hoặc không thể mở"
          description="Tài liệu này có thể đã bị xóa khỏi workspace hoặc đường dẫn không hợp lệ."
          action={
            <div className="flex items-center gap-2">
              {fromChatId ? (
                <Button
                  variant="default"
                  onClick={() => navigate(`/chat/${fromChatId}`)}
                >
                  Quay lại hội thoại
                </Button>
              ) : null}
              <Button variant="outline" onClick={() => navigate("/documents")}>
                Về danh sách tài liệu
              </Button>
            </div>
          }
        />
      </div>
    )
  }

  const siblingDocs = documents.filter((d) => d.workspaceId === doc.workspaceId)
  const wsNotebooks = notebooks.filter((n) => n.workspaceId === doc.workspaceId)
  const isPlainMarkdown = doc.fileType === "md" && !q.trim() && !citeParam

  const visibleChunks =
    q.trim() !== "" || doc.pageCount <= 1
      ? filteredChunks
      : filteredChunks.filter((c) => c.page === selectedPage)

  const highlightText = (text: string) => {
    const needle = citation?.highlight || q.trim()
    if (!needle) return text
    const i = text.toLowerCase().indexOf(needle.toLowerCase())
    if (i < 0) return text
    return (
      <>
        {text.slice(0, i)}
        <mark className="rounded bg-bg-active px-1 py-0.5 font-medium text-ink">
          {text.slice(i, i + needle.length)}
        </mark>
        {text.slice(i + needle.length)}
      </>
    )
  }

  const handleRename = (nextName: string) => {
    const trimmed = nextName.trim()
    if (!trimmed) return
    updateDocument(doc.id, { fileName: trimmed })
    toast({ title: "Đã đổi tên tài liệu", tone: "success" })
  }

  const handleDelete = async () => {
    try {
      if (status.backendOnline && !doc.mock) {
        await deleteDocumentApi(doc.id)
      }
    } catch {
      toast({
        title: "Không xóa được trên máy chủ, đã xóa khỏi giao diện",
        tone: "warning",
      })
    }
    deleteDocument(doc.id)
    toast({ title: "Đã xóa tài liệu", tone: "info" })
    navigate("/documents")
  }

  const handleDownload = () => {
    if (!downloadExtractedText(doc)) {
      toast({
        title: "Chưa có văn bản trích xuất để tải xuống",
        tone: "warning",
      })
    }
  }

  return (
    <div className="mx-auto max-w-5xl px-4 py-6 md:px-8">
      {/* Thanh điều hướng trên: Quay lại tài liệu / Quay lại hội thoại + Chuyển nguồn nhanh */}
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Button
            variant="ghost"
            size="sm"
            leftIcon={<ArrowLeft className="h-3.5 w-3.5" />}
            onClick={() => navigate("/documents")}
          >
            Tài liệu
          </Button>
          {fromChatId ? (
            <Button
              variant="outline"
              size="sm"
              leftIcon={<MessageSquare className="h-3.5 w-3.5" />}
              onClick={() => navigate(`/chat/${fromChatId}`)}
            >
              Quay lại hội thoại
            </Button>
          ) : null}
        </div>

        {/* Chuyển nguồn nhanh trong cùng Workspace */}
        {siblingDocs.length > 1 ? (
          <div className="flex items-center gap-2 text-xs">
            <span className="text-muted">Chuyển nguồn:</span>
            <Select
              aria-label="Chuyển sang tài liệu khác"
              value={doc.id}
              onChange={(e) => {
                const nextId = e.target.value
                const suffix = fromChatId ? `?fromChat=${fromChatId}` : ""
                navigate(`/documents/${nextId}${suffix}`)
              }}
              className="h-7 w-48 text-xs"
            >
              {siblingDocs.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.fileName}
                </option>
              ))}
            </Select>
          </div>
        ) : null}
      </div>

      {/* Tiêu đề tài liệu & Hành động */}
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3 border-b border-line pb-4">
        <div className="min-w-0 flex-1">
          <InlineEdit
            value={doc.fileName}
            ariaLabel="Tên tài liệu"
            validate={(next) => (!next.trim() ? "Tên không được để trống." : null)}
            onSave={handleRename}
            className="text-xl font-semibold tracking-tight text-ink"
            inputClassName="text-lg font-semibold"
          />
          <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted">
            <span className="font-medium uppercase text-ink">{doc.fileType}</span>
            <span>·</span>
            <span>{formatBytes(doc.fileSize)}</span>
            <span>·</span>
            <span>{doc.pageCount} trang</span>
            <span>·</span>
            <span>Tải lên {formatDate(doc.createdAt)}</span>
          </div>
        </div>

        <div className="flex items-center gap-1.5">
          <StatusBadge status={doc.status} />
          <DropdownMenu
            align="end"
            trigger={
              <Button variant="outline" size="icon" className="h-8 w-8" aria-label="Thao tác tài liệu">
                <MoreHorizontal className="h-4 w-4" />
              </Button>
            }
          >
            <DropdownMenuItem
              icon={<Pencil className="h-3.5 w-3.5" />}
              onClick={() => setRenameOpen(true)}
            >
              Đổi tên tài liệu
            </DropdownMenuItem>
            <DropdownMenuItem
              icon={<Download className="h-3.5 w-3.5" />}
              disabled={!doc.extractedText?.trim()}
              onClick={handleDownload}
            >
              Tải văn bản trích xuất
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem
              tone="danger"
              icon={<Trash2 className="h-3.5 w-3.5" />}
              onClick={() => setDeleteOpen(true)}
            >
              Xóa tài liệu
            </DropdownMenuItem>
          </DropdownMenu>
        </div>
      </div>

      {/* Thanh chọn nhanh Workspace & Notebook */}
      <div className="mb-5 flex flex-wrap items-center gap-3 text-xs">
        <div className="flex items-center gap-1.5">
          <span className="text-muted">Workspace:</span>
          <Select
            aria-label="Workspace liên quan"
            value={doc.workspaceId}
            onChange={(e) => updateDocument(doc.id, { workspaceId: e.target.value, notebookId: null })}
            className="h-7 w-44 text-xs"
          >
            {workspaces.map((w) => (
              <option key={w.id} value={w.id}>
                {w.name}
              </option>
            ))}
          </Select>
        </div>

        <div className="flex items-center gap-1.5">
          <span className="text-muted">Notebook:</span>
          <Select
            aria-label="Notebook liên quan"
            value={doc.notebookId ?? ""}
            onChange={(e) => updateDocument(doc.id, { notebookId: e.target.value || null })}
            className="h-7 w-44 text-xs"
          >
            <option value="">Chưa gắn notebook</option>
            {wsNotebooks.map((n) => (
              <option key={n.id} value={n.id}>
                {n.name}
              </option>
            ))}
          </Select>
        </div>

        {doc.fileType === "pdf" ? (
          <span className="ml-auto text-muted">
            Đang hiển thị văn bản trích xuất theo trang (chưa có luồng file PDF nhị phân từ máy chủ).
          </span>
        ) : null}
      </div>

      {/* Thông báo khi đang xem trích dẫn từ AI Chat */}
      {citation ? (
        <div className="mb-5 flex flex-wrap items-center justify-between gap-2 rounded-md border border-line bg-bg-secondary px-3 py-2 text-xs">
          <div>
            <span className="font-semibold text-ink">Đang đối chiếu trích dẫn [{citation.refId}]:</span>{" "}
            <span className="text-muted">
              {citation.pageNumber ? `Trang ${citation.pageNumber}` : "Toàn văn"}
              {citation.chunkIndex ? ` · Chunk #${citation.chunkIndex}` : ""}
            </span>
          </div>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => navigate(`/documents/${doc.id}`)}
          >
            Bỏ lọc trích dẫn
          </Button>
        </div>
      ) : null}

      {/* Nội dung chính & Danh sách Chunks */}
      <div className="flex flex-col gap-6 md:flex-row">
        <div className="min-w-0 flex-1">
          {doc.pageCount > 1 && !q.trim() && !isPlainMarkdown ? (
            <div className="mb-3 flex items-center justify-between border-b border-line pb-2 text-xs">
              <span className="font-medium text-ink">
                Trang {selectedPage} / {doc.pageCount}
              </span>
              <div className="flex items-center gap-1.5">
                <Button
                  variant="outline"
                  size="sm"
                  disabled={selectedPage <= 1}
                  onClick={() => setSelectedPage((p) => p - 1)}
                >
                  Trước
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={selectedPage >= doc.pageCount}
                  onClick={() => setSelectedPage((p) => p + 1)}
                >
                  Sau
                </Button>
              </div>
            </div>
          ) : null}

          {!doc.extractedText?.trim() ? (
            <EmptyState
              compact
              title="Chưa có nội dung trích xuất"
              description="Tài liệu đang chờ xử lý hoặc trích xuất thất bại."
            />
          ) : isPlainMarkdown ? (
            <article className="markdown-body max-w-3xl rounded-lg border border-line bg-bg p-5 text-[14px] leading-7">
              <Markdown remarkPlugins={[remarkGfm]}>{doc.extractedText}</Markdown>
            </article>
          ) : visibleChunks.length === 0 ? (
            <EmptyState
              compact
              title="Không có đoạn văn khớp tìm kiếm"
              description="Thử từ khóa khác hoặc chuyển sang trang khác."
              action={
                <Button variant="outline" size="sm" onClick={() => setQ("")}>
                  Xóa tìm kiếm
                </Button>
              }
            />
          ) : (
            <article className="space-y-3 text-[14px] leading-7 text-ink">
              {visibleChunks.map((c) => {
                const isTargetChunk =
                  String(c.index) === chunkParam ||
                  (citation?.chunkIndex != null && c.index === citation.chunkIndex)
                return (
                  <div
                    key={c.id}
                    className={`rounded-lg border p-4 transition-colors ${
                      isTargetChunk
                        ? "border-ink bg-bg-secondary/60"
                        : "border-line bg-bg"
                    }`}
                  >
                    <div className="mb-1 flex items-center justify-between text-xs text-muted">
                      <span className="font-medium text-ink">Chunk #{c.index}</span>
                      <span>Trang {c.page}</span>
                    </div>
                    <p className="whitespace-pre-line">{highlightText(c.content)}</p>
                  </div>
                )
              })}
            </article>
          )}
        </div>

        {/* Cột phải: Tìm kiếm và điều hướng Chunk */}
        <aside className="w-full shrink-0 border-t border-line pt-4 md:w-72 md:border-l md:border-t-0 md:pl-5 md:pt-0">
          <div className="relative mb-3">
            <Search className="pointer-events-none absolute left-2.5 top-2.5 h-3.5 w-3.5 text-muted" />
            <Input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Tìm trong tài liệu..."
              className="h-8 pl-8 text-xs"
            />
          </div>

          <p className="mb-2 text-[11px] font-medium uppercase tracking-wide text-muted">
            Các đoạn trích ({filteredChunks.length})
          </p>

          <ul className="max-h-[480px] space-y-1.5 overflow-y-auto pr-1">
            {filteredChunks.map((c) => (
              <li key={c.id}>
                <button
                  type="button"
                  onClick={() => setSelectedPage(c.page)}
                  className={`w-full rounded-md border px-2.5 py-2 text-left text-xs transition-colors ${
                    c.page === selectedPage && !q.trim()
                      ? "border-ink bg-bg-secondary font-medium text-ink"
                      : "border-line bg-bg text-muted hover:bg-bg-hover hover:text-ink"
                  }`}
                >
                  <div className="flex items-center justify-between text-[11px]">
                    <span>Chunk #{c.index}</span>
                    <span>Tr. {c.page}</span>
                  </div>
                  <p className="mt-0.5 line-clamp-2">{c.content}</p>
                </button>
              </li>
            ))}
          </ul>
        </aside>
      </div>

      <NameDialog
        open={renameOpen}
        title="Đổi tên tài liệu"
        initialName={doc.fileName}
        onClose={() => setRenameOpen(false)}
        onSubmit={handleRename}
      />

      <ConfirmDialog
        open={deleteOpen}
        title="Xóa tài liệu?"
        description={`Xóa "${doc.fileName}" khỏi kho tri thức?`}
        onClose={() => setDeleteOpen(false)}
        onConfirm={() => void handleDelete()}
      />
    </div>
  )
}
