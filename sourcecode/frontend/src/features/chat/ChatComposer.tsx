import { useRef } from "react"
import {
  BookOpen,
  ChevronDown,
  Cpu,
  FileText,
  FolderOpen,
  Loader2,
  Paperclip,
  Send,
  Square,
  X,
} from "lucide-react"
import {
  Button,
  DropdownMenu,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  Tooltip,
} from "@/components/ui"
import type { AIMode, KnowledgeDocument, Notebook, Workspace } from "@/types"
import { AI_MODEL_OPTIONS, getModeDescriptor } from "@/services/chat-service"

export function ChatComposer({
  value,
  onChange,
  onSend,
  onCancel,
  busy,
  aiMode = "auto",
  onModeChange,
  modelId,
  onModelChange,
  currentWorkspace,
  notebooks,
  selectedNotebookId,
  onSelectNotebook,
  workspaceDocuments,
  attachedDocIds,
  onToggleAttachDoc,
  onClearAttachedDocs,
}: {
  value: string
  onChange: (next: string) => void
  onSend: () => void
  onCancel: () => void
  busy: boolean
  aiMode?: AIMode
  onModeChange?: (mode: AIMode) => void
  modelId: string
  onModelChange: (modelId: string) => void
  currentWorkspace?: Workspace
  notebooks: Notebook[]
  selectedNotebookId: string | null
  onSelectNotebook: (notebookId: string | null) => void
  workspaceDocuments: KnowledgeDocument[]
  attachedDocIds: string[]
  onToggleAttachDoc: (docId: string) => void
  onClearAttachedDocs: () => void
  backendOnline?: boolean
}) {
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const selectedNotebook = notebooks.find((n) => n.id === selectedNotebookId)
  const attachedDocs = workspaceDocuments.filter((d) => attachedDocIds.includes(d.id))
  const readyDocCount = workspaceDocuments.filter((d) => d.status === "ready").length
  const currentModelOption =
    AI_MODEL_OPTIONS.find((m) => m.id === modelId) ?? AI_MODEL_OPTIONS[0]

  const adjustHeight = (el: HTMLTextAreaElement) => {
    el.style.height = "auto"
    const nextHeight = Math.min(Math.max(el.scrollHeight, 44), 180)
    el.style.height = `${nextHeight}px`
  }

  const handleTextChange = (next: string) => {
    onChange(next)
    if (textareaRef.current) {
      adjustHeight(textareaRef.current)
    }
  }

  const handleTriggerSend = () => {
    if (!value.trim() || busy) return
    onSend()
    if (textareaRef.current) {
      textareaRef.current.style.height = "44px"
    }
  }

  // Nhãn hiển thị phạm vi tài liệu đang được sử dụng để truy xuất
  const scopeLabel =
    attachedDocs.length > 0
      ? `${attachedDocs.length} tài liệu đính kèm`
      : selectedNotebook
        ? `Notebook: ${selectedNotebook.name}`
        : `Toàn bộ ${currentWorkspace?.name ?? "Workspace"} (${readyDocCount} tài liệu)`

  const attachTooltip =
    attachedDocIds.length > 0
      ? `Đính kèm tài liệu (${attachedDocIds.length} đã chọn)`
      : "Đính kèm tài liệu cụ thể vào câu hỏi"

  const modelTooltip = `Mô hình trả lời: ${currentModelOption?.label ?? modelId}`

  return (
    <div className="border-t border-[#E6F0EE] bg-white px-4 pt-2.5 pb-4 md:px-8">
      <div className="mx-auto max-w-3xl">
        <div className="overflow-hidden rounded-2xl border border-[#CBE0DC] bg-white shadow-[0_4px_20px_-4px_rgba(11,35,32,0.06)] transition-all focus-within:border-[#0F766E] focus-within:ring-2 focus-within:ring-[#0F766E]/12">
          {/* Thanh hiển thị phạm vi tài liệu đang được sử dụng để truy xuất + Chip đính kèm */}
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[#EDF4F2] bg-[#F8FBFA] px-3.5 py-1.5 text-xs">
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="text-[11px] font-medium text-[#647D7A]">Phạm vi truy xuất:</span>

              <DropdownMenu
                align="start"
                trigger={
                  <button
                    type="button"
                    className="inline-flex items-center gap-1 rounded-lg border border-[#D5E6E2] bg-white px-2 py-0.5 text-[11px] font-semibold text-[#0F766E] transition-colors hover:bg-[#F0F9F7]"
                  >
                    <FolderOpen className="h-3 w-3" />
                    <span className="max-w-[220px] truncate">{scopeLabel}</span>
                    <ChevronDown className="h-3 w-3 text-[#647D7A]" />
                  </button>
                }
              >
                <DropdownMenuLabel>Chọn phạm vi truy xuất tài liệu</DropdownMenuLabel>
                <DropdownMenuItem
                  shortcut={!selectedNotebookId && attachedDocs.length === 0 ? "Đang chọn" : undefined}
                  onClick={() => {
                    onSelectNotebook(null)
                    onClearAttachedDocs()
                  }}
                >
                  Toàn bộ {currentWorkspace?.name ?? "Workspace"} ({readyDocCount} tài liệu)
                </DropdownMenuItem>
                {notebooks.length > 0 ? <DropdownMenuSeparator /> : null}
                {notebooks.map((nb) => (
                  <DropdownMenuItem
                    key={nb.id}
                    shortcut={selectedNotebookId === nb.id ? "Đang chọn" : undefined}
                    onClick={() => onSelectNotebook(nb.id)}
                  >
                    Notebook: {nb.name}
                  </DropdownMenuItem>
                ))}
              </DropdownMenu>

              {/* Các chip tài liệu đính kèm trực tiếp */}
              {attachedDocs.map((doc) => (
                <span
                  key={doc.id}
                  className="inline-flex items-center gap-1 rounded-lg border border-[#CBE4DF] bg-[#E2F3EF]/60 px-2 py-0.5 text-[11px] font-medium text-[#0B1716]"
                >
                  <FileText className="h-3 w-3 text-[#0F766E]" />
                  <span className="max-w-[150px] truncate">{doc.fileName}</span>
                  <button
                    type="button"
                    onClick={() => onToggleAttachDoc(doc.id)}
                    className="ml-0.5 text-[#647D7A] hover:text-[#0B1716]"
                    aria-label={`Bỏ đính kèm ${doc.fileName}`}
                  >
                    <X className="h-3 w-3" />
                  </button>
                </span>
              ))}

              {attachedDocs.length > 1 ? (
                <button
                  type="button"
                  onClick={onClearAttachedDocs}
                  className="text-[11px] text-[#647D7A] underline hover:text-[#0B1716]"
                >
                  Bỏ chọn hết
                </button>
              ) : null}
            </div>

            <span className="hidden text-[11px] text-[#7A9490] sm:inline">
              Chế độ: <strong className="font-semibold text-[#37524F]">{getModeDescriptor(aiMode).label}</strong>
            </span>
          </div>

          {/* Ô nhập Textarea tự giãn chiều cao (hỗ trợ nhiều dòng) */}
          <div className="px-3.5 pt-2.5 pb-1">
            <textarea
              ref={textareaRef}
              value={value}
              onChange={(e) => handleTextChange(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault()
                  handleTriggerSend()
                }
              }}
              rows={1}
              placeholder={`Đặt câu hỏi về tài liệu trong "${currentWorkspace?.name ?? "Workspace"}"... (Shift + Enter để xuống dòng)`}
              className="max-h-[180px] min-h-[42px] w-full resize-none border-0 bg-transparent py-1 text-sm leading-6 text-[#0B1716] placeholder:text-[#7A9490] focus:outline-none focus-visible:outline-none"
            />
          </div>

          {/* Thanh công cụ dưới: Đính kèm tài liệu, Chọn Notebook, Chọn Model & Gửi */}
          <div className="flex items-center justify-between gap-2 px-3 pb-2.5 pt-1">
            <div className="flex items-center gap-1">
              {/* Nút đính kèm tài liệu */}
              <DropdownMenu
                align="start"
                trigger={
                  <span>
                    <Tooltip content={attachTooltip} side="top">
                      <button
                        type="button"
                        aria-label={attachTooltip}
                        className={`inline-flex h-7 items-center gap-1.5 rounded-lg px-2.5 text-xs transition-colors ${
                          attachedDocIds.length > 0
                            ? "bg-[#E2F3EF] font-semibold text-[#0F766E]"
                            : "text-[#526B68] hover:bg-[#F0F7F5] hover:text-[#0B1716]"
                        }`}
                      >
                        <Paperclip className="h-3.5 w-3.5" />
                        <span>Đính kèm{attachedDocIds.length > 0 ? ` (${attachedDocIds.length})` : ""}</span>
                      </button>
                    </Tooltip>
                  </span>
                }
              >
                <DropdownMenuLabel>Chọn tài liệu đính kèm trong Workspace</DropdownMenuLabel>
                {workspaceDocuments.length === 0 ? (
                  <div className="px-2.5 py-2 text-xs text-muted">
                    Chưa có tài liệu trong không gian này.
                  </div>
                ) : (
                  workspaceDocuments.map((doc) => {
                    const isAttached = attachedDocIds.includes(doc.id)
                    return (
                      <DropdownMenuItem
                        key={doc.id}
                        icon={<FileText className="h-3.5 w-3.5" />}
                        shortcut={isAttached ? "Đã chọn" : undefined}
                        onClick={() => onToggleAttachDoc(doc.id)}
                      >
                        {doc.fileName}
                      </DropdownMenuItem>
                    )
                  })
                )}
              </DropdownMenu>

              {/* Nút chọn Notebook nếu có */}
              {notebooks.length > 0 ? (
                <DropdownMenu
                  align="start"
                  trigger={
                    <span>
                      <Tooltip content="Giới hạn theo Notebook" side="top">
                        <button
                          type="button"
                          className={`inline-flex h-7 items-center gap-1 rounded-lg px-2 text-xs transition-colors ${
                            selectedNotebook
                              ? "bg-[#E2F3EF] font-semibold text-[#0F766E]"
                              : "text-[#526B68] hover:bg-[#F0F7F5] hover:text-[#0B1716]"
                          }`}
                        >
                          <BookOpen className="h-3.5 w-3.5" />
                          {selectedNotebook ? (
                            <span className="max-w-[110px] truncate">{selectedNotebook.name}</span>
                          ) : null}
                        </button>
                      </Tooltip>
                    </span>
                  }
                >
                  <DropdownMenuLabel>Phạm vi Notebook</DropdownMenuLabel>
                  <DropdownMenuItem
                    shortcut={!selectedNotebookId ? "Đang chọn" : undefined}
                    onClick={() => onSelectNotebook(null)}
                  >
                    Tất cả tài liệu trong Workspace
                  </DropdownMenuItem>
                  <DropdownMenuSeparator />
                  {notebooks.map((nb) => (
                    <DropdownMenuItem
                      key={nb.id}
                      shortcut={selectedNotebookId === nb.id ? "Đang chọn" : undefined}
                      onClick={() => onSelectNotebook(nb.id)}
                    >
                      {nb.name}
                    </DropdownMenuItem>
                  ))}
                </DropdownMenu>
              ) : null}

              {/* Nút chọn mô hình AI */}
              <DropdownMenu
                align="start"
                trigger={
                  <span>
                    <Tooltip content={modelTooltip} side="top">
                      <button
                        type="button"
                        aria-label={modelTooltip}
                        className="inline-flex h-7 items-center gap-1 rounded-lg px-2 text-xs text-[#526B68] transition-colors hover:bg-[#F0F7F5] hover:text-[#0B1716]"
                      >
                        <Cpu className="h-3.5 w-3.5" />
                        <span className="hidden font-mono text-[11px] sm:inline">
                          {currentModelOption?.label ?? modelId}
                        </span>
                      </button>
                    </Tooltip>
                  </span>
                }
              >
                <DropdownMenuLabel>Chọn mô hình LLM</DropdownMenuLabel>
                {AI_MODEL_OPTIONS.map((m) => (
                  <DropdownMenuItem
                    key={m.id}
                    shortcut={modelId === m.id ? "Đang chọn" : undefined}
                    onClick={() => onModelChange(m.id)}
                  >
                    <div>
                      <div className="font-medium text-ink">{m.label}</div>
                      <div className="text-[11px] text-muted">{m.description}</div>
                    </div>
                  </DropdownMenuItem>
                ))}
              </DropdownMenu>

              {/* Đổi nhanh chế độ RAG nếu cần */}
              {onModeChange ? (
                <DropdownMenu
                  align="start"
                  trigger={
                    <button
                      type="button"
                      className="inline-flex h-7 items-center gap-1 rounded-lg px-2 text-xs text-[#526B68] transition-colors hover:bg-[#F0F7F5] hover:text-[#0B1716] sm:hidden"
                    >
                      <span>{getModeDescriptor(aiMode).label}</span>
                    </button>
                  }
                >
                  <DropdownMenuLabel>Chế độ RAG</DropdownMenuLabel>
                  {(["auto", "local", "hybrid", "web"] as AIMode[]).map((m) => (
                    <DropdownMenuItem
                      key={m}
                      shortcut={aiMode === m ? "Đang chọn" : undefined}
                      onClick={() => onModeChange(m)}
                    >
                      {getModeDescriptor(m).label}
                    </DropdownMenuItem>
                  ))}
                </DropdownMenu>
              ) : null}
            </div>

            <div className="flex items-center gap-2">
              {busy ? (
                <div className="flex items-center gap-1.5">
                  <Loader2 className="h-3.5 w-3.5 animate-spin text-[#0F766E]" />
                  <Button
                    type="button"
                    variant="danger"
                    size="sm"
                    leftIcon={<Square className="h-3 w-3" />}
                    onClick={onCancel}
                  >
                    Dừng
                  </Button>
                </div>
              ) : (
                <Tooltip content="Gửi câu hỏi (Enter)" side="top">
                  <button
                    type="button"
                    disabled={!value.trim()}
                    onClick={handleTriggerSend}
                    className="inline-flex h-8 items-center gap-1.5 rounded-full bg-[#0B1315] px-4 text-xs font-semibold text-white shadow-2xs transition-colors hover:bg-[#0F766E] disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    <span>Gửi</span>
                    <Send className="h-3 w-3" />
                  </button>
                </Tooltip>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
