import { useState } from "react"
import { useNavigate } from "react-router-dom"
import { ArrowRightLeft, BookOpen, FilePlus2, FileUp, Pencil, Plus, Search, StickyNote, Trash2 } from "lucide-react"
import { ConfirmDialog, NameDialog } from "@/components/common/NameDialog"
import {
  Button,
  DropdownMenuItem,
  DropdownMenuSeparator,
  EmptyState,
  Input,
  Select,
  Tooltip,
} from "@/components/ui"
import { useAppStore } from "@/store/app-store"
import { relativeTime } from "@/utils/format"
import type { Notebook } from "@/types"
import { RowMenu } from "./ContentLists"
import { MoveNotebookDialog } from "./MoveNotebookDialog"
import { QuickNoteDialog } from "./QuickNoteDialog"
import { getNotebookStats, hasDuplicateName, sortNotebookRows, type NotebookSort } from "./workspace-utils"

/** Danh sách notebook của một workspace: tìm kiếm, sắp xếp, tạo/đổi tên/xóa/chuyển. */
export function NotebookSection({
  workspaceId,
  onCreate,
}: {
  workspaceId: string
  onCreate: () => void
}) {
  const navigate = useNavigate()
  const notebooks = useAppStore((s) => s.notebooks)
  const documents = useAppStore((s) => s.documents)
  const notes = useAppStore((s) => s.notes)
  const renameNotebook = useAppStore((s) => s.renameNotebook)
  const deleteNotebook = useAppStore((s) => s.deleteNotebook)
  const setCurrent = useAppStore((s) => s.setCurrentWorkspace)
  const toast = useAppStore((s) => s.toast)

  const [q, setQ] = useState("")
  const [sort, setSort] = useState<NotebookSort>("updated")
  const [renameTarget, setRenameTarget] = useState<Notebook | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<Notebook | null>(null)
  const [moveTarget, setMoveTarget] = useState<Notebook | null>(null)
  const [noteNotebookId, setNoteNotebookId] = useState<string | null>(null)

  const wsNotebooks = notebooks.filter((n) => n.workspaceId === workspaceId)
  const rows = sortNotebookRows(
    wsNotebooks
      .filter((n) => n.name.toLowerCase().includes(q.trim().toLowerCase()))
      .map((notebook) => ({ notebook, stats: getNotebookStats(notebook, documents, notes) })),
    sort,
  )

  const open = (nb: Notebook) => navigate(`/knowledge/${workspaceId}/notebooks/${nb.id}`)
  const addDocument = (nb: Notebook) => {
    setCurrent(workspaceId)
    navigate(`/documents?notebook=${nb.id}`)
  }

  const deleteStats = deleteTarget ? getNotebookStats(deleteTarget, documents, notes) : null

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <div className="relative w-full max-w-xs">
          <Search className="pointer-events-none absolute left-2.5 top-2.5 h-3.5 w-3.5 text-muted" />
          <Input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Tìm notebook"
            aria-label="Tìm notebook"
            className="pl-8"
          />
        </div>
        <div className="w-44">
          <Select value={sort} onChange={(e) => setSort(e.target.value as NotebookSort)} aria-label="Sắp xếp notebook">
            <option value="updated">Mới cập nhật</option>
            <option value="name">Tên (A–Z)</option>
            <option value="documents">Nhiều tài liệu nhất</option>
          </Select>
        </div>
        <Button className="ml-auto" leftIcon={<Plus className="h-4 w-4" />} onClick={onCreate}>
          Thêm notebook
        </Button>
      </div>

      {wsNotebooks.length === 0 ? (
        <EmptyState
          compact
          icon={<BookOpen className="h-4 w-4" />}
          title="Workspace chưa có notebook"
          description="Notebook giúp nhóm tài liệu và ghi chú theo chủ đề trong workspace này."
          action={<Button onClick={onCreate}>Thêm notebook</Button>}
        />
      ) : rows.length === 0 ? (
        <EmptyState
          compact
          title="Không tìm thấy notebook"
          description={`Không có notebook nào khớp với "${q}".`}
          action={
            <Button variant="outline" onClick={() => setQ("")}>
              Xóa bộ lọc
            </Button>
          }
        />
      ) : (
        <ul className="divide-y divide-line border-y border-line">
          {rows.map(({ notebook, stats }) => (
            <li key={notebook.id} className="group flex items-center gap-2 transition-colors hover:bg-bg-hover/70">
              <button
                type="button"
                onClick={() => open(notebook)}
                className="flex min-w-0 flex-1 items-center gap-3 py-2.5 text-left"
              >
                <BookOpen className="h-4 w-4 shrink-0 text-muted" />
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium text-ink">{notebook.name}</p>
                  <p className="truncate text-xs text-muted">
                    {stats.documentCount} tài liệu · {stats.noteCount} ghi chú · {relativeTime(stats.updatedAt)}
                  </p>
                </div>
              </button>

              <div className="hidden items-center gap-0.5 transition-opacity md:flex md:opacity-0 md:group-focus-within:opacity-100 md:group-hover:opacity-100">
                <Tooltip content="Thêm tài liệu vào notebook" side="top">
                  <Button
                    variant="ghost"
                    size="icon"
                    aria-label={`Thêm tài liệu vào ${notebook.name}`}
                    onClick={() => addDocument(notebook)}
                  >
                    <FileUp className="h-4 w-4 text-muted" />
                  </Button>
                </Tooltip>
                <Tooltip content="Thêm ghi chú vào notebook" side="top">
                  <Button
                    variant="ghost"
                    size="icon"
                    aria-label={`Thêm ghi chú vào ${notebook.name}`}
                    onClick={() => setNoteNotebookId(notebook.id)}
                  >
                    <StickyNote className="h-4 w-4 text-muted" />
                  </Button>
                </Tooltip>
              </div>

              <RowMenu label={`Tùy chọn cho notebook ${notebook.name}`}>
                <DropdownMenuItem icon={<BookOpen className="h-3.5 w-3.5" />} onClick={() => open(notebook)}>
                  Mở notebook
                </DropdownMenuItem>
                <DropdownMenuItem icon={<FileUp className="h-3.5 w-3.5" />} onClick={() => addDocument(notebook)}>
                  Thêm tài liệu
                </DropdownMenuItem>
                <DropdownMenuItem
                  icon={<FilePlus2 className="h-3.5 w-3.5" />}
                  onClick={() => setNoteNotebookId(notebook.id)}
                >
                  Thêm ghi chú
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem icon={<Pencil className="h-3.5 w-3.5" />} onClick={() => setRenameTarget(notebook)}>
                  Đổi tên
                </DropdownMenuItem>
                <DropdownMenuItem
                  icon={<ArrowRightLeft className="h-3.5 w-3.5" />}
                  onClick={() => setMoveTarget(notebook)}
                >
                  Chuyển sang workspace khác
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem
                  tone="danger"
                  icon={<Trash2 className="h-3.5 w-3.5" />}
                  onClick={() => setDeleteTarget(notebook)}
                >
                  Xóa notebook
                </DropdownMenuItem>
              </RowMenu>
            </li>
          ))}
        </ul>
      )}

      <NameDialog
        open={Boolean(renameTarget)}
        title="Đổi tên notebook"
        initialName={renameTarget?.name ?? ""}
        validate={(name) =>
          hasDuplicateName(
            wsNotebooks.filter((n) => n.id !== renameTarget?.id).map((n) => n.name),
            name,
          )
            ? "Đã có notebook cùng tên trong workspace này."
            : null
        }
        onClose={() => setRenameTarget(null)}
        onSubmit={(name) => {
          if (renameTarget) {
            renameNotebook(renameTarget.id, name)
            toast({ title: "Đã đổi tên notebook", tone: "success" })
          }
        }}
      />
      <ConfirmDialog
        open={Boolean(deleteTarget)}
        title={`Xóa notebook "${deleteTarget?.name ?? ""}"?`}
        description={`${deleteStats?.documentCount ?? 0} tài liệu và ${deleteStats?.noteCount ?? 0} ghi chú bên trong sẽ được giữ lại trong workspace ở mục "Chưa phân loại".`}
        confirmLabel="Xóa notebook"
        onClose={() => setDeleteTarget(null)}
        onConfirm={() => {
          if (deleteTarget) {
            deleteNotebook(deleteTarget.id)
            toast({ title: "Đã xóa notebook", tone: "success" })
          }
        }}
      />
      <MoveNotebookDialog notebook={moveTarget} onClose={() => setMoveTarget(null)} />
      <QuickNoteDialog
        open={noteNotebookId !== null}
        workspaceId={workspaceId}
        defaultNotebookId={noteNotebookId}
        onClose={() => setNoteNotebookId(null)}
      />
    </div>
  )
}
