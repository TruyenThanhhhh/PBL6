import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from "react"
import { cn } from "@/utils/cn"

const DropdownMenuContext = createContext<{ close: () => void }>({ close: () => {} })

export function DropdownMenu({
  trigger,
  align = "end",
  children,
  className,
  fullWidth = false,
}: {
  trigger: ReactNode
  align?: "start" | "end"
  children: ReactNode
  className?: string
  fullWidth?: boolean
}) {
  const [open, setOpen] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)

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
    <DropdownMenuContext.Provider value={{ close: () => setOpen(false) }}>
      <div
        ref={containerRef}
        className={cn("relative text-left", fullWidth ? "w-full block" : "inline-block")}
      >
        <div
          onClick={() => setOpen((o) => !o)}
          className={cn(fullWidth ? "w-full flex" : "inline-flex")}
        >
          {trigger}
        </div>
        {open ? (
          <div
            role="menu"
            className={cn(
              "absolute top-[calc(100%+4px)] z-40 min-w-[196px] rounded-lg border border-line bg-bg p-1 shadow-lg",
              align === "end" ? "right-0" : "left-0",
              className,
            )}
          >
            {children}
          </div>
        ) : null}
      </div>
    </DropdownMenuContext.Provider>
  )
}

export function DropdownMenuLabel({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className={cn("px-2.5 py-1 text-[11px] font-medium uppercase tracking-wide text-muted", className)}>
      {children}
    </div>
  )
}

export function DropdownMenuSeparator() {
  return <div className="my-1 h-px bg-line" role="separator" />
}

export function DropdownMenuItem({
  icon,
  shortcut,
  tone = "default",
  disabled = false,
  onClick,
  children,
  className,
}: {
  icon?: ReactNode
  shortcut?: string
  tone?: "default" | "danger"
  disabled?: boolean
  onClick?: () => void
  children: ReactNode
  className?: string
}) {
  const { close } = useContext(DropdownMenuContext)
  return (
    <button
      type="button"
      role="menuitem"
      disabled={disabled}
      onClick={() => {
        if (disabled) return
        onClick?.()
        close()
      }}
      className={cn(
        "flex w-full items-center justify-between gap-3 rounded-md px-2.5 py-1.5 text-left text-sm transition-colors disabled:pointer-events-none disabled:opacity-45",
        tone === "danger"
          ? "text-error hover:bg-error-soft"
          : "text-ink hover:bg-bg-secondary",
        className,
      )}
    >
      {icon || shortcut ? (
        <>
          <span className="flex items-center gap-2 truncate">
            {icon ? <span className="shrink-0 text-muted">{icon}</span> : null}
            <span className="truncate">{children}</span>
          </span>
          {shortcut ? <kbd className="text-[11px] text-muted">{shortcut}</kbd> : null}
        </>
      ) : (
        children
      )}
    </button>
  )
}
