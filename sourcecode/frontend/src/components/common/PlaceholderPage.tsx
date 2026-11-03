import { useLocation, useNavigate } from "react-router-dom"
import { ArrowLeft, Compass, Layers } from "lucide-react"
import { PageHeader } from "@/components/common/PageHeader"
import { Badge, Button, EmptyState } from "@/components/ui"

export function PlaceholderPage({
  title,
  description,
  breadcrumb,
}: {
  title?: string
  description?: string
  breadcrumb?: string[]
}) {
  const location = useLocation()
  const navigate = useNavigate()

  const resolvedTitle = title ?? "Tính năng đang trong lộ trình phát triển"
  const resolvedDesc =
    description ??
    `Đường dẫn "${location.pathname}" chưa được triển khai chi tiết ở task hiện tại hoặc không tồn tại.`

  return (
    <div className="mx-auto max-w-4xl px-4 py-8 md:px-8">
      <PageHeader
        breadcrumb={breadcrumb ?? ["Hệ thống", "Placeholder"]}
        title={resolvedTitle}
        description="Trang giữ chỗ chuẩn hóa theo phong cách Notion-inspired của Personal AI Knowledge Platform."
        actions={
          <Badge tone="neutral" dot>
            Route: {location.pathname}
          </Badge>
        }
      />

      <EmptyState
        icon={<Compass className="h-4 w-4" />}
        title={resolvedTitle}
        description={resolvedDesc}
        action={
          <div className="flex flex-wrap items-center justify-center gap-2">
            <Button
              variant="outline"
              size="sm"
              leftIcon={<ArrowLeft className="h-3.5 w-3.5" />}
              onClick={() => navigate(-1)}
            >
              Quay lại trang trước
            </Button>
            <Button
              variant="default"
              size="sm"
              leftIcon={<Layers className="h-3.5 w-3.5" />}
              onClick={() => navigate("/dashboard")}
            >
              Về trang Tổng quan
            </Button>
          </div>
        }
      />
    </div>
  )
}
