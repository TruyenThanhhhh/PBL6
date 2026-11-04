import { useEffect, useState } from "react"
import { Link, useNavigate } from "react-router-dom"
import { ArrowLeft, KeyRound, Mail, RefreshCw, Sparkles } from "lucide-react"
import { Alert } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { FormField, Input } from "@/components/ui/input"
import {
  googleLoginUrl,
  isBackendReachable,
  isGoogleAuthEnabled,
  login,
  register,
} from "@/services/auth-service"

type AuthMode = "login" | "register"

export function LoginPage() {
  const navigate = useNavigate()
  const [mode, setMode] = useState<AuthMode>("login")
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [confirmPassword, setConfirmPassword] = useState("")
  const [error, setError] = useState("")
  const [submitting, setSubmitting] = useState(false)
  const [googleEnabled, setGoogleEnabled] = useState(false)
  const [backendOnline, setBackendOnline] = useState<boolean | null>(null)
  const [checkingBackend, setCheckingBackend] = useState(false)

  const checkBackend = async () => {
    setCheckingBackend(true)
    const online = await isBackendReachable()
    setBackendOnline(online)
    setCheckingBackend(false)
    return online
  }

  useEffect(() => {
    let active = true
    isGoogleAuthEnabled().then((enabled) => {
      if (active) setGoogleEnabled(enabled)
    })
    isBackendReachable().then((online) => {
      if (active) setBackendOnline(online)
    })
    return () => {
      active = false
    }
  }, [])

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setError("")
    if (mode === "register" && password !== confirmPassword) {
      setError("Mật khẩu xác nhận không khớp.")
      return
    }
    if (password.length < 10) {
      setError("Mật khẩu cần tối thiểu 10 ký tự.")
      return
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
        await register(email.trim(), password)
        navigate("/onboarding", { replace: true })
        return
      } else {
        await login(email.trim(), password)
      }
      navigate("/hub", { replace: true })
    } catch (err) {
      setError(err instanceof Error ? err.message : "Không thể xác thực tài khoản.")
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-[#F1F5F4] px-4 py-10">
      <div className="w-full max-w-md">
        <Link
          to="/hub"
          className="mb-5 inline-flex items-center gap-1.5 text-xs font-medium text-[#526B68] hover:text-[#0B1716]"
        >
          <ArrowLeft className="h-3.5 w-3.5" />
          Tiếp tục với dữ liệu mô phỏng
        </Link>

        <div className="rounded-2xl border border-[#D5E6E2] bg-white p-7 shadow-[0_18px_50px_-24px_rgba(11,35,32,0.35)]">
          <div className="mb-6 flex items-center gap-2.5">
            <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-[#0F766E] text-white">
              <Sparkles className="h-4 w-4" />
            </span>
            <div>
              <p className="font-sans text-lg font-bold tracking-tight text-[#0B1716]">
                motivo<span className="text-[#0D9488]">.</span>
              </p>
              <p className="text-xs text-[#647D7A]">Personal AI Knowledge Platform</p>
            </div>
          </div>

          <h1 className="text-xl font-semibold text-[#0B1716]">
            {mode === "login" ? "Đăng nhập" : "Tạo tài khoản"}
          </h1>
          <p className="mt-1 text-xs text-[#647D7A]">
            {mode === "login"
              ? "Đăng nhập để đồng bộ workspace, tài liệu và lịch sử chat với backend."
              : "Tạo tài khoản mới để bắt đầu lưu tri thức cá nhân trên backend."}
          </p>

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
            <FormField label="Email">
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

            <FormField
              label="Mật khẩu"
              hint={mode === "register" ? "Tối thiểu 10 ký tự" : undefined}
            >
              <div className="relative">
                <KeyRound className="pointer-events-none absolute top-1/2 left-3 h-3.5 w-3.5 -translate-y-1/2 text-[#7A9490]" />
                <Input
                  type="password"
                  required
                  minLength={10}
                  autoComplete={mode === "login" ? "current-password" : "new-password"}
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  placeholder="••••••••••"
                  className="pl-9"
                />
              </div>
            </FormField>

            {mode === "register" ? (
              <FormField label="Xác nhận mật khẩu">
                <Input
                  type="password"
                  required
                  minLength={10}
                  autoComplete="new-password"
                  value={confirmPassword}
                  onChange={(event) => setConfirmPassword(event.target.value)}
                  placeholder="••••••••••"
                />
              </FormField>
            ) : null}

            {error ? (
              <Alert tone="error" title="Không thể xác thực" description={error} />
            ) : null}

            <Button type="submit" className="w-full" loading={submitting}>
              {mode === "login" ? "Đăng nhập" : "Tạo tài khoản"}
            </Button>
          </form>

          {googleEnabled ? (
            <Button
              type="button"
              variant="outline"
              className="mt-3 w-full"
              onClick={() => {
                window.location.href = googleLoginUrl()
              }}
            >
              Đăng nhập bằng Google
            </Button>
          ) : null}

          <p className="mt-5 text-center text-xs text-[#647D7A]">
            {mode === "login" ? "Chưa có tài khoản? " : "Đã có tài khoản? "}
            <button
              type="button"
              className="font-semibold text-[#0F766E] hover:underline"
              onClick={() => {
                setMode(mode === "login" ? "register" : "login")
                setError("")
              }}
            >
              {mode === "login" ? "Đăng ký" : "Đăng nhập"}
            </button>
          </p>
        </div>
      </div>
    </div>
  )
}
