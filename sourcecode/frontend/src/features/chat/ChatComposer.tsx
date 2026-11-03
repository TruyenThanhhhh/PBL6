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
  SlidersHorizontal,
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
      ? `${attachedDocs.length} tài liệu đã chọn`
      : selectedNotebook
        ? `Notebook: ${selectedNotebook.name}`
        : `Toàn bộ ${currentWorkspace?.name ?? "Workspace"} (${readyDocCount} tài liệu)`

  const attachTooltip =
    attachedDocIds.length > 0
      ? `Đính kèm tài liệu (${attachedDocIds.length} đã chọn)`
      : "Chọn tài liệu cụ thể để hỏi"

  const modelTooltip = `Mô hình trả lời: ${currentModelOption?.label ?? modelId}`

  return (
    <div className="border-t border-slate-200/80 bg-white px-4 pt-2.5 pb-4 md:px-8">
      <div className="mx-auto max-w-3xl">
        <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-[0_4px_20px_-4px_rgba(15,23,42,0.06)] transition-all focus-within:border-[#2563EB] focus-within:ring-2 focus-within:ring-[#2563EB]/12">
          {/* Thanh trạng thái trên: Chọn Phạm vi truy xuất & Chế độ truy xuất */}
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 bg-slate-50/70 px-3.5 py-1.5 text-xs">
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="text-[11px] font-medium text-slate-500">Phạm vi truy xuất:</span>

              <DropdownMenu
                align="start"
                trigger={
                  <button
                    type="button"
                    className="inline-flex items-center gap-1 rounded-lg border border-slate-200 bg-white px-2 py-0.5 text-[11px] font-semibold text-[#2563EB] transition-colors hover:bg-[#EFF6FF]"
                  >
                    <FolderOpen className="h-3 w-3" />
                    <span className="max-w-[220px] truncate">{scopeLabel}</span>
                    <ChevronDown className="h-3 w-3 text-slate-400" />
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
                  className="inline-flex items-center gap-1 rounded-lg border border-[#BFDBFE] bg-[#EFF6FF] px-2 py-0.5 text-[11px] font-medium text-slate-900"
                >
                  <FileText className="h-3 w-3 text-[#2563EB]" />
                  <span className="max-w-[140px] truncate">{doc.fileName}</span>
                  <button
                    type="button"
                    onClick={() => onToggleAttachDoc(doc.id)}
                    className="ml-0.5 text-slate-400 hover:text-slate-900"
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
                  className="text-[11px] text-slate-500 underline hover:text-slate-900"
                >
                  Bỏ chọn hết
                </button>
              ) : null}
            </div>

            {/* Menu chọn Chế độ truy xuất ngay tại thanh Composer */}
            {onModeChange ? (
              <DropdownMenu
                align="end"
                trigger={
                  <button
                    type="button"
                    className="inline-flex items-center gap-1 rounded-lg border border-slate-200 bg-white px-2 py-0.5 text-[11px] font-medium text-slate-700 transition-colors hover:border-[#2563EB]/50 hover:text-[#2563EB]"
                  >
                    <SlidersHorizontal className="h-3 w-3 text-[#2563EB]" />
                    <span>Chế độ: <strong>{getModeDescriptor(aiMode).label}</strong></span>
                    <ChevronDown className="h-3 w-3 text-slate-400" />
                  </button>
                }
              >
                <DropdownMenuLabel>Chế độ tìm kiếm &amp; RAG</DropdownMenuLabel>
                {(["auto", "local", "hybrid", "web"] as AIMode[]).map((m) => {
                  const desc = getModeDescriptor(m)
                  return (
                    <DropdownMenuItem
                      key={m}
                      shortcut={aiMode === m ? "Đang chọn" : undefined}
                      onClick={() => onModeChange(m)}
                    >
                      <div>
                        <div className="font-medium text-slate-900">{desc.label}</div>
                        <div className="text-[11px] text-slate-500">{desc.shortHint}</div>
                      </div>
                    </DropdownMenuItem>
                  )
                })}
              </DropdownMenu>
            ) : null}
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
              className="max-h-[180px] min-h-[42px] w-full resize-none border-0 bg-transparent py-1 text-sm leading-6 text-slate-900 placeholder:text-slate-400 focus:outline-none focus-visible:outline-none"
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
                            ? "bg-[#EFF6FF] font-semibold text-[#2563EB]"
                            : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"
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
                  <div className="px-2.5 py-2 text-xs text-slate-500">
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
                              ? "bg-[#EFF6FF] font-semibold text-[#2563EB]"
                              : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"
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
                        className="inline-flex h-7 items-center gap-1 rounded-lg px-2 text-xs text-slate-600 transition-colors hover:bg-slate-100 hover:text-slate-900"
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
                      <div className="font-medium text-slate-900">{m.label}</div>
                      <div className="text-[11px] text-slate-500">{m.description}</div>
                    </div>
                  </DropdownMenuItem>
                ))}
              </DropdownMenu>
            </div>

            <div className="flex items-center gap-2">
              {busy ? (
                <div className="flex items-center gap-1.5">
                  <Loader2 className="h-3.5 w-3.5 animate-spin text-[#2563EB]" />
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
                    className="inline-flex h-8 items-center gap-1.5 rounded-full bg-[#2563EB] px-4 text-xs font-semibold text-white shadow-2xs transition-colors hover:bg-[#1D4ED8] disabled:cursor-not-allowed disabled:opacity-40"
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
