import { useEffect, useMemo, useState } from "react"
import { useNavigate } from "react-router-dom"
import {
  BookOpen,
  FileText,
  FolderOpen,
  MessageSquare,
  Search,
  StickyNote,
  X,
} from "lucide-react"
import { useAppStore } from "@/store/app-store"
import type { SearchHit } from "@/types"

type GroupFilter = "all" | SearchHit["kind"]

const GROUP_LABELS: Record<SearchHit["kind"], string> = {
  workspace: "Workspace",
  notebook: "Notebook",
  document: "Tài liệu",
  note: "Ghi chú",
  conversation: "Hội thoại",
  research: "Nghiên cứu",
}

const GROUP_ICONS: Record<SearchHit["kind"], typeof FolderOpen> = {
  workspace: FolderOpen,
  notebook: BookOpen,
  document: FileText,
  note: StickyNote,
  conversation: MessageSquare,
  research: FileText,
}

export function GlobalSearch() {
  const [open, setOpen] = useState(false)
  const [q, setQ] = useState("")
  const [filter, setFilter] = useState<GroupFilter>("all")
  const [activeIndex, setActiveIndex] = useState(0)

  const navigate = useNavigate()
  const workspaces = useAppStore((s) => s.workspaces)
  const notebooks = useAppStore((s) => s.notebooks)
  const documents = useAppStore((s) => s.documents)
  const notes = useAppStore((s) => s.notes)
  const conversations = useAppStore((s) => s.conversations)
  const status = useAppStore((s) => s.status)

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault()
        setOpen((prev) => !prev)
      }
      if (e.key === "Escape") {
        setOpen(false)
      }
    }
    const onOpen = () => setOpen(true)
    window.addEventListener("keydown", onKey)
    window.addEventListener("open-search", onOpen)
    return () => {
      window.removeEventListener("keydown", onKey)
      window.removeEventListener("open-search", onOpen)
    }
  }, [])

  const hits = useMemo(() => {
    const query = q.trim().toLowerCase()
    const list: SearchHit[] = []

    // Khi chưa nhập từ khóa, hiển thị gợi ý truy cập nhanh các mục gần đây
    if (!query) {
      workspaces.slice(0, 2).forEach((w) => {
        list.push({
          id: w.id,
          kind: "workspace",
          title: w.name,
          snippet: w.description || "Không gian tri thức",
          path: `/knowledge/${w.id}`,
          trail: "Workspace",
        })
      })
      documents.slice(0, 3).forEach((d) => {
        list.push({
          id: d.id,
          kind: "document",
          title: d.fileName,
          snippet: `${d.fileType.toUpperCase()} · ${d.totalChunks} chunks`,
          path: `/documents/${d.id}`,
          trail: "Tài liệu",
        })
      })
      conversations.slice(0, 2).forEach((c) => {
        list.push({
          id: c.id,
          kind: "conversation",
          title: c.title,
          snippet: `${c.messages.length} tin nhắn`,
          path: `/chat/${c.id}`,
          trail: "Hội thoại",
        })
      })
      return filter === "all" ? list : list.filter((h) => h.kind === filter)
    }

    workspaces.forEach((w) => {
      if (w.name.toLowerCase().includes(query) || w.description.toLowerCase().includes(query)) {
        list.push({
          id: w.id,
          kind: "workspace",
          title: w.name,
          snippet: w.description || "Workspace",
          path: `/knowledge/${w.id}`,
          trail: "Workspace",
        })
      }
    })

    notebooks.forEach((n) => {
      if (n.name.toLowerCase().includes(query)) {
        const ws = workspaces.find((w) => w.id === n.workspaceId)
        list.push({
          id: n.id,
          kind: "notebook",
          title: n.name,
          snippet: ws ? `Thuộc ${ws.name}` : "Notebook",
          path: `/knowledge/${n.workspaceId}/notebooks/${n.id}`,
          trail: "Notebook",
        })
      }
    })

    documents.forEach((d) => {
      const nameMatch = d.fileName.toLowerCase().includes(query)
      const textMatch = d.extractedText.toLowerCase().includes(query)
      if (nameMatch || textMatch) {
        list.push({
          id: d.id,
          kind: "document",
          title: d.fileName,
          snippet: textMatch
            ? d.extractedText.slice(0, 110)
            : `${d.fileType.toUpperCase()} · Metadata tên tệp`,
          path: `/documents/${d.id}`,
          trail: "Tài liệu",
        })
      }
    })

    notes.forEach((n) => {
      if (n.title.toLowerCase().includes(query) || n.content.toLowerCase().includes(query)) {
        list.push({
          id: n.id,
          kind: "note",
          title: n.title,
          snippet: n.content.slice(0, 110) || "Ghi chú",
          path: `/study?tab=notes`,
          trail: "Ghi chú",
        })
      }
    })

    conversations.forEach((c) => {
      if (
        c.title.toLowerCase().includes(query) ||
        c.messages.some((m) => m.content.toLowerCase().includes(query))
      ) {
        list.push({
          id: c.id,
          kind: "conversation",
          title: c.title,
          snippet: c.messages.at(-1)?.content.slice(0, 110) ?? "Hội thoại AI",
          path: `/chat/${c.id}`,
          trail: "Hội thoại",
        })
      }
    })

    const filtered = filter === "all" ? list : list.filter((h) => h.kind === filter)
    return filtered.slice(0, 24)
  }, [q, filter, workspaces, notebooks, documents, notes, conversations])

  if (!open) return null

  const groups: SearchHit["kind"][] = [
    "workspace",
    "notebook",
    "document",
    "note",
    "conversation",
  ]

  const handleOpenHit = (hit: SearchHit) => {
    navigate(hit.path)
    setOpen(false)
    setQ("")
  }

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center p-4 pt-[10vh]">
      <button
        type="button"
        className="fixed inset-0 bg-ink/30"
        aria-label="Đóng tìm kiếm"
        onClick={() => setOpen(false)}
      />

      <div
        role="dialog"
        aria-modal="true"
        aria-label="Tìm kiếm toàn cục"
        className="relative z-10 w-full max-w-xl overflow-hidden rounded-xl border border-line bg-bg"
      >
        {/* Thanh nhập từ khóa */}
        <div className="flex items-center gap-2 border-b border-line px-3.5 py-2.5">
          <Search className="h-4 w-4 shrink-0 text-muted" />
          <input
            autoFocus
            value={q}
            onChange={(e) => {
              setQ(e.target.value)
              setActiveIndex(0)
            }}
            onKeyDown={(e) => {
              if (e.key === "ArrowDown") {
                e.preventDefault()
                setActiveIndex((i) => (hits.length ? (i + 1) % hits.length : 0))
              } else if (e.key === "ArrowUp") {
                e.preventDefault()
                setActiveIndex((i) =>
                  hits.length ? (i - 1 + hits.length) % hits.length : 0,
                )
              } else if (e.key === "Enter" && hits[activeIndex]) {
                e.preventDefault()
                handleOpenHit(hits[activeIndex])
              }
            }}
            placeholder="Tìm workspace, notebook, tài liệu, ghi chú, hội thoại..."
            className="w-full border-0 bg-transparent text-sm text-ink placeholder:text-muted focus:outline-none focus-visible:outline-none"
          />
          {q ? (
            <button
              type="button"
              onClick={() => setQ("")}
              className="rounded p-1 text-muted hover:text-ink"
              aria-label="Xóa từ khóa"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          ) : null}
          <kbd className="rounded border border-line bg-bg-secondary px-1.5 py-0.5 text-[10px] text-muted">
            Esc
          </kbd>
        </div>

        {/* Bộ lọc nhóm đối tượng */}
        <div className="flex gap-1 overflow-x-auto border-b border-line bg-bg-secondary/40 px-3 py-1.5 text-xs">
          {(["all", ...groups] as GroupFilter[]).map((g) => (
            <button
              key={g}
              type="button"
              onClick={() => {
                setFilter(g)
                setActiveIndex(0)
              }}
              className={`shrink-0 rounded px-2 py-0.5 transition-colors ${
                filter === g
                  ? "bg-bg-active font-medium text-ink"
                  : "text-muted hover:bg-bg-hover hover:text-ink"
              }`}
            >
              {g === "all" ? "Tất cả" : GROUP_LABELS[g]}
            </button>
          ))}
        </div>

        {/* Danh sách kết quả chia nhóm */}
        <div className="max-h-[52vh] overflow-y-auto p-2">
          {hits.length === 0 ? (
            <div className="py-10 text-center text-xs text-muted">
              Không tìm thấy kết quả phù hợp với &ldquo;{q}&rdquo;.
            </div>
          ) : (
            groups.map((g) => {
              const items = hits.filter((h) => h.kind === g)
              if (items.length === 0) return null
              const Icon = GROUP_ICONS[g]
              return (
                <div key={g} className="mb-2 last:mb-0">
                  <p className="px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide text-muted">
                    {GROUP_LABELS[g]}
                  </p>
                  {items.map((h) => {
                    const globalIdx = hits.findIndex(
                      (item) => item.kind === h.kind && item.id === h.id,
                    )
                    const isSelected = globalIdx === activeIndex
                    return (
                      <button
                        key={`${h.kind}-${h.id}`}
                        type="button"
                        onMouseEnter={() => setActiveIndex(globalIdx)}
                        onClick={() => handleOpenHit(h)}
                        className={`flex w-full items-center gap-2.5 rounded-md px-2.5 py-2 text-left transition-colors ${
                          isSelected ? "bg-bg-active text-ink" : "hover:bg-bg-hover"
                        }`}
                      >
                        <Icon className="h-4 w-4 shrink-0 text-muted" />
                        <div className="min-w-0 flex-1">
                          <p className="truncate text-[13px] font-medium text-ink">{h.title}</p>
                          <p className="truncate text-xs text-muted">{h.snippet}</p>
                        </div>
                        <span className="shrink-0 text-[11px] text-muted">{h.trail}</span>
                      </button>
                    )
                  })}
                </div>
              )
            })
          )}
        </div>

        {/* Ghi chú phạm vi tìm kiếm trung thực */}
        <div className="flex flex-wrap items-center justify-between gap-2 border-t border-line bg-bg-secondary/50 px-3.5 py-2 text-[11px] text-muted">
          <span>
            Phạm vi: Tìm trên metadata và văn bản đã trích xuất trong bộ nhớ trình duyệt
            {!status.backendOnline ? " (Dữ liệu mô phỏng cục bộ)" : ""}.
          </span>
          <span>↑↓ di chuyển · Enter mở</span>
        </div>
      </div>
    </div>
  )
}
