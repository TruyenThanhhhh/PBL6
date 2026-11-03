import { useRef, useState } from "react"
import { AlertCircle, CheckCircle2, FileUp, Loader2, Trash2, Upload, X } from "lucide-react"
import { Alert, Badge, Button, FormField, Select } from "@/components/ui"
import { buildUploadedDocument, useAppStore } from "@/store/app-store"
import { fetchDocuments, uploadDocumentWithProgress } from "@/services/api"
import { ACCEPTED_EXTENSIONS, formatBytes, uid } from "@/utils/format"
import {
  buildStagedItem,
  MAX_FILE_SIZE_BYTES,
  readPlainTextIfPossible,
  type StagedUploadItem,
} from "./document-utils"

export function DocumentUploadPanel({
  targetWorkspaceId,
  targetNotebookId,
  onTargetWorkspaceChange,
  onTargetNotebookChange,
}: {
  targetWorkspaceId: string
  targetNotebookId: string
  onTargetWorkspaceChange: (wsId: string) => void
  onTargetNotebookChange: (nbId: string) => void
}) {
  const workspaces = useAppStore((s) => s.workspaces)
  const notebooks = useAppStore((s) => s.notebooks)
  const documents = useAppStore((s) => s.documents)
  const addDocument = useAppStore((s) => s.addDocument)
  const replaceDocs = useAppStore((s) => s.replaceDocumentsFromBackend)
  const status = useAppStore((s) => s.status)
  const toast = useAppStore((s) => s.toast)

  const [drag, setDrag] = useState(false)
  const [queue, setQueue] = useState<StagedUploadItem[]>([])
  const [uploading, setUploading] = useState(false)
  const abortRef = useRef<AbortController | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const wsDocs = documents.filter((d) => d.workspaceId === targetWorkspaceId)
  const wsNotebooks = notebooks.filter((n) => n.workspaceId === targetWorkspaceId)

  const enqueueFiles = (files: FileList | File[]) => {
    const incoming = Array.from(files)
    if (!incoming.length) return

    setQueue((prev) => {
      const existingNames = new Set(prev.map((item) => item.fileName.toLowerCase()))
      const additions: StagedUploadItem[] = []
      for (const file of incoming) {
        if (existingNames.has(file.name.toLowerCase())) continue
        existingNames.add(file.name.toLowerCase())
        additions.push(buildStagedItem(file, wsDocs, uid("stage")))
      }
      return [...prev, ...additions]
    })
  }

  const removeStaged = (id: string) => {
    setQueue((prev) => prev.filter((item) => item.id !== id))
  }

  const clearQueue = () => {
    if (uploading && abortRef.current) {
      abortRef.current.abort()
    }
    setQueue([])
  }

  const validItems = queue.filter((item) => !item.error && item.uploadState !== "done")
  const invalidCount = queue.filter((item) => Boolean(item.error)).length

  const handleStartUpload = async () => {
    if (!validItems.length || uploading) return
    setUploading(true)
    const controller = new AbortController()
    abortRef.current = controller

    let successCount = 0

    for (const item of validItems) {
      if (controller.signal.aborted) break

      setQueue((prev) =>
        prev.map((q) => (q.id === item.id ? { ...q, uploadState: "uploading", progress: 5 } : q)),
      )

      try {
        if (status.backendOnline) {
          await uploadDocumentWithProgress(targetWorkspaceId, item.file, {
            notebookId: targetNotebookId || null,
            signal: controller.signal,
            onProgress: (pct) => {
              setQueue((prev) =>
                prev.map((q) => (q.id === item.id ? { ...q, progress: pct } : q)),
              )
            },
          })
          setQueue((prev) =>
            prev.map((q) =>
              q.id === item.id ? { ...q, uploadState: "done", progress: 100 } : q,
            ),
          )
          successCount += 1
        } else {
          // Chế độ mô phỏng cục bộ: không tự tạo tiến trình giả hay tuyên bố đã lưu lên server
          const localDoc = buildUploadedDocument(
            item.file,
            targetWorkspaceId,
            targetNotebookId || null,
          )
          const plain = await readPlainTextIfPossible(item.file)
          if (plain) {
            localDoc.extractedText = plain
            localDoc.pageCount = Math.max(1, Math.ceil(plain.length / 1200))
            localDoc.totalChunks = Math.max(1, Math.ceil(plain.length / 400))
          } else {
            localDoc.extractedText =
              "Tệp được thêm ở chế độ mô phỏng cục bộ trên trình duyệt. Kết nối Backend để trích xuất văn bản, chia chunk và lập chỉ mục Hybrid RAG thật."
          }
          addDocument(localDoc)
          setQueue((prev) =>
            prev.map((q) =>
              q.id === item.id ? { ...q, uploadState: "done", progress: 100 } : q,
            ),
          )
          successCount += 1
        }
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err)
        setQueue((prev) =>
          prev.map((q) =>
            q.id === item.id ? { ...q, uploadState: "error", error: msg } : q,
          ),
        )
      }
    }

    if (status.backendOnline && successCount > 0) {
      try {
        const refreshed = await fetchDocuments(targetWorkspaceId)
        replaceDocs(refreshed)
      } catch {
        // Giữ nguyên danh sách nếu gọi lại lỗi
      }
      toast({
        title: `Đã tải lên ${successCount} tệp tới Backend`,
        description: "Tài liệu đã được gửi tới máy chủ để xử lý.",
        tone: "success",
      })
    } else if (!status.backendOnline && successCount > 0) {
      toast({
        title: `Đã thêm ${successCount} tệp vào danh sách mô phỏng cục bộ`,
        description: "Backend chưa kết nối — tệp chỉ lưu tạm trên trình duyệt, chưa được lập chỉ mục thật.",
        tone: "warning",
      })
    }

    setUploading(false)
    abortRef.current = null
    // Xóa các mục đã hoàn tất khỏi hàng đợi chờ
    setQueue((prev) => prev.filter((q) => q.uploadState !== "done"))
  }

  return (
    <section aria-label="Tải lên tài liệu" className="motivo-card mb-6 p-4">
      <div className="mb-4 grid gap-3 sm:grid-cols-2">
        <FormField label="Workspace đích" hint="Nơi lưu tài liệu">
          <Select
            value={targetWorkspaceId}
            onChange={(e) => {
              onTargetWorkspaceChange(e.target.value)
              onTargetNotebookChange("")
            }}
          >
            {workspaces.map((w) => (
              <option key={w.id} value={w.id}>
                {w.name}
              </option>
            ))}
          </Select>
        </FormField>

        <FormField label="Notebook đích (tuỳ chọn)" hint="Phân loại trong workspace">
          <Select
            value={targetNotebookId}
            onChange={(e) => onTargetNotebookChange(e.target.value)}
          >
            <option value="">-- Chưa phân loại vào notebook --</option>
            {wsNotebooks.map((n) => (
              <option key={n.id} value={n.id}>
                {n.name}
              </option>
            ))}
          </Select>
        </FormField>
      </div>

      {/* Dropzone */}
      <div
        onDragOver={(e) => {
          e.preventDefault()
          setDrag(true)
        }}
        onDragLeave={() => setDrag(false)}
        onDrop={(e) => {
          e.preventDefault()
          setDrag(false)
          enqueueFiles(e.dataTransfer.files)
        }}
        className={`flex flex-col items-center justify-center rounded-lg border border-dashed px-4 py-7 text-center text-sm transition-colors ${
          drag ? "border-ink bg-bg-hover" : "border-line bg-bg-secondary/60"
        }`}
      >
        <FileUp className="mb-2 h-5 w-5 text-muted" />
        <p className="font-medium text-ink">Kéo thả tệp vào đây để đưa vào danh sách chờ</p>
        <p className="mt-1 text-xs text-muted">
          Hỗ trợ: {ACCEPTED_EXTENSIONS.join(", ")} · Tối đa {formatBytes(MAX_FILE_SIZE_BYTES)} / tệp
        </p>
        <div className="mt-3">
          <input
            ref={fileInputRef}
            type="file"
            multiple
            className="hidden"
            accept={ACCEPTED_EXTENSIONS.join(",")}
            onChange={(e) => {
              if (e.target.files) enqueueFiles(e.target.files)
              e.target.value = ""
            }}
          />
          <Button
            type="button"
            variant="outline"
            size="sm"
            leftIcon={<Upload className="h-3.5 w-3.5" />}
            onClick={() => fileInputRef.current?.click()}
          >
            Chọn tệp từ máy
          </Button>
        </div>
      </div>

      {/* Staging Queue */}
      {queue.length > 0 ? (
        <div className="mt-4 space-y-3 border-t border-line pt-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <p className="text-sm font-medium text-ink">
                Danh sách chờ ({queue.length} tệp đã chọn)
              </p>
              <p className="text-xs text-muted">
                Các tệp sẵn sàng để tải lên không gian làm việc.
              </p>
            </div>
            <div className="flex items-center gap-2">
              {uploading ? (
                <Button
                  variant="danger"
                  size="sm"
                  onClick={() => abortRef.current?.abort()}
                >
                  Hủy tải lên
                </Button>
              ) : (
                <Button
                  variant="ghost"
                  size="sm"
                  leftIcon={<Trash2 className="h-3.5 w-3.5" />}
                  onClick={clearQueue}
                >
                  Xóa danh sách chờ
                </Button>
              )}
              <Button
                variant="default"
                size="sm"
                loading={uploading}
                disabled={validItems.length === 0}
                onClick={() => void handleStartUpload()}
              >
                Tải lên ({validItems.length})
              </Button>
            </div>
          </div>

          {invalidCount > 0 ? (
            <Alert
              tone="error"
              title={`${invalidCount} tệp không hợp lệ`}
              description="Vui lòng loại bỏ các tệp báo lỗi định dạng, trùng tên hoặc vượt quá 25 MB."
            />
          ) : null}

          <ul className="divide-y divide-line rounded-md border border-line bg-bg">
            {queue.map((item) => (
              <li key={item.id} className="px-3 py-2.5 text-sm">
                <div className="flex items-center justify-between gap-3">
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="truncate font-medium text-ink">{item.fileName}</span>
                      <Badge tone="neutral">{item.fileType.toUpperCase()}</Badge>
                      <span className="text-xs text-muted">{formatBytes(item.fileSize)}</span>
                      {item.error ? (
                        <Badge tone="error" dot>
                          Không hợp lệ
                        </Badge>
                      ) : item.uploadState === "uploading" ? (
                        <Badge tone="warning" dot>
                          Đang tải lên ({item.progress}%)
                        </Badge>
                      ) : item.uploadState === "done" ? (
                        <Badge tone="success" dot>
                          Hoàn tất
                        </Badge>
                      ) : (
                        <Badge tone="neutral" dot>
                          Chờ tải lên
                        </Badge>
                      )}
                    </div>
                    {item.error ? (
                      <p className="mt-1 flex items-center gap-1 text-xs text-error">
                        <AlertCircle className="h-3.5 w-3.5 shrink-0" />
                        <span>{item.error}</span>
                      </p>
                    ) : null}
                  </div>

                  <div className="flex shrink-0 items-center gap-2">
                    {item.uploadState === "uploading" ? (
                      <Loader2 className="h-4 w-4 animate-spin text-muted" />
                    ) : item.uploadState === "done" ? (
                      <CheckCircle2 className="h-4 w-4 text-success" />
                    ) : null}
                    <Button
                      variant="ghost"
                      size="icon"
                      disabled={uploading && item.uploadState === "uploading"}
                      onClick={() => removeStaged(item.id)}
                      aria-label={`Loại ${item.fileName} khỏi danh sách chờ`}
                    >
                      <X className="h-4 w-4 text-muted" />
                    </Button>
                  </div>
                </div>

                {status.backendOnline && item.uploadState === "uploading" ? (
                  <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-bg-secondary">
                    <div
                      className="h-full bg-ink transition-all"
                      style={{ width: `${item.progress}%` }}
                    />
                  </div>
                ) : null}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  )
}
