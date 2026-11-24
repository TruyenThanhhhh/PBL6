import { cloneElement, isValidElement, useState, type ReactNode } from "react"
import Markdown from "react-markdown"
import remarkGfm from "remark-gfm"
import { Check, Copy } from "lucide-react"
import { useAppStore } from "@/store/app-store"

function cleanMathDisplay(text: string): string {
  let res = text
    .replace(/\\boxed\{([^{}]+)\}/g, "**$1**")
    .replace(/\\text\{([^{}]+)\}/g, "$1")
    .replace(/\\(?:left|right)\b/g, "")

  for (let i = 0; i < 4; i++) {
    const prev = res
    res = res
      .replace(/\\sqrt\{([^{}]+)\}/g, (_m, inner: string) => {
        const clean = inner.trim()
        return /^[\w.,]+$/.test(clean) ? `√${clean}` : `√(${clean})`
      })
      .replace(/\\frac\{([^{}]+)\}\{([^{}]+)\}/g, (_m, num: string, den: string) => {
        const n = num.trim()
        const d = den.trim()
        const nFmt = /^[\w.()√π]+$/.test(n) ? n : `(${n})`
        const dFmt = /^[\w.()√π]+$/.test(d) ? d : `(${d})`
        return `${nFmt}/${dFmt}`
      })
    if (res === prev) break
  }

  return res
    .replace(/\\times/g, "×")
    .replace(/\\cdot/g, "·")
    .replace(/\\%/g, "%")
    .replace(/\\pi/g, "π")
    .replace(/\\approx/g, "≈")
    .replace(/\\pm/g, "±")
    .replace(/\\leq?/g, "≤")
    .replace(/\\geq?/g, "≥")
    .replace(/\\neq?/g, "≠")
    .replace(/\\Delta/g, "Δ")
    .replace(/\\alpha/g, "α")
    .replace(/\\beta/g, "β")
    .replace(/\\Leftrightarrow/g, "⇔")
    .replace(/\\Rightarrow/g, "⇒")
    .replace(/\\rightarrow/g, "→")
    .replace(/\\infty/g, "∞")
    .replace(/\\arctan/g, "arctan")
    .replace(/\\arcsin/g, "arcsin")
    .replace(/\\arccos/g, "arccos")
    .replace(/\\sin/g, "sin")
    .replace(/\\cos/g, "cos")
    .replace(/\\tan/g, "tan")
    .replace(/\\cot/g, "cot")
    .replace(/\\in\b/g, "∈")
    .replace(/\\perp/g, "⊥")
    .replace(/\\\((.*?)\\\)/gs, (_m, inner: string) => inner.trim())
    .replace(/\\\[(.*?)\\\]/gs, (_m, inner: string) => `\n\n> **${inner.trim()}**\n\n`)
    .replace(/\b(sin|cos|tan|cot|arcsin|arccos|arctan|log)\s*\{([^{}]+)\}/g, "$1($2)")
    .replace(/\{([A-Za-z0-9αβγθΔπ]{1,3})\}/g, "$1")
    .replace(/\^\{2\}|\^2(?![0-9])/g, "²")
    .replace(/\^\{3\}|\^3(?![0-9])/g, "³")
    .replace(/\^\{([^}]+)\}/g, "^$1")
    .replace(/(?<=[a-zA-Z])_\{([0-9]+)\}|(?<=[a-zA-Z])_([0-9])(?![0-9])/g, (_m, g1?: string, g2?: string) => {
      const subMap: Record<string, string> = { "0": "₀", "1": "₁", "2": "₂", "3": "₃", "4": "₄", "5": "₅", "6": "₆", "7": "₇", "8": "₈", "9": "₉" }
      const raw = g1 || g2 || ""
      return raw.split("").map((ch) => subMap[ch] ?? ch).join("")
    })
    .replace(/_\{([^}]+)\}/g, "($1)")
    .replace(/\(\s+([^()\n]{2,80}?)\s+\)/g, "($1)")
}

function withCitationChips(text: string) {
  // Gỡ heading rỗng kiểu '### **[1]' hoặc '**[1]' chưa đóng trước khi chuyển chip trích dẫn
  const normalizedHeading = text
    .replace(/^#{1,4}\s*\*{0,2}\s*\[(?:Tài liệu |Nguồn(?:\s*web)? |Web )?(\d{1,3})\]\*{0,2}\s*$/gim, "")
    .replace(/^(\*{1,2})\[(\d{1,3})\](?!\*{1,2})\s*$/gm, "[$2]")
  // Làm sạch ký hiệu LaTeX thô và các biến thể trích dẫn lồng tên file từ LLM nhỏ
  const cleaned = cleanMathDisplay(normalizedHeading)
    .replace(/"?\[\s*(?:Tài liệu|Nguồn(?:\s*web)?|Web)\s*\[?\s*(\d{1,3})\s*\]?\s*\]?\s*:\s*[^\]\n"]{2,180}\]?"?/gi, "[[cite:$1]]")
    .replace(/"?\[\s*(?:Tài liệu|Nguồn(?:\s*web)?|Web)\s*\[?\s*(\d{1,3})\s*\]?\s*\]?"?/gi, "[[cite:$1]]")
  return cleaned.replace(/\[(\d{1,3})\]/g, (_m, n: string) => `[[cite:${n}]]`)
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
          h1({ children }) {
            return <h1>{renderNodes(children, setActive)}</h1>
          },
          h2({ children }) {
            return <h2>{renderNodes(children, setActive)}</h2>
          },
          h3({ children }) {
            return <h3>{renderNodes(children, setActive)}</h3>
          },
          h4({ children }) {
            return <h4>{renderNodes(children, setActive)}</h4>
          },
          strong({ children }) {
            return <strong>{renderNodes(children, setActive)}</strong>
          },
          em({ children }) {
            return <em>{renderNodes(children, setActive)}</em>
          },
          blockquote({ children }) {
            return <blockquote>{renderNodes(children, setActive)}</blockquote>
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
    if (isValidElement<{ children?: ReactNode }>(child) && child.props?.children !== undefined) {
      return cloneElement(child, { key: child.key ?? `el-${i}` }, renderNodes(child.props.children, setActive))
    }
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
        onClick={() => {
          setActive(n)
          window.dispatchEvent(new CustomEvent("studio-context-tab", { detail: "citations" }))
        }}
        aria-label={`Mở nguồn trích dẫn ${n}`}
      >
        {n}
      </button>
    )
  })
}
