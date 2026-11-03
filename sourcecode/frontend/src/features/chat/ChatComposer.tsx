import { useRef } from "react"
import {
  ArrowUp,
  BookOpen,
  ChevronDown,
  Cpu,
  FileText,
  FolderOpen,
  Loader2,
  Paperclip,
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

  const scopeLabel =
    attachedDocs.length > 0
      ? `${attachedDocs.length} tài liệu đã chọn`
      : selectedNotebook
        ? selectedNotebook.name
        : `${currentWorkspace?.name ?? "Workspace"} (${readyDocCount} tài liệu)`

  return (
    <div className="bg-white px-4 pt-2 pb-5 md:px-8">
      <div className="mx-auto max-w-3xl">
        {/* Khung nhập liệu với border rõ nét (#B5C9C5 -> focus #087F73) và shadow rất nhẹ */}
        <div className="overflow-hidden rounded-2xl border border-[#B5C9C5] bg-white shadow-[0_2px_10px_rgba(23,43,41,0.05)] transition-all focus-within:border-[#087F73] focus-within:ring-2 focus-within:ring-[#087F73]/15">
          {/* Chip tài liệu đính kèm (chỉ hiển thị khi có đính kèm) */}
          {attachedDocs.length > 0 ? (
            <div className="flex flex-wrap items-center gap-1.5 border-b border-[#E5EEEC] bg-[#F8FAFA] px-3.5 py-2 text-xs">
              {attachedDocs.map((doc) => (
                <span
                  key={doc.id}
                  className="inline-flex items-center gap-1 rounded-md border border-[#D4E2DF] bg-white px-2 py-0.5 text-[11px] font-medium text-[#172B29]"
                >
                  <FileText className="h-3 w-3 text-[#087F73]" />
                  <span className="max-w-[160px] truncate">{doc.fileName}</span>
                  <button
                    type="button"
                    onClick={() => onToggleAttachDoc(doc.id)}
                    className="ml-0.5 text-[#647C79] hover:text-[#172B29]"
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
                  className="text-[11px] text-[#647C79] underline hover:text-[#172B29]"
                >
                  Xóa hết
                </button>
              ) : null}
            </div>
          ) : null}

          {/* Ô nhập Textarea tự giãn chiều cao */}
          <div className="px-4 pt-3 pb-1">
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
              placeholder="Đặt câu hỏi từ tài liệu của bạn..."
              className="max-h-[180px] min-h-[42px] w-full resize-none border-0 bg-transparent py-1 text-[14px] leading-6 text-[#172B29] placeholder:text-[#647C79] focus:outline-none focus-visible:outline-none"
            />
          </div>

          {/* Thanh công cụ dưới: Phạm vi tài liệu, Đính kèm, Model & Nút Gửi (#087F73) */}
          <div className="flex items-center justify-between gap-2 px-3 pb-2.5 pt-1">
            <div className="flex flex-wrap items-center gap-1">
              {/* Chọn phạm vi tài liệu truy xuất */}
              <DropdownMenu
                align="start"
                trigger={
                  <span>
                    <Tooltip content="Phạm vi tài liệu truy xuất" side="top">
                      <button
                        type="button"
                        className="inline-flex h-7 items-center gap-1.5 rounded-lg border border-[#D4E2DF] bg-[#F5F8F7] px-2.5 text-xs font-medium text-[#172B29] transition-colors hover:border-[#087F73]"
                      >
                        <FolderOpen className="h-3.5 w-3.5 text-[#087F73]" />
                        <span className="max-w-[200px] truncate">{scopeLabel}</span>
                        <ChevronDown className="h-3 w-3 text-[#647C79]" />
                      </button>
                    </Tooltip>
                  </span>
                }
              >
                <DropdownMenuLabel>Phạm vi truy xuất</DropdownMenuLabel>
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
                    icon={<BookOpen className="h-3.5 w-3.5" />}
                    shortcut={selectedNotebookId === nb.id ? "Đang chọn" : undefined}
                    onClick={() => onSelectNotebook(nb.id)}
                  >
                    {nb.name}
                  </DropdownMenuItem>
                ))}
              </DropdownMenu>

              {/* Đính kèm tài liệu */}
              <DropdownMenu
                align="start"
                trigger={
                  <span>
                    <Tooltip content="Đính kèm tài liệu cụ thể" side="top">
                      <button
                        type="button"
                        aria-label="Đính kèm tài liệu"
                        className={`inline-flex h-7 items-center gap-1 rounded-lg px-2 text-xs transition-colors ${
                          attachedDocIds.length > 0
                            ? "font-semibold text-[#087F73]"
                            : "text-[#647C79] hover:bg-[#F0F5F4] hover:text-[#172B29]"
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
                <DropdownMenuLabel>Đính kèm tài liệu</DropdownMenuLabel>
                {workspaceDocuments.length === 0 ? (
                  <div className="px-2.5 py-2 text-xs text-[#647C79]">
                    Chưa có tài liệu trong Workspace.
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

              {/* Chọn mô hình LLM */}
              <DropdownMenu
                align="start"
                trigger={
                  <span>
                    <Tooltip content={`Mô hình: ${currentModelOption?.label ?? modelId}`} side="top">
                      <button
                        type="button"
                        aria-label="Chọn mô hình LLM"
                        className="inline-flex h-7 items-center gap-1 rounded-lg px-2 text-xs text-[#647C79] transition-colors hover:bg-[#F0F5F4] hover:text-[#172B29]"
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
                <DropdownMenuLabel>Mô hình LLM</DropdownMenuLabel>
                {AI_MODEL_OPTIONS.map((m) => (
                  <DropdownMenuItem
                    key={m.id}
                    shortcut={modelId === m.id ? "Đang chọn" : undefined}
                    onClick={() => onModelChange(m.id)}
                  >
                    <div>
                      <div className="font-medium text-[#172B29]">{m.label}</div>
                      <div className="text-[11px] text-[#647C79]">{m.description}</div>
                    </div>
                  </DropdownMenuItem>
                ))}
              </DropdownMenu>

              {onModeChange ? (
                <DropdownMenu
                  align="start"
                  trigger={
                    <button
                      type="button"
                      className="inline-flex h-7 items-center gap-1 rounded-lg px-2 text-xs text-[#647C79] transition-colors hover:bg-[#F0F5F4] hover:text-[#172B29] sm:hidden"
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

            {/* Nút Gửi CTA Primary #087F73 */}
            <div className="flex items-center gap-2">
              {busy ? (
                <div className="flex items-center gap-1.5">
                  <Loader2 className="h-3.5 w-3.5 animate-spin text-[#087F73]" />
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
                    aria-label="Gửi câu hỏi"
                    className="inline-flex h-8 w-8 items-center justify-center rounded-lg bg-[#087F73] text-white transition-colors hover:bg-[#06665C] disabled:cursor-not-allowed disabled:bg-[#D4E2DF] disabled:text-[#647C79]"
                  >
                    <ArrowUp className="h-4 w-4" />
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
