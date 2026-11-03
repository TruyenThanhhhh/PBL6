import { Link } from "react-router-dom"
import { useAuthSession } from "@/hooks/useAuthSession"
import { useAppStore } from "@/store/app-store"

export function ConnectionBanner() {
  const status = useAppStore((s) => s.status)
  const { authenticated } = useAuthSession()

  // Chỉ hiển thị thông báo mỏng khi trình duyệt mất kết nối mạng hoàn toàn.
  // Trạng thái kỹ thuật chi tiết được đặt trong Settings → System Status theo đúng định hướng tối giản.
  if (status.internetOnline && (authenticated || status.backendOnline)) return null

  if (!status.internetOnline) {
    return (
      <div className="border-b border-line bg-bg-secondary px-4 py-1.5 text-xs text-muted md:px-6">
        Trình duyệt đang ngoại tuyến (Offline) — dữ liệu cục bộ vẫn khả dụng; tính năng trực tuyến tạm ngưng.
      </div>
    )
  }

  return (
    <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line bg-warning-soft px-4 py-1.5 text-xs text-ink md:px-6">
      <span>Chưa đăng nhập hoặc backend chưa kết nối — đang hiển thị dữ liệu mô phỏng.</span>
      <Link to="/login" className="font-semibold text-brand hover:underline">
        Đăng nhập backend
      </Link>
    </div>
  )
}
