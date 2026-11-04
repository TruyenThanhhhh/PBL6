import { useEffect, useMemo, useState } from "react"
import { useNavigate, useParams, useSearchParams } from "react-router-dom"
import Markdown from "react-markdown"
import remarkGfm from "remark-gfm"
import {
  ArrowLeft,
  Download,
  ExternalLink,
  FileText,
  Globe,
  Loader2,
  MessageSquare,
  MoreHorizontal,
  Pencil,
  Quote,
  Search,
  Sparkles,
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
import { deleteDocumentApi, fetchDocumentChunks } from "@/services/api"
import { parseDocumentChunks, type ParsedDocumentChunk } from "@/services/source-service"
import { useAppStore } from "@/store/app-store"
import { formatBytes, formatDate } from "@/utils/format"
import type { KnowledgeDocument } from "@/types"

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

  const docFromStore = documents.find((d) => d.id === documentId)

  const citeParam = params.get("cite")
  const pageParam = params.get("page")
  const chunkParam = params.get("chunk")
  const fromChatId = params.get("fromChat")

  const [serverDoc, setServerDoc] = useState<KnowledgeDocument | null>(null)
  const [serverChunks, setServerChunks] = useState<ParsedDocumentChunk[]>([])
  const [loadingChunks, setLoadingChunks] = useState(false)

  const [q, setQ] = useState("")
  const [selectedPage, setSelectedPage] = useState<number>(() => {
    const p = Number(pageParam)
    return Number.isFinite(p) && p > 0 ? p : 1
  })
  const [renameOpen, setRenameOpen] = useState(false)
  const [deleteOpen, setDeleteOpen] = useState(false)

  // 1. Fetch chunks & document metadata thật từ Backend
  useEffect(() => {
    if (!documentId) return
    let active = true
    setLoadingChunks(true)

    fetchDocumentChunks(documentId)
      .then((res) => {
        if (!active) return
        const d = res.document
        const ext = d.file_name.split(".").pop()?.toLowerCase() || "other"
        const fileType =
          ext === "pdf" || ext === "docx" || ext === "pptx" || ext === "txt" || ext === "md"
            ? ext
            : "other"

        setServerDoc({
          id: d.id,
          workspaceId: d.workspace_id,
          notebookId: null,
          fileName: d.file_name,
          fileType,
          fileSize: d.file_size,
          status: (d.status === "indexed" ? "ready" : d.status) as any,
          createdAt: d.created_at,
          totalChunks: d.total_chunks,
          pageCount: d.total_pages || 1,
          extractedText: res.chunks.map((c) => c.content).join("\n\n"),
          mock: false,
        })

        const mappedChunks: ParsedDocumentChunk[] = res.chunks.map((c) => ({
          id: c.id,
          index: c.chunk_index,
          page: c.page_number,
          content: c.content,
        }))
        setServerChunks(mappedChunks)

        // Nếu có chunkParam hoặc citation, đảm bảo chuyển đến đúng trang chứa chunk đó
        const targetChunkIdx = chunkParam != null ? Number(chunkParam) : null
        if (targetChunkIdx != null) {
          const found = mappedChunks.find((c) => c.index === targetChunkIdx)
          if (found && found.page > 0) {
            setSelectedPage(found.page)
          }
        } else if (pageParam) {
          const p = Number(pageParam)
          if (p > 0) setSelectedPage(p)
        }
      })
      .catch((err) => {
        console.warn("Could not fetch document chunks from server:", err)
      })
      .finally(() => {
        if (active) setLoadingChunks(false)
      })

    return () => {
      active = false
    }
  }, [documentId, chunkParam, pageParam])

  const doc = docFromStore ?? serverDoc

  // Tìm Citation tương ứng trong cuộc trò chuyện (nếu có tham số `cite`)
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

  // Nếu có citation page, tự động đồng bộ selectedPage
  useEffect(() => {
    if (citation?.pageNumber && citation.pageNumber > 0) {
      setSelectedPage(citation.pageNumber)
    }
  }, [citation?.pageNumber])

  // Danh sách chunks: ưu tiên chunks từ backend, fallback về trích xuất text
  const chunks = useMemo(() => {
    if (serverChunks.length > 0) return serverChunks
    return parseDocumentChunks(doc ?? undefined)
  }, [serverChunks, doc])

  const filteredChunks = useMemo(() => {
    const kw = q.trim().toLowerCase()
    if (!kw) return chunks
    return chunks.filter((c) => c.content.toLowerCase().includes(kw))
  }, [chunks, q])

  // Tự động cuộn đến target chunk khi nạp xong
  const targetChunkIndex = useMemo(() => {
    if (chunkParam != null && Number.isFinite(Number(chunkParam))) {
      return Number(chunkParam)
    }
    return citation?.chunkIndex != null ? citation.chunkIndex : null
  }, [chunkParam, citation?.chunkIndex])

  const scrollToTargetChunk = () => {
    const el = document.getElementById("target-citation-chunk")
    if (el) {
      el.scrollIntoView({ behavior: "smooth", block: "center" })
    }
  }

  useEffect(() => {
    if (targetChunkIndex == null || loadingChunks) return
    const timer = window.setTimeout(() => {
      scrollToTargetChunk()
    }, 200)
    return () => window.clearTimeout(timer)
  }, [targetChunkIndex, selectedPage, loadingChunks])

  // Xử lý Highlight bôi vàng đoạn trích hoặc từ khóa tìm kiếm
  const highlightText = (text: string) => {
    const searchCandidate = q.trim()
    const citeHighlight = citation?.highlight?.trim()
    const citeSnippet = citation?.snippet?.trim()

    const needle = searchCandidate || citeHighlight || citeSnippet || ""
    if (!needle) return text

    // Thử tìm chính xác needle trong text
    let idx = text.toLowerCase().indexOf(needle.toLowerCase())
    let matchLength = needle.length

    // Nếu needle dài (snippet RAG) không match 100%, tách tìm cụm từ chính
    if (idx < 0 && needle.length > 20) {
      const phrases = needle
        .split(/[.\n;]/)
        .map((p) => p.trim())
        .filter((p) => p.length >= 10)
      for (const phrase of phrases) {
        const subIdx = text.toLowerCase().indexOf(phrase.toLowerCase())
        if (subIdx >= 0) {
          idx = subIdx
          matchLength = phrase.length
          break
        }
      }
    }

    if (idx < 0) return text

    return (
      <>
        {text.slice(0, idx)}
        <mark className="rounded bg-[#FFE58F] px-1 py-0.5 font-semibold text-[#874D00] shadow-2xs">
          {text.slice(idx, idx + matchLength)}
        </mark>
        {text.slice(idx + matchLength)}
      </>
    )
  }

  // Trường hợp đang tải ban đầu và chưa có thông tin doc
  if (!doc && loadingChunks) {
    return (
      <div className="mx-auto flex max-w-3xl flex-col items-center justify-center px-4 py-24 text-center">
        <Loader2 className="h-7 w-7 animate-spin text-[#087F73]" />
        <h2 className="mt-3 text-sm font-semibold text-[#172B29]">
          Đang tải dữ liệu và các đoạn trích của tài liệu...
        </h2>
        <p className="mt-1 text-xs text-[#647C79]">
          Hệ thống đang truy xuất các chunks từ chỉ mục Hybrid RAG.
        </p>
      </div>
    )
  }

  // Trường hợp nguồn Web hoặc tài liệu đã bị xóa
  if (!doc) {
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
          <div className="rounded-xl border border-[#DCE7E4] bg-white p-6 shadow-2xs">
            <div className="flex items-center gap-2">
              <Globe className="h-4 w-4 text-[#087F73]" />
              <h1 className="text-lg font-semibold text-[#172B29]">{citation.documentName}</h1>
              <Badge tone="neutral">Nguồn Web</Badge>
            </div>
            {citation.url ? (
              <a
                href={citation.url}
                target="_blank"
                rel="noreferrer"
                className="mt-2 inline-flex items-center gap-1 text-xs text-[#087F73] underline"
              >
                <span>{citation.url}</span>
                <ExternalLink className="h-3 w-3" />
              </a>
            ) : null}
            <blockquote className="mt-4 border-l-2 border-[#087F73] pl-3 text-sm italic text-[#172B29]">
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
                <Button variant="default" onClick={() => navigate(`/chat/${fromChatId}`)}>
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
  const isPlainMarkdown = doc.fileType === "md" && !q.trim() && !citeParam && serverChunks.length === 0

  const visibleChunks =
    q.trim() !== "" || doc.pageCount <= 1
      ? filteredChunks
      : filteredChunks.filter((c) => c.page === selectedPage)

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
            <span className="text-[#647C79]">Chuyển nguồn:</span>
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
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3 border-b border-[#DCE7E4] pb-4">
        <div className="min-w-0 flex-1">
          <InlineEdit
            value={doc.fileName}
            ariaLabel="Tên tài liệu"
            validate={(next) => (!next.trim() ? "Tên không được để trống." : null)}
            onSave={handleRename}
            className="text-xl font-semibold tracking-tight text-[#172B29]"
            inputClassName="text-lg font-semibold"
          />
          <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-[#647C79]">
            <span className="font-semibold uppercase text-[#172B29]">{doc.fileType}</span>
            <span>·</span>
            <span>{formatBytes(doc.fileSize)}</span>
            <span>·</span>
            <span>{doc.pageCount} trang</span>
            <span>·</span>
            <span>{chunks.length} chunks</span>
            <span>·</span>
            <span>Tải lên {formatDate(doc.createdAt)}</span>
          </div>
        </div>

        <div className="flex items-center gap-1.5">
          <StatusBadge status={doc.status} />
          <DropdownMenu
            align="end"
            trigger={
              <Button
                variant="outline"
                size="icon"
                className="h-8 w-8"
                aria-label="Thao tác tài liệu"
              >
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
          <span className="text-[#647C79]">Workspace:</span>
          <Select
            aria-label="Workspace liên quan"
            value={doc.workspaceId}
            onChange={(e) =>
              updateDocument(doc.id, { workspaceId: e.target.value, notebookId: null })
            }
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
          <span className="text-[#647C79]">Notebook:</span>
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

        {loadingChunks && (
          <span className="ml-auto inline-flex items-center gap-1 text-[11px] text-[#087F73]">
            <Loader2 className="h-3 w-3 animate-spin" />
            Đang tải chunks từ SQLite...
          </span>
        )}
      </div>

      {/* Thông báo nổi bật khi đối chiếu trích dẫn từ AI Chat */}
      {citeParam || targetChunkIndex != null ? (
        <div className="mb-5 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-[#087F73]/40 bg-[#E8F4F2] px-3.5 py-3 text-xs text-[#172B29] shadow-2xs">
          <div className="flex items-center gap-2">
            <div className="flex h-6 w-6 items-center justify-center rounded-lg bg-[#087F73] text-white">
              <Sparkles className="h-3.5 w-3.5" />
            </div>
            <div>
              <span className="font-semibold text-[#087F73]">
                {citeParam ? `Đang đối chiếu trích dẫn [${citeParam}]:` : "Đoạn trích dẫn mục tiêu:"}
              </span>{" "}
              <span className="text-[#647C79]">
                {pageParam ? `Trang ${pageParam}` : `Trang ${selectedPage}`}
                {targetChunkIndex != null ? ` · Chunk #${targetChunkIndex}` : ""}
              </span>
              {citation?.snippet ? (
                <p className="mt-0.5 max-w-xl truncate text-[11.5px] italic text-[#172B29]/80">
                  &ldquo;{citation.snippet}&rdquo;
                </p>
              ) : null}
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              className="h-7 text-xs border-[#087F73] text-[#087F73] hover:bg-white"
              onClick={scrollToTargetChunk}
            >
              Cuộn đến đoạn trích
            </Button>
            <Button
              variant="ghost"
              size="sm"
              className="h-7 text-xs text-[#647C79]"
              onClick={() => navigate(`/documents/${doc.id}`)}
            >
              Bỏ lọc trích dẫn
            </Button>
          </div>
        </div>
      ) : null}

      {/* Nội dung chính & Danh sách Chunks */}
      <div className="flex flex-col gap-6 md:flex-row">
        <div className="min-w-0 flex-1">
          {doc.pageCount > 1 && !q.trim() && !isPlainMarkdown ? (
            <div className="mb-3 flex items-center justify-between border-b border-[#DCE7E4] pb-2 text-xs">
              <span className="font-semibold text-[#172B29]">
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

          {visibleChunks.length === 0 && !loadingChunks ? (
            <EmptyState
              compact
              title="Không có đoạn trích nào ở trang này"
              description="Thử tìm kiếm từ khóa khác hoặc chuyển sang trang khác."
              action={
                q.trim() ? (
                  <Button variant="outline" size="sm" onClick={() => setQ("")}>
                    Xóa tìm kiếm
                  </Button>
                ) : undefined
              }
            />
          ) : isPlainMarkdown ? (
            <article className="markdown-body max-w-3xl rounded-xl border border-[#DCE7E4] bg-white p-5 text-[14px] leading-7">
              <Markdown remarkPlugins={[remarkGfm]}>{doc.extractedText}</Markdown>
            </article>
          ) : (
            <article className="space-y-3.5 text-[14px] leading-relaxed text-[#172B29]">
              {visibleChunks.map((c) => {
                const isTargetChunk = targetChunkIndex != null && c.index === targetChunkIndex
                return (
                  <div
                    key={c.id}
                    id={isTargetChunk ? "target-citation-chunk" : undefined}
                    className={`rounded-xl border p-4 transition-all duration-200 ${
                      isTargetChunk
                        ? "border-[#087F73] bg-[#E8F4F2]/80 ring-2 ring-[#087F73]/30 shadow-sm"
                        : "border-[#DCE7E4] bg-white hover:border-[#B4CDC7]"
                    }`}
                  >
                    <div className="mb-1.5 flex items-center justify-between text-xs text-[#647C79]">
                      <div className="flex items-center gap-2">
                        <span className="font-semibold text-[#172B29]">Chunk #{c.index}</span>
                        <span>· Trang {c.page}</span>
                      </div>
                      {isTargetChunk ? (
                        <span className="inline-flex items-center gap-1 rounded bg-[#087F73] px-2 py-0.5 text-[10.5px] font-semibold text-white shadow-2xs">
                          <Quote className="h-3 w-3" />
                          Đoạn trích dẫn đối chiếu
                        </span>
                      ) : null}
                    </div>
                    <p className="whitespace-pre-line text-[13.5px] leading-relaxed">
                      {highlightText(c.content)}
                    </p>
                  </div>
                )
              })}
            </article>
          )}
        </div>

        {/* Cột phải: Tìm kiếm và điều hướng nhanh Chunk */}
        <aside className="w-full shrink-0 border-t border-[#DCE7E4] pt-4 md:w-72 md:border-l md:border-t-0 md:pl-5 md:pt-0">
          <div className="relative mb-3">
            <Search className="pointer-events-none absolute left-2.5 top-2.5 h-3.5 w-3.5 text-[#647C79]" />
            <Input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Tìm trong tài liệu..."
              className="h-8 pl-8 text-xs"
            />
          </div>

          <div className="mb-2 flex items-center justify-between px-0.5">
            <p className="text-[11px] font-semibold uppercase tracking-wider text-[#647C79]">
              Các đoạn trích ({filteredChunks.length})
            </p>
            {targetChunkIndex != null && (
              <button
                type="button"
                onClick={scrollToTargetChunk}
                className="text-[11px] font-semibold text-[#087F73] hover:underline"
              >
                Về đoạn trích
              </button>
            )}
          </div>

          <ul className="max-h-[520px] space-y-1.5 overflow-y-auto pr-1">
            {filteredChunks.map((c) => {
              const isTarget = targetChunkIndex != null && c.index === targetChunkIndex
              return (
                <li key={c.id}>
                  <button
                    type="button"
                    onClick={() => {
                      if (c.page > 0) setSelectedPage(c.page)
                      // Cuộn đến chunk sau khi chuyển trang
                      setTimeout(() => {
                        const el = document.getElementById(isTarget ? "target-citation-chunk" : "")
                        if (el) el.scrollIntoView({ behavior: "smooth", block: "center" })
                      }, 100)
                    }}
                    className={`w-full rounded-lg border px-2.5 py-2 text-left text-xs transition-colors ${
                      isTarget
                        ? "border-[#087F73] bg-[#E8F4F2] font-semibold text-[#087F73] shadow-2xs"
                        : c.page === selectedPage && !q.trim()
                          ? "border-[#DCE7E4] bg-[#F1F6F5] font-semibold text-[#172B29]"
                          : "border-transparent bg-white text-[#647C79] hover:bg-[#F1F6F5] hover:text-[#172B29]"
                    }`}
                  >
                    <div className="flex items-center justify-between text-[11px]">
                      <span className="font-medium">Chunk #{c.index}</span>
                      <span>Trang {c.page}</span>
                    </div>
                    <p className="mt-0.5 line-clamp-2 text-[11.5px] leading-normal">{c.content}</p>
                  </button>
                </li>
              )
            })}
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
