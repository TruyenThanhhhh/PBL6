import { useState } from "react"
import { Dialog } from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { FormField, Input, Textarea } from "@/components/ui/input"

function NameDialogForm({
  confirmLabel,
  initialName,
  initialDescription,
  showDescription,
  validate,
  onClose,
  onSubmit,
}: {
  confirmLabel: string
  initialName: string
  initialDescription: string
  showDescription: boolean
  validate?: (name: string) => string | null
  onClose: () => void
  onSubmit: (name: string, description: string) => void
}) {
  const [name, setName] = useState(initialName)
  const [desc, setDesc] = useState(initialDescription)
  const [error, setError] = useState<string | null>(null)

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault()
        const trimmed = name.trim()
        if (!trimmed) return
        const message = validate?.(trimmed) ?? null
        if (message) {
          setError(message)
          return
        }
        onSubmit(trimmed, desc.trim())
        onClose()
      }}
      className="space-y-3"
    >
      <FormField message={error ?? undefined} state={error ? "error" : "default"}>
        <Input
          autoFocus
          value={name}
          state={error ? "error" : "default"}
          onChange={(e) => {
            setName(e.target.value)
            if (error) setError(null)
          }}
          placeholder="Tên"
        />
      </FormField>
      {showDescription ? (
        <Textarea
          value={desc}
          onChange={(e) => setDesc(e.target.value)}
          placeholder="Mô tả (tuỳ chọn)"
        />
      ) : null}
      <div className="flex justify-end gap-2">
        <Button type="button" variant="outline" onClick={onClose}>
          Hủy
        </Button>
        <Button type="submit" disabled={!name.trim()}>
          {confirmLabel}
        </Button>
      </div>
    </form>
  )
}

export function NameDialog({
  open,
  title,
  description,
  confirmLabel = "Lưu",
  initialName = "",
  initialDescription = "",
  showDescription = false,
  validate,
  onClose,
  onSubmit,
}: {
  open: boolean
  title: string
  description?: string
  confirmLabel?: string
  initialName?: string
  initialDescription?: string
  showDescription?: boolean
  /** Trả về thông báo lỗi (chuỗi) nếu tên không hợp lệ, hoặc null nếu hợp lệ. */
  validate?: (name: string) => string | null
  onClose: () => void
  onSubmit: (name: string, description: string) => void
}) {
  if (!open) return null

  return (
    <Dialog open={open} title={title} description={description} onClose={onClose}>
      <NameDialogForm
        key={`${initialName}::${initialDescription}`}
        confirmLabel={confirmLabel}
        initialName={initialName}
        initialDescription={initialDescription}
        showDescription={showDescription}
        validate={validate}
        onClose={onClose}
        onSubmit={onSubmit}
      />
    </Dialog>
  )
}

export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel = "Xóa",
  onClose,
  onConfirm,
}: {
  open: boolean
  title: string
  description?: string
  confirmLabel?: string
  onClose: () => void
  onConfirm: () => void
}) {
  if (!open) return null
  return (
    <Dialog open={open} title={title} description={description} onClose={onClose}>
      <div className="flex justify-end gap-2">
        <Button variant="outline" onClick={onClose}>
          Hủy
        </Button>
        <Button
          variant="danger"
          onClick={() => {
            onConfirm()
            onClose()
          }}
        >
          {confirmLabel}
        </Button>
      </div>
    </Dialog>
  )
}
