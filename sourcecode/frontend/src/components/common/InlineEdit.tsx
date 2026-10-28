import { useState } from "react"
import { Input, Textarea } from "@/components/ui/input"
import { cn } from "@/utils/cn"

/**
 * Văn bản có thể chỉnh sửa tại chỗ: bấm để sửa, Enter để lưu, Esc để hủy, blur để lưu.
 * Với `multiline`, Shift+Enter xuống dòng.
 */
export function InlineEdit({
  value,
  onSave,
  ariaLabel,
  placeholder = "Nhấn để thêm",
  multiline = false,
  validate,
  className,
  inputClassName,
}: {
  value: string
  onSave: (next: string) => void
  ariaLabel: string
  placeholder?: string
  multiline?: boolean
  /** Trả về thông báo lỗi nếu giá trị không hợp lệ, hoặc null nếu hợp lệ. */
  validate?: (next: string) => string | null
  className?: string
  inputClassName?: string
}) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(value)
  const [error, setError] = useState<string | null>(null)

  const start = () => {
    setDraft(value)
    setError(null)
    setEditing(true)
  }

  const cancel = () => {
    setEditing(false)
    setError(null)
  }

  const commit = () => {
    const next = draft.trim()
    if (next === value.trim()) {
      cancel()
      return
    }
    const message = validate?.(next) ?? null
    if (message) {
      setError(message)
      return
    }
    onSave(next)
    setEditing(false)
    setError(null)
  }

  if (!editing) {
    return (
      <button
        type="button"
        onClick={start}
        aria-label={`Chỉnh sửa ${ariaLabel}`}
        title="Nhấn để chỉnh sửa"
        className={cn(
          "-mx-1.5 block w-full rounded-md px-1.5 text-left transition-colors hover:bg-bg-hover",
          className,
        )}
      >
        {value ? value : <span className="text-muted">{placeholder}</span>}
      </button>
    )
  }

  const shared = {
    autoFocus: true,
    "aria-label": ariaLabel,
    value: draft,
    state: error ? ("error" as const) : ("default" as const),
    onBlur: commit,
  }

  return (
    <div className="space-y-1">
      {multiline ? (
        <Textarea
          {...shared}
          rows={3}
          className={cn("min-h-[72px] text-sm", inputClassName)}
          onChange={(e) => {
            setDraft(e.target.value)
            if (error) setError(null)
          }}
          onKeyDown={(e) => {
            if (e.key === "Escape") cancel()
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault()
              commit()
            }
          }}
        />
      ) : (
        <Input
          {...shared}
          className={cn("h-auto py-1", inputClassName)}
          onChange={(e) => {
            setDraft(e.target.value)
            if (error) setError(null)
          }}
          onKeyDown={(e) => {
            if (e.key === "Escape") cancel()
            if (e.key === "Enter") {
              e.preventDefault()
              commit()
            }
          }}
        />
      )}
      {error ? (
        <p className="text-xs text-error">{error}</p>
      ) : (
        <p className="text-[11px] text-muted">
          Enter để lưu · Esc để hủy{multiline ? " · Shift+Enter xuống dòng" : ""}
        </p>
      )}
    </div>
  )
}
