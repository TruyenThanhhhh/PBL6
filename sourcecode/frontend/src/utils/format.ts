import type { DocumentStatus, FileKind } from "@/types"

export function uid(prefix = "id") {
  return `${prefix}_${Math.random().toString(36).slice(2, 10)}${Date.now().toString(36).slice(-4)}`
}

export function nowIso() {
  return new Date().toISOString()
}

export function formatDate(iso: string) {
  return new Intl.DateTimeFormat("vi-VN", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  }).format(new Date(iso))
}

export function formatDateTime(iso: string) {
  return new Intl.DateTimeFormat("vi-VN", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(iso))
}

export function formatBytes(bytes: number) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export function fileKindFromName(name: string): FileKind {
  const ext = name.split(".").pop()?.toLowerCase()
  if (ext === "pdf") return "pdf"
  if (ext === "docx" || ext === "doc") return "docx"
  if (ext === "pptx" || ext === "ppt") return "pptx"
  if (ext === "txt") return "txt"
  if (ext === "md" || ext === "markdown") return "md"
  return "other"
}

export const ACCEPTED_EXTENSIONS = [".pdf", ".docx", ".pptx", ".txt", ".md"]

export function isAcceptedFile(name: string) {
  const ext = `.${name.split(".").pop()?.toLowerCase()}`
  return ACCEPTED_EXTENSIONS.includes(ext)
}

export const STATUS_LABEL: Record<DocumentStatus, string> = {
  uploaded: "Đã tải lên",
  extracting: "Đang trích xuất",
  cleaning: "Đang làm sạch",
  chunking: "Đang chia chunk",
  embedding: "Đang embedding",
  indexing: "Đang indexing",
  ready: "Sẵn sàng truy xuất",
  failed: "Xử lý thất bại",
}

export const PIPELINE_STEPS: DocumentStatus[] = [
  "uploaded",
  "extracting",
  "cleaning",
  "chunking",
  "embedding",
  "indexing",
  "ready",
]

export function relativeTime(iso: string) {
  const diff = Date.now() - new Date(iso).getTime()
  const min = Math.floor(diff / 60000)
  if (min < 1) return "vừa xong"
  if (min < 60) return `${min} phút trước`
  const hour = Math.floor(min / 60)
  if (hour < 24) return `${hour} giờ trước`
  const day = Math.floor(hour / 24)
  return `${day} ngày trước`
}

export function greeting() {
  const h = new Date().getHours()
  if (h < 12) return "Chào buổi sáng"
  if (h < 18) return "Chào buổi chiều"
  return "Chào buổi tối"
}

export function todayFullLabel() {
  return new Intl.DateTimeFormat("vi-VN", {
    weekday: "long",
    day: "numeric",
    month: "long",
    year: "numeric",
  }).format(new Date())
}

export function isWithinDays(iso: string, days: number) {
  const cutoff = Date.now() - days * 86400000
  return new Date(iso).getTime() >= cutoff
}
