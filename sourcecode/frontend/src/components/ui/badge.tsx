import type { ReactNode } from "react"
import { cn } from "@/utils/cn"
import type { DocumentStatus } from "@/types"

export type BadgeTone = "neutral" | "accent" | "success" | "warning" | "error"

export function Badge({
  children,
  tone = "neutral",
  dot = false,
  className,
}: {
  children: ReactNode
  tone?: BadgeTone
  dot?: boolean
  className?: string
}) {
  const tones: Record<BadgeTone, string> = {
    neutral: "bg-bg-secondary text-muted border-line",
    accent: "bg-accent-soft text-accent border-accent/20",
    success: "bg-success-soft text-success border-success/25",
    warning: "bg-warning-soft text-warning border-warning/25",
    error: "bg-error-soft text-error border-error/25",
  }

  const dotColors: Record<BadgeTone, string> = {
    neutral: "bg-muted",
    accent: "bg-accent",
    success: "bg-success",
    warning: "bg-warning",
    error: "bg-error",
  }

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-md border px-1.5 py-0.5 text-[11px] font-medium leading-tight",
        tones[tone],
        className,
      )}
    >
      {dot ? <span className={cn("h-1.5 w-1.5 shrink-0 rounded-full", dotColors[tone])} /> : null}
      {children}
    </span>
  )
}

export function StatusBadge({ status }: { status: DocumentStatus }) {
  if (status === "ready") return <Badge tone="success" dot>Sẵn sàng</Badge>
  if (status === "failed") return <Badge tone="error" dot>Lỗi</Badge>
  if (status === "uploaded") return <Badge tone="neutral" dot>Đã tải lên</Badge>
  return <Badge tone="warning" dot>Đang xử lý</Badge>
}
