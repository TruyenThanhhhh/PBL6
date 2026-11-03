import { useMemo, useState } from "react"
import { useNavigate, useSearchParams } from "react-router-dom"
import {
  Download,
  Eye,
  FileText,
  FolderInput,
  LayoutList,
  MoreHorizontal,
  Pencil,
  Search,
  Table2,
  Trash2,
} from "lucide-react"
import { PageHeader } from "@/components/common/PageHeader"
import { ConfirmDialog, NameDialog } from "@/components/common/NameDialog"
import {
  Badge,
  Button,
  Dialog,
  DropdownMenu,
  DropdownMenuItem,
  DropdownMenuSeparator,
  EmptyState,
  FormField,
  Input,
  Select,
  StatusBadge,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui"
import { useAppStore } from "@/store/app-store"
import { deleteDocumentApi } from "@/services/api"
import { formatBytes, formatDate } from "@/utils/format"
import type { KnowledgeDocument } from "@/types"
import { DocumentUploadPanel } from "./DocumentUploadPanel"
import { downloadExtractedText } from "./document-utils"

export function DocumentsPage() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const documents = useAppStore((s) => s.documents)
  const workspaces = useAppStore((s) => s.workspaces)
  const notebooks = useAppStore((s) => s.notebooks)
  const currentWorkspaceId = useAppStore((s) => s.currentWorkspaceId)
  const setCurrentWorkspace = useAppStore((s) => s.setCurrentWorkspace)
  const updateDocument = useAppStore((s) => s.updateDocument)
  const deleteDocument = useAppStore((s) => s.deleteDocument)
  const toast = useAppStore((s) => s.toast)
  const status = useAppStore((s) => s.status)

  const activeWs = workspaces.find((w) => w.id === currentWorkspaceId) ?? workspaces[0]
  const activeWsId = activeWs?.id ?? "ws_default"

  // Target notebook cho khu vực Upload
  const [uploadNotebookId, setUploadNotebookId] = useState<string>(
    searchParams.get("notebook") ?? "",
  )

  // Bộ lọc danh sách tài liệu tối giản (luôn giới hạn trong activeWsId)
  const [q, setQ] = useState("")
  const [typeFilter, setTypeFilter] = useState<string>("all")
  const [statusFilter, setStatusFilter] = useState<"all" | "ready" | "processing" | "failed">("all")
  const [viewMode, setViewMode] = useState<"table" | "list">("table")

  // Dialog states
  const [renameDoc, setRenameDoc] = useState<KnowledgeDocument | null>(null)
  const [deleteDoc, setDeleteDoc] = useState<KnowledgeDocument | null>(null)
  const [moveDoc, setMoveDoc] = useState<KnowledgeDocument | null>(null)
  const [moveWsId, setMoveWsId] = useState<string>("")
  const [moveNbId, setMoveNbId] = useState<string>("")

  const moveWorkspaceNotebooks = useMemo(() => {
    if (!moveWsId) return []
    return notebooks.filter((n) => n.workspaceId === moveWsId)
  }, [notebooks, moveWsId])

  // Lọc nghiêm ngặt: chỉ tài liệu thuộc không gian hiện tại
  const wsDocuments = useMemo(
    () => documents.filter((d) => d.workspaceId === activeWsId),
    [documents, activeWsId],
  )

  const list = useMemo(() => {
    let rows = [...wsDocuments]

    if (q.trim()) {
      const kw = q.trim().toLowerCase()
      rows = rows.filter((d) => d.fileName.toLowerCase().includes(kw))
    }
    if (typeFilter !== "all") {
      rows = rows.filter((d) => d.fileType === typeFilter)
    }
    if (statusFilter === "ready") {
      rows = rows.filter((d) => d.status === "ready")
    } else if (statusFilter === "failed") {
      rows = rows.filter((d) => d.status === "failed")
    } else if (statusFilter === "processing") {
      rows = rows.filter((d) => d.status !== "ready" && d.status !== "failed")
    }

    rows.sort((a, b) => b.createdAt.localeCompare(a.createdAt))
    return rows
  }, [wsDocuments, q, typeFilter, statusFilter])

  const openMoveDialog = (doc: KnowledgeDocument) => {
    setMoveDoc(doc)
    setMoveWsId(doc.workspaceId)
    setMoveNbId(doc.notebookId ?? "")
  }

  const handleConfirmMove = () => {
    if (!moveDoc || !moveWsId) return
    updateDocument(moveDoc.id, {
      workspaceId: moveWsId,
      notebookId: moveNbId || null,
    })
    toast({
      title: "Đã chuyển vị trí tài liệu",
      tone: "success",
    })
    setMoveDoc(null)
  }

  const handleConfirmDelete = async () => {
    if (!deleteDoc) return
    try {
      if (status.backendOnline && !deleteDoc.mock) {
        await deleteDocumentApi(deleteDoc.id)
      }
    } catch {
      // Giữ nguyên xóa client
    }
    deleteDocument(deleteDoc.id)
    toast({
      title: "Đã xóa tài liệu",
      description: deleteDoc.fileName,
      tone: "info",
    })
    setDeleteDoc(null)
  }

  const handleDownload = (doc: KnowledgeDocument) => {
    const ok = downloadExtractedText(doc)
    if (!ok) {
      toast({
        title: "Chưa có nội dung văn bản để tải xuống",
        tone: "warning",
      })
    } else {
      toast({
        title: "Đã tải xuống văn bản trích xuất",
        tone: "success",
      })
    }
  }

  const resetFilters = () => {
    setQ("")
    setTypeFilter("all")
    setStatusFilter("all")
  }

  const renderActionMenu = (doc: KnowledgeDocument) => (
    <DropdownMenu
      align="end"
      trigger={
        <Button variant="ghost" size="icon" className="h-8 w-8" aria-label={`Thao tác với ${doc.fileName}`}>
          <MoreHorizontal className="h-4 w-4 text-muted" />
        </Button>
      }
    >
      <DropdownMenuItem
        icon={<Eye className="h-3.5 w-3.5" />}
        onClick={() => navigate(`/documents/${doc.id}`)}
      >
        Xem nội dung
      </DropdownMenuItem>
      <DropdownMenuItem
        icon={<Pencil className="h-3.5 w-3.5" />}
        onClick={() => setRenameDoc(doc)}
      >
        Đổi tên tài liệu
      </DropdownMenuItem>
      <DropdownMenuItem
        icon={<FolderInput className="h-3.5 w-3.5" />}
        onClick={() => openMoveDialog(doc)}
      >
        Chuyển không gian làm việc
      </DropdownMenuItem>
      <DropdownMenuItem
        icon={<Download className="h-3.5 w-3.5" />}
        disabled={!doc.extractedText?.trim()}
        onClick={() => handleDownload(doc)}
      >
        Tải xuống văn bản
      </DropdownMenuItem>
      <DropdownMenuSeparator />
      <DropdownMenuItem
        tone="danger"
        icon={<Trash2 className="h-3.5 w-3.5" />}
        onClick={() => setDeleteDoc(doc)}
      >
        Xóa tài liệu
      </DropdownMenuItem>
    </DropdownMenu>
  )

  return (
    <div className="mx-auto max-w-5xl px-4 py-6 md:px-8">
      <PageHeader
        title="Tài liệu"
        description="Tải lên và quản lý các tài liệu tri thức trong không gian làm việc của bạn."
      />

      {/* Khu vực Tải lên tài liệu (tự động gắn vào không gian đang chọn) */}
      <DocumentUploadPanel
        targetWorkspaceId={activeWsId}
        targetNotebookId={uploadNotebookId}
        onTargetWorkspaceChange={setCurrentWorkspace}
        onTargetNotebookChange={setUploadNotebookId}
      />

      {/* 3. Bộ lọc tài liệu trong không gian hiện tại */}
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2.5">
        <div className="flex flex-1 flex-wrap items-center gap-2">
          <div className="relative w-full sm:w-64">
            <Search className="pointer-events-none absolute left-2.5 top-2.5 h-3.5 w-3.5 text-muted" />
            <Input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Tìm theo tên tài liệu..."
              className="h-8 pl-8 text-xs"
            />
          </div>

          <div className="w-36">
            <Select
              aria-label="Lọc theo loại tệp"
              value={typeFilter}
              onChange={(e) => setTypeFilter(e.target.value)}
              className="h-8 text-xs"
            >
              <option value="all">Tất cả định dạng</option>
              <option value="pdf">PDF (.pdf)</option>
              <option value="docx">DOCX (.docx)</option>
              <option value="pptx">PPTX (.pptx)</option>
              <option value="txt">TXT (.txt)</option>
              <option value="md">Markdown (.md)</option>
            </Select>
          </div>

          <div className="w-36">
            <Select
              aria-label="Lọc theo trạng thái"
              value={statusFilter}
              onChange={(e) =>
                setStatusFilter(e.target.value as "all" | "ready" | "processing" | "failed")
              }
              className="h-8 text-xs"
            >
              <option value="all">Mọi trạng thái</option>
              <option value="ready">Sẵn sàng</option>
              <option value="processing">Đang xử lý</option>
              <option value="failed">Lỗi</option>
            </Select>
          </div>
        </div>

        {/* Chuyển chế độ Bảng / Danh sách */}
        <div className="flex items-center gap-0.5 rounded-lg border border-line bg-bg p-0.5">
          <Button
            variant={viewMode === "table" ? "secondary" : "ghost"}
            size="sm"
            className="h-7 px-2 text-xs"
            leftIcon={<Table2 className="h-3.5 w-3.5" />}
            onClick={() => setViewMode("table")}
          >
            Bảng
          </Button>
          <Button
            variant={viewMode === "list" ? "secondary" : "ghost"}
            size="sm"
            className="h-7 px-2 text-xs"
            leftIcon={<LayoutList className="h-3.5 w-3.5" />}
            onClick={() => setViewMode("list")}
          >
            Danh sách
          </Button>
        </div>
      </div>

      {/* Danh sách tài liệu */}
      {wsDocuments.length === 0 ? (
        <EmptyState
          icon={<FileText className="h-5 w-5" />}
          title={`Không gian "${activeWs?.name}" chưa có tài liệu nào`}
          description="Kéo-thả hoặc chọn tệp ở phía trên để thêm tài liệu vào không gian này, hoặc bấm 'Đổi không gian' để làm việc với tài liệu khác."
        />
      ) : list.length === 0 ? (
        <EmptyState
          icon={<Search className="h-5 w-5" />}
          title="Không tìm thấy tài liệu phù hợp"
          description="Thử thay đổi từ khóa tìm kiếm hoặc đặt lại bộ lọc."
          action={
            <Button variant="outline" size="sm" onClick={resetFilters}>
              Đặt lại bộ lọc
            </Button>
          }
        />
      ) : viewMode === "table" ? (
        <div className="motivo-card overflow-hidden">
          <Table>
            <TableHeader>
              <TableRow className="border-b border-line bg-bg-secondary/40 text-xs text-muted">
                <TableHead className="font-semibold text-ink">Tên tài liệu</TableHead>
                <TableHead className="font-semibold text-ink">Định dạng</TableHead>
                <TableHead className="font-semibold text-ink">Không gian</TableHead>
                <TableHead className="font-semibold text-ink">Kích thước</TableHead>
                <TableHead className="font-semibold text-ink">Ngày tải lên</TableHead>
                <TableHead className="font-semibold text-ink">Trạng thái</TableHead>
                <TableHead className="text-right font-semibold text-ink">Thao tác</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {list.map((d) => {
                const ws = workspaces.find((w) => w.id === d.workspaceId)
                return (
                  <TableRow key={d.id} className="transition-colors hover:bg-bg-hover/60">
                    <TableCell>
                      <button
                        type="button"
                        onClick={() => navigate(`/documents/${d.id}`)}
                        className="text-left font-semibold text-ink hover:text-brand"
                      >
                        {d.fileName}
                      </button>
                    </TableCell>
                    <TableCell>
                      <Badge tone="neutral">{d.fileType.toUpperCase()}</Badge>
                    </TableCell>
                    <TableCell className="text-xs text-muted">
                      {ws?.name ?? "—"}
                    </TableCell>
                    <TableCell className="text-xs text-muted">
                      {formatBytes(d.fileSize)}
                    </TableCell>
                    <TableCell className="text-xs text-muted">
                      {formatDate(d.createdAt)}
                    </TableCell>
                    <TableCell>
                      <StatusBadge status={d.status} />
                    </TableCell>
                    <TableCell className="text-right">
                      {renderActionMenu(d)}
                    </TableCell>
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
        </div>
      ) : (
        <div className="motivo-card divide-y divide-line/70 overflow-hidden">
          {list.map((d) => {
            const ws = workspaces.find((w) => w.id === d.workspaceId)
            return (
              <div
                key={d.id}
                className="flex flex-wrap items-center justify-between gap-3 p-3.5 transition-colors hover:bg-bg-hover/60"
              >
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => navigate(`/documents/${d.id}`)}
                      className="truncate text-xs font-semibold text-ink hover:text-brand"
                    >
                      {d.fileName}
                    </button>
                    <Badge tone="neutral">{d.fileType.toUpperCase()}</Badge>
                  </div>
                  <div className="mt-1 flex flex-wrap items-center gap-2 text-[11px] text-muted">
                    <span>{ws?.name ?? "Không gian"}</span>
                    <span>·</span>
                    <span>{formatBytes(d.fileSize)}</span>
                    <span>·</span>
                    <span>Tải lên {formatDate(d.createdAt)}</span>
                  </div>
                </div>

                <div className="flex items-center gap-2">
                  <StatusBadge status={d.status} />
                  {renderActionMenu(d)}
                </div>
              </div>
            )
          })}
        </div>
      )}

      {/* Dialog đổi tên */}
      <NameDialog
        open={Boolean(renameDoc)}
        title="Đổi tên tài liệu"
        initialName={renameDoc?.fileName ?? ""}
        onClose={() => setRenameDoc(null)}
        onSubmit={(name) => {
          if (renameDoc) {
            updateDocument(renameDoc.id, { fileName: name })
            toast({ title: "Đã đổi tên tài liệu", tone: "success" })
            setRenameDoc(null)
          }
        }}
      />

      {/* Dialog xác nhận xóa */}
      <ConfirmDialog
        open={Boolean(deleteDoc)}
        title="Xóa tài liệu?"
        description={
          deleteDoc
            ? `Bạn có chắc muốn xóa tài liệu "${deleteDoc.fileName}"?`
            : undefined
        }
        onClose={() => setDeleteDoc(null)}
        onConfirm={handleConfirmDelete}
      />

      {/* Dialog chuyển Workspace / Notebook */}
      <Dialog
        open={Boolean(moveDoc)}
        title="Chuyển không gian tài liệu"
        onClose={() => setMoveDoc(null)}
      >
        <div className="space-y-4">
          <FormField label="Không gian làm việc đích">
            <Select
              value={moveWsId}
              onChange={(e) => {
                setMoveWsId(e.target.value)
                setMoveNbId("")
              }}
            >
              {workspaces.map((w) => (
                <option key={w.id} value={w.id}>
                  {w.name}
                </option>
              ))}
            </Select>
          </FormField>

          {moveWorkspaceNotebooks.length > 0 ? (
            <FormField label="Notebook đích (tuỳ chọn)">
              <Select value={moveNbId} onChange={(e) => setMoveNbId(e.target.value)}>
                <option value="">-- Không phân loại vào notebook --</option>
                {moveWorkspaceNotebooks.map((n) => (
                  <option key={n.id} value={n.id}>
                    {n.name}
                  </option>
                ))}
              </Select>
            </FormField>
          ) : null}

          <div className="flex justify-end gap-2 pt-2">
            <Button variant="outline" size="sm" onClick={() => setMoveDoc(null)}>
              Hủy
            </Button>
            <Button size="sm" onClick={handleConfirmMove}>
              Xác nhận chuyển
            </Button>
          </div>
        </div>
      </Dialog>
    </div>
  )
}
