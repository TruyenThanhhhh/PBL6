import { useState } from "react"
import { ChevronDown, Download, FileCode2, FileText } from "lucide-react"
import { Button, DropdownMenu, DropdownMenuItem, type ButtonProps } from "@/components/ui"
import { useAppStore } from "@/store/app-store"
import {
  downloadExportedDocument,
  type ExportDocumentFormat,
} from "@/utils/export-document"

const EXPORT_FORMAT_OPTIONS: Array<{
  format: ExportDocumentFormat
  label: string
  extLabel: string
}> = [
  { format: "md", label: "Markdown", extLabel: ".md" },
  { format: "docx", label: "Word Document", extLabel: ".docx" },
  { format: "pdf", label: "PDF Document", extLabel: ".pdf" },
]

export function ExportFormatMenu({
  title,
  content,
  label = "Tải file",
  size = "sm",
  variant = "outline",
  align = "end",
  side = "bottom",
  disabled = false,
  className,
}: {
  title: string
  content: string
  label?: string
  size?: ButtonProps["size"]
  variant?: ButtonProps["variant"]
  align?: "start" | "end"
  side?: "bottom" | "top"
  disabled?: boolean
  className?: string
}) {
  const toast = useAppStore((s) => s.toast)
  const [exportingFormat, setExportingFormat] = useState<ExportDocumentFormat | null>(null)
  const isDisabled = disabled || !content.trim() || exportingFormat !== null

  const handleExport = async (format: ExportDocumentFormat) => {
    if (!content.trim() || exportingFormat !== null) return
    setExportingFormat(format)
    try {
      const filename = await downloadExportedDocument({ title, content, format })
      toast({
        title: `Đã tải xuống ${filename}`,
        tone: "success",
      })
    } catch (err) {
      const detail = err instanceof Error ? err.message : ""
      toast({
        title: `Không thể xuất định dạng .${format}`,
        description:
          detail || "Vui lòng kiểm tra kết nối backend hoặc chọn tải bản .md.",
        tone: "error",
      })
    } finally {
      setExportingFormat(null)
    }
  }

  const triggerButton = (
    <Button
      type="button"
      variant={variant}
      size={size}
      disabled={isDisabled}
      loading={exportingFormat !== null}
      leftIcon={<Download className="h-3.5 w-3.5" />}
      className={className}
    >
      <span>{exportingFormat ? `Đang xuất .${exportingFormat}...` : label}</span>
      <ChevronDown className="h-3 w-3 opacity-75" />
    </Button>
  )

  if (isDisabled) {
    return triggerButton
  }

  return (
    <DropdownMenu align={align} side={side} trigger={triggerButton}>
      {EXPORT_FORMAT_OPTIONS.map((opt) => (
        <DropdownMenuItem
          key={opt.format}
          icon={
            opt.format === "md" ? (
              <FileCode2 className="h-3.5 w-3.5 text-[#087F73]" />
            ) : (
              <FileText className="h-3.5 w-3.5 text-[#087F73]" />
            )
          }
          shortcut={opt.extLabel}
          onClick={() => void handleExport(opt.format)}
        >
          {opt.label}
        </DropdownMenuItem>
      ))}
    </DropdownMenu>
  )
}
