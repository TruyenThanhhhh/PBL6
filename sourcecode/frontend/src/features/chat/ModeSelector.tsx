import { Bot, ChevronDown, Globe, Layers, Monitor } from "lucide-react"
import {
  DropdownMenu,
  DropdownMenuItem,
  DropdownMenuLabel,
  Tooltip,
} from "@/components/ui"
import type { AIMode } from "@/types"
import { AI_MODE_DESCRIPTORS, getModeDescriptor } from "@/services/chat-service"

const MODE_ICONS: Record<AIMode, typeof Bot> = {
  auto: Bot,
  local: Monitor,
  web: Globe,
  hybrid: Layers,
}

export function ModeSelector({
  value,
  onChange,
}: {
  value: AIMode
  onChange: (mode: AIMode) => void
  showDescription?: boolean
  backendOnline?: boolean
}) {
  const activeMode = getModeDescriptor(value)
  const ActiveIcon = MODE_ICONS[value]

  return (
    <DropdownMenu
      align="end"
      trigger={
        <span>
          <Tooltip
            content={`Chế độ tìm kiếm: ${activeMode.label} — ${activeMode.shortHint}`}
            side="bottom"
          >
            <button
              type="button"
              aria-label={`Chế độ tìm kiếm hiện tại: ${activeMode.label}`}
              className="inline-flex h-8 items-center gap-1.5 rounded-md border border-line bg-bg px-2.5 text-xs font-medium text-ink transition-colors hover:bg-bg-hover"
            >
              <ActiveIcon className="h-3.5 w-3.5 text-muted" />
              <span>{activeMode.label}</span>
              <ChevronDown className="h-3 w-3 text-muted" />
            </button>
          </Tooltip>
        </span>
      }
    >
      <DropdownMenuLabel>Cài đặt nguồn tìm kiếm</DropdownMenuLabel>
      {AI_MODE_DESCRIPTORS.map((m) => {
        const Icon = MODE_ICONS[m.id]
        const isSelected = value === m.id
        return (
          <DropdownMenuItem
            key={m.id}
            icon={<Icon className="h-3.5 w-3.5" />}
            shortcut={isSelected ? "Đang chọn" : undefined}
            onClick={() => onChange(m.id)}
          >
            <div>
              <div className={isSelected ? "font-semibold text-ink" : "font-medium text-ink"}>
                {m.label}
              </div>
              <div className="text-[11px] text-muted">{m.shortHint}</div>
            </div>
          </DropdownMenuItem>
        )
      })}
    </DropdownMenu>
  )
}
