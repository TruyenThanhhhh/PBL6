import { useState } from "react"
import { Button, Dialog, FormField, Select } from "@/components/ui"
import { useAppStore } from "@/store/app-store"
import type { Notebook } from "@/types"
import { hasDuplicateName } from "./workspace-utils"

function MoveForm({
  notebook,
  onClose,
  onMoved,
}: {
  notebook: Notebook
  onClose: () => void
  onMoved?: (targetWorkspaceId: string) => void
}) {
  const workspaces = useAppStore((s) => s.workspaces)
  const notebooks = useAppStore((s) => s.notebooks)
  const moveNotebook = useAppStore((s) => s.moveNotebook)
  const toast = useAppStore((s) => s.toast)

  const targets = workspaces.filter((w) => w.id !== notebook.workspaceId)
  const [target, setTarget] = useState(targets[0]?.id ?? "")

  if (targets.length === 0) {
    return (
      <div className="space-y-4">
        <p className="text-sm text-muted">Chưa có workspace khác. Hãy tạo workspace mới trước khi chuyển notebook.</p>
        <div className="flex justify-end">
          <Button variant="outline" onClick={onClose}>
            Đóng
          </Button>
        </div>
      </div>
    )
  }

  const duplicate =
    Boolean(target) &&
    hasDuplicateName(
      notebooks.filter((n) => n.workspaceId === target).map((n) => n.name),
      notebook.name,
    )

  return (
    <form
      className="space-y-3"
      onSubmit={(e) => {
        e.preventDefault()
        if (!target || duplicate) return
        moveNotebook(notebook.id, target)
        toast({ title: "Đã chuyển notebook", description: "Tài liệu và ghi chú bên trong được chuyển theo.", tone: "success" })
        onMoved?.(target)
        onClose()
      }}
    >
      <FormField
        label="Workspace đích"
        state={duplicate ? "error" : "default"}
        message={duplicate ? "Workspace đích đã có notebook trùng tên." : undefined}
      >
        <Select value={target} state={duplicate ? "error" : "default"} onChange={(e) => setTarget(e.target.value)}>
          {targets.map((w) => (
            <option key={w.id} value={w.id}>
              {w.name}
            </option>
          ))}
        </Select>
      </FormField>
      <div className="flex justify-end gap-2 pt-1">
        <Button type="button" variant="outline" onClick={onClose}>
          Hủy
        </Button>
        <Button type="submit" disabled={!target || duplicate}>
          Chuyển
        </Button>
      </div>
    </form>
  )
}

export function MoveNotebookDialog({
  notebook,
  onClose,
  onMoved,
}: {
  notebook: Notebook | null
  onClose: () => void
  onMoved?: (targetWorkspaceId: string) => void
}) {
  if (!notebook) return null
  return (
    <Dialog
      open
      title={`Chuyển "${notebook.name}"`}
      description="Tài liệu và ghi chú thuộc notebook sẽ được chuyển cùng sang workspace đích."
      onClose={onClose}
    >
      <MoveForm key={notebook.id} notebook={notebook} onClose={onClose} onMoved={onMoved} />
    </Dialog>
  )
}
