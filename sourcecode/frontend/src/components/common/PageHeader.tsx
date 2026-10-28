import type { ReactNode } from "react"

export function PageHeader({
  title,
  description,
  actions,
}: {
  /** Giữ tương thích ngược với các trang cũ nhưng không lặp lại breadcrumb đã có trên AppHeader */
  breadcrumb?: string[]
  title: string
  description?: string
  actions?: ReactNode
}) {
  return (
    <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
      <div className="min-w-0">
        <h1 className="text-[26px] font-semibold tracking-tight text-ink">{title}</h1>
        {description ? (
          <p className="mt-1 max-w-2xl text-[13px] leading-relaxed text-muted">{description}</p>
        ) : null}
      </div>
      {actions ? <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div> : null}
    </div>
  )
}
