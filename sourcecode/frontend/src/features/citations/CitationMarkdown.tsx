import { useState, type ReactNode } from "react"
import Markdown from "react-markdown"
import remarkGfm from "remark-gfm"
import { Check, Copy } from "lucide-react"
import { useAppStore } from "@/store/app-store"

function withCitationChips(text: string) {
  return text.replace(/\[(\d+)\]/g, (_m, n: string) => `[[cite:${n}]]`)
}

function CodeBlockWithCopy({
  language,
  codeText,
}: {
  language?: string
  codeText: string
}) {
  const [copied, setCopied] = useState(false)

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(codeText)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 1800)
    } catch {
      // Bỏ qua nếu trình duyệt chặn clipboard
    }
  }

  return (
    <div className="my-3 overflow-hidden rounded-lg border border-line bg-bg-secondary">
      <div className="flex items-center justify-between border-b border-line px-3 py-1.5 text-[11px] text-muted">
        <span className="font-mono uppercase">{language || "code"}</span>
        <button
          type="button"
          onClick={() => void handleCopy()}
          className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-xs text-muted transition-colors hover:bg-bg-hover hover:text-ink"
          aria-label="Sao chép đoạn mã"
        >
          {copied ? (
            <>
              <Check className="h-3 w-3 text-success" />
              <span className="text-success">Đã chép</span>
            </>
          ) : (
            <>
              <Copy className="h-3 w-3" />
              <span>Sao chép mã</span>
            </>
          )}
        </button>
      </div>
      <pre className="m-0 overflow-x-auto border-0 bg-transparent p-3 font-mono text-[13px] leading-relaxed text-ink">
        <code>{codeText}</code>
      </pre>
    </div>
  )
}

export function CitationMarkdown({ content }: { content: string }) {
  const setActive = useAppStore((s) => s.setActiveCitation)
  const prepared = withCitationChips(content)

  return (
    <div className="markdown-body text-[15px] leading-7 text-ink">
      <Markdown
        remarkPlugins={[remarkGfm]}
        components={{
          p({ children }) {
            return <p>{renderNodes(children, setActive)}</p>
          },
          li({ children }) {
            return <li>{renderNodes(children, setActive)}</li>
          },
          td({ children }) {
            return <td>{renderNodes(children, setActive)}</td>
          },
          table({ children }) {
            return (
              <div className="my-3 overflow-x-auto rounded-lg border border-line">
                <table className="m-0 w-full border-collapse text-sm">{children}</table>
              </div>
            )
          },
          code({ className, children }) {
            const raw = String(children ?? "").replace(/\n$/, "")
            const match = /language-(\w+)/.exec(className || "")
            const isBlock = Boolean(match) || raw.includes("\n")
            if (isBlock) {
              return <CodeBlockWithCopy language={match?.[1]} codeText={raw} />
            }
            return (
              <code className="rounded border border-line bg-bg-secondary px-1.5 py-0.5 font-mono text-[13px] text-ink">
                {children}
              </code>
            )
          },
          pre({ children }) {
            return <>{children}</>
          },
        }}
      >
        {prepared}
      </Markdown>
    </div>
  )
}

function renderNodes(children: ReactNode, setActive: (n: number) => void): ReactNode {
  return flatten(children).map((child, i) => {
    if (typeof child === "string") return replaceCites(child, setActive, i)
    return child
  })
}

function flatten(children: ReactNode): ReactNode[] {
  if (Array.isArray(children)) return children.flatMap(flatten)
  return [children]
}

function replaceCites(text: string, setActive: (n: number) => void, key: number) {
  const parts = text.split(/(\[\[cite:\d+\]\])/)
  return parts.map((part, i) => {
    const m = part.match(/\[\[cite:(\d+)\]\]/)
    if (!m) return <span key={`${key}-${i}`}>{part}</span>
    const n = Number(m[1])
    return (
      <button
        key={`${key}-${i}`}
        type="button"
        className="citation-chip"
        onClick={() => setActive(n)}
        aria-label={`Mở nguồn trích dẫn ${n}`}
      >
        {n}
      </button>
    )
  })
}
