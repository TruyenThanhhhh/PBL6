import { useRef, useState } from "react"
import { AlertCircle, CheckCircle2, FileUp, Loader2, Trash2, Upload, X } from "lucide-react"
import { Alert, Badge, Button } from "@/components/ui"
import { buildUploadedDocument, useAppStore } from "@/store/app-store"
import {
  fetchDocuments,
  generateWorkspaceMetadataApi,
  mapBackendWorkspace,
  uploadDocumentWithProgress,
} from "@/services/api"
import type { Workspace } from "@/types"
import { ACCEPTED_EXTENSIONS, formatBytes, uid } from "@/utils/format"
import { cn } from "@/utils/cn"
import {
  buildStagedItem,
  MAX_FILE_SIZE_BYTES,
  readPlainTextIfPossible,
  type StagedUploadItem,
} from "./document-utils"

export function DocumentUploadPanel({
  targetWorkspaceId,
  targetNotebookId,
}: {
  targetWorkspaceId: string
  targetNotebookId?: string
  onTargetWorkspaceChange?: (wsId: string) => void
  onTargetNotebookChange?: (nbId: string) => void
}) {
  const documents = useAppStore((s) => s.documents)
  const addDocument = useAppStore((s) => s.addDocument)
  const replaceDocs = useAppStore((s) => s.replaceDocumentsFromBackend)
  const mergeWorkspaces = useAppStore((s) => s.mergeWorkspacesFromBackend)
  const status = useAppStore((s) => s.status)
  const toast = useAppStore((s) => s.toast)

  const [drag, setDrag] = useState(false)
  const [queue, setQueue] = useState<StagedUploadItem[]>([])
  const [uploading, setUploading] = useState(false)
  const [updatingMetadata, setUpdatingMetadata] = useState(false)
  const abortRef = useRef<AbortController | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const wsDocs = documents.filter((d) => d.workspaceId === targetWorkspaceId)

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
    const isBatchUpload = validItems.length > 1
    let updatedWorkspace: Workspace | null = null

    for (const item of validItems) {
      if (controller.signal.aborted) break

      setQueue((prev) =>
        prev.map((q) =>
          q.id === item.id
            ? {
                ...q,
                uploadState: "uploading",
                progress: 5,
                currentPhase: "upload",
                stageLabel: "Đang tải tệp lên máy chủ (5%)...",
              }
            : q,
        ),
      )

      let stageTimer: ReturnType<typeof setInterval> | null = null

      try {
        if (status.backendOnline) {
          const uploadPromise = uploadDocumentWithProgress(targetWorkspaceId, item.file, {
            notebookId: targetNotebookId || null,
            deferMetadata: true,
            replaceDocumentId: item.updateAsNewVersion ? item.replaceDocumentId : undefined,
            signal: controller.signal,
            onProgress: (pct) => {
              // Mạng upload chiếm 5% - 25%
              const networkProgress = Math.round(5 + (pct / 100) * 20)
              setQueue((prev) =>
                prev.map((q) => {
                  if (q.id !== item.id) return q
                  if (pct >= 100 && q.currentPhase === "upload") {
                    return {
                      ...q,
                      progress: 26,
                      currentPhase: "extract",
                      stageLabel: "Tệp đã lên máy chủ · Đang đọc cấu trúc & trích xuất nội dung...",
                    }
                  }
                  return {
                    ...q,
                    progress: networkProgress,
                    stageLabel: `Đang tải tệp lên máy chủ (${pct}%)...`,
                  }
                }),
              )

              // Khi file vừa chuyển hết lên máy chủ qua mạng (pct >= 100), kích hoạt tiến trình mô phỏng các bước AI phía backend
              if (pct >= 100 && !stageTimer) {
                let currentSim = 26
                stageTimer = setInterval(() => {
                  currentSim += Math.floor(Math.random() * 3) + 2
                  if (currentSim > 95) currentSim = 95

                  let phase: "extract" | "chunk" | "embed" | "index" = "extract"
                  let label = "Đang đọc cấu trúc & trích xuất văn bản..."

                  if (currentSim >= 45 && currentSim < 65) {
                    phase = "chunk"
                    label = "Đang chia nhỏ phân đoạn thông minh (Chunking) & bảo toàn ngữ cảnh..."
                  } else if (currentSim >= 65 && currentSim < 85) {
                    phase = "embed"
                    label = "Đang sinh vector embedding ngữ nghĩa (BGE-M3) trên CPU..."
                  } else if (currentSim >= 85) {
                    phase = "index"
                    label = "Đang tối ưu chỉ mục Hybrid RAG (FTS5 + Vector SQLite)..."
                  }

                  setQueue((prev) =>
                    prev.map((q) =>
                      q.id === item.id && q.uploadState === "uploading"
                        ? {
                            ...q,
                            progress: currentSim,
                            currentPhase: phase,
                            stageLabel: label,
                          }
                        : q,
                    ),
                  )
                }, 750)
              }
            },
          })

          const res = await uploadPromise
          if (!isBatchUpload && res?.workspace) {
            updatedWorkspace = mapBackendWorkspace(res.workspace)
          }

          if (stageTimer) {
            clearInterval(stageTimer)
            stageTimer = null
          }

          const docMeta = res?.document as Record<string, unknown> | undefined
          const chunks = Number(docMeta?.total_chunks ?? 0)

          setQueue((prev) =>
            prev.map((q) =>
              q.id === item.id
                ? {
                    ...q,
                    uploadState: "done",
                    progress: 100,
                    currentPhase: "ready",
                    totalChunks: chunks,
                    stageLabel:
                      chunks > 0
                        ? `Hoàn tất! Đã lập chỉ mục ${chunks} chunks & vector sẵn sàng hỏi đáp AI.`
                        : "Hoàn tất! Tài liệu đã sẵn sàng truy xuất.",
                  }
                : q,
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
              q.id === item.id
                ? {
                    ...q,
                    uploadState: "done",
                    progress: 100,
                    currentPhase: "ready",
                    stageLabel: "Đã lưu tạm trên trình duyệt (chế độ cục bộ).",
                  }
                : q,
            ),
          )
          successCount += 1
        }
      } catch (err) {
        if (stageTimer) {
          clearInterval(stageTimer)
          stageTimer = null
        }
        const msg = err instanceof Error ? err.message : String(err)
        setQueue((prev) =>
          prev.map((q) =>
            q.id === item.id
              ? {
                  ...q,
                  uploadState: "error",
                  error: msg,
                  stageLabel: `Thất bại: ${msg}`,
                }
              : q,
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

      if (isBatchUpload || !updatedWorkspace) {
        setUpdatingMetadata(true)
        void generateWorkspaceMetadataApi(targetWorkspaceId)
          .then((metaRes) => {
            if (metaRes.workspace) {
              mergeWorkspaces([metaRes.workspace])
            }
          })
          .catch(() => {
            // Không làm gián đoạn trạng thái upload thành công nếu sinh metadata lỗi
          })
          .finally(() => {
            setUpdatingMetadata(false)
          })
      }

      if (updatedWorkspace) {
        mergeWorkspaces([updatedWorkspace])
      }

      toast({
        title: `Đã xử lý & lập chỉ mục ${successCount} tài liệu thành công`,
        description: updatedWorkspace
          ? `Đã cập nhật workspace "${updatedWorkspace.name}".`
          : "Các đoạn văn bản đã được lập chỉ mục FTS5 & đang đồng bộ vector ngữ nghĩa.",
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
    // Cho người dùng xem trạng thái hoàn tất 100% trong 1.5 giây trước khi tự dọn dẹp hàng đợi
    setTimeout(() => {
      setQueue((prev) => prev.filter((q) => q.uploadState !== "done"))
    }, 1500)
  }

  return (
    <section aria-label="Tải lên tài liệu" className="motivo-card mb-6 p-4">
      {updatingMetadata ? (
        <div className="mb-3 flex items-center gap-2 rounded-lg border border-brand/25 bg-brand-soft/60 px-3 py-2 text-xs font-medium text-ink">
          <Loader2 className="h-3.5 w-3.5 animate-spin text-brand" />
          <span>Đã tải xong lô tài liệu · AI đang tạo tiêu đề và mô tả cho Workspace...</span>
        </div>
      ) : null}
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

          <ul className="divide-y divide-line rounded-lg border border-line bg-bg overflow-hidden shadow-2xs">
            {queue.map((item) => {
              const isUploading = item.uploadState === "uploading"
              const isDone = item.uploadState === "done"
              const isError = Boolean(item.error)

              return (
                <li key={item.id} className="p-3.5 text-sm transition-colors hover:bg-bg-hover/30">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="truncate font-semibold text-ink">{item.fileName}</span>
                        <Badge tone="neutral">{item.fileType.toUpperCase()}</Badge>
                        <span className="text-xs text-muted">{formatBytes(item.fileSize)}</span>

                        {isError ? (
                          <Badge tone="error" dot>
                            Không hợp lệ
                          </Badge>
                        ) : isUploading ? (
                          <Badge tone="warning" dot>
                            {item.currentPhase === "upload" && `Đang tải lên (${item.progress}%)`}
                            {item.currentPhase === "extract" && `Trích xuất (${item.progress}%)`}
                            {item.currentPhase === "chunk" && `Chia chunk (${item.progress}%)`}
                            {item.currentPhase === "embed" && `Vector BGE-M3 (${item.progress}%)`}
                            {item.currentPhase === "index" && `Lập chỉ mục (${item.progress}%)`}
                            {!item.currentPhase && `Đang xử lý (${item.progress}%)`}
                          </Badge>
                        ) : isDone ? (
                          <Badge tone="success" dot>
                            Hoàn tất {item.totalChunks ? `(${item.totalChunks} chunks)` : ""}
                          </Badge>
                        ) : (
                          <Badge tone="neutral" dot>
                            Chờ tải lên
                          </Badge>
                        )}
                      </div>

                      {/* Tùy chọn nâng cấp phiên bản mới nếu trùng tên tài liệu đã có */}
                      {item.replaceDocumentId && item.uploadState === "staged" ? (
                        <label className="mt-1.5 flex cursor-pointer items-center gap-2 rounded border border-[#DCE7E4] bg-[#F1F6F5] px-2 py-1 text-[11px] text-[#172B29]">
                          <input
                            type="checkbox"
                            checked={Boolean(item.updateAsNewVersion)}
                            onChange={(e) =>
                              setQueue((prev) =>
                                prev.map((q) =>
                                  q.id === item.id ? { ...q, updateAsNewVersion: e.target.checked } : q,
                                ),
                              )
                            }
                          />
                          <span>
                            Cập nhật thành <strong>Phiên bản v{item.nextVersionNumber ?? 2}</strong> (ưu tiên bản mới khi hỏi đáp AI)
                          </span>
                        </label>
                      ) : null}

                      {/* Thông báo lỗi nếu có */}
                      {isError ? (
                        <p className="mt-1.5 flex items-center gap-1 text-xs text-error">
                          <AlertCircle className="h-3.5 w-3.5 shrink-0" />
                          <span>{item.error}</span>
                        </p>
                      ) : null}

                      {/* Phụ đề trạng thái động khi đang xử lý */}
                      {isUploading && (
                        <div className="mt-1.5 flex items-center gap-1.5 text-xs font-medium text-[#0F766E]">
                          <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin text-[#0F766E]" />
                          <span className="truncate">{item.stageLabel || "Đang xử lý tài liệu trên máy chủ..."}</span>
                        </div>
                      )}

                      {/* Banner hoàn tất thành công */}
                      {isDone && (
                        <div className="mt-2 flex items-center justify-between rounded-md border border-emerald-200 bg-emerald-50/70 px-2.5 py-1.5 text-xs text-emerald-800">
                          <div className="flex items-center gap-1.5 font-medium">
                            <CheckCircle2 className="h-3.5 w-3.5 shrink-0 text-emerald-600" />
                            <span>{item.stageLabel || "Tài liệu đã sẵn sàng truy xuất!"}</span>
                          </div>
                          <span className="shrink-0 rounded-full bg-emerald-100/90 px-2 py-0.5 text-[11px] font-bold text-emerald-700">
                            100% Hoàn tất
                          </span>
                        </div>
                      )}
                    </div>

                    <div className="flex shrink-0 items-center gap-2">
                      {isUploading ? (
                        <Loader2 className="h-4 w-4 animate-spin text-[#0F766E]" />
                      ) : isDone ? (
                        <CheckCircle2 className="h-4 w-4 text-success" />
                      ) : null}
                      <Button
                        variant="ghost"
                        size="icon"
                        disabled={uploading && isUploading}
                        onClick={() => removeStaged(item.id)}
                        aria-label={`Loại ${item.fileName} khỏi danh sách chờ`}
                      >
                        <X className="h-4 w-4 text-muted" />
                      </Button>
                    </div>
                  </div>

                  {/* Thanh tiến trình chi tiết khi đang tải / xử lý trên máy chủ */}
                  {status.backendOnline && isUploading && (
                    <div className="mt-3 space-y-2 border-t border-line/60 pt-2.5">
                      <div className="flex items-center justify-between text-xs">
                        <span className="text-[11px] font-medium text-muted">
                          Tiến trình xử lý Hybrid RAG
                        </span>
                        <span className="text-xs font-bold text-[#0F766E]">{item.progress}%</span>
                      </div>

                      {/* Thanh Progress Bar với gradient & animation mượt mà */}
                      <div className="h-2 w-full overflow-hidden rounded-full bg-[#E6F4F1]">
                        <div
                          className="h-full rounded-full bg-gradient-to-r from-[#0F766E] via-[#0D9488] to-[#14B8A6] transition-all duration-300 ease-out shadow-xs"
                          style={{ width: `${Math.max(5, item.progress)}%` }}
                        />
                      </div>

                      {/* 4 mốc xử lý trực quan: 1. Tải tệp -> 2. Trích xuất -> 3. Chia chunk -> 4. Vector RAG */}
                      <div className="grid grid-cols-4 gap-1.5 pt-0.5 text-[11px]">
                        <div
                          className={cn(
                            "flex items-center justify-center gap-1 rounded py-1 px-1.5 border transition-all text-center",
                            item.progress >= 25
                              ? "border-emerald-200 bg-emerald-50 text-emerald-700 font-medium"
                              : "border-line bg-bg-secondary text-muted"
                          )}
                        >
                          <span className="font-bold">1.</span> Tải tệp {item.progress >= 25 ? "✓" : ""}
                        </div>
                        <div
                          className={cn(
                            "flex items-center justify-center gap-1 rounded py-1 px-1.5 border transition-all text-center",
                            item.progress >= 48
                              ? "border-emerald-200 bg-emerald-50 text-emerald-700 font-medium"
                              : item.progress >= 25
                                ? "border-teal-300 bg-teal-50 text-teal-800 font-semibold animate-pulse"
                                : "border-line bg-bg-secondary text-muted"
                          )}
                        >
                          <span className="font-bold">2.</span> Trích xuất {item.progress >= 48 ? "✓" : ""}
                        </div>
                        <div
                          className={cn(
                            "flex items-center justify-center gap-1 rounded py-1 px-1.5 border transition-all text-center",
                            item.progress >= 68
                              ? "border-emerald-200 bg-emerald-50 text-emerald-700 font-medium"
                              : item.progress >= 48
                                ? "border-teal-300 bg-teal-50 text-teal-800 font-semibold animate-pulse"
                                : "border-line bg-bg-secondary text-muted"
                          )}
                        >
                          <span className="font-bold">3.</span> Chia đoạn {item.progress >= 68 ? "✓" : ""}
                        </div>
                        <div
                          className={cn(
                            "flex items-center justify-center gap-1 rounded py-1 px-1.5 border transition-all text-center",
                            item.progress >= 98
                              ? "border-emerald-200 bg-emerald-50 text-emerald-700 font-medium"
                              : item.progress >= 68
                                ? "border-teal-300 bg-teal-50 text-teal-800 font-semibold animate-pulse"
                                : "border-line bg-bg-secondary text-muted"
                          )}
                        >
                          <span className="font-bold">4.</span> Vector RAG {item.progress >= 98 ? "✓" : ""}
                        </div>
                      </div>
                    </div>
                  )}
                </li>
              )
            })}
          </ul>
        </div>
      ) : null}
    </section>
  )
}
