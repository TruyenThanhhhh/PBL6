import { AlertCircle, AlertTriangle, CheckCircle2, Info, X } from "lucide-react"
import { useAppStore } from "@/store/app-store"
import { cn } from "@/utils/cn"
import type { Toast } from "@/types"

const TOAST_ICONS: Record<Toast["tone"], { Icon: typeof Info; color: string }> = {
  info: { Icon: Info, color: "text-muted" },
  success: { Icon: CheckCircle2, color: "text-success" },
  warning: { Icon: AlertTriangle, color: "text-warning" },
  error: { Icon: AlertCircle, color: "text-error" },
}

export function Toasts() {
  const toasts = useAppStore((s) => s.toasts)
  const dismiss = useAppStore((s) => s.dismissToast)
  return (
    <div className="pointer-events-none fixed right-4 top-4 z-50 flex w-80 flex-col gap-2">
      {toasts.map((t) => {
        const { Icon, color } = TOAST_ICONS[t.tone]
        return (
          <div
            key={t.id}
            role="status"
            className={cn(
              "pointer-events-auto rounded-lg border bg-bg px-3 py-2.5 text-sm",
              t.tone === "error" && "border-error/40",
              t.tone === "success" && "border-success/40",
              t.tone === "warning" && "border-warning/40",
              t.tone === "info" && "border-line",
            )}
          >
            <div className="flex items-start justify-between gap-2">
              <div className="flex min-w-0 items-start gap-2">
                <Icon className={cn("mt-0.5 h-4 w-4 shrink-0", color)} />
                <div className="min-w-0">
                  <p className="font-medium text-ink">{t.title}</p>
                  {t.description ? <p className="mt-0.5 text-xs text-muted">{t.description}</p> : null}
                </div>
              </div>
              <button
                type="button"
                onClick={() => dismiss(t.id)}
                aria-label="Đóng thông báo"
                className="shrink-0 rounded p-0.5 text-muted hover:bg-bg-secondary hover:text-ink"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </div>
          </div>
        )
      })}
    </div>
  )
}
