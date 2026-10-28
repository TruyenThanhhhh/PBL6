import type { ReactNode } from "react"
import { cn } from "@/utils/cn"

export function EmptyState({
  icon,
  title,
  description,
  action,
  compact = false,
  className,
}: {
  icon?: ReactNode
  title: string
  description: string
  action?: ReactNode
  compact?: boolean
  className?: string
}) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center rounded-lg border border-dashed border-line bg-bg-secondary/40 px-6 text-center",
        compact ? "py-8" : "py-14",
        className,
      )}
    >
      {icon ? (
        <div className="mb-3 flex h-9 w-9 items-center justify-center rounded-lg border border-line bg-bg text-muted">
          {icon}
        </div>
      ) : null}
      <p className="text-sm font-medium text-ink">{title}</p>
      <p className="mt-1 max-w-md text-sm text-muted">{description}</p>
      {action ? <div className="mt-4">{action}</div> : null}
    </div>
  )
}
