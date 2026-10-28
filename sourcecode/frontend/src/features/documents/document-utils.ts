import type { DocumentStatus, FileKind, KnowledgeDocument } from "@/types"
import { ACCEPTED_EXTENSIONS, fileKindFromName, formatBytes, isAcceptedFile } from "@/utils/format"

export const MAX_FILE_SIZE_BYTES = 25 * 1024 * 1024 // 25 MB

export type PipelineStageState = "pending" | "processing" | "completed" | "failed"

export interface PipelineStepDescriptor {
  key: "upload" | "extract" | "clean" | "chunk" | "embed" | "index"
  label: string
  viLabel: string
  statusMatch: DocumentStatus
}

export const DOCUMENT_PIPELINE_STAGES: PipelineStepDescriptor[] = [
  { key: "upload", label: "Upload", viLabel: "Tải lên", statusMatch: "uploaded" },
  { key: "extract", label: "Extract", viLabel: "Trích xuất", statusMatch: "extracting" },
  { key: "clean", label: "Clean", viLabel: "Làm sạch", statusMatch: "cleaning" },
  { key: "chunk", label: "Chunk", viLabel: "Chia đoạn", statusMatch: "chunking" },
  { key: "embed", label: "Embed", viLabel: "Tạo vector", statusMatch: "embedding" },
  { key: "index", label: "Index", viLabel: "Lập chỉ mục", statusMatch: "indexing" },
]

export function getOverallPipelineState(status: DocumentStatus): {
  state: PipelineStageState
  label: string
  viLabel: string
} {
  if (status === "ready") {
    return { state: "completed", label: "Completed", viLabel: "Hoàn tất (Ready)" }
  }
  if (status === "failed") {
    return { state: "failed", label: "Failed", viLabel: "Thất bại (Failed)" }
  }
  if (status === "uploaded") {
    return { state: "pending", label: "Pending", viLabel: "Chờ xử lý (Pending)" }
  }
  return { state: "processing", label: "Processing", viLabel: "Đang xử lý (Processing)" }
}

const STATUS_STAGE_INDEX: Record<DocumentStatus, number> = {
  uploaded: 0,
  extracting: 1,
  cleaning: 2,
  chunking: 3,
  embedding: 4,
  indexing: 5,
  ready: 6,
  failed: -1,
}

export function getStageStates(status: DocumentStatus): Array<
  PipelineStepDescriptor & { state: PipelineStageState }
> {
  const currentIdx = STATUS_STAGE_INDEX[status]
  return DOCUMENT_PIPELINE_STAGES.map((stage, index) => {
    if (status === "ready") {
      return { ...stage, state: "completed" }
    }
    if (status === "failed") {
      if (index === 0) return { ...stage, state: "completed" }
      if (index === 1) return { ...stage, state: "failed" }
      return { ...stage, state: "pending" }
    }
    if (status === "uploaded") {
      if (index === 0) return { ...stage, state: "completed" }
      return { ...stage, state: "pending" }
    }
    if (index < currentIdx) return { ...stage, state: "completed" }
    if (index === currentIdx) return { ...stage, state: "processing" }
    return { ...stage, state: "pending" }
  })
}

export interface StagedUploadItem {
  id: string
  file: File
  fileName: string
  fileType: FileKind
  fileSize: number
  error: string | null
  progress: number
  uploadState: "staged" | "uploading" | "done" | "error"
}

export function validateCandidateFile(
  file: File,
  existingDocsInWorkspace: KnowledgeDocument[],
): string | null {
  if (!isAcceptedFile(file.name)) {
    return `Định dạng không hỗ trợ. Chỉ chấp nhận: ${ACCEPTED_EXTENSIONS.join(", ")}.`
  }
  if (file.size === 0) {
    return "Tệp rỗng (0 B) không thể trích xuất nội dung."
  }
  if (file.size > MAX_FILE_SIZE_BYTES) {
    return `Dung lượng tệp (${formatBytes(file.size)}) vượt quá giới hạn ${formatBytes(MAX_FILE_SIZE_BYTES)}.`
  }
  const dup = existingDocsInWorkspace.some(
    (d) => d.fileName.toLowerCase() === file.name.toLowerCase(),
  )
  if (dup) {
    return "Đã có tài liệu trùng tên trong workspace đang chọn."
  }
  return null
}

export function buildStagedItem(
  file: File,
  existingDocsInWorkspace: KnowledgeDocument[],
  id: string,
): StagedUploadItem {
  return {
    id,
    file,
    fileName: file.name,
    fileType: fileKindFromName(file.name),
    fileSize: file.size,
    error: validateCandidateFile(file, existingDocsInWorkspace),
    progress: 0,
    uploadState: "staged",
  }
}

export async function readPlainTextIfPossible(file: File): Promise<string | null> {
  const kind = fileKindFromName(file.name)
  if (kind !== "txt" && kind !== "md") return null
  try {
    const text = await file.text()
    return text.trim() || null
  } catch {
    return null
  }
}

export function downloadExtractedText(doc: KnowledgeDocument): boolean {
  if (!doc.extractedText?.trim()) return false
  const baseName = doc.fileName.replace(/\.[^.]+$/, "")
  const ext = doc.fileType === "md" ? "md" : "txt"
  const blob = new Blob([doc.extractedText], { type: "text/plain;charset=utf-8" })
  const url = URL.createObjectURL(blob)
  const a = document.createElement("a")
  a.href = url
  a.download = `${baseName}-extracted.${ext}`
  a.click()
  URL.revokeObjectURL(url)
  return true
}
