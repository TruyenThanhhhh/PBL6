import { useId, useState, type ReactNode } from "react"
import { cn } from "@/utils/cn"

export function Tooltip({
  content,
  side = "top",
  children,
  className,
}: {
  content: ReactNode
  side?: "top" | "bottom" | "left" | "right"
  children: ReactNode
  className?: string
}) {
  const [open, setOpen] = useState(false)
  const id = useId()

  const positions = {
    top: "bottom-[calc(100%+6px)] left-1/2 -translate-x-1/2",
    bottom: "top-[calc(100%+6px)] left-1/2 -translate-x-1/2",
    left: "right-[calc(100%+6px)] top-1/2 -translate-y-1/2",
    right: "left-[calc(100%+6px)] top-1/2 -translate-y-1/2",
  }

  return (
    <span
      className="relative inline-flex items-center"
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
      onFocus={() => setOpen(true)}
      onBlur={() => setOpen(false)}
    >
      <span aria-describedby={open ? id : undefined} className="inline-flex">
        {children}
      </span>
      {open ? (
        <span
          id={id}
          role="tooltip"
          className={cn(
            "pointer-events-none absolute z-50 whitespace-nowrap rounded-md border border-line bg-ink px-2 py-1 text-xs font-medium text-bg",
            positions[side],
            className,
          )}
        >
          {content}
        </span>
      ) : null}
    </span>
  )
}
