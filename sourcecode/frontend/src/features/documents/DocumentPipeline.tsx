import { Check, Circle, Loader2, XCircle } from "lucide-react"
import { Badge, Tooltip } from "@/components/ui"
import { cn } from "@/utils/cn"
import type { DocumentStatus } from "@/types"
import { STATUS_LABEL } from "@/utils/format"
import {
  getOverallPipelineState,
  getStageStates,
  type PipelineStageState,
} from "./document-utils"

const STATE_BADGE_TONE: Record<PipelineStageState, "neutral" | "warning" | "success" | "error"> = {
  pending: "neutral",
  processing: "warning",
  completed: "success",
  failed: "error",
}

export function DocumentPipeline({
  status,
  compact = false,
}: {
  status: DocumentStatus
  mock?: boolean
  compact?: boolean
  onSelectMockStatus?: (next: DocumentStatus) => void
}) {
  const overall = getOverallPipelineState(status)
  const stages = getStageStates(status)

  if (compact) {
    return (
      <Tooltip content={`Trạng thái: ${STATUS_LABEL[status]}`} side="top">
        <div className="inline-flex items-center gap-1.5">
          <Badge tone={STATE_BADGE_TONE[overall.state]} dot>
            {overall.viLabel}
          </Badge>
        </div>
      </Tooltip>
    )
  }

  return (
    <div className="rounded-lg border border-line bg-bg p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs font-semibold text-ink">Tiến trình xử lý tài liệu</span>
          <Badge tone={STATE_BADGE_TONE[overall.state]} dot>
            {overall.viLabel}
          </Badge>
        </div>
        <span className="text-xs text-muted">{STATUS_LABEL[status]}</span>
      </div>

      <ol className="grid gap-2 sm:grid-cols-6">
        {stages.map((st, idx) => {
          return (
            <Tooltip
              key={st.key}
              content={`Bước ${idx + 1}: ${st.viLabel} (${st.label})`}
              side="top"
            >
              <li
                className={cn(
                  "flex items-center gap-2 rounded-md border px-2.5 py-2 text-xs",
                  st.state === "completed" && "border-success/30 bg-success-soft/40 text-ink",
                  st.state === "processing" &&
                    "border-warning/40 bg-warning-soft/50 font-medium text-ink",
                  st.state === "failed" &&
                    "border-error/40 bg-error-soft/50 font-medium text-error",
                  st.state === "pending" && "border-line bg-bg-secondary/50 text-muted",
                )}
              >
                <span className="shrink-0">
                  {st.state === "completed" ? (
                    <Check className="h-3.5 w-3.5 text-success" />
                  ) : st.state === "processing" ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin text-warning" />
                  ) : st.state === "failed" ? (
                    <XCircle className="h-3.5 w-3.5 text-error" />
                  ) : (
                    <Circle className="h-3.5 w-3.5 text-muted" />
                  )}
                </span>
                <div className="min-w-0">
                  <p className="truncate font-medium">
                    {idx + 1}. {st.viLabel}
                  </p>
                </div>
              </li>
            </Tooltip>
          )
        })}
      </ol>
    </div>
  )
}
