import type { ChatImageAttachment } from "@/types"

const SUPPORTED_MIME_TYPES = new Set<ChatImageAttachment["mimeType"]>([
  "image/png",
  "image/jpeg",
  "image/webp",
])

const MAX_DIMENSION_PX = 1280
const MAX_UPLOAD_BYTES = 4.5 * 1024 * 1024

function readFileAsDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result ?? ""))
    reader.onerror = () => reject(new Error("Không thể đọc dữ liệu ảnh"))
    reader.readAsDataURL(file)
  })
}

function loadImageElement(src: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image()
    img.onload = () => resolve(img)
    img.onerror = () => reject(new Error("Định dạng ảnh không hợp lệ"))
    img.src = src
  })
}

function estimateBase64Bytes(base64: string): number {
  return Math.floor((base64.length * 3) / 4)
}

/**
 * Chuẩn hóa, thu gọn kích thước ảnh xuống tối đa 1280px để tối ưu tốc độ Vision model cục bộ
 * và trả về base64 sạch không kèm prefix `data:...;base64,`.
 */
export async function prepareChatImageAttachment(file: File): Promise<ChatImageAttachment> {
  const rawMime = (file.type || "").toLowerCase()
  const targetMime: ChatImageAttachment["mimeType"] = SUPPORTED_MIME_TYPES.has(
    rawMime as ChatImageAttachment["mimeType"],
  )
    ? (rawMime as ChatImageAttachment["mimeType"])
    : "image/jpeg"

  if (!rawMime.startsWith("image/")) {
    throw new Error("Chỉ hỗ trợ tệp hình ảnh (PNG, JPG, WebP).")
  }
  if (file.size > 15 * 1024 * 1024) {
    throw new Error("Ảnh quá lớn (tối đa 15 MB trước khi nén).")
  }

  const originalDataUrl = await readFileAsDataUrl(file)
  const img = await loadImageElement(originalDataUrl)

  const maxSide = Math.max(img.width || 1, img.height || 1)
  let dataUrl = originalDataUrl
  let outMime: ChatImageAttachment["mimeType"] = targetMime

  if (maxSide > MAX_DIMENSION_PX || !SUPPORTED_MIME_TYPES.has(rawMime as ChatImageAttachment["mimeType"]) || file.size > 1.2 * 1024 * 1024) {
    const scale = Math.min(1, MAX_DIMENSION_PX / maxSide)
    const width = Math.max(1, Math.round(img.width * scale))
    const height = Math.max(1, Math.round(img.height * scale))
    const canvas = document.createElement("canvas")
    canvas.width = width
    canvas.height = height
    const ctx = canvas.getContext("2d")
    if (ctx) {
      ctx.drawImage(img, 0, 0, width, height)
      outMime = targetMime === "image/png" && file.size < 1.5 * 1024 * 1024 ? "image/png" : "image/jpeg"
      dataUrl = canvas.toDataURL(outMime, outMime === "image/jpeg" ? 0.86 : undefined)
    }
  }

  const commaIdx = dataUrl.indexOf(",")
  const base64 = commaIdx >= 0 ? dataUrl.slice(commaIdx + 1) : dataUrl
  const sizeBytes = estimateBase64Bytes(base64)
  if (!base64 || sizeBytes > MAX_UPLOAD_BYTES) {
    throw new Error("Ảnh sau khi nén vẫn vượt giới hạn 4.5 MB cho phép.")
  }

  return {
    base64,
    mimeType: outMime,
    dataUrl,
    name: file.name || `image.${outMime.split("/")[1]}`,
    sizeBytes,
  }
}
