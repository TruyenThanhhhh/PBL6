import type { ReactNode } from "react"
import { useNavigate } from "react-router-dom"
import { MoreHorizontal, Pencil, Trash2 } from "lucide-react"
import { Badge, Button, DropdownMenu, DropdownMenuItem, StatusBadge } from "@/components/ui"
import { formatBytes, relativeTime } from "@/utils/format"
import type { Conversation, KnowledgeDocument, Note, Notebook } from "@/types"

/** Nút `...` hiện khi hover/focus trên desktop, luôn hiện trên màn hình cảm ứng. */
export function RowMenu({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="shrink-0 transition-opacity md:opacity-0 md:group-focus-within:opacity-100 md:group-hover:opacity-100">
      <DropdownMenu
        trigger={
          <Button variant="ghost" size="icon" aria-label={label}>
            <MoreHorizontal className="h-4 w-4 text-muted" />
          </Button>
        }
      >
        {children}
      </DropdownMenu>
    </div>
  )
}

export function DocumentRows({ docs, notebooks }: { docs: KnowledgeDocument[]; notebooks: Notebook[] }) {
  const navigate = useNavigate()
  return (
    <ul className="divide-y divide-line border-y border-line">
      {docs.map((d) => {
        const nb = notebooks.find((n) => n.id === d.notebookId)
        return (
          <li key={d.id} className="group flex items-center gap-3 transition-colors hover:bg-bg-hover/70">
            <button
              type="button"
              onClick={() => navigate(`/documents/${d.id}`)}
              className="flex min-w-0 flex-1 items-center justify-between gap-3 py-2.5 text-left"
            >
              <div className="min-w-0">
                <div className="flex items-center gap-1.5">
                  <span className="truncate text-sm font-medium text-ink">{d.fileName}</span>
                  {d.mock ? (
                    <span className="shrink-0 rounded border border-line bg-bg-secondary px-1 text-[10px] text-muted">
                      mô phỏng
                    </span>
                  ) : null}
                </div>
                <p className="mt-0.5 truncate text-xs text-muted">
                  {d.fileType.toUpperCase()} · {formatBytes(d.fileSize)} · {nb ? nb.name : "Chưa phân loại"} ·{" "}
                  {relativeTime(d.createdAt)}
                </p>
              </div>
              <StatusBadge status={d.status} />
            </button>
          </li>
        )
      })}
    </ul>
  )
}

export function NoteRows({
  notes,
  notebooks,
  onEdit,
  onDelete,
}: {
  notes: Note[]
  notebooks: Notebook[]
  onEdit: (note: Note) => void
  onDelete: (note: Note) => void
}) {
  return (
    <ul className="divide-y divide-line border-y border-line">
      {notes.map((n) => {
        const nb = notebooks.find((x) => x.id === n.notebookId)
        return (
          <li key={n.id} className="group flex items-start gap-3 transition-colors hover:bg-bg-hover/70">
            <button type="button" onClick={() => onEdit(n)} className="min-w-0 flex-1 py-2.5 text-left">
              <div className="flex items-center justify-between gap-2">
                <span className="truncate text-sm font-medium text-ink">{n.title}</span>
                <span className="shrink-0 text-xs text-muted">{relativeTime(n.updatedAt)}</span>
              </div>
              <p className="mt-0.5 line-clamp-2 text-xs text-muted">{n.content || "Không có nội dung"}</p>
              <div className="mt-1">
                <Badge tone="neutral">{nb ? nb.name : "Chưa phân loại"}</Badge>
              </div>
            </button>
            <div className="pt-1.5">
              <RowMenu label={`Tùy chọn cho ghi chú ${n.title}`}>
                <DropdownMenuItem icon={<Pencil className="h-3.5 w-3.5" />} onClick={() => onEdit(n)}>
                  Chỉnh sửa
                </DropdownMenuItem>
                <DropdownMenuItem tone="danger" icon={<Trash2 className="h-3.5 w-3.5" />} onClick={() => onDelete(n)}>
                  Xóa ghi chú
                </DropdownMenuItem>
              </RowMenu>
            </div>
          </li>
        )
      })}
    </ul>
  )
}

export function ChatRows({ chats }: { chats: Conversation[] }) {
  const navigate = useNavigate()
  return (
    <ul className="divide-y divide-line border-y border-line">
      {chats.map((c) => {
        const last = [...c.messages].reverse().find((m) => m.role === "assistant")
        const isMock = !last?.engine || last.engine.startsWith("mock")
        return (
          <li key={c.id} className="transition-colors hover:bg-bg-hover/70">
            <button
              type="button"
              onClick={() => navigate(`/chat/${c.id}`)}
              className="flex w-full items-center justify-between gap-3 py-2.5 text-left"
            >
              <div className="min-w-0">
                <div className="flex items-center gap-1.5">
                  <span className="truncate text-sm font-medium text-ink">{c.title}</span>
                  {isMock ? (
                    <span className="shrink-0 rounded border border-line bg-bg-secondary px-1 text-[10px] text-muted">
                      mô phỏng
                    </span>
                  ) : null}
                </div>
                <p className="mt-0.5 text-xs text-muted">
                  {c.messages.length} tin nhắn · {relativeTime(c.updatedAt)}
                </p>
              </div>
            </button>
          </li>
        )
      })}
    </ul>
  )
}
