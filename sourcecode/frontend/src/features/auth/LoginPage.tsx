import { useEffect, useMemo, useState } from "react"
import { Link, useNavigate, useSearchParams } from "react-router-dom"
import {
  ArrowLeft,
  Building2,
  Briefcase,
  CheckCircle2,
  Eye,
  EyeOff,
  KeyRound,
  Mail,
  Phone,
  RefreshCw,
  ShieldCheck,
  Sparkles,
  User,
} from "lucide-react"
import { Alert } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { FormField, Input } from "@/components/ui/input"
import { Select } from "@/components/ui/select"
import {
  consumeOAuthTokenFromHash,
  fetchCurrentSession,
  googleLoginUrl,
  isBackendReachable,
  isGoogleAuthEnabled,
  login,
  register,
} from "@/services/auth-service"
import { useAppStore } from "@/store/app-store"

type AuthMode = "login" | "register"

const ROLE_OPTIONS = [
  "Sinh viên",
  "Giảng viên / Giáo viên",
  "Nghiên cứu viên",
  "Kỹ sư AI / Phần mềm",
  "Chuyên viên phân tích",
  "Khác",
]

function evaluatePasswordStrength(pwd: string): {
  score: number
  label: string
  colorClass: string
} {
  if (!pwd) return { score: 0, label: "", colorClass: "bg-slate-200" }
  let score = 0
  if (pwd.length >= 8) score += 1
  if (pwd.length >= 10) score += 1
  if (/[A-Z]/.test(pwd) && /[a-z]/.test(pwd)) score += 1
  if (/\d/.test(pwd) || /[^A-Za-z0-9]/.test(pwd)) score += 1

  if (score <= 1) return { score: 1, label: "Yếu", colorClass: "bg-rose-500" }
  if (score === 2) return { score: 2, label: "Trung bình", colorClass: "bg-amber-500" }
  if (score === 3) return { score: 3, label: "Khá mạnh", colorClass: "bg-teal-500" }
  return { score: 4, label: "Rất mạnh", colorClass: "bg-emerald-600" }
}

export function LoginPage() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const toast = useAppStore((s) => s.toast)

  const initialMode: AuthMode =
    searchParams.get("mode") === "register" ? "register" : "login"

  const [mode, setMode] = useState<AuthMode>(initialMode)

  // Thông tin đăng nhập & đăng ký
  const [lastName, setLastName] = useState("")
  const [firstName, setFirstName] = useState("")
  const [email, setEmail] = useState("")
  const [phone, setPhone] = useState("")
  const [organization, setOrganization] = useState("")
  const [roleTitle, setRoleTitle] = useState("Sinh viên")
  const [password, setPassword] = useState("")
  const [confirmPassword, setConfirmPassword] = useState("")
  const [rememberMe, setRememberMe] = useState(true)

  const [showPassword, setShowPassword] = useState(false)
  const [showConfirmPassword, setShowConfirmPassword] = useState(false)

  const [error, setError] = useState("")
  const [submitting, setSubmitting] = useState(false)
  const [googleEnabled, setGoogleEnabled] = useState(false)
  const [backendOnline, setBackendOnline] = useState<boolean | null>(null)
  const [checkingBackend, setCheckingBackend] = useState(false)

  const pwdStrength = useMemo(() => evaluatePasswordStrength(password), [password])

  const checkBackend = async () => {
    setCheckingBackend(true)
    const online = await isBackendReachable()
    setBackendOnline(online)
    setCheckingBackend(false)
    return online
  }

  useEffect(() => {
    const reqMode = searchParams.get("mode")
    if (reqMode === "register" || reqMode === "login") {
      setMode(reqMode)
    }
    const authError = searchParams.get("auth_error")
    if (authError === "google_auth_failed") {
      setError("Xác thực Google không thành công. Vui lòng thử lại hoặc đăng nhập bằng email.")
    } else if (authError === "google_profile_invalid") {
      setError("Tài khoản Google chưa xác minh email.")
    }
  }, [searchParams])

  useEffect(() => {
    let active = true
    if (consumeOAuthTokenFromHash()) {
      fetchCurrentSession()
        .then((session) => {
          if (active && session) {
            toast({
              title: "Đăng nhập thành công",
              description: `Chào mừng ${session.user.name}!`,
              tone: "success",
            })
            navigate("/hub", { replace: true })
          }
        })
        .catch(() => {})
    }
    isGoogleAuthEnabled().then((enabled) => {
      if (active) setGoogleEnabled(enabled)
    })
    isBackendReachable().then((online) => {
      if (active) setBackendOnline(online)
    })
    return () => {
      active = false
    }
  }, [navigate, toast])

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setError("")

    if (mode === "register") {
      if (!lastName.trim() || !firstName.trim()) {
        setError("Vui lòng nhập đầy đủ Họ & tên đệm và Tên của bạn.")
        return
      }
      if (password.length < 8) {
        setError("Mật khẩu cần tối thiểu 8 ký tự.")
        return
      }
      if (password !== confirmPassword) {
        setError("Mật khẩu xác nhận không khớp.")
        return
      }
    } else {
      if (!password) {
        setError("Vui lòng nhập mật khẩu.")
        return
      }
    }

    setSubmitting(true)
    try {
      const online = await checkBackend()
      if (!online) {
        setError(
          "Không kết nối được backend. Hãy chạy start_app.bat (hoặc start_all.bat) để khởi động server ở cổng 8000 rồi thử lại.",
        )
        return
      }

      if (mode === "register") {
        const session = await register({
          email: email.trim(),
          password,
          first_name: firstName.trim(),
          last_name: lastName.trim(),
          phone: phone.trim(),
          organization: organization.trim(),
          role_title: roleTitle.trim(),
        })
        toast({
          title: "Đăng ký tài khoản thành công!",
          description: `Xin chào ${session.user.name}, không gian tri thức của bạn đã sẵn sàng.`,
          tone: "success",
        })
        navigate("/onboarding", { replace: true })
        return
      } else {
        const session = await login(email.trim(), password, rememberMe)
        toast({
          title: "Đăng nhập thành công",
          description: `Chào mừng trở lại, ${session.user.name}!`,
          tone: "success",
        })
        navigate("/hub", { replace: true })
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Không thể xác thực tài khoản.")
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-[#EAF4F2] via-[#F1F5F4] to-[#E6F1F8] px-4 py-10">
      <div className={`w-full transition-all duration-200 ${mode === "register" ? "max-w-xl" : "max-w-md"}`}>
        <div className="mb-4 flex items-center justify-between">
          <Link
            to="/welcome"
            className="inline-flex items-center gap-1.5 text-xs font-medium text-[#526B68] transition-colors hover:text-[#0B1716]"
          >
            <ArrowLeft className="h-3.5 w-3.5" />
            Trang giới thiệu
          </Link>
          <Link
            to="/hub"
            className="inline-flex items-center gap-1 text-xs font-medium text-[#0F766E] hover:underline"
          >
            Trải nghiệm nhanh (Chế độ khách)
          </Link>
        </div>

        <div className="rounded-2xl border border-[#D5E6E2] bg-white p-6 sm:p-8 shadow-[0_18px_50px_-24px_rgba(11,35,32,0.3)]">
          {/* Header thương hiệu */}
          <div className="mb-5 flex items-center justify-between">
            <div className="flex items-center gap-2.5">
              <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-[#0F766E] text-white shadow-sm">
                <Sparkles className="h-4.5 w-4.5" />
              </span>
              <div>
                <p className="font-sans text-lg font-bold tracking-tight text-[#0B1716]">
                  motivo<span className="text-[#0D9488]">.rag</span>
                </p>
                <p className="text-xs text-[#647D7A]">Personal AI Knowledge Platform</p>
              </div>
            </div>

            <span className="inline-flex items-center gap-1.5 rounded-full border border-[#CBE4DF] bg-[#F4FAF9] px-2.5 py-1 text-[11px] font-medium text-[#0F766E]">
              <ShieldCheck className="h-3.5 w-3.5" />
              Local-First
            </span>
          </div>

          {/* Thanh chuyển đổi chế độ Đăng nhập / Đăng ký */}
          <div className="mb-6 grid grid-cols-2 rounded-xl bg-[#F0F5F4] p-1">
            <button
              type="button"
              onClick={() => {
                setMode("login")
                setError("")
              }}
              className={`rounded-lg py-2 text-xs font-semibold transition-all ${
                mode === "login"
                  ? "bg-white text-[#0B1716] shadow-2xs"
                  : "text-[#5C7875] hover:text-[#0B1716]"
              }`}
            >
              Đăng nhập
            </button>
            <button
              type="button"
              onClick={() => {
                setMode("register")
                setError("")
              }}
              className={`rounded-lg py-2 text-xs font-semibold transition-all ${
                mode === "register"
                  ? "bg-white text-[#0B1716] shadow-2xs"
                  : "text-[#5C7875] hover:text-[#0B1716]"
              }`}
            >
              Đăng ký tài khoản
            </button>
          </div>

          <div>
            <h1 className="text-xl font-bold text-[#0B1716]">
              {mode === "login" ? "Chào mừng bạn quay lại" : "Tạo hồ sơ tri thức cá nhân"}
            </h1>
            <p className="mt-1 text-xs leading-relaxed text-[#647D7A]">
              {mode === "login"
                ? "Đăng nhập để truy cập kho tài liệu, notebook, thẻ học và lịch sử hội thoại AI của bạn."
                : "Điền thông tin cá nhân bên dưới để hệ thống khởi tạo không gian làm việc riêng biệt cho bạn."}
            </p>
          </div>

          {backendOnline === false ? (
            <Alert
              tone="error"
              className="mt-4"
              title="Backend chưa chạy"
              description="Mở cửa sổ mới và chạy start_app.bat (hoặc start_all.bat), đợi đến khi thấy cổng 8000 hoạt động rồi thử lại."
              action={
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={checkBackend}
                  loading={checkingBackend}
                  leftIcon={<RefreshCw className="h-3.5 w-3.5" />}
                >
                  Kiểm tra lại
                </Button>
              }
            />
          ) : null}

          <form onSubmit={handleSubmit} className="mt-5 space-y-4">
            {/* Các trường bổ sung khi ĐĂNG KÝ */}
            {mode === "register" ? (
              <>
                <div className="grid grid-cols-1 gap-3.5 sm:grid-cols-12">
                  <div className="sm:col-span-7">
                    <FormField label="Họ và tên đệm *">
                      <div className="relative">
                        <User className="pointer-events-none absolute top-1/2 left-3 h-3.5 w-3.5 -translate-y-1/2 text-[#7A9490]" />
                        <Input
                          type="text"
                          required
                          autoComplete="family-name"
                          value={lastName}
                          onChange={(e) => setLastName(e.target.value)}
                          placeholder="Nguyễn Văn"
                          className="pl-9"
                        />
                      </div>
                    </FormField>
                  </div>

                  <div className="sm:col-span-5">
                    <FormField label="Tên gọi *">
                      <div className="relative">
                        <User className="pointer-events-none absolute top-1/2 left-3 h-3.5 w-3.5 -translate-y-1/2 text-[#7A9490]" />
                        <Input
                          type="text"
                          required
                          autoComplete="given-name"
                          value={firstName}
                          onChange={(e) => setFirstName(e.target.value)}
                          placeholder="Minh"
                          className="pl-9"
                        />
                      </div>
                    </FormField>
                  </div>
                </div>

                {(lastName.trim() || firstName.trim()) ? (
                  <div className="flex items-center gap-2 rounded-lg bg-[#F4FAF9] px-3 py-1.5 text-xs text-[#0F766E]">
                    <CheckCircle2 className="h-3.5 w-3.5 shrink-0" />
                    <span>
                      Tên hiển thị trên hệ thống:{" "}
                      <strong className="font-semibold">
                        {`${lastName.trim()} ${firstName.trim()}`.trim()}
                      </strong>
                    </span>
                  </div>
                ) : null}
              </>
            ) : null}

            {/* Email */}
            <FormField label="Địa chỉ Email *">
              <div className="relative">
                <Mail className="pointer-events-none absolute top-1/2 left-3 h-3.5 w-3.5 -translate-y-1/2 text-[#7A9490]" />
                <Input
                  type="email"
                  required
                  autoComplete="email"
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  placeholder="ban@example.com"
                  className="pl-9"
                />
              </div>
            </FormField>

            {/* Số điện thoại + Vai trò + Đơn vị khi ĐĂNG KÝ */}
            {mode === "register" ? (
              <>
                <div className="grid grid-cols-1 gap-3.5 sm:grid-cols-2">
                  <FormField label="Số điện thoại" hint="Tùy chọn">
                    <div className="relative">
                      <Phone className="pointer-events-none absolute top-1/2 left-3 h-3.5 w-3.5 -translate-y-1/2 text-[#7A9490]" />
                      <Input
                        type="tel"
                        autoComplete="tel"
                        value={phone}
                        onChange={(e) => setPhone(e.target.value)}
                        placeholder="0905 123 456"
                        className="pl-9"
                      />
                    </div>
                  </FormField>

                  <FormField label="Vai trò của bạn">
                    <div className="relative">
                      <Briefcase className="pointer-events-none absolute top-1/2 left-3 z-10 h-3.5 w-3.5 -translate-y-1/2 text-[#7A9490]" />
                      <Select
                        value={roleTitle}
                        onChange={(e) => setRoleTitle(e.target.value)}
                        className="pl-9"
                      >
                        {ROLE_OPTIONS.map((role) => (
                          <option key={role} value={role}>
                            {role}
                          </option>
                        ))}
                      </Select>
                    </div>
                  </FormField>
                </div>

                <FormField label="Trường học / Cơ quan / Tổ chức" hint="Tùy chọn">
                  <div className="relative">
                    <Building2 className="pointer-events-none absolute top-1/2 left-3 h-3.5 w-3.5 -translate-y-1/2 text-[#7A9490]" />
                    <Input
                      type="text"
                      autoComplete="organization"
                      value={organization}
                      onChange={(e) => setOrganization(e.target.value)}
                      placeholder="VD: Trường ĐH Bách Khoa - ĐH Đà Nẵng"
                      className="pl-9"
                    />
                  </div>
                </FormField>
              </>
            ) : null}

            {/* Mật khẩu & Xác nhận mật khẩu */}
            <div className={mode === "register" ? "grid grid-cols-1 gap-3.5 sm:grid-cols-2" : ""}>
              <FormField
                label="Mật khẩu *"
                hint={mode === "register" ? "Tối thiểu 8 ký tự" : undefined}
              >
                <div className="relative">
                  <KeyRound className="pointer-events-none absolute top-1/2 left-3 h-3.5 w-3.5 -translate-y-1/2 text-[#7A9490]" />
                  <Input
                    type={showPassword ? "text" : "password"}
                    required
                    minLength={mode === "register" ? 8 : 1}
                    autoComplete={mode === "login" ? "current-password" : "new-password"}
                    value={password}
                    onChange={(event) => setPassword(event.target.value)}
                    placeholder="••••••••"
                    className="pr-9 pl-9"
                  />
                  <button
                    type="button"
                    tabIndex={-1}
                    onClick={() => setShowPassword((prev) => !prev)}
                    className="absolute top-1/2 right-2.5 -translate-y-1/2 rounded p-1 text-[#7A9490] hover:text-[#0B1716]"
                    aria-label={showPassword ? "Ẩn mật khẩu" : "Hiện mật khẩu"}
                  >
                    {showPassword ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
                  </button>
                </div>
              </FormField>

              {mode === "register" ? (
                <FormField label="Xác nhận mật khẩu *">
                  <div className="relative">
                    <KeyRound className="pointer-events-none absolute top-1/2 left-3 h-3.5 w-3.5 -translate-y-1/2 text-[#7A9490]" />
                    <Input
                      type={showConfirmPassword ? "text" : "password"}
                      required
                      minLength={8}
                      autoComplete="new-password"
                      value={confirmPassword}
                      onChange={(event) => setConfirmPassword(event.target.value)}
                      placeholder="••••••••"
                      className="pr-9 pl-9"
                    />
                    <button
                      type="button"
                      tabIndex={-1}
                      onClick={() => setShowConfirmPassword((prev) => !prev)}
                      className="absolute top-1/2 right-2.5 -translate-y-1/2 rounded p-1 text-[#7A9490] hover:text-[#0B1716]"
                      aria-label={showConfirmPassword ? "Ẩn mật khẩu" : "Hiện mật khẩu"}
                    >
                      {showConfirmPassword ? (
                        <EyeOff className="h-3.5 w-3.5" />
                      ) : (
                        <Eye className="h-3.5 w-3.5" />
                      )}
                    </button>
                  </div>
                </FormField>
              ) : null}
            </div>

            {/* Thanh đánh giá độ mạnh mật khẩu khi đăng ký */}
            {mode === "register" && password.length > 0 ? (
              <div className="space-y-1">
                <div className="flex items-center justify-between text-[11px]">
                  <span className="text-[#647D7A]">Độ mạnh mật khẩu:</span>
                  <span className="font-semibold text-[#0B1716]">{pwdStrength.label}</span>
                </div>
                <div className="grid grid-cols-4 gap-1.5">
                  {[1, 2, 3, 4].map((level) => (
                    <div
                      key={level}
                      className={`h-1.5 rounded-full transition-colors ${
                        pwdStrength.score >= level ? pwdStrength.colorClass : "bg-slate-200"
                      }`}
                    />
                  ))}
                </div>
              </div>
            ) : null}

            {/* Tuỳ chọn Duy trì đăng nhập khi ở chế độ Login */}
            {mode === "login" ? (
              <div className="flex items-center justify-between pt-0.5 text-xs">
                <label className="inline-flex cursor-pointer items-center gap-2 text-[#526B68] select-none">
                  <input
                    type="checkbox"
                    checked={rememberMe}
                    onChange={(e) => setRememberMe(e.target.checked)}
                    className="h-3.5 w-3.5 rounded border-[#B6C8C4] accent-[#0F766E]"
                  />
                  <span>Ghi nhớ đăng nhập (7 ngày)</span>
                </label>
              </div>
            ) : null}

            {error ? (
              <Alert tone="error" title="Không thể xác thực" description={error} />
            ) : null}

            <Button type="submit" className="w-full py-2.5" loading={submitting}>
              {mode === "login" ? "Đăng nhập vào Workspace" : "Hoàn tất đăng ký tài khoản"}
            </Button>
          </form>

          {googleEnabled ? (
            <>
              <div className="my-4 flex items-center gap-3 text-xs text-[#8AA29E]">
                <span className="h-px flex-1 bg-[#E2ECE9]" />
                <span>hoặc tiếp tục với</span>
                <span className="h-px flex-1 bg-[#E2ECE9]" />
              </div>
              <Button
                type="button"
                variant="outline"
                className="w-full"
                onClick={() => {
                  window.location.href = googleLoginUrl()
                }}
              >
                Đăng nhập bằng Google
              </Button>
            </>
          ) : null}

          <p className="mt-5 text-center text-xs text-[#647D7A]">
            {mode === "login" ? "Chưa có tài khoản cá nhân? " : "Đã có tài khoản trên hệ thống? "}
            <button
              type="button"
              className="font-semibold text-[#0F766E] hover:underline"
              onClick={() => {
                setMode(mode === "login" ? "register" : "login")
                setError("")
              }}
            >
              {mode === "login" ? "Đăng ký ngay" : "Đăng nhập"}
            </button>
          </p>
        </div>
      </div>
    </div>
  )
}
