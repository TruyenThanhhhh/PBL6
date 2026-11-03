import { useMemo, useState } from "react"
import { useNavigate } from "react-router-dom"
import { Check, FolderOpen, LayoutGrid, List, MessageSquare, MoreHorizontal, Pencil, Plus, Search, Trash2 } from "lucide-react"
import { PageHeader } from "@/components/common/PageHeader"
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
  Tooltip,
} from "@/components/ui"
import { useAppStore } from "@/store/app-store"
import { isWithinDays, relativeTime } from "@/utils/format"
import type { Workspace } from "@/types"
import {
  describeWorkspaceDeletion,
  getWorkspaceCounts,
  hasDuplicateName,
} from "@/features/workspaces/workspace-utils"

type DocFilter = "all" | "ready" | "processing" | "failed"

export function KnowledgeBasePage() {
  const navigate = useNavigate()
  const workspaces = useAppStore((s) => s.workspaces)
  const notebooks = useAppStore((s) => s.notebooks)
  const documents = useAppStore((s) => s.documents)
  const notes = useAppStore((s) => s.notes)
  const conversations = useAppStore((s) => s.conversations)
  const currentWorkspaceId = useAppStore((s) => s.currentWorkspaceId)
  const setCurrent = useAppStore((s) => s.setCurrentWorkspace)
  const createWorkspace = useAppStore((s) => s.createWorkspace)
  const updateWorkspace = useAppStore((s) => s.updateWorkspace)
  const deleteWorkspace = useAppStore((s) => s.deleteWorkspace)
  const createConversation = useAppStore((s) => s.createConversation)
  const toast = useAppStore((s) => s.toast)

  const [q, setQ] = useState("")
  const [view, setView] = useState<"list" | "grid">("list")
  const [sort, setSort] = useState<"updated" | "name" | "documents">("updated")
  const [range, setRange] = useState<"all" | "7" | "30">("all")
  const [docState, setDocState] = useState<DocFilter>("all")
  const [createOpen, setCreateOpen] = useState(false)
  const [editTarget, setEditTarget] = useState<Workspace | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<Workspace | null>(null)

  const data = { notebooks, documents, notes, conversations }
  const filtersActive = q !== "" || range !== "all" || docState !== "all"

  const filtered = useMemo(() => {
    const query = q.trim().toLowerCase()
    const list = workspaces.filter((w) => {
      if (query && !w.name.toLowerCase().includes(query) && !w.description.toLowerCase().includes(query)) return false
      if (range !== "all" && !isWithinDays(w.updatedAt, Number(range))) return false
      const docs = documents.filter((d) => d.workspaceId === w.id)
      if (docState === "ready") return docs.some((d) => d.status === "ready")
      if (docState === "failed") return docs.some((d) => d.status === "failed")
      if (docState === "processing") return docs.some((d) => d.status !== "ready" && d.status !== "failed")
      return true
    })
    return [...list].sort((a, b) => {
      if (sort === "name") return a.name.localeCompare(b.name, "vi")
      if (sort === "documents") {
        return (
          documents.filter((d) => d.workspaceId === b.id).length -
          documents.filter((d) => d.workspaceId === a.id).length
        )
      }
      return b.updatedAt.localeCompare(a.updatedAt)
    })
  }, [workspaces, documents, q, sort, range, docState])

  const resetFilters = () => {
    setQ("")
    setRange("all")
    setDocState("all")
  }

  const validateName = (exceptId?: string) => (name: string) =>
    hasDuplicateName(
      workspaces.filter((w) => w.id !== exceptId).map((w) => w.name),
      name,
    )
      ? "Đã có workspace cùng tên."
      : null

  const openWorkspace = (w: Workspace) => {
    setCurrent(w.id)
    navigate(`/knowledge/${w.id}`)
  }

  const renderMenu = (w: Workspace) => (
    <DropdownMenu
      trigger={
        <Button variant="ghost" size="icon" aria-label={`Tùy chọn cho workspace ${w.name}`}>
          <MoreHorizontal className="h-4 w-4 text-muted" />
        </Button>
      }
    >
      <DropdownMenuItem icon={<FolderOpen className="h-3.5 w-3.5" />} onClick={() => openWorkspace(w)}>
        Mở workspace
      </DropdownMenuItem>
      <DropdownMenuItem icon={<Pencil className="h-3.5 w-3.5" />} onClick={() => setEditTarget(w)}>
        Đổi tên và mô tả
      </DropdownMenuItem>
      <DropdownMenuItem
        icon={<Check className="h-3.5 w-3.5" />}
        disabled={currentWorkspaceId === w.id}
        onClick={() => {
          setCurrent(w.id)
          toast({ title: `Đã chuyển sang "${w.name}"`, tone: "info" })
        }}
      >
        {currentWorkspaceId === w.id ? "Đang là workspace hiện tại" : "Đặt làm workspace hiện tại"}
      </DropdownMenuItem>
      <DropdownMenuItem
        icon={<MessageSquare className="h-3.5 w-3.5" />}
        onClick={() => {
          setCurrent(w.id)
          navigate(`/chat/${createConversation(w.id).id}`)
        }}
      >
        Hỏi đáp AI trong workspace
      </DropdownMenuItem>
      <DropdownMenuSeparator />
      <DropdownMenuItem tone="danger" icon={<Trash2 className="h-3.5 w-3.5" />} onClick={() => setDeleteTarget(w)}>
        Xóa workspace
      </DropdownMenuItem>
    </DropdownMenu>
  )

  const meta = (w: Workspace) => {
    const c = getWorkspaceCounts(w.id, data)
    return `${c.notebooks} notebook · ${c.documents} tài liệu · ${c.notes} ghi chú · ${c.conversations} hội thoại`
  }

  return (
    <div className="mx-auto max-w-5xl px-4 py-8 md:px-8">
      <PageHeader
        breadcrumb={["Kho tri thức"]}
        title="Kho tri thức"
        description="Tổ chức workspace và notebook. Dữ liệu lưu cục bộ trong trình duyệt, chưa đồng bộ máy chủ."
        actions={
          <Button leftIcon={<Plus className="h-4 w-4" />} onClick={() => setCreateOpen(true)}>
            Tạo workspace
          </Button>
        }
      />

      <div className="mb-4 flex flex-wrap items-center gap-2">
        <div className="relative w-full max-w-xs">
          <Search className="pointer-events-none absolute left-2.5 top-2.5 h-3.5 w-3.5 text-muted" />
          <Input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Tìm workspace"
            aria-label="Tìm workspace"
            className="pl-8"
          />
        </div>
        <div className="w-40">
          <Select value={sort} onChange={(e) => setSort(e.target.value as typeof sort)} aria-label="Sắp xếp">
            <option value="updated">Mới cập nhật</option>
            <option value="name">Tên (A–Z)</option>
            <option value="documents">Nhiều tài liệu nhất</option>
          </Select>
        </div>
        <div className="w-40">
          <Select value={range} onChange={(e) => setRange(e.target.value as typeof range)} aria-label="Lọc theo thời gian">
            <option value="all">Mọi thời gian</option>
            <option value="7">7 ngày qua</option>
            <option value="30">30 ngày qua</option>
          </Select>
        </div>
        <div className="w-52">
          <Select
            value={docState}
            onChange={(e) => setDocState(e.target.value as DocFilter)}
            aria-label="Lọc theo trạng thái tài liệu"
          >
            <option value="all">Mọi trạng thái tài liệu</option>
            <option value="ready">Có tài liệu sẵn sàng</option>
            <option value="processing">Có tài liệu đang xử lý</option>
            <option value="failed">Có tài liệu lỗi</option>
          </Select>
        </div>
        <div className="ml-auto flex rounded-md border border-line p-0.5">
          <Tooltip content="Dạng danh sách" side="bottom">
            <Button
              variant={view === "list" ? "secondary" : "ghost"}
              size="icon"
              aria-label="Dạng danh sách"
              aria-pressed={view === "list"}
              onClick={() => setView("list")}
            >
              <List className="h-4 w-4" />
            </Button>
          </Tooltip>
          <Tooltip content="Dạng lưới" side="bottom">
            <Button
              variant={view === "grid" ? "secondary" : "ghost"}
              size="icon"
              aria-label="Dạng lưới"
              aria-pressed={view === "grid"}
              onClick={() => setView("grid")}
            >
              <LayoutGrid className="h-4 w-4" />
            </Button>
          </Tooltip>
        </div>
      </div>

      {workspaces.length > 0 ? (
        <p className="mb-2 text-xs text-muted">
          {filtered.length}/{workspaces.length} workspace
          {filtersActive ? (
            <button type="button" className="ml-2 underline hover:text-ink" onClick={resetFilters}>
              Xóa bộ lọc
            </button>
          ) : null}
        </p>
      ) : null}

      {workspaces.length === 0 ? (
        <EmptyState
          icon={<FolderOpen className="h-4 w-4" />}
          title="Chưa có workspace"
          description="Tạo workspace đầu tiên để bắt đầu tổ chức tài liệu, notebook và ghi chú."
          action={<Button onClick={() => setCreateOpen(true)}>Tạo workspace</Button>}
        />
      ) : filtered.length === 0 ? (
        <EmptyState
          compact
          icon={<Search className="h-4 w-4" />}
          title="Không tìm thấy workspace"
          description="Không có workspace nào khớp với bộ lọc hiện tại."
          action={
            <Button variant="outline" onClick={resetFilters}>
              Xóa bộ lọc
            </Button>
          }
        />
      ) : view === "list" ? (
        <ul className="divide-y divide-line border-y border-line">
          {filtered.map((w) => (
            <li key={w.id} className="group flex items-center gap-2 transition-colors hover:bg-bg-hover/70">
              <button type="button" onClick={() => openWorkspace(w)} className="min-w-0 flex-1 py-3 text-left">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-sm font-medium text-ink">{w.name}</span>
                  {currentWorkspaceId === w.id ? <Badge tone="neutral">Đang chọn</Badge> : null}
                </div>
                <p className="mt-0.5 truncate text-xs text-muted">{w.description || "Không có mô tả"}</p>
                <p className="mt-0.5 text-xs text-muted">
                  {meta(w)} · {relativeTime(w.updatedAt)}
                </p>
              </button>
              <div className="shrink-0 transition-opacity md:opacity-0 md:group-focus-within:opacity-100 md:group-hover:opacity-100">
                {renderMenu(w)}
              </div>
            </li>
          ))}
        </ul>
      ) : (
        <div className="grid gap-px border border-line bg-line sm:grid-cols-2">
          {filtered.map((w) => (
            <div key={w.id} className="group relative bg-bg transition-colors hover:bg-bg-hover">
              <button type="button" onClick={() => openWorkspace(w)} className="block w-full p-4 pr-12 text-left">
                <div className="flex flex-wrap items-center gap-2">
                  <p className="font-medium text-ink">{w.name}</p>
                  {currentWorkspaceId === w.id ? <Badge tone="neutral">Đang chọn</Badge> : null}
                </div>
                <p className="mt-1 line-clamp-2 text-sm text-muted">{w.description || "Không có mô tả"}</p>
                <p className="mt-3 text-xs text-muted">
                  {meta(w)} · {relativeTime(w.updatedAt)}
                </p>
              </button>
              <div className="absolute right-2 top-2 transition-opacity md:opacity-0 md:group-focus-within:opacity-100 md:group-hover:opacity-100">
                {renderMenu(w)}
              </div>
            </div>
          ))}
        </div>
      )}

      <NameDialog
        open={createOpen}
        title="Tạo workspace"
        confirmLabel="Tạo"
        showDescription
        validate={validateName()}
        onClose={() => setCreateOpen(false)}
        onSubmit={(name, description) => {
          const ws = createWorkspace(name, description)
          toast({ title: "Đã tạo workspace", description: ws.name, tone: "success" })
          navigate(`/knowledge/${ws.id}`)
        }}
      />
      <NameDialog
        open={Boolean(editTarget)}
        title="Đổi tên và mô tả workspace"
        initialName={editTarget?.name ?? ""}
        initialDescription={editTarget?.description ?? ""}
        showDescription
        validate={validateName(editTarget?.id)}
        onClose={() => setEditTarget(null)}
        onSubmit={(name, description) => {
          if (editTarget) {
            updateWorkspace(editTarget.id, { name, description })
            toast({ title: "Đã cập nhật workspace", tone: "success" })
          }
        }}
      />
      <ConfirmDialog
        open={Boolean(deleteTarget)}
        title={`Xóa workspace "${deleteTarget?.name ?? ""}"?`}
        description={deleteTarget ? describeWorkspaceDeletion(getWorkspaceCounts(deleteTarget.id, data)) : undefined}
        confirmLabel="Xóa workspace"
        onClose={() => setDeleteTarget(null)}
        onConfirm={() => {
          if (deleteTarget) {
            deleteWorkspace(deleteTarget.id)
            toast({ title: "Đã xóa workspace", tone: "success" })
          }
        }}
      />
    </div>
  )
}
