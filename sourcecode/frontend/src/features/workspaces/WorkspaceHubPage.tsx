import { useEffect, useMemo, useRef, useState } from "react"
import { useNavigate } from "react-router-dom"
import {
  Activity,
  ArrowUpDown,
  ArrowUpRight,
  Bot,
  BrainCircuit,
  ChevronDown,
  ChevronRight,
  Database,
  FileCheck2,
  FileText,
  Files,
  FolderKanban,
  FolderPlus,
  Folders,
  Languages,
  Layers,
  MessageSquare,
  Moon,
  MoreHorizontal,
  Pencil,
  Plus,
  Search,
  Shield,
  ShieldCheck,
  Sliders,
  Sun,
  Trash2,
  UploadCloud,
} from "lucide-react"
import { ConfirmDialog, NameDialog } from "@/components/common/NameDialog"
import {
  Button,
  Dialog,
  DropdownMenu,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  FormField,
  Input,
  Select,
} from "@/components/ui"
import { useAppStore } from "@/store/app-store"
import { formatBytes, greeting, relativeTime } from "@/utils/format"
import { hasDuplicateName } from "@/features/workspaces/workspace-utils"
import type { Workspace } from "@/types"
import { cn } from "@/utils/cn"

const CATEGORIES = [
  "Tất cả",
  "Đại học",
  "Nghiên cứu",
  "Kỹ thuật",
  "Ngoại ngữ",
  "Dự án",
  "Cá nhân",
] as const

type CategoryType = (typeof CATEGORIES)[number]

type SortOption = "updated" | "name" | "documents"

function getCategoryMeta(category?: string) {
  switch (category) {
    case "Đại học":
      return {
        label: "Đại học",
        badgeClass: "text-teal-700 bg-teal-50",
        iconBoxClass: "bg-teal-50 border-teal-100 text-teal-700",
        hoverTitleClass: "group-hover:text-teal-800",
        hoverLinkClass: "hover:text-teal-700",
        Icon: ShieldCheck,
      }
    case "Kỹ thuật":
      return {
        label: "Kỹ thuật",
        badgeClass: "text-cyan-700 bg-cyan-50",
        iconBoxClass: "bg-cyan-50 border-cyan-100 text-cyan-700",
        hoverTitleClass: "group-hover:text-cyan-800",
        hoverLinkClass: "hover:text-cyan-700",
        Icon: Activity,
      }
    case "Ngoại ngữ":
      return {
        label: "Ngoại ngữ",
        badgeClass: "text-amber-700 bg-amber-50",
        iconBoxClass: "bg-amber-50 border-amber-100 text-amber-700",
        hoverTitleClass: "group-hover:text-amber-800",
        hoverLinkClass: "hover:text-amber-700",
        Icon: Languages,
      }
    case "Nghiên cứu":
      return {
        label: "Nghiên cứu",
        badgeClass: "text-indigo-700 bg-indigo-50",
        iconBoxClass: "bg-indigo-50 border-indigo-100 text-indigo-700",
        hoverTitleClass: "group-hover:text-indigo-800",
        hoverLinkClass: "hover:text-indigo-700",
        Icon: Bot,
      }
    case "Dự án":
      return {
        label: "Dự án",
        badgeClass: "text-emerald-700 bg-emerald-50",
        iconBoxClass: "bg-emerald-50 border-emerald-100 text-emerald-700",
        hoverTitleClass: "group-hover:text-emerald-800",
        hoverLinkClass: "hover:text-emerald-700",
        Icon: FolderKanban,
      }
    default:
      return {
        label: category || "Cá nhân",
        badgeClass: "text-brand-700 bg-brand-50",
        iconBoxClass: "bg-brand-50 border-brand-100 text-brand-700",
        hoverTitleClass: "group-hover:text-brand-800",
        hoverLinkClass: "hover:text-brand-700",
        Icon: Folders,
      }
  }
}

export function WorkspaceHubPage() {
  const navigate = useNavigate()
  const searchInputRef = useRef<HTMLInputElement>(null)

  const workspaces = useAppStore((s) => s.workspaces)
  const documents = useAppStore((s) => s.documents)
  const conversations = useAppStore((s) => s.conversations)
  const currentWorkspaceId = useAppStore((s) => s.currentWorkspaceId)
  const setCurrent = useAppStore((s) => s.setCurrentWorkspace)
  const createWorkspace = useAppStore((s) => s.createWorkspace)
  const updateWorkspace = useAppStore((s) => s.updateWorkspace)
  const deleteWorkspace = useAppStore((s) => s.deleteWorkspace)
  const createConversation = useAppStore((s) => s.createConversation)
  const status = useAppStore((s) => s.status)
  const theme = useAppStore((s) => s.theme)
  const setTheme = useAppStore((s) => s.setTheme)
  const localLlmModel = useAppStore((s) => s.localLlmModel)
  const toast = useAppStore((s) => s.toast)

  // Filters & Search
  const [searchQuery, setSearchQuery] = useState("")
  const [selectedCategory, setSelectedCategory] = useState<CategoryType>("Tất cả")
  const [sortOption, setSortOption] = useState<SortOption>("updated")

  // Dialogs
  const [createOpen, setCreateOpen] = useState(false)
  const [createCategory, setCreateCategory] = useState<string>("Dự án")
  const [editTarget, setEditTarget] = useState<Workspace | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<Workspace | null>(null)
  const [quickUploadOpen, setQuickUploadOpen] = useState(false)
  const [uploadTargetWs, setUploadTargetWs] = useState<string>(
    currentWorkspaceId || workspaces[0]?.id || "",
  )

  // ⌘K shortcut to focus search
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault()
        searchInputRef.current?.focus()
      }
    }
    window.addEventListener("keydown", onKeyDown)
    return () => window.removeEventListener("keydown", onKeyDown)
  }, [])

  // Calculate Metrics
  const totalDocs = documents.length
  const readyDocs = documents.filter((d) => d.status === "ready").length
  const groundedPct = totalDocs > 0 ? Math.round((readyDocs / totalDocs) * 100) : 100

  const totalChunks = useMemo(
    () => documents.reduce((acc, d) => acc + (d.totalChunks || 0), 0),
    [documents],
  )
  const formattedChunks = totalChunks >= 1000 ? `${(totalChunks / 1000).toFixed(1)}k` : `${totalChunks}`

  const totalSizeBytes = useMemo(
    () => documents.reduce((acc, d) => acc + (d.fileSize || 0), 0),
    [documents],
  )
  const totalSizeDisplay = formatBytes(totalSizeBytes)
  // Assume 8 GB quota for display
  const offlineMaxBytes = 8 * 1024 * 1024 * 1024
  const offlinePct = Math.min(Math.round((totalSizeBytes / offlineMaxBytes) * 100), 100)

  // Filtered and Sorted Workspaces
  const filteredWorkspaces = useMemo(() => {
    const q = searchQuery.trim().toLowerCase()
    const list = workspaces.filter((w) => {
      if (selectedCategory !== "Tất cả") {
        const cat = w.category || "Cá nhân"
        if (cat !== selectedCategory) return false
      }
      if (q) {
        const matchName = w.name.toLowerCase().includes(q)
        const matchDesc = (w.description || "").toLowerCase().includes(q)
        if (!matchName && !matchDesc) return false
      }
      return true
    })

    return [...list].sort((a, b) => {
      if (sortOption === "name") {
        return a.name.localeCompare(b.name, "vi")
      }
      if (sortOption === "documents") {
        const aDocs = documents.filter((d) => d.workspaceId === a.id).length
        const bDocs = documents.filter((d) => d.workspaceId === b.id).length
        return bDocs - aDocs
      }
      return b.updatedAt.localeCompare(a.updatedAt)
    })
  }, [workspaces, searchQuery, selectedCategory, sortOption, documents])

  // Actions
  const handleEnterWorkspace = (w: Workspace, toChat = false) => {
    setCurrent(w.id)
    toast({
      title: "Đã chọn không gian làm việc",
      description: w.name,
      tone: "info",
    })
    if (toChat) {
      const convInWs = conversations.find((c) => c.workspaceId === w.id)
      if (convInWs) {
        navigate(`/chat/${convInWs.id}`)
      } else {
        const newConv = createConversation(w.id)
        navigate(`/chat/${newConv.id}`)
      }
    } else {
      navigate("/dashboard")
    }
  }

  const handleStartPrimaryChat = () => {
    const activeWs = workspaces.find((w) => w.id === currentWorkspaceId) ?? workspaces[0]
    if (!activeWs) return
    handleEnterWorkspace(activeWs, true)
  }

  const validateWorkspaceName = (exceptId?: string) => (name: string) =>
    hasDuplicateName(
      workspaces.filter((w) => w.id !== exceptId).map((w) => w.name),
      name,
    )
      ? "Đã có không gian cùng tên."
      : null

  return (
    <div className="flex min-h-screen flex-col bg-canvas text-stone-800 antialiased selection:bg-brand-200 selection:text-brand-900">
      {/* 1. Global Header */}
      <header
        className="sticky top-0 z-50 border-b border-stone-200/70 glass-nav"
        data-purpose="global-header"
      >
        <div className="mx-auto flex h-14 max-w-7xl items-center justify-between px-6">
          {/* Logo */}
          <div className="flex items-center">
            <button
              type="button"
              onClick={() => navigate("/hub")}
              className="group flex items-center gap-2 text-left"
              aria-label="Về trang Hub"
            >
              <div className="flex h-8 w-8 items-center justify-center rounded-lg border border-brand-500/20 bg-brand-500/10 text-brand-600 transition-all duration-300 group-hover:bg-brand-500 group-hover:text-white">
                <svg
                  fill="none"
                  height="18"
                  stroke="currentColor"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth="2.2"
                  viewBox="0 0 24 24"
                  width="18"
                  aria-hidden="true"
                >
                  <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83" />
                  <circle cx="12" cy="12" r="3" />
                </svg>
              </div>
              <div className="flex items-baseline">
                <span className="font-sans text-xl font-bold tracking-tight text-stone-900">motivo</span>
                <span className="ml-0.5 font-editorial-serif text-base font-medium text-brand-600">.rag</span>
              </div>
            </button>
          </div>

          {/* Navigation Links */}
          <nav className="hidden items-center gap-1.5 text-xs font-medium text-stone-600 md:flex">
            <button
              type="button"
              onClick={() => navigate("/hub")}
              className="flex items-center gap-1.5 rounded-full bg-stone-100 px-3 py-1.5 font-semibold text-stone-900 shadow-2xs"
            >
              <FolderKanban className="h-3.5 w-3.5 text-brand-600" />
              <span>Workspaces</span>
            </button>

            <button
              type="button"
              onClick={() => navigate("/documents")}
              className="flex items-center gap-1.5 rounded-full px-3 py-1.5 transition-colors hover:bg-stone-100/70 hover:text-stone-900"
            >
              <Files className="h-3.5 w-3.5 text-stone-400" />
              <span>Tài liệu &amp; Nguồn</span>
            </button>

            <DropdownMenu
              align="start"
              trigger={
                <button
                  type="button"
                  className="flex items-center gap-1 rounded-full px-3 py-1.5 text-stone-600 transition-colors hover:bg-stone-100/70 hover:text-stone-900"
                >
                  <Sliders className="h-3.5 w-3.5 text-stone-400" />
                  <span>Hệ thống</span>
                  <ChevronDown className="h-3 w-3 text-stone-400" />
                </button>
              }
            >
              <DropdownMenuLabel>Tùy chọn hệ thống</DropdownMenuLabel>
              <DropdownMenuItem
                icon={<Activity className="h-3.5 w-3.5" />}
                onClick={() => navigate("/settings?section=status")}
              >
                Trạng thái hệ thống &amp; AI
              </DropdownMenuItem>
              <DropdownMenuItem
                icon={<Sliders className="h-3.5 w-3.5" />}
                onClick={() => navigate("/settings")}
              >
                Cài đặt mô hình LLM &amp; RAG
              </DropdownMenuItem>
              <DropdownMenuItem
                icon={<Layers className="h-3.5 w-3.5" />}
                onClick={() => navigate("/design-system")}
              >
                Giao diện &amp; Design System
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem
                icon={theme === "dark" ? <Sun className="h-3.5 w-3.5" /> : <Moon className="h-3.5 w-3.5" />}
                onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
              >
                {theme === "dark" ? "Chuyển sang giao diện sáng" : "Chuyển sang giao diện tối"}
              </DropdownMenuItem>
            </DropdownMenu>
          </nav>

          {/* Right Header Status & Controls */}
          <div className="flex items-center gap-3 md:gap-4">
            {/* Ollama Status Pill */}
            <div className="hidden items-center gap-1.5 rounded-full border border-stone-200/60 bg-stone-100/80 px-2.5 py-1 text-xs font-medium text-stone-600 lg:flex">
              <span className="relative flex h-2 w-2">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
                <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-500" />
              </span>
              <span className="text-[11px] text-stone-500">Ollama:</span>
              <span className="font-mono text-[11px] font-normal text-stone-800">
                {status.ollamaModels[0] || localLlmModel || "Llama-3.1 8B"}
              </span>
            </div>

            <div className="hidden h-4 w-px bg-stone-200 sm:block" />

            {/* Actions: + New Workspace & Profile */}
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => setCreateOpen(true)}
                className="inline-flex items-center gap-1.5 rounded-full bg-stone-900 px-3.5 py-1.5 text-xs font-medium text-white shadow-sm transition-all duration-200 hover:bg-brand-900"
              >
                <Plus className="h-3.5 w-3.5 stroke-[2.5]" />
                <span>Workspace mới</span>
              </button>

              <DropdownMenu
                align="end"
                trigger={
                  <button
                    type="button"
                    className="flex items-center gap-1.5 rounded-full border border-stone-200/60 p-0.5 pl-1 transition-colors hover:bg-stone-100"
                    title="Hồ sơ người dùng"
                  >
                    <div className="flex h-6 w-6 items-center justify-center rounded-full bg-stone-200 text-[10px] font-bold text-stone-700 ring-1 ring-white">
                      SM
                    </div>
                    <span className="hidden pr-1.5 text-xs font-medium text-stone-700 sm:inline">
                      Sophie
                    </span>
                  </button>
                }
              >
                <DropdownMenuLabel>Tài khoản cá nhân</DropdownMenuLabel>
                <DropdownMenuItem
                  icon={<Sliders className="h-3.5 w-3.5" />}
                  onClick={() => navigate("/settings")}
                >
                  Cài đặt tài khoản
                </DropdownMenuItem>
                <DropdownMenuItem
                  icon={theme === "dark" ? <Sun className="h-3.5 w-3.5" /> : <Moon className="h-3.5 w-3.5" />}
                  onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
                >
                  {theme === "dark" ? "Giao diện sáng" : "Giao diện tối"}
                </DropdownMenuItem>
              </DropdownMenu>
            </div>
          </div>
        </div>
      </header>

      {/* 2. Main Content */}
      <main
        className="mx-auto w-full max-w-7xl flex-1 space-y-8 px-6 py-6"
        data-purpose="workspace-hub-main"
      >
        {/* Hero Section */}
        <section
          className="flex flex-col justify-between gap-4 pb-2 sm:flex-row sm:items-center"
          data-purpose="welcome-and-search"
        >
          <div>
            <h1 className="font-editorial-serif text-3xl font-medium tracking-tight text-stone-950 md:text-4xl">
              {greeting()}, <span className="font-normal italic text-brand-700">Sophie</span> 👋
            </h1>
            <p className="mt-1 text-sm font-light text-stone-500">
              Tiếp tục khám phá kho tri thức của bạn.
            </p>
          </div>

          <div className="flex items-center gap-2.5">
            <button
              type="button"
              onClick={() => {
                if (workspaces[0]) setUploadTargetWs(currentWorkspaceId || workspaces[0].id)
                setQuickUploadOpen(true)
              }}
              className="inline-flex items-center gap-1.5 rounded-full border border-stone-200 bg-white px-3.5 py-2 text-xs font-medium text-stone-700 shadow-sm transition hover:bg-stone-50"
            >
              <UploadCloud className="h-3.5 w-3.5 text-stone-500" />
              <span>Nhập tài liệu</span>
            </button>

            <button
              type="button"
              onClick={handleStartPrimaryChat}
              className="group inline-flex items-center gap-1.5 rounded-full bg-stone-950 px-4 py-2 text-xs font-medium text-white shadow-sm transition hover:bg-brand-900"
            >
              <span>Mở Chatbot RAG</span>
              <ArrowUpRight className="h-3.5 w-3.5 transition-transform group-hover:-translate-y-0.5 group-hover:translate-x-0.5" />
            </button>
          </div>
        </section>

        {/* Quick Metrics Section */}
        <section
          className="grid grid-cols-2 gap-3.5 md:gap-4 lg:grid-cols-4"
          data-purpose="metrics-dashboard"
        >
          {/* Metric 1: Tổng số Workspace */}
          <div className="flex flex-col justify-between rounded-2xl border border-stone-200/70 bg-white p-4 shadow-sm transition-all duration-300 hover:shadow-soft">
            <div className="mb-2 flex items-center justify-between">
              <span className="text-[11px] font-semibold uppercase tracking-wider text-stone-500">
                Workspace
              </span>
              <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-brand-50 text-brand-600">
                <Folders className="h-3.5 w-3.5" />
              </div>
            </div>
            <div className="flex items-baseline gap-2">
              <span className="font-sans text-2xl font-bold tracking-tight text-stone-900">
                {workspaces.length}
              </span>
              <span className="rounded-full bg-brand-50 px-1.5 py-0.5 text-[10px] font-semibold text-brand-700">
                Active
              </span>
            </div>
            <p className="mt-2 text-[11px] text-stone-400">Theo dự án &amp; môn học</p>
          </div>

          {/* Metric 2: Tài liệu đã học & chỉ mục */}
          <div className="flex flex-col justify-between rounded-2xl border border-stone-200/70 bg-white p-4 shadow-sm transition-all duration-300 hover:shadow-soft">
            <div className="mb-2 flex items-center justify-between">
              <span className="text-[11px] font-semibold uppercase tracking-wider text-stone-500">
                Tài liệu đã học
              </span>
              <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-emerald-50 text-emerald-600">
                <FileCheck2 className="h-3.5 w-3.5" />
              </div>
            </div>
            <div className="flex items-baseline gap-2">
              <span className="font-sans text-2xl font-bold tracking-tight text-stone-900">
                {totalDocs}
              </span>
              <span className="rounded-full bg-emerald-50 px-1.5 py-0.5 text-[10px] font-semibold text-emerald-700">
                {groundedPct}% Grounded
              </span>
            </div>
            <p className="mt-2 text-[11px] text-stone-400">PDF, Web, Markdown</p>
          </div>

          {/* Metric 3: Đoạn trích tri thức */}
          <div className="flex flex-col justify-between rounded-2xl border border-stone-200/70 bg-white p-4 shadow-sm transition-all duration-300 hover:shadow-soft">
            <div className="mb-2 flex items-center justify-between">
              <span className="text-[11px] font-semibold uppercase tracking-wider text-stone-500">
                Đoạn trích tri thức
              </span>
              <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-teal-50 text-teal-600">
                <BrainCircuit className="h-3.5 w-3.5" />
              </div>
            </div>
            <div className="flex items-baseline gap-2">
              <span className="font-sans text-2xl font-bold tracking-tight text-stone-900">
                {formattedChunks}
              </span>
              <span className="rounded-full bg-teal-50 px-1.5 py-0.5 text-[10px] font-medium text-teal-700">
                Sẵn sàng
              </span>
            </div>
            <p className="mt-2 text-[11px] text-stone-400">Trích dẫn chuẩn dòng</p>
          </div>

          {/* Metric 4: Bộ nhớ tri thức Offline */}
          <div className="flex flex-col justify-between rounded-2xl border border-stone-200/70 bg-white p-4 shadow-sm transition-all duration-300 hover:shadow-soft">
            <div className="mb-2 flex items-center justify-between">
              <span className="text-[11px] font-semibold uppercase tracking-wider text-stone-500">
                Bộ nhớ Offline
              </span>
              <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-amber-50 text-amber-600">
                <Shield className="h-3.5 w-3.5" />
              </div>
            </div>
            <div className="flex items-baseline gap-2">
              <span className="font-sans text-2xl font-bold tracking-tight text-stone-900">
                {totalSizeDisplay}
              </span>
              <span className="text-[11px] text-stone-400">/ 8 GB ({offlinePct}%)</span>
            </div>
            <div className="mt-2 h-1 w-full overflow-hidden rounded-full bg-stone-100">
              <div
                className="h-1 rounded-full bg-brand-500 transition-all duration-500"
                style={{ width: `${Math.max(offlinePct, 4)}%` }}
              />
            </div>
          </div>
        </section>

        {/* Workspace Grid Section */}
        <section className="space-y-5" data-purpose="workspace-list-view">
          {/* Section Header */}
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2.5">
                <h2 className="font-editorial-serif text-xl font-medium text-stone-900">
                  Không gian làm việc gần đây
                </h2>
                <span className="rounded-full bg-stone-200/80 px-2 py-0.5 text-xs font-medium text-stone-700">
                  {filteredWorkspaces.length} mục
                </span>
              </div>
            </div>

            {/* Search & Filter Toolbar */}
            <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-center">
              {/* Compact Search Bar */}
              <div className="relative flex max-w-md flex-1 items-center gap-2 rounded-xl border border-stone-200/80 bg-white px-3 py-1.5 shadow-sm transition-all focus-within:border-brand-500 focus-within:ring-2 focus-within:ring-brand-500/20">
                <Search className="h-4 w-4 shrink-0 text-stone-400" />
                <input
                  ref={searchInputRef}
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="w-full border-none bg-transparent py-1 font-sans text-xs text-stone-800 placeholder-stone-400 outline-none focus:ring-0"
                  placeholder="Tìm kiếm Workspace... (⌘K)"
                  type="text"
                />
                <div className="hidden items-center gap-1 pl-1 text-[10px] font-medium text-stone-400 sm:flex">
                  <kbd className="rounded border border-stone-200 bg-stone-100 px-1.5 py-0.5 font-mono text-[10px] text-stone-600">
                    ⌘K
                  </kbd>
                </div>
              </div>

              {/* Filter Pills & Sorting */}
              <div className="flex flex-wrap items-center gap-2.5 sm:flex-nowrap">
                <div className="flex flex-wrap items-center rounded-full bg-stone-100/90 p-0.5 text-xs font-medium text-stone-600">
                  {CATEGORIES.map((cat) => {
                    const active = selectedCategory === cat
                    return (
                      <button
                        key={cat}
                        type="button"
                        onClick={() => setSelectedCategory(cat)}
                        className={cn(
                          "rounded-full px-3 py-1 transition-all",
                          active
                            ? "bg-white text-stone-900 shadow-sm"
                            : "hover:text-stone-900",
                        )}
                      >
                        {cat}
                      </button>
                    )
                  })}
                </div>

                {/* Sort Option */}
                <DropdownMenu
                  align="end"
                  trigger={
                    <button
                      type="button"
                      className="flex cursor-pointer items-center gap-1 rounded-full border border-stone-200 bg-white px-2.5 py-1.5 text-xs text-stone-500 hover:bg-stone-50"
                    >
                      <ArrowUpDown className="h-3.5 w-3.5" />
                      <span>
                        {sortOption === "updated"
                          ? "Cập nhật gần nhất"
                          : sortOption === "name"
                            ? "Tên A-Z"
                            : "Số tài liệu"}
                      </span>
                    </button>
                  }
                >
                  <DropdownMenuItem onClick={() => setSortOption("updated")}>
                    Cập nhật gần nhất
                  </DropdownMenuItem>
                  <DropdownMenuItem onClick={() => setSortOption("name")}>
                    Tên A-Z
                  </DropdownMenuItem>
                  <DropdownMenuItem onClick={() => setSortOption("documents")}>
                    Nhiều tài liệu nhất
                  </DropdownMenuItem>
                </DropdownMenu>
              </div>
            </div>
          </div>

          {/* Grid Cards */}
          <div className="grid grid-cols-1 gap-5 md:grid-cols-2 lg:grid-cols-3">
            {filteredWorkspaces.map((w) => {
              const meta = getCategoryMeta(w.category)
              const wsDocs = documents.filter((d) => d.workspaceId === w.id)
              const docCount = wsDocs.length
              const chunkCount = wsDocs.reduce((acc, d) => acc + (d.totalChunks || 0), 0)
              const sizeBytes = wsDocs.reduce((acc, d) => acc + (d.fileSize || 0), 0)
              const sizeDisplay = sizeBytes > 0 ? formatBytes(sizeBytes) : "0 MB"

              return (
                <article
                  key={w.id}
                  className="group flex flex-col justify-between rounded-2xl border border-stone-200/80 bg-white p-5 shadow-sm transition-all duration-300 hover:-translate-y-0.5 hover:shadow-hover"
                >
                  <div className="space-y-3">
                    {/* Card Top: Icon, Category & Actions */}
                    <div className="flex items-start justify-between">
                      <div className="flex items-center gap-2.5">
                        <div
                          className={cn(
                            "flex h-10 w-10 items-center justify-center rounded-xl border transition-transform group-hover:scale-105",
                            meta.iconBoxClass,
                          )}
                        >
                          <meta.Icon className="h-5 w-5" />
                        </div>
                        <div>
                          <span
                            className={cn(
                              "rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider",
                              meta.badgeClass,
                            )}
                          >
                            {meta.label}
                          </span>
                          <span className="mt-0.5 block text-xs text-stone-400">
                            {relativeTime(w.updatedAt)}
                          </span>
                        </div>
                      </div>

                      <DropdownMenu
                        align="end"
                        trigger={
                          <button
                            type="button"
                            className="rounded-full p-1 text-stone-400 transition hover:bg-stone-50 hover:text-stone-700"
                            title="Tùy chọn"
                            aria-label={`Tùy chọn cho ${w.name}`}
                          >
                            <MoreHorizontal className="h-4 w-4" />
                          </button>
                        }
                      >
                        <DropdownMenuItem
                          icon={<FolderKanban className="h-3.5 w-3.5" />}
                          onClick={() => handleEnterWorkspace(w, false)}
                        >
                          Mở Workspace
                        </DropdownMenuItem>
                        <DropdownMenuItem
                          icon={<MessageSquare className="h-3.5 w-3.5" />}
                          onClick={() => handleEnterWorkspace(w, true)}
                        >
                          Hỏi đáp AI trong workspace
                        </DropdownMenuItem>
                        <DropdownMenuItem
                          icon={<Pencil className="h-3.5 w-3.5" />}
                          onClick={() => setEditTarget(w)}
                        >
                          Đổi tên &amp; mô tả
                        </DropdownMenuItem>
                        <DropdownMenuSeparator />
                        <DropdownMenuItem
                          tone="danger"
                          icon={<Trash2 className="h-3.5 w-3.5" />}
                          onClick={() => setDeleteTarget(w)}
                        >
                          Xóa workspace
                        </DropdownMenuItem>
                      </DropdownMenu>
                    </div>

                    {/* Card Title & Description */}
                    <div>
                      <button
                        type="button"
                        onClick={() => handleEnterWorkspace(w, false)}
                        className={cn(
                          "text-left text-base font-semibold text-stone-900 transition",
                          meta.hoverTitleClass,
                        )}
                      >
                        {w.name}
                      </button>
                      <p className="mt-1 line-clamp-2 text-xs leading-relaxed text-stone-500">
                        {w.description || "Không gian làm việc với tài liệu và trợ lý RAG cá nhân."}
                      </p>
                    </div>

                    {/* Stats pills */}
                    <div className="flex flex-wrap gap-2 pt-1 text-xs text-stone-600">
                      <span className="inline-flex items-center gap-1 rounded-md bg-stone-100/90 px-2 py-0.5 text-[11px]">
                        <FileText className="h-3 w-3 text-stone-400" />
                        <span>{docCount} tài liệu</span>
                      </span>
                      <span className="inline-flex items-center gap-1 rounded-md bg-stone-100/90 px-2 py-0.5 text-[11px]">
                        <Layers className="h-3 w-3 text-stone-400" />
                        <span>{chunkCount} Chunks</span>
                      </span>
                      <span className="inline-flex items-center gap-1 rounded-md bg-stone-100/90 px-2 py-0.5 text-[11px]">
                        <Database className="h-3 w-3 text-stone-400" />
                        <span>{sizeDisplay}</span>
                      </span>
                    </div>
                  </div>

                  {/* Card Footer: Status & Action Link */}
                  <div className="mt-4 flex items-center justify-between border-t border-stone-100 pt-3 text-xs">
                    <span className="inline-flex items-center gap-1.5 font-medium text-emerald-700">
                      <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
                      <span>Đồng bộ hoàn tất</span>
                    </span>

                    <button
                      type="button"
                      onClick={() => handleEnterWorkspace(w, true)}
                      className={cn(
                        "group/link inline-flex items-center gap-1 font-semibold text-stone-800 transition",
                        meta.hoverLinkClass,
                      )}
                    >
                      <span>Hỏi đáp</span>
                      <ChevronRight className="h-3.5 w-3.5 transition-transform group-hover/link:translate-x-0.5" />
                    </button>
                  </div>
                </article>
              )
            })}

            {/* Empty State / Create New Callout */}
            <button
              type="button"
              onClick={() => setCreateOpen(true)}
              className="group flex min-h-[220px] cursor-pointer flex-col items-center justify-center rounded-2xl bg-brand-50/20 p-5 text-center transition-all duration-300 dashed-border hover:bg-brand-50/50"
            >
              <div className="mb-3 flex h-11 w-11 items-center justify-center rounded-xl border border-brand-200/80 bg-white text-brand-600 shadow-sm transition-all group-hover:scale-110 group-hover:bg-brand-500 group-hover:text-white">
                <FolderPlus className="h-5 w-5 stroke-[1.8]" />
              </div>
              <h3 className="text-sm font-semibold text-stone-900 group-hover:text-brand-800">
                Tạo Workspace mới
              </h3>
              <p className="mt-1 max-w-[200px] text-[11px] leading-relaxed text-stone-500">
                Kéo thả thư mục tài liệu PDF để tự động vector hóa.
              </p>
              <span className="mt-3 inline-flex items-center gap-1 rounded-full bg-brand-100/60 px-3 py-1 text-[11px] font-semibold text-brand-700">
                + Bắt đầu ngay
              </span>
            </button>
          </div>
        </section>
      </main>

      {/* 3. Site Footer */}
      <footer
        className="mt-auto border-t border-stone-200/80 bg-white"
        data-purpose="site-footer"
      >
        <div className="mx-auto flex max-w-7xl flex-col items-center justify-between gap-4 px-6 py-8 text-xs text-stone-500 sm:flex-row">
          <div className="flex items-center gap-2">
            <div className="h-2 w-2 rounded-full bg-brand-500" />
            <span className="font-sans font-medium text-stone-700">motivo.rag</span>
            <span>— Kiến trúc Local NotebookLM &amp; Trợ lý cá nhân</span>
          </div>

          <div className="flex flex-wrap items-center gap-6">
            <button
              type="button"
              onClick={() => navigate("/settings")}
              className="transition hover:text-stone-800"
            >
              Quyền riêng tư &amp; Mã hóa
            </button>
            <button
              type="button"
              onClick={() => navigate("/settings?section=vector")}
              className="transition hover:text-stone-800"
            >
              Cổng kết nối Qdrant
            </button>
            <button
              type="button"
              onClick={() => navigate("/design-system")}
              className="transition hover:text-stone-800"
            >
              Tài liệu API &amp; Giao diện
            </button>
            <span>&copy; 2025-2026 Motivo.rag. All rights reserved.</span>
          </div>
        </div>
      </footer>

      {/* Dialog: Create Workspace */}
      <Dialog
        open={createOpen}
        title="Tạo Workspace mới"
        onClose={() => setCreateOpen(false)}
      >
        <form
          onSubmit={(e) => {
            e.preventDefault()
            const form = e.currentTarget
            const nameInput = form.elements.namedItem("wsName") as HTMLInputElement
            const descInput = form.elements.namedItem("wsDesc") as HTMLTextAreaElement
            const name = nameInput.value.trim()
            if (!name) return

            const duplicate = hasDuplicateName(
              workspaces.map((w) => w.name),
              name,
            )
            if (duplicate) {
              toast({ title: "Đã có Workspace cùng tên", tone: "error" })
              return
            }

            const ws = createWorkspace(name, descInput.value.trim(), createCategory)
            toast({
              title: "Đã tạo Workspace mới",
              description: ws.name,
              tone: "success",
            })
            setCreateOpen(false)
            handleEnterWorkspace(ws, false)
          }}
          className="space-y-3"
        >
          <FormField label="Tên Workspace">
            <Input
              name="wsName"
              autoFocus
              required
              placeholder="Ví dụ: Đồ án Mạng & An toàn thông tin..."
            />
          </FormField>

          <FormField label="Danh mục">
            <Select
              value={createCategory}
              onChange={(e) => setCreateCategory(e.target.value)}
            >
              <option value="Đại học">Đại học</option>
              <option value="Nghiên cứu">Nghiên cứu</option>
              <option value="Kỹ thuật">Kỹ thuật</option>
              <option value="Ngoại ngữ">Ngoại ngữ</option>
              <option value="Dự án">Dự án</option>
              <option value="Cá nhân">Cá nhân</option>
            </Select>
          </FormField>

          <FormField label="Mô tả">
            <textarea
              name="wsDesc"
              rows={3}
              className="w-full rounded-md border border-line bg-bg p-2 text-xs text-ink placeholder:text-muted focus:border-brand focus:outline-hidden"
              placeholder="Mô tả ngắn gọn về đề tài, tài liệu hoặc mục tiêu nghiên cứu..."
            />
          </FormField>

          <div className="flex justify-end gap-2 pt-2">
            <Button
              type="button"
              variant="outline"
              onClick={() => setCreateOpen(false)}
            >
              Hủy
            </Button>
            <Button type="submit">Tạo không gian</Button>
          </div>
        </form>
      </Dialog>

      {/* Dialog: Edit Workspace */}
      <NameDialog
        open={Boolean(editTarget)}
        title="Đổi tên &amp; mô tả Workspace"
        initialName={editTarget?.name ?? ""}
        initialDescription={editTarget?.description ?? ""}
        showDescription
        validate={validateWorkspaceName(editTarget?.id)}
        onClose={() => setEditTarget(null)}
        onSubmit={(name, description) => {
          if (!editTarget) return
          updateWorkspace(editTarget.id, { name, description })
          toast({ title: "Đã cập nhật Workspace", tone: "success" })
          setEditTarget(null)
        }}
      />

      {/* Dialog: Delete Workspace */}
      <ConfirmDialog
        open={Boolean(deleteTarget)}
        title="Xóa Workspace"
        description={`Bạn có chắc chắn muốn xóa "${deleteTarget?.name}"? Toàn bộ tài liệu và hội thoại bên trong sẽ bị gỡ bỏ.`}
        confirmLabel="Xóa vĩnh viễn"
        onClose={() => setDeleteTarget(null)}
        onConfirm={() => {
          if (!deleteTarget) return
          deleteWorkspace(deleteTarget.id)
          toast({ title: "Đã xóa Workspace", description: deleteTarget.name, tone: "info" })
          setDeleteTarget(null)
        }}
      />

      {/* Dialog: Quick Upload */}
      <Dialog
        open={quickUploadOpen}
        title="Nhập tài liệu vào Workspace"
        onClose={() => setQuickUploadOpen(false)}
      >
        <div className="space-y-4">
          <FormField label="Chọn Workspace đích">
            <Select
              value={uploadTargetWs}
              onChange={(e) => setUploadTargetWs(e.target.value)}
            >
              {workspaces.map((w) => (
                <option key={w.id} value={w.id}>
                  {w.name} ({w.category || "Cá nhân"})
                </option>
              ))}
            </Select>
          </FormField>

          <p className="text-xs text-stone-500">
            Chuyển đến trang Quản lý tài liệu của Workspace để kéo thả tệp PDF, DOCX, PPTX hoặc Markdown.
          </p>

          <div className="flex justify-end gap-2 pt-2">
            <Button
              type="button"
              variant="outline"
              onClick={() => setQuickUploadOpen(false)}
            >
              Đóng
            </Button>
            <Button
              type="button"
              onClick={() => {
                if (uploadTargetWs) {
                  setCurrent(uploadTargetWs)
                }
                setQuickUploadOpen(false)
                navigate("/documents")
              }}
            >
              Đến trang tải tài liệu
            </Button>
          </div>
        </div>
      </Dialog>
    </div>
  )
}
