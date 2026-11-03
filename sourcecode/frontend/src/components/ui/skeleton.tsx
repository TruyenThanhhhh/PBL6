import type { HTMLAttributes } from "react"
import { cn } from "@/utils/cn"

export function Skeleton({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      aria-hidden="true"
      className={cn("animate-pulse rounded-md border border-line/50 bg-bg-secondary", className)}
      {...props}
    />
  )
}

export function SkeletonLines({
  lines = 3,
  className,
}: {
  lines?: number
  className?: string
}) {
  const widths = ["w-full", "w-11/12", "w-4/5", "w-3/5"]
  return (
    <div className={cn("space-y-2", className)} aria-busy="true" aria-label="Đang tải nội dung">
      {Array.from({ length: lines }).map((_, idx) => (
        <Skeleton key={idx} className={cn("h-3.5", widths[idx % widths.length])} />
      ))}
    </div>
  )
}
