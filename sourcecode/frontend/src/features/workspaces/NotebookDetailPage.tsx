import { useState } from "react"
import { Link, useNavigate, useParams } from "react-router-dom"
import {
  ArrowRightLeft,
  ChevronRight,
  FilePlus2,
  FileUp,
  MoreHorizontal,
  Pencil,
  Search,
  Trash2,
} from "lucide-react"
import { ConfirmDialog } from "@/components/common/NameDialog"
import { InlineEdit } from "@/components/common/InlineEdit"
import {
  Button,
  DropdownMenu,
  DropdownMenuItem,
  DropdownMenuSeparator,
  EmptyState,
  Input,
  Select,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/components/ui"
import { useAppStore } from "@/store/app-store"
import { relativeTime } from "@/utils/format"
import type { Note } from "@/types"
import { DocumentRows, NoteRows } from "./ContentLists"
import { MoveNotebookDialog } from "./MoveNotebookDialog"
import { QuickNoteDialog } from "./QuickNoteDialog"
import { getNotebookStats, hasDuplicateName } from "./workspace-utils"

type ItemSort = "updated" | "name"

export function NotebookDetailPage() {
  const { workspaceId, notebookId } = useParams()
  const navigate = useNavigate()

  const workspaces = useAppStore((s) => s.workspaces)
  const notebooks = useAppStore((s) => s.notebooks)
  const documents = useAppStore((s) => s.documents)
  const notes = useAppStore((s) => s.notes)
  const renameNotebook = useAppStore((s) => s.renameNotebook)
  const deleteNotebook = useAppStore((s) => s.deleteNotebook)
  const deleteNote = useAppStore((s) => s.deleteNote)
  const setCurrent = useAppStore((s) => s.setCurrentWorkspace)
  const toast = useAppStore((s) => s.toast)

  const [tab, setTab] = useState("documents")
  const [q, setQ] = useState("")
  const [sort, setSort] = useState<ItemSort>("updated")
  const [deleteOpen, setDeleteOpen] = useState(false)
  const [moveOpen, setMoveOpen] = useState(false)
  const [noteDialog, setNoteDialog] = useState<{ open: boolean; note: Note | null }>({ open: false, note: null })
  const [noteToDelete, setNoteToDelete] = useState<Note | null>(null)

  const ws = workspaces.find((w) => w.id === workspaceId)
  const nb = notebooks.find((n) => n.id === notebookId && n.workspaceId === workspaceId)

  if (!ws || !nb) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-8 md:px-8">
        <EmptyState
          title="Không tìm thấy notebook"
          description="Notebook có thể đã bị xóa, đã được chuyển sang workspace khác hoặc đường dẫn không đúng."
          action={<Button onClick={() => navigate(ws ? `/knowledge/${ws.id}?tab=notebooks` : "/knowledge")}>Quay lại</Button>}
        />
      </div>
    )
  }

  const stats = getNotebookStats(nb, documents, notes)
  const needle = q.trim().toLowerCase()

  const nbDocs = documents
    .filter((d) => d.notebookId === nb.id && d.fileName.toLowerCase().includes(needle))
    .sort((a, b) => (sort === "name" ? a.fileName.localeCompare(b.fileName, "vi") : b.createdAt.localeCompare(a.createdAt)))
  const nbNotes = notes
    .filter(
      (n) =>
        n.notebookId === nb.id &&
        (n.title.toLowerCase().includes(needle) || n.content.toLowerCase().includes(needle)),
    )
    .sort((a, b) => (sort === "name" ? a.title.localeCompare(b.title, "vi") : b.updatedAt.localeCompare(a.updatedAt)))

  const wsNotebooks = notebooks.filter((n) => n.workspaceId === ws.id)

  const addDocument = () => {
    setCurrent(ws.id)
    navigate(`/documents?notebook=${nb.id}`)
  }

  return (
    <div className="mx-auto max-w-5xl px-4 py-8 md:px-8">
      <nav aria-label="Đường dẫn" className="mb-2 flex flex-wrap items-center gap-1 text-xs text-muted">
        <Link to="/knowledge" className="transition-colors hover:text-ink">
          Kho tri thức
        </Link>
        <ChevronRight className="h-3 w-3" />
        <Link to={`/knowledge/${ws.id}?tab=notebooks`} className="transition-colors hover:text-ink">
          {ws.name}
        </Link>
        <ChevronRight className="h-3 w-3" />
        <span className="truncate text-ink">{nb.name}</span>
      </nav>

      <div className="mb-5 flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <h1 className="text-[26px] font-semibold tracking-tight text-ink">
            <InlineEdit
              ariaLabel="tên notebook"
              value={nb.name}
              inputClassName="text-[22px] font-semibold"
              validate={(name) =>
                !name
                  ? "Tên không được để trống."
                  : hasDuplicateName(
                        wsNotebooks.filter((n) => n.id !== nb.id).map((n) => n.name),
                        name,
                      )
                    ? "Đã có notebook cùng tên trong workspace này."
                    : null
              }
              onSave={(name) => {
                renameNotebook(nb.id, name)
                toast({ title: "Đã đổi tên notebook", tone: "success" })
              }}
            />
          </h1>
          <p className="mt-2 text-xs text-muted">
            {stats.documentCount} tài liệu · {stats.noteCount} ghi chú · Cập nhật {relativeTime(stats.updatedAt)}
          </p>
        </div>

        <DropdownMenu
          trigger={
            <Button variant="outline" size="icon" aria-label="Thao tác notebook">
              <MoreHorizontal className="h-4 w-4" />
            </Button>
          }
        >
          <DropdownMenuItem icon={<FileUp className="h-3.5 w-3.5" />} onClick={addDocument}>
            Thêm tài liệu
          </DropdownMenuItem>
          <DropdownMenuItem
            icon={<FilePlus2 className="h-3.5 w-3.5" />}
            onClick={() => setNoteDialog({ open: true, note: null })}
          >
            Thêm ghi chú
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem
            icon={<Pencil className="h-3.5 w-3.5" />}
            onClick={() => toast({ title: "Nhấn vào tiêu đề notebook để đổi tên", tone: "info" })}
          >
            Đổi tên
          </DropdownMenuItem>
          <DropdownMenuItem icon={<ArrowRightLeft className="h-3.5 w-3.5" />} onClick={() => setMoveOpen(true)}>
            Chuyển sang workspace khác
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem tone="danger" icon={<Trash2 className="h-3.5 w-3.5" />} onClick={() => setDeleteOpen(true)}>
            Xóa notebook
          </DropdownMenuItem>
        </DropdownMenu>
      </div>

      <div className="mb-6 flex flex-wrap items-center gap-2">
        <Button leftIcon={<FileUp className="h-4 w-4" />} onClick={addDocument}>
          Thêm tài liệu
        </Button>
        <Button
          variant="outline"
          leftIcon={<FilePlus2 className="h-4 w-4" />}
          onClick={() => setNoteDialog({ open: true, note: null })}
        >
          Thêm ghi chú
        </Button>
      </div>

      <div className="mb-3 flex flex-wrap items-center gap-2">
        <div className="relative w-full max-w-xs">
          <Search className="pointer-events-none absolute left-2.5 top-2.5 h-3.5 w-3.5 text-muted" />
          <Input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Tìm trong notebook"
            aria-label="Tìm trong notebook"
            className="pl-8"
          />
        </div>
        <div className="w-44">
          <Select value={sort} onChange={(e) => setSort(e.target.value as ItemSort)} aria-label="Sắp xếp nội dung">
            <option value="updated">Mới cập nhật</option>
            <option value="name">Tên (A–Z)</option>
          </Select>
        </div>
      </div>

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="documents">
            Tài liệu <span className="text-xs text-muted">{nbDocs.length}</span>
          </TabsTrigger>
          <TabsTrigger value="notes">
            Ghi chú <span className="text-xs text-muted">{nbNotes.length}</span>
          </TabsTrigger>
        </TabsList>

        <TabsContent value="documents">
          {nbDocs.length === 0 ? (
            <EmptyState
              compact
              icon={<FileUp className="h-4 w-4" />}
              title={q ? "Không tìm thấy tài liệu" : "Notebook chưa có tài liệu"}
              description={q ? `Không có tài liệu nào khớp với "${q}".` : "Thêm tài liệu để lưu vào notebook này."}
              action={q ? <Button variant="outline" onClick={() => setQ("")}>Xóa bộ lọc</Button> : <Button onClick={addDocument}>Thêm tài liệu</Button>}
            />
          ) : (
            <DocumentRows docs={nbDocs} notebooks={wsNotebooks} />
          )}
        </TabsContent>

        <TabsContent value="notes">
          {nbNotes.length === 0 ? (
            <EmptyState
              compact
              icon={<FilePlus2 className="h-4 w-4" />}
              title={q ? "Không tìm thấy ghi chú" : "Notebook chưa có ghi chú"}
              description={q ? `Không có ghi chú nào khớp với "${q}".` : "Thêm ghi chú để lưu ý tưởng và tóm tắt."}
              action={
                q ? (
                  <Button variant="outline" onClick={() => setQ("")}>
                    Xóa bộ lọc
                  </Button>
                ) : (
                  <Button onClick={() => setNoteDialog({ open: true, note: null })}>Thêm ghi chú</Button>
                )
              }
            />
          ) : (
            <NoteRows
              notes={nbNotes}
              notebooks={wsNotebooks}
              onEdit={(note) => setNoteDialog({ open: true, note })}
              onDelete={setNoteToDelete}
            />
          )}
        </TabsContent>
      </Tabs>

      <QuickNoteDialog
        open={noteDialog.open}
        workspaceId={ws.id}
        defaultNotebookId={nb.id}
        note={noteDialog.note}
        onClose={() => setNoteDialog({ open: false, note: null })}
      />
      <ConfirmDialog
        open={Boolean(noteToDelete)}
        title={`Xóa ghi chú "${noteToDelete?.title ?? ""}"?`}
        confirmLabel="Xóa ghi chú"
        onClose={() => setNoteToDelete(null)}
        onConfirm={() => {
          if (noteToDelete) {
            deleteNote(noteToDelete.id)
            toast({ title: "Đã xóa ghi chú", tone: "success" })
          }
        }}
      />
      <ConfirmDialog
        open={deleteOpen}
        title={`Xóa notebook "${nb.name}"?`}
        description={`${stats.documentCount} tài liệu và ${stats.noteCount} ghi chú bên trong sẽ được giữ lại trong workspace ở mục "Chưa phân loại".`}
        confirmLabel="Xóa notebook"
        onClose={() => setDeleteOpen(false)}
        onConfirm={() => {
          deleteNotebook(nb.id)
          toast({ title: "Đã xóa notebook", tone: "success" })
          navigate(`/knowledge/${ws.id}?tab=notebooks`)
        }}
      />
      <MoveNotebookDialog
        notebook={moveOpen ? nb : null}
        onClose={() => setMoveOpen(false)}
        onMoved={(target) => navigate(`/knowledge/${target}/notebooks/${nb.id}`)}
      />
    </div>
  )
}
