import { useAppStore } from "@/store/app-store"

export function ConnectionBanner() {
  const status = useAppStore((s) => s.status)

  // Chỉ hiển thị thông báo mỏng khi trình duyệt mất kết nối mạng hoàn toàn.
  // Trạng thái kỹ thuật chi tiết được đặt trong Settings → System Status theo đúng định hướng tối giản.
  if (status.internetOnline) return null

  return (
    <div className="border-b border-line bg-bg-secondary px-4 py-1.5 text-xs text-muted md:px-6">
      Trình duyệt đang ngoại tuyến (Offline) — dữ liệu cục bộ vẫn khả dụng; tính năng trực tuyến tạm ngưng.
    </div>
  )
}
