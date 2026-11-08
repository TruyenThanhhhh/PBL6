import { useEffect, useState } from "react"
import { useNavigate, useSearchParams } from "react-router-dom"
import {
  Activity,
  Bot,
  Database,
  KeyRound,
  Palette,
  RefreshCw,
  Settings,
  Shield,
  Sun,
  Moon,
  Trash2,
  User,
} from "lucide-react"
import { ConfirmDialog } from "@/components/common/NameDialog"
import { PageHeader } from "@/components/common/PageHeader"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { FormField, Input } from "@/components/ui/input"
import { Select } from "@/components/ui/select"
import { useAuthSession } from "@/hooks/useAuthSession"
import { useAppStore } from "@/store/app-store"
import { fetchSystemStatus } from "@/services/api"
import { changePassword, logout, updateProfile } from "@/services/auth-service"
import type { AIMode } from "@/types"

type SettingsSection =
  | "account"
  | "general"
  | "appearance"
  | "models"
  | "storage"
  | "privacy"
  | "status"

const SECTIONS: { id: SettingsSection; label: string; icon: typeof Settings }[] = [
  { id: "account", label: "Hồ sơ cá nhân", icon: User },
  { id: "general", label: "General", icon: Settings },
  { id: "appearance", label: "Appearance", icon: Palette },
  { id: "models", label: "AI Models", icon: Bot },
  { id: "storage", label: "Storage & Indexing", icon: Database },
  { id: "privacy", label: "Privacy", icon: Shield },
  { id: "status", label: "System Status", icon: Activity },
]

export function SettingsPage() {
  const navigate = useNavigate()
  const { user, authenticated } = useAuthSession()
  const [searchParams, setSearchParams] = useSearchParams()
  const paramSection = searchParams.get("section") as SettingsSection | null
  const activeSection: SettingsSection =
    SECTIONS.find((s) => s.id === paramSection)?.id ?? "account"

  const setSection = (id: SettingsSection) => {
    setSearchParams({ section: id })
  }

  const [firstName, setFirstName] = useState(user?.first_name ?? "")
  const [lastName, setLastName] = useState(user?.last_name ?? "")
  const [phone, setPhone] = useState(user?.phone ?? "")
  const [organization, setOrganization] = useState(user?.organization ?? "")
  const [roleTitle, setRoleTitle] = useState(user?.role_title || "Sinh viên")
  const [savingProfile, setSavingProfile] = useState(false)

  const [currentPassword, setCurrentPassword] = useState("")
  const [newPassword, setNewPassword] = useState("")
  const [confirmNewPassword, setConfirmNewPassword] = useState("")
  const [savingPassword, setSavingPassword] = useState(false)

  useEffect(() => {
    if (user) {
      setFirstName(user.first_name ?? "")
      setLastName(user.last_name ?? "")
      setPhone(user.phone ?? "")
      setOrganization(user.organization ?? "")
      setRoleTitle(user.role_title || "Sinh viên")
    }
  }, [user])

  const theme = useAppStore((s) => s.theme)
  const setTheme = useAppStore((s) => s.setTheme)
  const language = useAppStore((s) => s.language)
  const defaultAiMode = useAppStore((s) => s.defaultAiMode)
  const webSearchEnabled = useAppStore((s) => s.webSearchEnabled)
  const confirmBeforeExternal = useAppStore((s) => s.confirmBeforeExternal)
  const localLlmModel = useAppStore((s) => s.localLlmModel)
  const embeddingModel = useAppStore((s) => s.embeddingModel)
  const vectorDb = useAppStore((s) => s.vectorDb)
  const storagePath = useAppStore((s) => s.storagePath)
  const updateSettings = useAppStore((s) => s.updateSettings)
  const setAiMode = useAppStore((s) => s.setAiMode)
  const setStatus = useAppStore((s) => s.setStatus)
  const currentStatus = useAppStore((s) => s.status)
  const workspaces = useAppStore((s) => s.workspaces)
  const currentWorkspaceId = useAppStore((s) => s.currentWorkspaceId)
  const setCurrentWorkspace = useAppStore((s) => s.setCurrentWorkspace)
  const documents = useAppStore((s) => s.documents)
  const conversations = useAppStore((s) => s.conversations)
  const notes = useAppStore((s) => s.notes)
  const clearLocalData = useAppStore((s) => s.clearLocalData)
  const toast = useAppStore((s) => s.toast)

  const [checking, setChecking] = useState(false)
  const [confirmResetOpen, setConfirmResetOpen] = useState(false)

  const readyDocs = documents.filter((d) => d.status === "ready").length
  const failedDocs = documents.filter((d) => d.status === "failed").length
  const processingDocs = documents.filter(
    (d) => d.status !== "ready" && d.status !== "failed",
  ).length

  const checkBackend = async () => {
    setChecking(true)
    try {
      const s = await fetchSystemStatus()
      setStatus(s)
      toast({
        title: s.backendOnline ? "Đã kết nối Backend" : "Đang dùng dữ liệu mô phỏng",
        description: s.message,
        tone: s.backendOnline ? "success" : "warning",
      })
    } catch {
      setStatus({
        ...currentStatus,
        backendOnline: false,
        usingMock: true,
        message: "Không kết nối được http://localhost:8000",
      })
      toast({ title: "Không kết nối được Backend", tone: "error" })
    } finally {
      setChecking(false)
    }
  }

  return (
    <div className="mx-auto max-w-[1040px] px-4 py-8 md:px-8">
      <PageHeader
        title="Cài đặt"
        description="Quản lý tuỳ chọn không gian làm việc, giao diện, mô hình AI, lưu trữ và quyền riêng tư."
      />

      <div className="flex flex-col gap-6 md:flex-row">
        {/* Sub-navigation bên trái */}
        <aside className="w-full shrink-0 md:w-52">
          <nav className="flex flex-row gap-1 overflow-x-auto pb-2 md:flex-col md:overflow-visible md:pb-0">
            {SECTIONS.map((sec) => {
              const Icon = sec.icon
              const isActive = activeSection === sec.id
              return (
                <button
                  key={sec.id}
                  type="button"
                  onClick={() => setSection(sec.id)}
                  className={`flex shrink-0 items-center gap-2.5 rounded-md px-2.5 py-1.5 text-left text-[13px] transition-colors ${
                    isActive
                      ? "bg-bg-active font-medium text-ink"
                      : "text-muted hover:bg-bg-hover hover:text-ink"
                  }`}
                >
                  <Icon className="h-4 w-4 shrink-0" />
                  <span>{sec.label}</span>
                </button>
              )
            })}
          </nav>
        </aside>

        {/* Nội dung section */}
        <div className="min-w-0 flex-1 rounded-lg border border-line bg-bg p-5 md:p-6">
          {activeSection === "account" && (
            <div className="space-y-6">
              <div>
                <h2 className="text-base font-semibold text-ink">Hồ sơ cá nhân &amp; Tài khoản</h2>
                <p className="mt-0.5 text-xs text-muted">
                  Quản lý thông tin họ tên, số điện thoại, đơn vị công tác/học tập và bảo mật mật khẩu.
                </p>
              </div>

              {!authenticated ? (
                <div className="rounded-lg border border-line bg-bg-secondary p-5">
                  <div className="text-sm font-medium text-ink">Bạn đang ở chế độ Khách (Chưa đăng nhập)</div>
                  <p className="mt-1 text-xs text-muted">
                    Đăng nhập hoặc đăng ký tài khoản để lưu trữ thông tin cá nhân, đồng bộ Workspace và tài liệu trên cơ sở dữ liệu SQLite.
                  </p>
                  <div className="mt-4 flex flex-wrap gap-2.5">
                    <Button size="sm" onClick={() => navigate("/login")}>
                      Đăng nhập
                    </Button>
                    <Button size="sm" variant="outline" onClick={() => navigate("/login?mode=register")}>
                      Đăng ký tài khoản mới
                    </Button>
                  </div>
                </div>
              ) : (
                <>
                  <form
                    className="space-y-4 border-t border-line pt-4"
                    onSubmit={async (e) => {
                      e.preventDefault()
                      if (!lastName.trim() && !firstName.trim()) {
                        toast({ title: "Vui lòng nhập họ và tên", tone: "error" })
                        return
                      }
                      setSavingProfile(true)
                      try {
                        const updated = await updateProfile({
                          first_name: firstName.trim(),
                          last_name: lastName.trim(),
                          phone: phone.trim(),
                          organization: organization.trim(),
                          role_title: roleTitle.trim(),
                        })
                        toast({
                          title: "Đã lưu hồ sơ cá nhân",
                          description: `Tên hiển thị: ${updated.name}`,
                          tone: "success",
                        })
                      } catch (err) {
                        toast({
                          title: "Không thể cập nhật hồ sơ",
                          description: err instanceof Error ? err.message : "Lỗi kết nối",
                          tone: "error",
                        })
                      } finally {
                        setSavingProfile(false)
                      }
                    }}
                  >
                    <div className="flex items-center gap-3.5 rounded-lg border border-line bg-bg-secondary p-3.5">
                      <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-[#0F766E] text-sm font-bold text-white">
                        {(user?.name || user?.email || "U").slice(0, 2).toUpperCase()}
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="truncate text-sm font-semibold text-ink">{user?.name}</div>
                        <div className="truncate text-xs text-muted">{user?.email}</div>
                      </div>
                      <Badge tone="success">Đã xác thực</Badge>
                    </div>

                    <div className="grid gap-4 sm:grid-cols-2">
                      <FormField label="Họ và tên đệm">
                        <Input
                          value={lastName}
                          onChange={(e) => setLastName(e.target.value)}
                          placeholder="Nguyễn Văn"
                        />
                      </FormField>
                      <FormField label="Tên gọi">
                        <Input
                          value={firstName}
                          onChange={(e) => setFirstName(e.target.value)}
                          placeholder="Minh"
                        />
                      </FormField>
                    </div>

                    <div className="grid gap-4 sm:grid-cols-2">
                      <FormField label="Số điện thoại">
                        <Input
                          value={phone}
                          onChange={(e) => setPhone(e.target.value)}
                          placeholder="0905 123 456"
                        />
                      </FormField>
                      <FormField label="Vai trò">
                        <Select value={roleTitle} onChange={(e) => setRoleTitle(e.target.value)}>
                          <option value="Sinh viên">Sinh viên</option>
                          <option value="Giảng viên / Giáo viên">Giảng viên / Giáo viên</option>
                          <option value="Nghiên cứu viên">Nghiên cứu viên</option>
                          <option value="Kỹ sư AI / Phần mềm">Kỹ sư AI / Phần mềm</option>
                          <option value="Chuyên viên phân tích">Chuyên viên phân tích</option>
                          <option value="Khác">Khác</option>
                        </Select>
                      </FormField>
                    </div>

                    <FormField label="Trường học / Cơ quan / Tổ chức">
                      <Input
                        value={organization}
                        onChange={(e) => setOrganization(e.target.value)}
                        placeholder="VD: Trường ĐH Bách Khoa - ĐH Đà Nẵng"
                      />
                    </FormField>

                    <div className="flex items-center justify-between pt-2">
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        onClick={() => {
                          logout()
                          navigate("/login")
                        }}
                      >
                        Đăng xuất tài khoản
                      </Button>
                      <Button type="submit" size="sm" loading={savingProfile}>
                        Lưu thay đổi hồ sơ
                      </Button>
                    </div>
                  </form>

                  <form
                    className="space-y-4 border-t border-line pt-5"
                    onSubmit={async (e) => {
                      e.preventDefault()
                      if (newPassword.length < 8) {
                        toast({ title: "Mật khẩu mới cần tối thiểu 8 ký tự", tone: "error" })
                        return
                      }
                      if (newPassword !== confirmNewPassword) {
                        toast({ title: "Mật khẩu xác nhận không khớp", tone: "error" })
                        return
                      }
                      setSavingPassword(true)
                      try {
                        const msg = await changePassword(currentPassword, newPassword)
                        setCurrentPassword("")
                        setNewPassword("")
                        setConfirmNewPassword("")
                        toast({ title: msg, tone: "success" })
                      } catch (err) {
                        toast({
                          title: "Không thể đổi mật khẩu",
                          description: err instanceof Error ? err.message : "Lỗi kết nối",
                          tone: "error",
                        })
                      } finally {
                        setSavingPassword(false)
                      }
                    }}
                  >
                    <div className="flex items-center gap-2">
                      <KeyRound className="h-4 w-4 text-muted" />
                      <h3 className="text-sm font-semibold text-ink">Đổi mật khẩu bảo mật</h3>
                    </div>

                    <div className="grid gap-3.5 sm:grid-cols-3">
                      <FormField label="Mật khẩu hiện tại">
                        <Input
                          type="password"
                          required
                          value={currentPassword}
                          onChange={(e) => setCurrentPassword(e.target.value)}
                          placeholder="••••••••"
                        />
                      </FormField>
                      <FormField label="Mật khẩu mới (≥ 8 ký tự)">
                        <Input
                          type="password"
                          required
                          minLength={8}
                          value={newPassword}
                          onChange={(e) => setNewPassword(e.target.value)}
                          placeholder="••••••••"
                        />
                      </FormField>
                      <FormField label="Xác nhận mật khẩu mới">
                        <Input
                          type="password"
                          required
                          minLength={8}
                          value={confirmNewPassword}
                          onChange={(e) => setConfirmNewPassword(e.target.value)}
                          placeholder="••••••••"
                        />
                      </FormField>
                    </div>

                    <div className="flex justify-end">
                      <Button type="submit" variant="outline" size="sm" loading={savingPassword}>
                        Cập nhật mật khẩu
                      </Button>
                    </div>
                  </form>
                </>
              )}
            </div>
          )}

          {activeSection === "general" && (
            <div className="space-y-6">
              <div>
                <h2 className="text-base font-semibold text-ink">Cài đặt chung (General)</h2>
                <p className="mt-0.5 text-xs text-muted">
                  Cấu hình không gian làm việc mặc định, ngôn ngữ hiển thị và chế độ AI khởi đầu.
                </p>
              </div>

              <div className="space-y-4 border-t border-line pt-4">
                <div>
                  <label className="mb-1.5 block text-xs font-medium text-ink">
                    Workspace đang làm việc
                  </label>
                  <Select
                    value={currentWorkspaceId}
                    onChange={(e) => {
                      setCurrentWorkspace(e.target.value)
                      toast({ title: "Đã chuyển workspace mặc định", tone: "success" })
                    }}
                  >
                    {workspaces.map((w) => (
                      <option key={w.id} value={w.id}>
                        {w.name}
                      </option>
                    ))}
                  </Select>
                </div>

                <div>
                  <label className="mb-1.5 block text-xs font-medium text-ink">
                    Ngôn ngữ giao diện
                  </label>
                  <Select
                    value={language}
                    onChange={(e) => {
                      updateSettings({ language: e.target.value as "vi" | "en" })
                      toast({ title: "Đã lưu tuỳ chọn ngôn ngữ", tone: "success" })
                    }}
                  >
                    <option value="vi">Tiếng Việt</option>
                    <option value="en">English (Nhãn hệ thống chính hiện ưu tiên Tiếng Việt)</option>
                  </Select>
                </div>

                <div>
                  <label className="mb-1.5 block text-xs font-medium text-ink">
                    Chế độ AI mặc định khi mở phiên hỏi đáp
                  </label>
                  <Select
                    value={defaultAiMode}
                    onChange={(e) => {
                      const mode = e.target.value as AIMode
                      updateSettings({ defaultAiMode: mode })
                      setAiMode(mode)
                      toast({ title: `Đã đặt chế độ mặc định: ${mode.toUpperCase()}`, tone: "success" })
                    }}
                  >
                    <option value="auto">Auto — Tự chọn nguồn phù hợp</option>
                    <option value="local">Local — Chỉ truy xuất tài liệu nội bộ</option>
                    <option value="web">Web — Kết hợp tìm kiếm Web</option>
                    <option value="hybrid">Hybrid — Kết hợp Local RAG + Web</option>
                  </Select>
                </div>
              </div>
            </div>
          )}

          {activeSection === "appearance" && (
            <div className="space-y-6">
              <div>
                <h2 className="text-base font-semibold text-ink">Giao diện (Appearance)</h2>
                <p className="mt-0.5 text-xs text-muted">
                  Tùy chỉnh chế độ Sáng / Tối theo phong cách Notion-inspired Minimal Workspace.
                </p>
              </div>

              <div className="space-y-4 border-t border-line pt-4">
                <div className="grid gap-3 sm:grid-cols-2">
                  <button
                    type="button"
                    onClick={() => setTheme("light")}
                    className={`flex items-center gap-3 rounded-lg border p-3.5 text-left transition-colors ${
                      theme === "light"
                        ? "border-ink bg-bg-secondary"
                        : "border-line hover:bg-bg-hover"
                    }`}
                  >
                    <Sun className="h-4 w-4 text-ink" />
                    <div>
                      <div className="text-sm font-medium text-ink">Light Mode</div>
                      <div className="text-xs text-muted">Nền sáng #FFFFFF, chữ #191919</div>
                    </div>
                  </button>

                  <button
                    type="button"
                    onClick={() => setTheme("dark")}
                    className={`flex items-center gap-3 rounded-lg border p-3.5 text-left transition-colors ${
                      theme === "dark"
                        ? "border-ink bg-bg-secondary"
                        : "border-line hover:bg-bg-hover"
                    }`}
                  >
                    <Moon className="h-4 w-4 text-ink" />
                    <div>
                      <div className="text-sm font-medium text-ink">Dark Mode</div>
                      <div className="text-xs text-muted">Nền tối dịu mắt #191919</div>
                    </div>
                  </button>
                </div>

                <div className="flex items-center justify-between rounded-md border border-line bg-bg-secondary/40 px-3.5 py-2.5">
                  <div>
                    <div className="text-xs font-medium text-ink">Design System & UI Tokens</div>
                    <div className="text-[11px] text-muted">
                      Xem bảng màu trung tính, typography và các component chuẩn hóa.
                    </div>
                  </div>
                  <Button
                    size="sm"
                    variant="outline"
                    leftIcon={<Palette className="h-3.5 w-3.5" />}
                    onClick={() => navigate("/design-system")}
                  >
                    Mở Preview
                  </Button>
                </div>
              </div>
            </div>
          )}

          {activeSection === "models" && (
            <div className="space-y-6">
              <div>
                <h2 className="text-base font-semibold text-ink">Mô hình AI (AI Models)</h2>
                <p className="mt-0.5 text-xs text-muted">
                  Phân biệt rõ cấu hình lưu trên giao diện và trạng thái thực thi thực tế từ Backend / Ollama.
                </p>
              </div>

              <div className="grid gap-2.5 border-t border-line pt-4 sm:grid-cols-3">
                <div className="rounded-md border border-line bg-bg-secondary/40 p-3">
                  <div className="text-[11px] text-muted">Model chọn trên UI</div>
                  <div className="mt-0.5 font-mono text-xs font-semibold text-ink">
                    {localLlmModel || "Chưa đặt"}
                  </div>
                </div>
                <div className="rounded-md border border-line bg-bg-secondary/40 p-3">
                  <div className="text-[11px] text-muted">Embedding cấu hình</div>
                  <div className="mt-0.5 font-mono text-xs font-semibold text-ink">
                    {embeddingModel || "Chưa đặt"}
                  </div>
                </div>
                <div className="rounded-md border border-line bg-bg-secondary/40 p-3">
                  <div className="text-[11px] text-muted">Trạng thái Runtime thực tế</div>
                  <div className="mt-1">
                    {currentStatus.backendOnline && currentStatus.ollamaRunning ? (
                      <Badge tone="success">Connected · Đang chạy</Badge>
                    ) : currentStatus.backendOnline ? (
                      <Badge tone="warning">Not configured trên Server</Badge>
                    ) : (
                      <Badge tone="neutral">Disconnected · Mock fallback</Badge>
                    )}
                  </div>
                </div>
              </div>

              <div className="space-y-3">
                <div>
                  <label className="mb-1 block text-xs font-medium text-ink">
                    Tên mô hình Local LLM (Ollama)
                  </label>
                  <Input
                    value={localLlmModel}
                    onChange={(e) => updateSettings({ localLlmModel: e.target.value })}
                    placeholder="Ví dụ: qwen2.5:7b, llama3.1:8b"
                  />
                </div>
                <div>
                  <label className="mb-1 block text-xs font-medium text-ink">
                    Mô hình Embedding
                  </label>
                  <Input
                    value={embeddingModel}
                    onChange={(e) => updateSettings({ embeddingModel: e.target.value })}
                    placeholder="Ví dụ: bge-m3, nomic-embed-text"
                  />
                </div>
                <p className="text-[11px] text-muted">
                  Lưu ý: Thay đổi tại đây được lưu vào cấu hình client. Để thực thi suy luận thật, dịch vụ Backend và Ollama cần đang chạy với model tương ứng.
                </p>
              </div>
            </div>
          )}

          {activeSection === "storage" && (
            <div className="space-y-6">
              <div>
                <h2 className="text-base font-semibold text-ink">
                  Lưu trữ & Chỉ mục (Storage & Indexing)
                </h2>
                <p className="mt-0.5 text-xs text-muted">
                  Thống kê tài liệu trong kho tri thức và phân biệt nơi lưu trữ dữ liệu hiện tại.
                </p>
              </div>

              <div className="grid grid-cols-2 gap-2.5 border-t border-line pt-4 sm:grid-cols-4">
                <div className="rounded-md border border-line p-3">
                  <div className="text-[11px] text-muted">Sẵn sàng truy xuất</div>
                  <div className="mt-0.5 text-base font-semibold text-ink">{readyDocs}</div>
                </div>
                <div className="rounded-md border border-line p-3">
                  <div className="text-[11px] text-muted">Đang xử lý / Chờ</div>
                  <div className="mt-0.5 text-base font-semibold text-ink">{processingDocs}</div>
                </div>
                <div className="rounded-md border border-line p-3">
                  <div className="text-[11px] text-muted">Lỗi chỉ mục</div>
                  <div className="mt-0.5 text-base font-semibold text-ink">{failedDocs}</div>
                </div>
                <div className="rounded-md border border-line p-3">
                  <div className="text-[11px] text-muted">Ghi chú & Hội thoại</div>
                  <div className="mt-0.5 text-base font-semibold text-ink">
                    {notes.length} · {conversations.length}
                  </div>
                </div>
              </div>

              <div className="space-y-3">
                <div>
                  <label className="mb-1 block text-xs font-medium text-ink">Vector Database</label>
                  <Input
                    value={vectorDb}
                    onChange={(e) => updateSettings({ vectorDb: e.target.value })}
                  />
                </div>
                <div>
                  <label className="mb-1 block text-xs font-medium text-ink">
                    Đường dẫn thư mục dữ liệu (cấu hình mục tiêu cho Backend)
                  </label>
                  <Input
                    value={storagePath}
                    onChange={(e) => updateSettings({ storagePath: e.target.value })}
                  />
                </div>
              </div>

              <div className="rounded-md border border-line bg-bg-secondary/40 p-3 text-xs text-muted">
                <span className="font-medium text-ink">Phân biệt phạm vi lưu trữ: </span>
                Khi chưa kết nối Backend ({currentStatus.usingMock ? "đang ở chế độ Mock/LocalStorage" : "đã kết nối"}), mọi thay đổi về workspace, tài liệu tải lên từ trình duyệt, ghi chú và câu hỏi ôn tập được lưu trong <code>localStorage</code> của trình duyệt chứ chưa ghi xuống đĩa cứng máy chủ hay đánh chỉ mục vector thực.
              </div>
            </div>
          )}

          {activeSection === "privacy" && (
            <div className="space-y-6">
              <div>
                <h2 className="text-base font-semibold text-ink">Quyền riêng tư (Privacy)</h2>
                <p className="mt-0.5 text-xs text-muted">
                  Kiểm soát việc kết nối ra bên ngoài và quản lý dữ liệu lưu trên trình duyệt của bạn.
                </p>
              </div>

              <div className="space-y-3 border-t border-line pt-4">
                <label className="flex cursor-pointer items-start gap-3 rounded-md border border-line p-3.5 hover:bg-bg-hover">
                  <input
                    type="checkbox"
                    checked={webSearchEnabled}
                    onChange={(e) => updateSettings({ webSearchEnabled: e.target.checked })}
                    className="mt-0.5"
                  />
                  <div>
                    <div className="text-xs font-medium text-ink">
                      Cho phép sử dụng chế độ tìm kiếm Web (Web / Hybrid)
                    </div>
                    <div className="mt-0.5 text-[11px] text-muted">
                      Khi tắt, AI Chat sẽ chỉ cho phép truy vấn cục bộ (Local) và chặn các yêu cầu chọn chế độ Web hoặc Hybrid.
                    </div>
                  </div>
                </label>

                <label className="flex cursor-pointer items-start gap-3 rounded-md border border-line p-3.5 hover:bg-bg-hover">
                  <input
                    type="checkbox"
                    checked={confirmBeforeExternal}
                    onChange={(e) => updateSettings({ confirmBeforeExternal: e.target.checked })}
                    className="mt-0.5"
                  />
                  <div>
                    <div className="text-xs font-medium text-ink">
                      Hiển thị cảnh báo khi truy vấn có thể gửi ra ngoài
                    </div>
                    <div className="mt-0.5 text-[11px] text-muted">
                      Nhắc người dùng trên giao diện chat khi đang chọn chế độ kết hợp tìm kiếm bên ngoài.
                    </div>
                  </div>
                </label>
              </div>

              <div className="border-t border-line pt-4">
                <h3 className="text-xs font-semibold text-ink">Khôi phục / Xóa dữ liệu trình duyệt</h3>
                <p className="mt-1 text-xs text-muted">
                  Xóa toàn bộ thay đổi đã lưu trong <code>localStorage</code> trên trình duyệt này và khôi phục bộ dữ liệu mẫu ban đầu. Thao tác này không xóa dữ liệu trên máy chủ nếu có.
                </p>
                <div className="mt-3">
                  <Button
                    variant="danger"
                    size="sm"
                    leftIcon={<Trash2 className="h-3.5 w-3.5" />}
                    onClick={() => setConfirmResetOpen(true)}
                  >
                    Xóa thay đổi & khôi phục dữ liệu mẫu
                  </Button>
                </div>
              </div>
            </div>
          )}

          {activeSection === "status" && (
            <div className="space-y-6">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <h2 className="text-base font-semibold text-ink">
                    Trạng thái hệ thống (System Status)
                  </h2>
                  <p className="mt-0.5 text-xs text-muted">
                    Hiển thị trung thực trạng thái kết nối thực tế giữa Frontend và các dịch vụ Backend.
                  </p>
                </div>
                <Button
                  size="sm"
                  variant="outline"
                  loading={checking}
                  leftIcon={<RefreshCw className="h-3.5 w-3.5" />}
                  onClick={() => void checkBackend()}
                >
                  Kiểm tra lại
                </Button>
              </div>

              <div className="divide-y divide-line rounded-md border border-line">
                <div className="flex items-center justify-between px-4 py-3 text-xs">
                  <div>
                    <div className="font-medium text-ink">Backend API (FastAPI)</div>
                    <div className="text-[11px] text-muted">Endpoint: http://localhost:8000</div>
                  </div>
                  <Badge tone={currentStatus.backendOnline ? "success" : "neutral"}>
                    {currentStatus.backendOnline ? "Connected" : "Disconnected"}
                  </Badge>
                </div>

                <div className="flex items-center justify-between px-4 py-3 text-xs">
                  <div>
                    <div className="font-medium text-ink">Local LLM Runtime (Ollama)</div>
                    <div className="text-[11px] text-muted">Model cấu hình: {localLlmModel}</div>
                  </div>
                  <Badge
                    tone={
                      currentStatus.backendOnline && currentStatus.ollamaRunning
                        ? "success"
                        : "neutral"
                    }
                  >
                    {currentStatus.backendOnline
                      ? currentStatus.ollamaRunning
                        ? "Connected"
                        : "Not configured"
                      : "Unknown (Backend offline)"}
                  </Badge>
                </div>

                <div className="flex items-center justify-between px-4 py-3 text-xs">
                  <div>
                    <div className="font-medium text-ink">Vector Index & RAG Pipeline</div>
                    <div className="text-[11px] text-muted">
                      Engine cấu hình: {vectorDb} · {embeddingModel}
                    </div>
                  </div>
                  <Badge
                    tone={
                      currentStatus.backendOnline && !currentStatus.usingMock
                        ? "success"
                        : "warning"
                    }
                  >
                    {currentStatus.backendOnline && !currentStatus.usingMock
                      ? "Connected"
                      : "Mock data"}
                  </Badge>
                </div>

                <div className="flex items-center justify-between px-4 py-3 text-xs">
                  <div>
                    <div className="font-medium text-ink">Nguồn dữ liệu hiển thị hiện tại</div>
                    <div className="text-[11px] text-muted">{currentStatus.message}</div>
                  </div>
                  <Badge tone={currentStatus.usingMock ? "warning" : "success"}>
                    {currentStatus.usingMock ? "Mock data + LocalStorage" : "Live Backend"}
                  </Badge>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      <ConfirmDialog
        open={confirmResetOpen}
        title="Khôi phục dữ liệu mẫu?"
        description="Toàn bộ workspace, tài liệu, ghi chú, hội thoại và nghiên cứu bạn đã chỉnh sửa trên trình duyệt sẽ được đặt lại về dữ liệu mẫu ban đầu."
        confirmLabel="Khôi phục"
        onClose={() => setConfirmResetOpen(false)}
        onConfirm={() => {
          clearLocalData()
          setConfirmResetOpen(false)
        }}
      />
    </div>
  )
}
