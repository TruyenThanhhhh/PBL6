import { useState } from "react"
import { Button, Dialog, FormField, Input, Select, Textarea } from "@/components/ui"
import { useAppStore } from "@/store/app-store"
import { nowIso, uid } from "@/utils/format"
import type { Note } from "@/types"

function NoteForm({
  workspaceId,
  defaultNotebookId,
  note,
  onClose,
}: {
  workspaceId: string
  defaultNotebookId: string | null
  note: Note | null
  onClose: () => void
}) {
  const notebooks = useAppStore((s) => s.notebooks)
  const documents = useAppStore((s) => s.documents)
  const saveNote = useAppStore((s) => s.saveNote)
  const log = useAppStore((s) => s.log)
  const toast = useAppStore((s) => s.toast)

  const [title, setTitle] = useState(note?.title ?? "")
  const [content, setContent] = useState(note?.content ?? "")
  const [notebookId, setNotebookId] = useState(note?.notebookId ?? defaultNotebookId ?? "")
  const [documentId, setDocumentId] = useState(note?.documentId ?? "")

  const wsNotebooks = notebooks.filter((n) => n.workspaceId === workspaceId)
  const wsDocs = documents.filter((d) => d.workspaceId === workspaceId)

  return (
    <form
      className="space-y-3"
      onSubmit={(e) => {
        e.preventDefault()
        const trimmed = title.trim()
        if (!trimmed) return
        saveNote({
          id: note?.id ?? uid("note"),
          workspaceId,
          notebookId: notebookId || null,
          documentId: documentId || null,
          title: trimmed,
          content: content.trim(),
          updatedAt: nowIso(),
        })
        if (!note) log(`Tạo ghi chú "${trimmed}"`, "study")
        toast({ title: note ? "Đã cập nhật ghi chú" : "Đã lưu ghi chú mới", tone: "success" })
        onClose()
      }}
    >
      <FormField label="Tiêu đề">
        <Input autoFocus value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Tiêu đề ghi chú" />
      </FormField>
      <div className="grid gap-3 sm:grid-cols-2">
        <FormField label="Notebook">
          <Select value={notebookId} onChange={(e) => setNotebookId(e.target.value)}>
            <option value="">Chưa phân loại</option>
            {wsNotebooks.map((n) => (
              <option key={n.id} value={n.id}>
                {n.name}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField label="Tài liệu liên quan">
          <Select value={documentId} onChange={(e) => setDocumentId(e.target.value)}>
            <option value="">Không gắn tài liệu</option>
            {wsDocs.map((d) => (
              <option key={d.id} value={d.id}>
                {d.fileName}
              </option>
            ))}
          </Select>
        </FormField>
      </div>
      <FormField label="Nội dung">
        <Textarea rows={5} value={content} onChange={(e) => setContent(e.target.value)} placeholder="Nội dung ghi chú..." />
      </FormField>
      <div className="flex justify-end gap-2 pt-1">
        <Button type="button" variant="outline" onClick={onClose}>
          Hủy
        </Button>
        <Button type="submit" disabled={!title.trim()}>
          {note ? "Lưu thay đổi" : "Lưu ghi chú"}
        </Button>
      </div>
    </form>
  )
}

/** Hộp thoại tạo hoặc sửa ghi chú, dùng chung cho trang workspace và notebook. */
export function QuickNoteDialog({
  open,
  workspaceId,
  defaultNotebookId = null,
  note = null,
  onClose,
}: {
  open: boolean
  workspaceId: string
  defaultNotebookId?: string | null
  note?: Note | null
  onClose: () => void
}) {
  if (!open) return null
  return (
    <Dialog
      open={open}
      title={note ? "Chỉnh sửa ghi chú" : "Thêm ghi chú"}
      description="Ghi chú lưu trong phiên làm việc này (trạng thái cục bộ, chưa đồng bộ máy chủ)."
      onClose={onClose}
    >
      <NoteForm
        key={note?.id ?? "new"}
        workspaceId={workspaceId}
        defaultNotebookId={defaultNotebookId}
        note={note}
        onClose={onClose}
      />
    </Dialog>
  )
}
