import { useRef } from "react"
import {
  BookOpen,
  Cpu,
  FileText,
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
import { AI_MODEL_OPTIONS } from "@/services/chat-service"

export function ChatComposer({
  value,
  onChange,
  onSend,
  onCancel,
  busy,
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

  const scopeTooltip = selectedNotebook
    ? `Phạm vi tìm kiếm: Notebook "${selectedNotebook.name}"`
    : `Phạm vi tìm kiếm: Toàn bộ "${currentWorkspace?.name ?? "Workspace"}"`

  const attachTooltip =
    attachedDocIds.length > 0
      ? `Đính kèm tài liệu (${attachedDocIds.length} đã chọn)`
      : "Đính kèm tài liệu cụ thể vào câu hỏi"

  const modelTooltip = `Mô hình trả lời: ${currentModelOption?.label ?? modelId}`

  return (
    <div className="px-4 pb-5 pt-2 md:px-8">
      <div className="mx-auto max-w-3xl">
        <div className="motivo-card overflow-hidden transition-colors focus-within:border-brand">
          {/* Chỉ hiển thị chip khi người dùng chủ động đính kèm tài liệu hoặc giới hạn riêng 1 Notebook */}
          {attachedDocs.length > 0 || selectedNotebook ? (
            <div className="flex flex-wrap items-center gap-1.5 border-b border-line px-3 py-1.5 text-xs">
              {selectedNotebook ? (
                <span className="inline-flex items-center gap-1 rounded-md border border-line bg-bg-secondary px-2 py-0.5 text-ink">
                  <BookOpen className="h-3 w-3 text-muted" />
                  <span>{selectedNotebook.name}</span>
                  <button
                    type="button"
                    onClick={() => onSelectNotebook(null)}
                    className="ml-0.5 text-muted hover:text-ink"
                    aria-label="Bỏ giới hạn notebook"
                  >
                    <X className="h-3 w-3" />
                  </button>
                </span>
              ) : null}

              {attachedDocs.map((doc) => (
                <span
                  key={doc.id}
                  className="inline-flex items-center gap-1 rounded-md border border-line bg-bg-secondary px-2 py-0.5 text-ink"
                >
                  <FileText className="h-3 w-3 text-muted" />
                  <span className="max-w-[180px] truncate">{doc.fileName}</span>
                  <button
                    type="button"
                    onClick={() => onToggleAttachDoc(doc.id)}
                    className="ml-0.5 text-muted hover:text-ink"
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
                  className="text-[11px] text-muted underline hover:text-ink"
                >
                  Xóa hết
                </button>
              ) : null}
            </div>
          ) : null}

          {/* Ô nhập Textarea tự giãn chiều cao */}
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
              placeholder="Nhập câu hỏi của bạn..."
              className="max-h-[180px] min-h-[40px] w-full resize-none border-0 bg-transparent py-1 text-sm leading-6 text-ink placeholder:text-muted focus:outline-none focus-visible:outline-none"
            />
          </div>

          {/* Thanh công cụ dưới tối giản: các nút chức năng chỉ hiện icon, mô tả hiển thị khi di chuột vào */}
          <div className="flex items-center justify-between gap-2 px-2.5 pb-2 pt-1">
            <div className="flex items-center gap-1">
              {/* Nút đính kèm tài liệu (chỉ hiện chữ khi hover) */}
              <DropdownMenu
                align="start"
                trigger={
                  <span>
                    <Tooltip content={attachTooltip} side="top">
                      <button
                        type="button"
                        aria-label={attachTooltip}
                        className={`inline-flex h-7 items-center gap-1 rounded-md px-2 text-xs transition-colors ${
                          attachedDocIds.length > 0
                            ? "bg-bg-active font-medium text-ink"
                            : "text-muted hover:bg-bg-hover hover:text-ink"
                        }`}
                      >
                        <Paperclip className="h-3.5 w-3.5" />
                        {attachedDocIds.length > 0 ? (
                          <span>{attachedDocIds.length}</span>
                        ) : null}
                      </button>
                    </Tooltip>
                  </span>
                }
              >
                <DropdownMenuLabel>Chọn tài liệu đính kèm</DropdownMenuLabel>
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

              {/* Nút chọn phạm vi tìm kiếm (chỉ hiện mô tả khi hover) */}
              <DropdownMenu
                align="start"
                trigger={
                  <span>
                    <Tooltip content={scopeTooltip} side="top">
                      <button
                        type="button"
                        aria-label={scopeTooltip}
                        className={`inline-flex h-7 items-center gap-1 rounded-md px-2 text-xs transition-colors ${
                          selectedNotebook
                            ? "bg-bg-active font-medium text-ink"
                            : "text-muted hover:bg-bg-hover hover:text-ink"
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
                <DropdownMenuLabel>Phạm vi tìm kiếm tài liệu</DropdownMenuLabel>
                <DropdownMenuItem
                  shortcut={!selectedNotebookId ? "Đang chọn" : undefined}
                  onClick={() => onSelectNotebook(null)}
                >
                  Toàn bộ {currentWorkspace?.name ?? "không gian hiện tại"}
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

              {/* Nút chọn mô hình AI (chỉ hiện mô tả khi hover) */}
              <DropdownMenu
                align="start"
                trigger={
                  <span>
                    <Tooltip content={modelTooltip} side="top">
                      <button
                        type="button"
                        aria-label={modelTooltip}
                        className="inline-flex h-7 items-center justify-center rounded-md px-2 text-xs text-muted transition-colors hover:bg-bg-hover hover:text-ink"
                      >
                        <Cpu className="h-3.5 w-3.5" />
                      </button>
                    </Tooltip>
                  </span>
                }
              >
                <DropdownMenuLabel>Chọn mô hình trả lời</DropdownMenuLabel>
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
            </div>

            <div className="flex items-center gap-2">
              {busy ? (
                <div className="flex items-center gap-1.5">
                  <Loader2 className="h-3.5 w-3.5 animate-spin text-muted" />
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
                  <Button
                    type="button"
                    variant="default"
                    size="sm"
                    disabled={!value.trim()}
                    leftIcon={<Send className="h-3.5 w-3.5" />}
                    onClick={handleTriggerSend}
                  >
                    Gửi
                  </Button>
                </Tooltip>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
