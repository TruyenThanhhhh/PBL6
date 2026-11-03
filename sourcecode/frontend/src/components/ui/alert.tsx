import type { ReactNode } from "react"
import { AlertCircle, AlertTriangle, CheckCircle2, Info, X } from "lucide-react"
import { cn } from "@/utils/cn"

export type AlertTone = "info" | "success" | "warning" | "error" | "accent"

const TONE_STYLES: Record<AlertTone, { wrapper: string; iconColor: string; DefaultIcon: typeof Info }> = {
  info: {
    wrapper: "border-line bg-bg-secondary text-ink",
    iconColor: "text-muted",
    DefaultIcon: Info,
  },
  accent: {
    wrapper: "border-accent/30 bg-accent-soft text-ink",
    iconColor: "text-accent",
    DefaultIcon: Info,
  },
  success: {
    wrapper: "border-success/30 bg-success-soft text-ink",
    iconColor: "text-success",
    DefaultIcon: CheckCircle2,
  },
  warning: {
    wrapper: "border-warning/30 bg-warning-soft text-ink",
    iconColor: "text-warning",
    DefaultIcon: AlertTriangle,
  },
  error: {
    wrapper: "border-error/30 bg-error-soft text-ink",
    iconColor: "text-error",
    DefaultIcon: AlertCircle,
  },
}

export function Alert({
  tone = "info",
  title,
  description,
  icon,
  action,
  onDismiss,
  className,
}: {
  tone?: AlertTone
  title: string
  description?: ReactNode
  icon?: ReactNode
  action?: ReactNode
  onDismiss?: () => void
  className?: string
}) {
  const { wrapper, iconColor, DefaultIcon } = TONE_STYLES[tone]
  return (
    <div
      role={tone === "error" || tone === "warning" ? "alert" : "status"}
      className={cn("flex items-start justify-between gap-3 rounded-lg border px-3.5 py-2.5 text-sm", wrapper, className)}
    >
      <div className="flex min-w-0 items-start gap-2.5">
        <span className={cn("mt-0.5 shrink-0", iconColor)}>
          {icon ?? <DefaultIcon className="h-4 w-4" />}
        </span>
        <div className="min-w-0">
          <p className="font-medium leading-snug text-ink">{title}</p>
          {description ? <div className="mt-0.5 text-xs text-muted">{description}</div> : null}
          {action ? <div className="mt-2">{action}</div> : null}
        </div>
      </div>
      {onDismiss ? (
        <button
          type="button"
          onClick={onDismiss}
          aria-label="Đóng thông báo"
          className="shrink-0 rounded p-0.5 text-muted hover:bg-bg hover:text-ink"
        >
          <X className="h-3.5 w-3.5" />
        </button>
      ) : null}
    </div>
  )
}
