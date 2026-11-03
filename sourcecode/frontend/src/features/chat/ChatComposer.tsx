import { useRef } from "react"
import {
  ArrowUp,
  BookOpen,
  Check,
  ChevronDown,
  Cpu,
  FileText,
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
import { formatBytes } from "@/utils/format"
import { cn } from "@/utils/cn"

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
  const attachedDocs = workspaceDocuments.filter((d) => attachedDocIds.includes(d.id))
  const currentModelOption =
    AI_MODEL_OPTIONS.find((m) => m.id === modelId) ?? AI_MODEL_OPTIONS[0]

  const adjustHeight = (el: HTMLTextAreaElement) => {
    el.style.height = "auto"
    const nextHeight = Math.min(Math.max(el.scrollHeight, 40), 160)
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
      textareaRef.current.style.height = "40px"
    }
  }

  const scopeLabel =
    attachedDocs.length === 0
      ? `Tất cả tài liệu (${workspaceDocuments.length})`
      : attachedDocs.length === 1
        ? attachedDocs[0].fileName
        : `${attachedDocs.length}/${workspaceDocuments.length} tài liệu đã chọn`

  return (
    <div className="bg-white px-4 pt-1.5 pb-3.5 md:px-8 border-t border-[#DCE7E4]/70">
      <div className="mx-auto max-w-3xl">
        {/* Khung nhập liệu với border rõ (#DCE7E4 -> focus #087F73) và shadow rất nhẹ */}
        <div className="overflow-hidden rounded-xl border border-[#DCE7E4] bg-white shadow-2xs transition-all focus-within:border-[#087F73] focus-within:ring-1 focus-within:ring-[#087F73]/20">
          {/* Chip tài liệu đính kèm (chỉ hiển thị khi có đính kèm) */}
          {attachedDocs.length > 0 ? (
            <div className="flex flex-wrap items-center gap-1.5 border-b border-[#DCE7E4] bg-[#F1F6F5] px-3 py-1.5 text-xs">
              {attachedDocs.map((doc) => (
                <span
                  key={doc.id}
                  className="inline-flex items-center gap-1 rounded border border-[#DCE7E4] bg-white px-2 py-0.5 text-[11px] font-medium text-[#172B29]"
                >
                  <FileText className="h-3 w-3 text-[#087F73]" />
                  <span className="max-w-[150px] truncate">{doc.fileName}</span>
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
              placeholder="Đặt câu hỏi từ tài liệu của bạn... (Enter để gửi)"
              className="max-h-[160px] min-h-[40px] w-full resize-none border-0 bg-transparent py-1 text-sm leading-relaxed text-[#172B29] placeholder:text-[#647C79] focus:outline-none focus-visible:outline-none"
            />
          </div>

          {/* Thanh công cụ dưới: Scope, Attach, Model & Send Button */}
          <div className="flex items-center justify-between gap-2 px-2.5 pb-2 pt-0.5">
            <div className="flex flex-wrap items-center gap-1">
              {/* Chọn nguồn tài liệu truy xuất (Kiểu NotebookLM: chọn tất cả hoặc từng tài liệu cụ thể) */}
              <DropdownMenu
                align="start"
                trigger={
                  <span>
                    <Tooltip content="Chọn phạm vi tài liệu trong không gian" side="top">
                      <button
                        type="button"
                        className={cn(
                          "inline-flex h-6.5 items-center gap-1 rounded-md border px-2 text-[11px] font-medium transition-colors",
                          attachedDocs.length > 0
                            ? "border-[#087F73] bg-[#087F73]/10 text-[#087F73]"
                            : "border-[#DCE7E4] bg-[#F1F6F5] text-[#172B29] hover:border-[#087F73]",
                        )}
                      >
                        <FileText className="h-3 w-3 text-[#087F73]" />
                        <span className="max-w-[200px] truncate">{scopeLabel}</span>
                        <ChevronDown className="h-2.5 w-2.5 text-[#647C79]" />
                      </button>
                    </Tooltip>
                  </span>
                }
              >
                <DropdownMenuLabel>Phạm vi tài liệu ({workspaceDocuments.length})</DropdownMenuLabel>
                <DropdownMenuItem
                  icon={
                    <Check
                      className={cn(
                        "h-3.5 w-3.5",
                        attachedDocs.length === 0 ? "text-[#087F73]" : "opacity-0",
                      )}
                    />
                  }
                  onClick={() => {
                    onSelectNotebook(null)
                    onClearAttachedDocs()
                  }}
                >
                  <span className={cn(attachedDocs.length === 0 && "font-semibold text-[#087F73]")}>
                    Tất cả tài liệu ({workspaceDocuments.length})
                  </span>
                </DropdownMenuItem>

                <DropdownMenuSeparator />
                <DropdownMenuLabel>Tài liệu trong không gian</DropdownMenuLabel>
                {workspaceDocuments.length === 0 ? (
                  <div className="px-3 py-2 text-xs text-[#647C79]">
                    Chưa có tài liệu nào trong không gian này.
                  </div>
                ) : (
                  workspaceDocuments.map((doc) => {
                    const isAttached = attachedDocIds.includes(doc.id)
                    return (
                      <DropdownMenuItem
                        key={doc.id}
                        icon={
                          <span
                            className={cn(
                              "flex h-3.5 w-3.5 items-center justify-center rounded border",
                              isAttached
                                ? "border-[#087F73] bg-[#087F73] text-white"
                                : "border-[#DCE7E4]",
                            )}
                          >
                            {isAttached ? <Check className="h-2.5 w-2.5 stroke-[3]" /> : null}
                          </span>
                        }
                        onClick={() => onToggleAttachDoc(doc.id)}
                        className="flex items-center justify-between gap-3"
                      >
                        <span
                          className={cn(
                            "truncate text-xs",
                            isAttached && "font-semibold text-[#087F73]",
                          )}
                        >
                          {doc.fileName}
                        </span>
                        <span className="shrink-0 text-[10.5px] text-[#647C79]">
                          {formatBytes(doc.fileSize)}
                        </span>
                      </DropdownMenuItem>
                    )
                  })
                )}

                {notebooks.length > 0 ? (
                  <>
                    <DropdownMenuSeparator />
                    <DropdownMenuLabel>Phân loại Notebook</DropdownMenuLabel>
                    {notebooks.map((nb) => (
                      <DropdownMenuItem
                        key={nb.id}
                        icon={<BookOpen className="h-3.5 w-3.5 text-[#647C79]" />}
                        shortcut={selectedNotebookId === nb.id ? "Đang chọn" : undefined}
                        onClick={() => onSelectNotebook(nb.id)}
                      >
                        {nb.name}
                      </DropdownMenuItem>
                    ))}
                  </>
                ) : null}
              </DropdownMenu>

              {/* Đính kèm tài liệu */}
              <DropdownMenu
                align="start"
                trigger={
                  <span>
                    <Tooltip content="Đính kèm tài liệu" side="top">
                      <button
                        type="button"
                        aria-label="Đính kèm tài liệu"
                        className={cn(
                          "inline-flex h-6.5 items-center gap-1 rounded-md px-1.5 text-xs transition-colors",
                          attachedDocIds.length > 0
                            ? "bg-[#087F73]/10 font-semibold text-[#087F73]"
                            : "text-[#647C79] hover:bg-[#F1F6F5] hover:text-[#172B29]",
                        )}
                      >
                        <Paperclip className="h-3.5 w-3.5" />
                        {attachedDocIds.length > 0 ? (
                          <span className="text-[10px]">{attachedDocIds.length}</span>
                        ) : null}
                      </button>
                    </Tooltip>
                  </span>
                }
              >
                <DropdownMenuLabel>Đính kèm tài liệu ({workspaceDocuments.length})</DropdownMenuLabel>
                {workspaceDocuments.length === 0 ? (
                  <div className="px-2.5 py-2 text-xs text-[#647C79]">
                    Chưa có tài liệu trong không gian này.
                  </div>
                ) : (
                  workspaceDocuments.map((doc) => {
                    const isAttached = attachedDocIds.includes(doc.id)
                    return (
                      <DropdownMenuItem
                        key={doc.id}
                        icon={
                          <span
                            className={cn(
                              "flex h-3.5 w-3.5 items-center justify-center rounded border",
                              isAttached
                                ? "border-[#087F73] bg-[#087F73] text-white"
                                : "border-[#DCE7E4]",
                            )}
                          >
                            {isAttached ? <Check className="h-2.5 w-2.5 stroke-[3]" /> : null}
                          </span>
                        }
                        onClick={() => onToggleAttachDoc(doc.id)}
                        className="flex items-center justify-between gap-3"
                      >
                        <span
                          className={cn(
                            "truncate text-xs",
                            isAttached && "font-semibold text-[#087F73]",
                          )}
                        >
                          {doc.fileName}
                        </span>
                        <span className="shrink-0 text-[10.5px] text-[#647C79]">
                          {formatBytes(doc.fileSize)}
                        </span>
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
                        className="inline-flex h-6.5 items-center gap-1 rounded-md px-1.5 text-xs text-[#647C79] transition-colors hover:bg-[#F1F6F5] hover:text-[#172B29]"
                      >
                        <Cpu className="h-3.5 w-3.5" />
                        <span className="hidden font-mono text-[10.5px] sm:inline">
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
                      className="inline-flex h-6.5 items-center gap-1 rounded-md px-1.5 text-xs text-[#647C79] transition-colors hover:bg-[#F1F6F5] hover:text-[#172B29] sm:hidden"
                    >
                      <span className="text-[10.5px]">{getModeDescriptor(aiMode).label}</span>
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
                    className="h-7 text-xs"
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
                    className="inline-flex h-7 w-7 items-center justify-center rounded-lg bg-[#087F73] text-white transition-colors hover:bg-[#06665C] disabled:cursor-not-allowed disabled:bg-[#DCE7E4] disabled:text-[#647C79]"
                  >
                    <ArrowUp className="h-3.5 w-3.5" />
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
