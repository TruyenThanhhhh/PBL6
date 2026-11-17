import { exportStudyDocumentApi, type ExportDocumentFormat } from "@/services/api"

export type { ExportDocumentFormat }

function sanitizeExportFilename(title: string, ext: ExportDocumentFormat): string {
  const cleaned = (title || "")
    .replace(/[\\/:*?"<>|\r\n]+/g, " ")
    .replace(/\s+/g, "_")
    .replace(/[^a-zA-Z0-9\u00C0-\u1EF9._-]+/g, "_")
    .replace(/^[_.-]+|[_.-]+$/g, "")
    .slice(0, 80)
  return `${cleaned || "tai_lieu_hoc_tap"}.${ext}`
}

function triggerBlobDownload(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement("a")
  anchor.href = url
  anchor.download = filename
  document.body.appendChild(anchor)
  anchor.click()
  document.body.removeChild(anchor)
  URL.revokeObjectURL(url)
}

/**
 * Xuất nội dung Markdown sang các định dạng (.md, .docx, .pdf).
 * Định dạng .md tải trực tiếp trên trình duyệt; .docx và .pdf được tạo từ backend.
 */
export async function downloadExportedDocument({
  title,
  content,
  format,
}: {
  title: string
  content: string
  format: ExportDocumentFormat
}): Promise<string> {
  const safeTitle = (title || "").trim() || "Tài liệu học tập"
  const filename = sanitizeExportFilename(safeTitle, format)

  if (format === "md") {
    const body = content.trim()
    const mdText =
      safeTitle && !body.startsWith(`# ${safeTitle}`)
        ? `# ${safeTitle}\n\n${body}\n`
        : `${body}\n`
    const blob = new Blob([mdText], { type: "text/markdown;charset=utf-8" })
    triggerBlobDownload(blob, filename)
    return filename
  }

  const blob = await exportStudyDocumentApi({
    title: safeTitle,
    content,
    format,
  })
  triggerBlobDownload(blob, filename)
  return filename
}
