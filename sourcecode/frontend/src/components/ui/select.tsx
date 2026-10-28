import { useEffect, useRef, useState, type ReactNode, type SelectHTMLAttributes } from "react"
import { Check, ChevronDown } from "lucide-react"
import { cn } from "@/utils/cn"
import type { FieldValidationState } from "./input"

const stateClasses: Record<FieldValidationState, string> = {
  default: "border-line hover:border-muted/60 focus-visible:border-ink focus-visible:outline-ink",
  error: "border-error bg-error-soft/30 focus-visible:border-error focus-visible:outline-error",
  warning: "border-warning bg-warning-soft/30 focus-visible:border-warning focus-visible:outline-warning",
  success: "border-success bg-success-soft/30 focus-visible:border-success focus-visible:outline-success",
}

export interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  state?: FieldValidationState
}

export function Select({ className, state = "default", children, ...props }: SelectProps) {
  return (
    <div className="relative inline-flex w-full items-center">
      <select
        aria-invalid={state === "error" || undefined}
        className={cn(
          "h-9 w-full appearance-none rounded-md border bg-bg pl-3 pr-8 text-sm text-ink transition-colors focus-visible:outline-2 focus-visible:outline-offset-0 disabled:cursor-not-allowed disabled:bg-bg-secondary disabled:opacity-50",
          stateClasses[state],
          className,
        )}
        {...props}
      >
        {children}
      </select>
      <ChevronDown className="pointer-events-none absolute right-2.5 h-3.5 w-3.5 text-muted" />
    </div>
  )
}

export interface SelectDropdownOption {
  value: string
  label: string
  description?: string
  icon?: ReactNode
  disabled?: boolean
}

export function SelectDropdown({
  value,
  options,
  placeholder = "Chọn một mục...",
  disabled = false,
  state = "default",
  onChange,
  className,
}: {
  value: string
  options: SelectDropdownOption[]
  placeholder?: string
  disabled?: boolean
  state?: FieldValidationState
  onChange: (value: string) => void
  className?: string
}) {
  const [open, setOpen] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)
  const selected = options.find((o) => o.value === value)

  useEffect(() => {
    if (!open) return
    const onMouseDown = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false)
    }
    window.addEventListener("mousedown", onMouseDown)
    window.addEventListener("keydown", onKeyDown)
    return () => {
      window.removeEventListener("mousedown", onMouseDown)
      window.removeEventListener("keydown", onKeyDown)
    }
  }, [open])

  return (
    <div ref={containerRef} className={cn("relative w-full", className)}>
      <button
        type="button"
        disabled={disabled}
        aria-haspopup="listbox"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
        className={cn(
          "flex h-9 w-full items-center justify-between gap-2 rounded-md border bg-bg px-3 text-left text-sm text-ink transition-colors focus-visible:outline-2 focus-visible:outline-offset-0 disabled:cursor-not-allowed disabled:bg-bg-secondary disabled:opacity-50",
          stateClasses[state],
        )}
      >
        <span className={cn("flex items-center gap-2 truncate", !selected && "text-muted")}>
          {selected?.icon}
          <span className="truncate">{selected ? selected.label : placeholder}</span>
        </span>
        <ChevronDown className={cn("h-3.5 w-3.5 shrink-0 text-muted transition-transform", open && "rotate-180")} />
      </button>

      {open ? (
        <div
          role="listbox"
          className="absolute left-0 top-[calc(100%+4px)] z-40 max-h-60 w-full overflow-y-auto rounded-md border border-line bg-bg p-1"
        >
          {options.map((opt) => {
            const isSelected = opt.value === value
            return (
              <button
                key={opt.value}
                type="button"
                role="option"
                aria-selected={isSelected}
                disabled={opt.disabled}
                onClick={() => {
                  onChange(opt.value)
                  setOpen(false)
                }}
                className={cn(
                  "flex w-full items-start justify-between gap-2 rounded-md px-2.5 py-1.5 text-left text-sm transition-colors hover:bg-bg-hover disabled:pointer-events-none disabled:opacity-45",
                  isSelected && "bg-bg-active font-medium text-ink",
                )}
              >
                <span className="flex min-w-0 items-start gap-2">
                  {opt.icon ? <span className="mt-0.5 shrink-0 text-muted">{opt.icon}</span> : null}
                  <span className="min-w-0">
                    <span className="block truncate">{opt.label}</span>
                    {opt.description ? (
                      <span className="block truncate text-xs font-normal text-muted">{opt.description}</span>
                    ) : null}
                  </span>
                </span>
                {isSelected ? <Check className="mt-0.5 h-3.5 w-3.5 shrink-0 text-ink" /> : null}
              </button>
            )
          })}
        </div>
      ) : null}
    </div>
  )
}
