import { useEffect, useState } from "react"
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom"
import {
  ChevronRight,
  FilePlus2,
  FileUp,
  FolderPlus,
  MessageSquare,
  Pencil,
  Plus,
  Trash2,
  Check,
  BookOpen,
} from "lucide-react"
import { ConfirmDialog, NameDialog } from "@/components/common/NameDialog"
import { InlineEdit } from "@/components/common/InlineEdit"
import {
  Button,
  DropdownMenu,
  DropdownMenuItem,
  DropdownMenuSeparator,
  EmptyState,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/components/ui"
import { MoreHorizontal } from "lucide-react"
import { useAppStore } from "@/store/app-store"
import { relativeTime } from "@/utils/format"
import type { Note } from "@/types"
import { ChatRows, DocumentRows, NoteRows } from "./ContentLists"
import { NotebookSection } from "./NotebookSection"
import { QuickNoteDialog } from "./QuickNoteDialog"
import { describeWorkspaceDeletion, getWorkspaceCounts, hasDuplicateName } from "./workspace-utils"

const TAB_IDS = ["overview", "notebooks", "documents", "notes", "chats"] as const
type TabId = (typeof TAB_IDS)[number]

function isTabId(value: string | null): value is TabId {
  return TAB_IDS.includes(value as TabId)
}

export function WorkspaceDetailPage() {
  const { workspaceId } = useParams()
  const navigate = useNavigate()
  const [params, setParams] = useSearchParams()

  const workspaces = useAppStore((s) => s.workspaces)
  const notebooks = useAppStore((s) => s.notebooks)
  const documents = useAppStore((s) => s.documents)
  const notes = useAppStore((s) => s.notes)
  const conversations = useAppStore((s) => s.conversations)
  const currentWorkspaceId = useAppStore((s) => s.currentWorkspaceId)
  const updateWorkspace = useAppStore((s) => s.updateWorkspace)
  const deleteWorkspace = useAppStore((s) => s.deleteWorkspace)
  const deleteNote = useAppStore((s) => s.deleteNote)
  const createNotebook = useAppStore((s) => s.createNotebook)
  const createConversation = useAppStore((s) => s.createConversation)
  const setCurrent = useAppStore((s) => s.setCurrentWorkspace)
  const toast = useAppStore((s) => s.toast)

  const [editOpen, setEditOpen] = useState(false)
  const [deleteOpen, setDeleteOpen] = useState(false)
  const [notebookOpen, setNotebookOpen] = useState(false)
  const [noteDialog, setNoteDialog] = useState<{ open: boolean; note: Note | null }>({ open: false, note: null })
  const [noteToDelete, setNoteToDelete] = useState<Note | null>(null)

  const ws = workspaces.find((w) => w.id === workspaceId)

  useEffect(() => {
    if (ws && currentWorkspaceId !== ws.id) {
      setCurrent(ws.id)
    }
  }, [ws, currentWorkspaceId, setCurrent])

  if (!ws) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-8 md:px-8">
        <EmptyState
          title="Không tìm thấy workspace"
          description="Workspace có thể đã bị xóa hoặc đường dẫn không đúng."
          action={<Button onClick={() => navigate("/knowledge")}>Về Kho tri thức</Button>}
        />
      </div>
    )
  }

  const tabParam = params.get("tab")
  const tab: TabId = isTabId(tabParam) ? tabParam : "overview"
  const setTab = (next: string) => setParams(next === "overview" ? {} : { tab: next }, { replace: true })

  const nbs = notebooks.filter((n) => n.workspaceId === ws.id)
  const docs = documents.filter((d) => d.workspaceId === ws.id)
  const wsNotes = notes.filter((n) => n.workspaceId === ws.id)
  const chats = conversations.filter((c) => c.workspaceId === ws.id)
  const isCurrent = currentWorkspaceId === ws.id
  const counts = getWorkspaceCounts(ws.id, { notebooks, documents, notes, conversations })

  const sortedDocs = [...docs].sort((a, b) => b.createdAt.localeCompare(a.createdAt))
  const sortedNotes = [...wsNotes].sort((a, b) => b.updatedAt.localeCompare(a.updatedAt))
  const sortedChats = [...chats].sort((a, b) => b.updatedAt.localeCompare(a.updatedAt))

  const recent = [
    ...docs.map((d) => ({ id: d.id, kind: "Tài liệu", title: d.fileName, at: d.createdAt, open: () => navigate(`/documents/${d.id}`) })),
    ...wsNotes.map((n) => ({ id: n.id, kind: "Ghi chú", title: n.title, at: n.updatedAt, open: () => setNoteDialog({ open: true, note: n }) })),
    ...chats.map((c) => ({ id: c.id, kind: "Hội thoại", title: c.title, at: c.updatedAt, open: () => navigate(`/chat/${c.id}`) })),
  ]
    .sort((a, b) => b.at.localeCompare(a.at))
    .slice(0, 8)

  const goAddDocument = () => {
    setCurrent(ws.id)
    navigate("/documents")
  }
  const newChat = () => {
    setCurrent(ws.id)
    const c = createConversation(ws.id)
    navigate(`/chat/${c.id}`)
  }
  const validateWorkspaceName = (name: string) =>
    hasDuplicateName(
      workspaces.filter((w) => w.id !== ws.id).map((w) => w.name),
      name,
    )
      ? "Đã có workspace cùng tên."
      : null

  return (
    <div className="mx-auto max-w-5xl px-4 py-8 md:px-8">
      {/* Breadcrumb + title + actions */}
      <nav aria-label="Đường dẫn" className="mb-2 flex items-center gap-1 text-xs text-muted">
        <Link to="/knowledge" className="transition-colors hover:text-ink">
          Kho tri thức
        </Link>
        <ChevronRight className="h-3 w-3" />
        <span className="truncate text-ink">{ws.name}</span>
      </nav>

      <div className="mb-5 flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <h1 className="text-[26px] font-semibold tracking-tight text-ink">
            <InlineEdit
              ariaLabel="tên workspace"
              value={ws.name}
              inputClassName="text-[22px] font-semibold"
              validate={(name) => (name ? validateWorkspaceName(name) : "Tên không được để trống.")}
              onSave={(name) => {
                updateWorkspace(ws.id, { name })
                toast({ title: "Đã đổi tên workspace", tone: "success" })
              }}
            />
          </h1>
          <div className="mt-1 max-w-2xl text-sm text-muted">
            <InlineEdit
              multiline
              ariaLabel="mô tả workspace"
              placeholder="Thêm mô tả cho workspace..."
              value={ws.description}
              onSave={(description) => {
                updateWorkspace(ws.id, { description })
                toast({ title: "Đã cập nhật mô tả", tone: "success" })
              }}
            />
          </div>
          <p className="mt-2 text-xs text-muted">
            Cập nhật {relativeTime(ws.updatedAt)} · {isCurrent ? "Đang là workspace hiện tại" : "Không phải workspace hiện tại"}
          </p>
        </div>

        <DropdownMenu
          trigger={
            <Button variant="outline" size="icon" aria-label="Thao tác workspace">
              <MoreHorizontal className="h-4 w-4" />
            </Button>
          }
        >
          <DropdownMenuItem icon={<Pencil className="h-3.5 w-3.5" />} onClick={() => setEditOpen(true)}>
            Chỉnh sửa tên và mô tả
          </DropdownMenuItem>
          <DropdownMenuItem
            icon={<Check className="h-3.5 w-3.5" />}
            disabled={isCurrent}
            onClick={() => {
              setCurrent(ws.id)
              toast({ title: `Đã chuyển sang "${ws.name}"`, tone: "info" })
            }}
          >
            {isCurrent ? "Đang là workspace hiện tại" : "Đặt làm workspace hiện tại"}
          </DropdownMenuItem>
          <DropdownMenuItem icon={<MessageSquare className="h-3.5 w-3.5" />} onClick={newChat}>
            Hỏi đáp AI trong workspace
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem tone="danger" icon={<Trash2 className="h-3.5 w-3.5" />} onClick={() => setDeleteOpen(true)}>
            Xóa workspace
          </DropdownMenuItem>
        </DropdownMenu>
      </div>

      {/* Quick actions */}
      <div className="mb-6 flex flex-wrap items-center gap-2">
        <Button leftIcon={<FolderPlus className="h-4 w-4" />} onClick={() => setNotebookOpen(true)}>
          Thêm notebook
        </Button>
        <Button variant="outline" leftIcon={<FileUp className="h-4 w-4" />} onClick={goAddDocument}>
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

      {/* Tabs */}
      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="overview">Tổng quan</TabsTrigger>
          <TabsTrigger value="notebooks">
            Notebook <span className="text-xs text-muted">{nbs.length}</span>
          </TabsTrigger>
          <TabsTrigger value="documents">
            Tài liệu <span className="text-xs text-muted">{docs.length}</span>
          </TabsTrigger>
          <TabsTrigger value="notes">
            Ghi chú <span className="text-xs text-muted">{wsNotes.length}</span>
          </TabsTrigger>
          <TabsTrigger value="chats">
            Hội thoại AI <span className="text-xs text-muted">{chats.length}</span>
          </TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="space-y-8">
          <dl className="grid grid-cols-2 divide-x divide-y divide-line border-y border-l-0 border-line sm:grid-cols-4 sm:divide-y-0">
            {[
              ["Notebook", counts.notebooks],
              ["Tài liệu", counts.documents],
              ["Ghi chú", counts.notes],
              ["Hội thoại AI", counts.conversations],
            ].map(([label, value], i) => (
              <div key={label} className={i % 2 === 0 ? "py-3 pr-4" : "px-4 py-3"}>
                <dt className="text-xs text-muted">{label}</dt>
                <dd className="mt-0.5 text-xl font-semibold tracking-tight">{value}</dd>
              </div>
            ))}
          </dl>

          <section>
            <h2 className="mb-2 text-base font-semibold">Nội dung gần đây</h2>
            {recent.length === 0 ? (
              <EmptyState
                compact
                title="Workspace chưa có nội dung"
                description="Thêm notebook, tài liệu hoặc ghi chú để bắt đầu."
              />
            ) : (
              <ul className="divide-y divide-line border-y border-line">
                {recent.map((item) => (
                  <li key={`${item.kind}-${item.id}`} className="transition-colors hover:bg-bg-hover/70">
                    <button type="button" onClick={item.open} className="flex w-full items-center gap-3 py-2.5 text-left">
                      <span className="w-20 shrink-0 text-xs text-muted">{item.kind}</span>
                      <span className="min-w-0 flex-1 truncate text-sm text-ink">{item.title}</span>
                      <span className="shrink-0 text-xs text-muted">{relativeTime(item.at)}</span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section>
            <div className="mb-2 flex items-center justify-between">
              <h2 className="text-base font-semibold">Notebook</h2>
              <Button variant="ghost" size="sm" onClick={() => setTab("notebooks")}>
                Quản lý notebook
              </Button>
            </div>
            {nbs.length === 0 ? (
              <EmptyState
                compact
                icon={<BookOpen className="h-4 w-4" />}
                title="Chưa có notebook"
                description="Tạo notebook để nhóm tài liệu và ghi chú theo chủ đề."
                action={<Button onClick={() => setNotebookOpen(true)}>Thêm notebook</Button>}
              />
            ) : (
              <ul className="divide-y divide-line border-y border-line">
                {nbs.slice(0, 5).map((n) => (
                  <li key={n.id} className="transition-colors hover:bg-bg-hover/70">
                    <button
                      type="button"
                      onClick={() => navigate(`/knowledge/${ws.id}/notebooks/${n.id}`)}
                      className="flex w-full items-center justify-between py-2.5 text-left"
                    >
                      <span className="truncate text-sm text-ink">{n.name}</span>
                      <span className="text-xs text-muted">
                        {documents.filter((d) => d.notebookId === n.id).length} tài liệu ·{" "}
                        {notes.filter((x) => x.notebookId === n.id).length} ghi chú
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </TabsContent>

        <TabsContent value="notebooks">
          <NotebookSection workspaceId={ws.id} onCreate={() => setNotebookOpen(true)} />
        </TabsContent>

        <TabsContent value="documents">
          {sortedDocs.length === 0 ? (
            <EmptyState
              compact
              icon={<FileUp className="h-4 w-4" />}
              title="Workspace chưa có tài liệu"
              description="Tải lên PDF, DOCX, PPTX, TXT hoặc Markdown trong trình quản lý tài liệu."
              action={<Button onClick={goAddDocument}>Thêm tài liệu</Button>}
            />
          ) : (
            <DocumentRows docs={sortedDocs} notebooks={nbs} />
          )}
        </TabsContent>

        <TabsContent value="notes">
          {sortedNotes.length === 0 ? (
            <EmptyState
              compact
              icon={<FilePlus2 className="h-4 w-4" />}
              title="Workspace chưa có ghi chú"
              description="Lưu tóm tắt hoặc nhận xét quan trọng khi đọc tài liệu."
              action={<Button onClick={() => setNoteDialog({ open: true, note: null })}>Thêm ghi chú</Button>}
            />
          ) : (
            <NoteRows
              notes={sortedNotes}
              notebooks={nbs}
              onEdit={(note) => setNoteDialog({ open: true, note })}
              onDelete={setNoteToDelete}
            />
          )}
        </TabsContent>

        <TabsContent value="chats">
          <div className="mb-3 flex justify-end">
            <Button variant="outline" leftIcon={<Plus className="h-4 w-4" />} onClick={newChat}>
              Hội thoại mới
            </Button>
          </div>
          {sortedChats.length === 0 ? (
            <EmptyState
              compact
              icon={<MessageSquare className="h-4 w-4" />}
              title="Chưa có hội thoại AI"
              description="Đặt câu hỏi dựa trên tài liệu trong workspace này."
              action={<Button onClick={newChat}>Hỏi đáp AI</Button>}
            />
          ) : (
            <ChatRows chats={sortedChats} />
          )}
        </TabsContent>
      </Tabs>

      {/* Dialogs */}
      <NameDialog
        open={editOpen}
        title="Chỉnh sửa workspace"
        initialName={ws.name}
        initialDescription={ws.description}
        showDescription
        validate={validateWorkspaceName}
        onClose={() => setEditOpen(false)}
        onSubmit={(name, description) => {
          updateWorkspace(ws.id, { name, description })
          toast({ title: "Đã cập nhật workspace", tone: "success" })
        }}
      />
      <NameDialog
        open={notebookOpen}
        title="Thêm notebook"
        confirmLabel="Thêm"
        validate={(name) =>
          hasDuplicateName(
            nbs.map((n) => n.name),
            name,
          )
            ? "Đã có notebook cùng tên trong workspace này."
            : null
        }
        onClose={() => setNotebookOpen(false)}
        onSubmit={(name) => {
          createNotebook(ws.id, name)
          toast({ title: "Đã thêm notebook", tone: "success" })
          setTab("notebooks")
        }}
      />
      <QuickNoteDialog
        open={noteDialog.open}
        workspaceId={ws.id}
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
        title={`Xóa workspace "${ws.name}"?`}
        description={describeWorkspaceDeletion(counts)}
        confirmLabel="Xóa workspace"
        onClose={() => setDeleteOpen(false)}
        onConfirm={() => {
          deleteWorkspace(ws.id)
          toast({ title: "Đã xóa workspace", tone: "success" })
          navigate("/knowledge")
        }}
      />
    </div>
  )
}
