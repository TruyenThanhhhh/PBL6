import { useEffect, type ReactNode } from "react"
import { X } from "lucide-react"
import { Button } from "./button"
import { cn } from "@/utils/cn"

export function Dialog({
  open,
  title,
  description,
  children,
  footer,
  size = "md",
  onClose,
  className,
}: {
  open: boolean
  title: string
  description?: string
  children: ReactNode
  footer?: ReactNode
  size?: "sm" | "md" | "lg"
  onClose: () => void
  className?: string
}) {
  useEffect(() => {
    if (!open) return
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose()
    }
    window.addEventListener("keydown", onKeyDown)
    return () => window.removeEventListener("keydown", onKeyDown)
  }, [open, onClose])

  if (!open) return null

  const sizes = {
    sm: "max-w-sm",
    md: "max-w-md",
    lg: "max-w-xl",
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <button className="absolute inset-0 bg-ink/30" aria-label="Đóng" onClick={onClose} />
      <div
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className={cn(
          "relative z-10 w-full rounded-[10px] border border-line bg-bg p-5",
          sizes[size],
          className,
        )}
      >
        <div className="mb-4 flex items-start justify-between gap-3">
          <div>
            <h2 className="text-base font-semibold text-ink">{title}</h2>
            {description ? <p className="mt-1 text-sm text-muted">{description}</p> : null}
          </div>
          <Button variant="ghost" size="icon" onClick={onClose} aria-label="Đóng">
            <X className="h-4 w-4" />
          </Button>
        </div>
        <div>{children}</div>
        {footer ? <div className="mt-5 flex justify-end gap-2 border-t border-line pt-4">{footer}</div> : null}
      </div>
    </div>
  )
}
