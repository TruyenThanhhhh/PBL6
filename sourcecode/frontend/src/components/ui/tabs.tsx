import { createContext, useContext, useState, type ReactNode } from "react"
import { cn } from "@/utils/cn"

interface TabsContextValue {
  activeValue: string
  setValue: (value: string) => void
}

const TabsContext = createContext<TabsContextValue | null>(null)

export function Tabs({
  defaultValue = "",
  value,
  onValueChange,
  children,
  className,
}: {
  defaultValue?: string
  value?: string
  onValueChange?: (value: string) => void
  children: ReactNode
  className?: string
}) {
  const [internal, setInternal] = useState(defaultValue)
  const activeValue = value !== undefined ? value : internal

  const setValue = (next: string) => {
    if (value === undefined) setInternal(next)
    onValueChange?.(next)
  }

  return (
    <TabsContext.Provider value={{ activeValue, setValue }}>
      <div className={cn("w-full", className)}>{children}</div>
    </TabsContext.Provider>
  )
}

export function TabsList({
  variant = "underline",
  children,
  className,
}: {
  variant?: "underline" | "segmented"
  children: ReactNode
  className?: string
}) {
  return (
    <div
      role="tablist"
      className={cn(
        variant === "underline"
          ? "flex flex-wrap items-center gap-1 border-b border-line"
          : "inline-flex items-center gap-1 rounded-lg border border-line bg-bg-secondary p-1",
        className,
      )}
    >
      {children}
    </div>
  )
}

export function TabsTrigger({
  value,
  disabled = false,
  variant = "underline",
  children,
  className,
}: {
  value: string
  disabled?: boolean
  variant?: "underline" | "segmented"
  children: ReactNode
  className?: string
}) {
  const ctx = useContext(TabsContext)
  if (!ctx) return null
  const isActive = ctx.activeValue === value

  return (
    <button
      type="button"
      role="tab"
      aria-selected={isActive}
      disabled={disabled}
      onClick={() => ctx.setValue(value)}
      className={cn(
        "inline-flex items-center gap-1.5 text-sm transition-colors disabled:pointer-events-none disabled:opacity-45",
        variant === "underline"
          ? cn(
              "-mb-px border-b-2 px-3 py-2",
              isActive
                ? "border-ink font-medium text-ink"
                : "border-transparent text-muted hover:text-ink",
            )
          : cn(
              "rounded-md px-2.5 py-1 text-xs",
              isActive ? "bg-bg font-medium text-ink" : "text-muted hover:text-ink",
            ),
        className,
      )}
    >
      {children}
    </button>
  )
}

export function TabsContent({
  value,
  children,
  className,
}: {
  value: string
  children: ReactNode
  className?: string
}) {
  const ctx = useContext(TabsContext)
  if (!ctx || ctx.activeValue !== value) return null
  return (
    <div role="tabpanel" className={cn("pt-4", className)}>
      {children}
    </div>
  )
}
