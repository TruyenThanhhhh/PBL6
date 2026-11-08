import { useState } from "react"
import { Link, useNavigate } from "react-router-dom"
import {
  ArrowRight,
  Check,
  ChevronDown,
  Cpu,
  Database,
  Download,
  Globe,
  HardDrive,
  Info,
  Loader2,
  Lock,
  Server,
  Shield,
  ShieldCheck,
} from "lucide-react"
import { useSystemStatus } from "@/hooks/useSystemStatus"
import { useAuthSession } from "@/hooks/useAuthSession"
import { useAppStore } from "@/store/app-store"
import { cn } from "@/utils/cn"

type ModelPackage = "standard" | "light" | "deepseek" | "mistral"
type PrivacyMode = "strict_offline" | "hybrid_rag"

export function OnboardingPage() {
  const navigate = useNavigate()
  useSystemStatus()
  const { user } = useAuthSession()
  const status = useAppStore((s) => s.status)
  const updateSettings = useAppStore((s) => s.updateSettings)
  const toast = useAppStore((s) => s.toast)

  // Selection states
  const [selectedPackage, setSelectedPackage] = useState<ModelPackage>("standard")
  const [privacyMode, setPrivacyMode] = useState<PrivacyMode>("strict_offline")
  const [showAdvancedModels, setShowAdvancedModels] = useState(false)

  // Simulated download / model installation state
  const [downloading, setDownloading] = useState(false)
  const [downloadProgress, setDownloadProgress] = useState(0)
  const [downloadStep, setDownloadStep] = useState("")
  const [installedPackages, setInstalledPackages] = useState<Record<string, boolean>>({
    light: true, // Qwen 2.5 3B is already present on local Ollama
    standard: false,
  })

  const displayName = user?.name || "Sophie"
  const userInitials = displayName
    .split(" ")
    .map((w) => w[0])
    .join("")
    .slice(0, 2)
    .toUpperCase() || "SM"

  // Quick download model simulator
  const handleDownloadModel = (pkg: ModelPackage) => {
    if (downloading) return
    setDownloading(true)
    setDownloadProgress(10)
    setDownloadStep("Đang kết nối Ollama IPC và phân bổ VRAM...")

    setTimeout(() => {
      setDownloadProgress(45)
      setDownloadStep("Đang tải tệp GGUF Q4_K_M (~4.2 GB / 5.8 GB)...")
    }, 900)

    setTimeout(() => {
      setDownloadProgress(82)
      setDownloadStep("Đang khởi tạo KV Cache và kiểm tra chỉ mục Vector BGE-M3...")
    }, 1800)

    setTimeout(() => {
      setDownloadProgress(100)
      setDownloadStep("Cài đặt thành công! Mô hình đã sẵn sàng hoạt động.")
      setInstalledPackages((prev) => ({ ...prev, [pkg]: true }))
      setDownloading(false)
      toast({
        title: "Tải mô hình thành công",
        description: "Mô hình đã được nạp vào Local Ollama Engine.",
        tone: "success",
      })
    }, 2600)
  }

  // Handle completion
  const handleFinishOnboarding = () => {
    const chosenModel =
      selectedPackage === "standard"
        ? "llama3.1:8b"
        : selectedPackage === "light"
          ? "qwen2.5:3b"
          : selectedPackage === "deepseek"
            ? "deepseek-r1:7b"
            : "mistral:7b"

    updateSettings({
      localLlmModel: chosenModel,
      webSearchEnabled: privacyMode === "hybrid_rag",
      defaultAiMode: privacyMode === "strict_offline" ? "local" : "auto",
    })

    try {
      localStorage.setItem("motivo_onboarding_completed", "true")
      localStorage.setItem("motivo_privacy_mode", privacyMode)
      localStorage.setItem("motivo_model_package", selectedPackage)
      localStorage.setItem("motivo_local_model", chosenModel)
    } catch {
      // Ignore if localStorage is restricted
    }

    toast({
      title: "Khởi tạo thành công!",
      description: "Chào mừng bạn đến với không gian làm việc tri thức Motivo.",
      tone: "success",
    })

    navigate("/hub", { replace: true })
  }

  // Reset to recommended defaults
  const handleResetDefaults = () => {
    setSelectedPackage("standard")
    setPrivacyMode("strict_offline")
    setShowAdvancedModels(false)
    toast({
      title: "Đã khôi phục mặc định",
      description: "Gói Tiêu chuẩn và Chế độ Strict Offline được kích hoạt.",
      tone: "info",
    })
  }

  return (
    <div className="min-h-screen bg-[#F5F8F7] text-[#172B29] selection:bg-[#99F6E4] selection:text-[#0F766E] font-sans pb-16">
      {/* Top Header */}
      <header className="sticky top-0 z-40 border-b border-[#DCE7E4] bg-white/90 backdrop-blur-md">
        <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-6">
          {/* Logo & Step indicator */}
          <div className="flex items-center gap-3">
            <Link to="/" className="flex items-center gap-2 group">
              <div className="flex h-7 w-7 items-center justify-center rounded-full bg-[#087F73] text-white shadow-xs">
                <svg className="h-3.5 w-3.5 fill-current" viewBox="0 0 24 24" aria-hidden="true">
                  <path d="M12 2a1 1 0 0 1 1 1v6.2l4.38-4.38a1 1 0 1 1 1.42 1.42L14.42 10.6l6.2.02a1 1 0 0 1 0 2l-6.2-.02 4.38 4.38a1 1 0 0 1-1.42 1.42L13 14.02V20.2a1 1 0 0 1-2 0v-6.18l-4.38 4.38a1 1 0 1 1-1.42-1.42l4.38-4.38-6.2-.02a1 1 0 1 1 0-2l6.2.02-4.38-4.38a1 1 0 0 1 1.42-1.42L11 8.82V3a1 1 0 0 1 1-1Z" />
                </svg>
              </div>
              <span className="font-bold tracking-tight text-[#172B29] text-base">
                motivo<span className="text-[#087F73]">.rag</span>
              </span>
            </Link>
            <span className="text-[#DCE7E4]">/</span>
            <span className="inline-flex items-center gap-1.5 rounded-full bg-[#F0F5F4] px-2.5 py-0.5 text-xs font-medium text-[#647C79]">
              <span className="h-1.5 w-1.5 rounded-full bg-[#087F73]"></span>
              Thiết lập ban đầu • Bước 1/2
            </span>
          </div>

          {/* Right Status & Actions */}
          <div className="flex items-center gap-4 text-xs">
            {/* Live Ollama Engine Status */}
            <div className="hidden sm:inline-flex items-center gap-1.5 rounded-full border border-[#DCE7E4] bg-white px-2.5 py-1 text-[#172B29]">
              <span
                className={cn(
                  "h-2 w-2 rounded-full",
                  status.ollamaRunning ? "bg-emerald-500 animate-pulse" : "bg-amber-500",
                )}
              />
              <span className="font-medium text-[11px]">
                {status.ollamaRunning ? "Ollama: Sẵn sàng" : "Ollama: Chờ kết nối"}
              </span>
            </div>

            {/* Quick Skip to Workspace */}
            <button
              type="button"
              onClick={() => navigate("/hub", { replace: true })}
              className="inline-flex items-center gap-1 text-[#647C79] hover:text-[#172B29] font-medium transition-colors"
            >
              <span>Bỏ qua &amp; Vào Workspace</span>
              <ArrowRight className="h-3.5 w-3.5" />
            </button>

            {/* User Profile Pill */}
            <div className="flex items-center gap-2 pl-2 border-l border-[#DCE7E4]">
              <div className="flex h-7 w-7 items-center justify-center rounded-full bg-[#087F73] text-white font-semibold text-[11px]">
                {userInitials}
              </div>
              <span className="hidden md:inline font-medium text-[#172B29] text-xs">
                {displayName}
              </span>
            </div>
          </div>
        </div>
      </header>

      {/* Main Content Container */}
      <main className="mx-auto max-w-6xl px-6 pt-8 pb-12 space-y-8">
        {/* Hero Welcome Banner */}
        <section className="relative overflow-hidden rounded-3xl border border-[#DCE7E4] bg-white p-6 sm:p-8 shadow-xs">
          <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-6">
            <div className="space-y-3 max-w-2xl">
              {/* Badge */}
              <div className="inline-flex items-center gap-2 rounded-full border border-[#B6E9DF] bg-[#DFF5F0] px-3 py-1 text-xs font-semibold text-[#0F766E]">
                <Check className="h-3.5 w-3.5 stroke-[2.5]" />
                <span>Khởi tạo môi trường Local AI &amp; Bảo mật riêng tư</span>
              </div>

              {/* Title */}
              <h1 className="text-3xl sm:text-4xl font-bold tracking-tight text-[#172B29]">
                Chào mừng bạn,{" "}
                <span className="bg-gradient-to-r from-[#0F766E] via-[#0D9488] to-[#0284C7] bg-clip-text font-serif-italic font-semibold text-transparent underline decoration-[#0D9488]/35 decoration-2 underline-offset-8">
                  {displayName}
                </span>{" "}
                👋
              </h1>

              {/* Subtitle */}
              <p className="text-sm sm:text-base leading-relaxed text-[#647C79]">
                Thiết lập nhanh môi trường AI trên máy của bạn chỉ trong 2 bước đơn giản. Mọi dữ liệu luôn được lưu trữ cục bộ, bảo mật tuyệt đối không rời khỏi thiết bị.
              </p>
            </div>

            {/* Hardware Capability Tag */}
            <div className="shrink-0">
              <div className="inline-flex items-center gap-2 rounded-2xl border border-[#DCE7E4] bg-[#F8FAFC] px-4 py-2.5 text-xs text-[#172B29] font-mono shadow-2xs">
                <Cpu className="h-4 w-4 text-[#087F73]" />
                <span>Phát hiện: Apple Silicon / Windows GPU (16-Core Metal)</span>
              </div>
            </div>
          </div>
        </section>

        {/* 4 Diagnostic System Check Cards */}
        <section aria-label="Kiểm tra hệ thống">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {/* Card 1: Engine AI */}
            <div className="rounded-2xl border border-[#DCE7E4] bg-white p-4.5 shadow-2xs transition-all hover:border-[#087F73]/40">
              <div className="flex items-center justify-between text-xs text-[#647C79] font-semibold uppercase tracking-wider mb-2">
                <span>ENGINE AI</span>
                <Server className="h-4 w-4 text-[#087F73]" />
              </div>
              <div className="flex items-center gap-2 mb-1">
                <span className="text-lg font-bold text-[#172B29]">Ollama Core</span>
                <span
                  className={cn(
                    "rounded-full px-2 py-0.5 text-[11px] font-medium border",
                    status.ollamaRunning
                      ? "bg-[#DFF5F0] text-[#0F766E] border-[#B6E9DF]"
                      : "bg-amber-50 text-amber-700 border-amber-200",
                  )}
                >
                  {status.ollamaRunning ? "● Đã kết nối" : "Chờ kết nối"}
                </span>
              </div>
              <p className="text-xs text-[#647C79]">Cổng IPC: localhost:11434</p>
            </div>

            {/* Card 2: Vector Database */}
            <div className="rounded-2xl border border-[#DCE7E4] bg-white p-4.5 shadow-2xs transition-all hover:border-[#087F73]/40">
              <div className="flex items-center justify-between text-xs text-[#647C79] font-semibold uppercase tracking-wider mb-2">
                <span>VECTOR DATABASE</span>
                <Database className="h-4 w-4 text-[#087F73]" />
              </div>
              <div className="flex items-center gap-2 mb-1">
                <span className="text-lg font-bold text-[#172B29]">Qdrant Local</span>
                <span className="rounded-full bg-[#DFF5F0] text-[#0F766E] border border-[#B6E9DF] px-2 py-0.5 text-[11px] font-medium">
                  Sẵn sàng
                </span>
              </div>
              <p className="text-xs text-[#647C79]">Truy vấn siêu tốc ~2.1 ms</p>
            </div>

            {/* Card 3: Memory / VRAM */}
            <div className="rounded-2xl border border-[#DCE7E4] bg-white p-4.5 shadow-2xs transition-all hover:border-[#087F73]/40">
              <div className="flex items-center justify-between text-xs text-[#647C79] font-semibold uppercase tracking-wider mb-2">
                <span>BỘ NHỚ RAM / VRAM</span>
                <HardDrive className="h-4 w-4 text-[#087F73]" />
              </div>
              <div className="flex items-baseline justify-between mb-1">
                <span className="text-lg font-bold text-[#172B29]">32 GB</span>
                <span className="text-xs font-medium text-[#087F73]">18.4 GB trống</span>
              </div>
              {/* Progress bar */}
              <div className="h-1.5 w-full rounded-full bg-[#F0F5F4] overflow-hidden mb-1.5">
                <div className="h-full bg-[#087F73] rounded-full" style={{ width: "58%" }}></div>
              </div>
              <p className="text-[11px] text-[#647C79]">Đủ điều kiện chạy mô hình 8B</p>
            </div>

            {/* Card 4: Privacy Mode */}
            <div className="rounded-2xl border border-[#DCE7E4] bg-white p-4.5 shadow-2xs transition-all hover:border-[#087F73]/40">
              <div className="flex items-center justify-between text-xs text-[#647C79] font-semibold uppercase tracking-wider mb-2">
                <span>QUYỀN RIÊNG TƯ</span>
                <ShieldCheck className="h-4 w-4 text-[#087F73]" />
              </div>
              <div className="flex items-center gap-2 mb-1">
                <span className="text-lg font-bold text-[#172B29]">100% Offline</span>
                <span className="rounded-full bg-[#E0F2FE] text-[#0284C7] border border-[#BAE6FD] px-2 py-0.5 text-[11px] font-medium">
                  Air-Gapped
                </span>
              </div>
              <p className="text-xs text-[#647C79]">Mã hóa AES-256 nội bộ</p>
            </div>
          </div>
        </section>

        {/* STEP 1: Chọn gói mô hình AI */}
        <section className="space-y-4 rounded-3xl border border-[#DCE7E4] bg-white p-6 sm:p-7 shadow-xs">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 border-b border-[#DCE7E4]/70 pb-4">
            <div className="flex items-center gap-3">
              <div className="flex h-7 w-7 items-center justify-center rounded-full bg-[#087F73] text-white font-bold text-xs">
                1
              </div>
              <div>
                <h2 className="text-base sm:text-lg font-bold text-[#172B29]">
                  Chọn gói mô hình trí tuệ nhân tạo (AI Models)
                </h2>
                <p className="text-xs text-[#647C79]">
                  Mô hình chạy trực tiếp trên card đồ họa máy tính, không gửi dữ liệu ra ngoài
                </p>
              </div>
            </div>
            <span className="text-xs text-[#647C79] font-medium sm:text-right">
              Tải một lần • Dùng vĩnh viễn
            </span>
          </div>

          {/* 2 Primary Packages Grid */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-1">
            {/* Package A: Tiêu chuẩn (Recommended) */}
            <div
              onClick={() => setSelectedPackage("standard")}
              className={cn(
                "relative flex flex-col justify-between rounded-2xl border p-5 cursor-pointer transition-all duration-200",
                selectedPackage === "standard"
                  ? "border-[#087F73] bg-[#F1F9F8] ring-1 ring-[#087F73] shadow-sm"
                  : "border-[#DCE7E4] bg-white hover:border-[#087F73]/50 hover:bg-[#FAFDFD]",
              )}
            >
              <div className="space-y-3">
                <div className="flex items-start justify-between">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="rounded-full bg-[#DFF5F0] text-[#0F766E] border border-[#B6E9DF] px-2.5 py-0.5 text-xs font-semibold">
                      Khuyên dùng
                    </span>
                    <span className="text-xs font-mono text-[#647C79]">~5.8 GB</span>
                  </div>
                  <div
                    className={cn(
                      "flex h-5 w-5 items-center justify-center rounded-full border transition-colors",
                      selectedPackage === "standard"
                        ? "border-[#087F73] bg-[#087F73] text-white"
                        : "border-[#DCE7E4] bg-white",
                    )}
                  >
                    {selectedPackage === "standard" && <Check className="h-3 w-3 stroke-[3]" />}
                  </div>
                </div>

                <div>
                  <h3 className="text-base font-bold text-[#172B29]">
                    Gói Tiêu chuẩn (BGE-M3 + Llama 3.1 8B)
                  </h3>
                  <p className="text-xs leading-relaxed text-[#647C79] mt-1.5">
                    Tối ưu sâu cho Tiếng Việt và thuật ngữ kỹ thuật, đọc hiểu tài liệu lớn (8k context), tổng hợp báo cáo và trích dẫn chuẩn xác không gây ảo giác.
                  </p>
                </div>
              </div>

              <div className="mt-4 pt-3 border-t border-[#DCE7E4]/60 flex items-center justify-between text-xs text-[#647C79]">
                <div className="flex items-center gap-1.5 font-medium">
                  {installedPackages.standard ? (
                    <span className="text-[#087F73] inline-flex items-center gap-1">
                      <Check className="h-3.5 w-3.5" /> Đã sẵn sàng trên máy
                    </span>
                  ) : downloading && selectedPackage === "standard" ? (
                    <span className="text-[#087F73] inline-flex items-center gap-1">
                      <Loader2 className="h-3.5 w-3.5 animate-spin" /> {downloadStep}
                    </span>
                  ) : (
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation()
                        handleDownloadModel("standard")
                      }}
                      className="inline-flex items-center gap-1 text-[#087F73] hover:underline font-semibold"
                    >
                      <Download className="h-3 w-3" /> Tải về máy (~5.8 GB)
                    </button>
                  )}
                </div>
                <span className="font-mono text-[11px]">Q4_K_M GGUF</span>
              </div>
            </div>

            {/* Package B: Siêu nhẹ */}
            <div
              onClick={() => setSelectedPackage("light")}
              className={cn(
                "relative flex flex-col justify-between rounded-2xl border p-5 cursor-pointer transition-all duration-200",
                selectedPackage === "light"
                  ? "border-[#087F73] bg-[#F1F9F8] ring-1 ring-[#087F73] shadow-sm"
                  : "border-[#DCE7E4] bg-white hover:border-[#087F73]/50 hover:bg-[#FAFDFD]",
              )}
            >
              <div className="space-y-3">
                <div className="flex items-start justify-between">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="rounded-full bg-[#F0F5F4] text-[#647C79] border border-[#DCE7E4] px-2.5 py-0.5 text-xs font-semibold">
                      Máy cấu hình vừa
                    </span>
                    <span className="text-xs font-mono text-[#647C79]">~2.4 GB</span>
                  </div>
                  <div
                    className={cn(
                      "flex h-5 w-5 items-center justify-center rounded-full border transition-colors",
                      selectedPackage === "light"
                        ? "border-[#087F73] bg-[#087F73] text-white"
                        : "border-[#DCE7E4] bg-white",
                    )}
                  >
                    {selectedPackage === "light" && <Check className="h-3 w-3 stroke-[3]" />}
                  </div>
                </div>

                <div>
                  <h3 className="text-base font-bold text-[#172B29]">
                    Gói Siêu nhẹ (MiniLM + Qwen 2.5 3B)
                  </h3>
                  <p className="text-xs leading-relaxed text-[#647C79] mt-1.5">
                    Tốc độ phản hồi cực nhanh, chiếm ít tài nguyên RAM nhất (~4GB RAM). Phù hợp máy tính văn phòng hoặc khi cần tiết kiệm pin tối đa.
                  </p>
                </div>
              </div>

              <div className="mt-4 pt-3 border-t border-[#DCE7E4]/60 flex items-center justify-between text-xs text-[#647C79]">
                <div className="flex items-center gap-1.5 font-medium">
                  {installedPackages.light || status.ollamaModels.some((m) => m.includes("qwen2.5:3b")) ? (
                    <span className="text-[#087F73] inline-flex items-center gap-1">
                      <Check className="h-3.5 w-3.5" /> Đã cài sẵn trong Ollama
                    </span>
                  ) : (
                    <span>Nhấp để chọn gói này</span>
                  )}
                </div>
                <span className="font-mono text-[11px]">Q4_K_S GGUF</span>
              </div>
            </div>
          </div>

          {/* Download progress bar if currently downloading */}
          {downloading && (
            <div className="rounded-2xl border border-[#B6E9DF] bg-[#F0FDF9] p-4 space-y-2">
              <div className="flex items-center justify-between text-xs">
                <span className="font-semibold text-[#0F766E] flex items-center gap-2">
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  {downloadStep}
                </span>
                <span className="font-mono font-bold text-[#0F766E]">{downloadProgress}%</span>
              </div>
              <div className="h-2 w-full rounded-full bg-[#CCFBF1] overflow-hidden">
                <div
                  className="h-full bg-[#0D9488] transition-all duration-300 rounded-full"
                  style={{ width: `${downloadProgress}%` }}
                />
              </div>
            </div>
          )}

          {/* Accordion: Tùy chỉnh mô hình nâng cao */}
          <div className="pt-2">
            <button
              type="button"
              onClick={() => setShowAdvancedModels((prev) => !prev)}
              className="inline-flex items-center gap-2 text-xs font-semibold text-[#087F73] hover:text-[#065F56] transition-colors py-1"
            >
              <Cpu className="h-3.5 w-3.5" />
              <span>Tùy chỉnh mô hình nâng cao (DeepSeek-R1, Mistral, Gemma 2)...</span>
              <ChevronDown
                className={cn("h-3.5 w-3.5 transition-transform duration-200", showAdvancedModels && "rotate-180")}
              />
            </button>

            {showAdvancedModels && (
              <div className="mt-3 grid grid-cols-1 sm:grid-cols-2 gap-3 pt-2 border-t border-[#DCE7E4]/50">
                {/* DeepSeek R1 7B */}
                <div
                  onClick={() => setSelectedPackage("deepseek")}
                  className={cn(
                    "p-3.5 rounded-xl border text-xs cursor-pointer transition-all",
                    selectedPackage === "deepseek"
                      ? "border-[#087F73] bg-[#F1F9F8] ring-1 ring-[#087F73]"
                      : "border-[#DCE7E4] bg-white hover:border-[#087F73]/50",
                  )}
                >
                  <div className="flex items-center justify-between mb-1">
                    <span className="font-bold text-[#172B29]">DeepSeek-R1 Distill 7B</span>
                    <span className="font-mono text-[#647C79] text-[11px]">~4.7 GB</span>
                  </div>
                  <p className="text-[11px] text-[#647C79] leading-normal">
                    Mô hình suy luận logic, lập trình và giải toán chuyên sâu.
                  </p>
                </div>

                {/* Mistral NeMo 12B */}
                <div
                  onClick={() => setSelectedPackage("mistral")}
                  className={cn(
                    "p-3.5 rounded-xl border text-xs cursor-pointer transition-all",
                    selectedPackage === "mistral"
                      ? "border-[#087F73] bg-[#F1F9F8] ring-1 ring-[#087F73]"
                      : "border-[#DCE7E4] bg-white hover:border-[#087F73]/50",
                  )}
                >
                  <div className="flex items-center justify-between mb-1">
                    <span className="font-bold text-[#172B29]">Mistral NeMo 12B</span>
                    <span className="font-mono text-[#647C79] text-[11px]">~7.1 GB</span>
                  </div>
                  <p className="text-[11px] text-[#647C79] leading-normal">
                    Hỗ trợ ngữ cảnh siêu dài (128k context), mạnh về dịch thuật đa ngôn ngữ.
                  </p>
                </div>
              </div>
            )}
          </div>
        </section>

        {/* STEP 2: Thiết lập quyền riêng tư (Privacy Mode) */}
        <section className="space-y-4 rounded-3xl border border-[#DCE7E4] bg-white p-6 sm:p-7 shadow-xs">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 border-b border-[#DCE7E4]/70 pb-4">
            <div className="flex items-center gap-3">
              <div className="flex h-7 w-7 items-center justify-center rounded-full bg-[#087F73] text-white font-bold text-xs">
                2
              </div>
              <div>
                <h2 className="text-base sm:text-lg font-bold text-[#172B29]">
                  Chế độ bảo mật &amp; tra cứu (Privacy &amp; Search Policy)
                </h2>
                <p className="text-xs text-[#647C79]">
                  Kiểm soát quyền truy cập mạng và mức độ bảo mật dữ liệu
                </p>
              </div>
            </div>
            <span className="text-xs text-[#647C79] font-medium sm:text-right">
              Có thể thay đổi trong Cài đặt
            </span>
          </div>

          {/* 2 Privacy Options */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-1">
            {/* Option A: Strict Offline */}
            <div
              onClick={() => setPrivacyMode("strict_offline")}
              className={cn(
                "relative flex flex-col justify-between rounded-2xl border p-5 cursor-pointer transition-all duration-200",
                privacyMode === "strict_offline"
                  ? "border-[#087F73] bg-[#F1F9F8] ring-1 ring-[#087F73] shadow-sm"
                  : "border-[#DCE7E4] bg-white hover:border-[#087F73]/50 hover:bg-[#FAFDFD]",
              )}
            >
              <div className="space-y-3">
                <div className="flex items-start justify-between">
                  <div className="flex items-center gap-2">
                    <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-[#DFF5F0] text-[#0F766E] border border-[#B6E9DF]">
                      <Shield className="h-4 w-4" />
                    </div>
                    <div>
                      <h3 className="text-base font-bold text-[#172B29]">
                        Strict Offline (Nội bộ 100%)
                      </h3>
                      <span className="text-[10px] font-bold tracking-wider text-[#0F766E] uppercase">
                        Khuyên dùng bảo mật tuyệt đối
                      </span>
                    </div>
                  </div>
                  <div
                    className={cn(
                      "flex h-5 w-5 items-center justify-center rounded-full border transition-colors",
                      privacyMode === "strict_offline"
                        ? "border-[#087F73] bg-[#087F73] text-white"
                        : "border-[#DCE7E4] bg-white",
                    )}
                  >
                    {privacyMode === "strict_offline" && <Check className="h-3 w-3 stroke-[3]" />}
                  </div>
                </div>

                <p className="text-xs leading-relaxed text-[#647C79]">
                  Hoàn toàn ngắt kết nối internet. Không có byte dữ liệu nào rời khỏi máy tính của bạn. Xử lý tài liệu nội bộ chuẩn Air-Gapped.
                </p>
              </div>

              {/* Badges / Chips */}
              <div className="mt-4 pt-3 border-t border-[#DCE7E4]/60 flex flex-wrap items-center gap-1.5 text-[11px] text-[#647C79]">
                <span className="inline-flex items-center gap-1 rounded-md border border-[#DCE7E4] bg-white px-2 py-0.5 font-medium">
                  <Lock className="h-2.5 w-2.5 text-[#087F73]" /> Air-Gapped
                </span>
                <span className="inline-flex items-center gap-1 rounded-md border border-[#DCE7E4] bg-white px-2 py-0.5 font-medium">
                  Mã hóa AES-256
                </span>
                <span className="inline-flex items-center gap-1 rounded-md border border-[#DCE7E4] bg-white px-2 py-0.5 font-medium">
                  Zero Telemetry
                </span>
              </div>
            </div>

            {/* Option B: Hybrid RAG */}
            <div
              onClick={() => setPrivacyMode("hybrid_rag")}
              className={cn(
                "relative flex flex-col justify-between rounded-2xl border p-5 cursor-pointer transition-all duration-200",
                privacyMode === "hybrid_rag"
                  ? "border-[#087F73] bg-[#F1F9F8] ring-1 ring-[#087F73] shadow-sm"
                  : "border-[#DCE7E4] bg-white hover:border-[#087F73]/50 hover:bg-[#FAFDFD]",
              )}
            >
              <div className="space-y-3">
                <div className="flex items-start justify-between">
                  <div className="flex items-center gap-2">
                    <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-[#E0F2FE] text-[#0284C7] border border-[#BAE6FD]">
                      <Globe className="h-4 w-4" />
                    </div>
                    <div>
                      <h3 className="text-base font-bold text-[#172B29]">
                        Hybrid RAG (Mở rộng tra cứu Web)
                      </h3>
                      <span className="text-[10px] font-bold tracking-wider text-[#0284C7] uppercase">
                        Linh hoạt &amp; Cập nhật thông tin
                      </span>
                    </div>
                  </div>
                  <div
                    className={cn(
                      "flex h-5 w-5 items-center justify-center rounded-full border transition-colors",
                      privacyMode === "hybrid_rag"
                        ? "border-[#087F73] bg-[#087F73] text-white"
                        : "border-[#DCE7E4] bg-white",
                    )}
                  >
                    {privacyMode === "hybrid_rag" && <Check className="h-3 w-3 stroke-[3]" />}
                  </div>
                </div>

                <p className="text-xs leading-relaxed text-[#647C79]">
                  Ưu tiên dữ liệu trên máy, cho phép tìm kiếm thêm thông tin thời gian thực từ Google/DuckDuckGo khi tài liệu nội bộ chưa có lời giải.
                </p>
              </div>

              {/* Badges / Chips */}
              <div className="mt-4 pt-3 border-t border-[#DCE7E4]/60 flex flex-wrap items-center gap-1.5 text-[11px] text-[#647C79]">
                <span className="inline-flex items-center gap-1 rounded-md border border-[#DCE7E4] bg-white px-2 py-0.5 font-medium">
                  Web Search
                </span>
                <span className="inline-flex items-center gap-1 rounded-md border border-[#DCE7E4] bg-white px-2 py-0.5 font-medium">
                  Live News Feed
                </span>
                <span className="inline-flex items-center gap-1 rounded-md border border-[#DCE7E4] bg-white px-2 py-0.5 font-medium">
                  Masked Query
                </span>
              </div>
            </div>
          </div>
        </section>

        {/* Bottom Actions Bar */}
        <section className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 rounded-2xl border border-[#DCE7E4] bg-white px-6 py-4 shadow-xs">
          <div className="flex items-center gap-2 text-xs text-[#647C79]">
            <Info className="h-4 w-4 shrink-0 text-[#087F73]" />
            <span>Bạn luôn có thể thay đổi các cài đặt này bất cứ lúc nào trong mục Cài đặt hệ thống.</span>
          </div>

          <div className="flex items-center gap-3 shrink-0">
            <button
              type="button"
              onClick={handleResetDefaults}
              className="rounded-full border border-[#DCE7E4] bg-white px-4 py-2 text-xs font-semibold text-[#647C79] hover:bg-[#F0F5F4] hover:text-[#172B29] transition-colors"
            >
              Thiết lập mặc định
            </button>
            <button
              type="button"
              onClick={handleFinishOnboarding}
              className="inline-flex items-center gap-2 rounded-full bg-slate-950 px-6 py-2.5 text-xs sm:text-sm font-semibold text-white shadow-pill hover:bg-slate-800 active:scale-95 transition-all"
            >
              <span>Hoàn tất &amp; Khám phá Workspace</span>
              <ArrowRight className="h-4 w-4 text-[#5EEAD4]" />
            </button>
          </div>
        </section>
      </main>

      {/* Footer */}
      <footer className="mx-auto max-w-6xl px-6 pt-4 flex flex-col sm:flex-row items-center justify-between text-xs text-[#647C79] gap-3">
        <div>
          motivo.rag — Kiến trúc Local NotebookLM &amp; Trợ lý cá nhân
        </div>
        <div className="flex items-center gap-4 text-[11px]">
          <span className="hover:text-[#172B29] cursor-pointer">Quyền riêng tư</span>
          <span>•</span>
          <span className="hover:text-[#172B29] cursor-pointer">Tài liệu</span>
          <span>•</span>
          <span className="font-mono text-slate-400">v0.9.4-edge</span>
        </div>
      </footer>
    </div>
  )
}
