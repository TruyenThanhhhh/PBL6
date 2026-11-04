import { useEffect } from "react"
import { useQuery } from "@tanstack/react-query"
import { fetchDocuments, fetchSystemStatus, fetchWorkspaces } from "@/services/api"
import { fetchCurrentSession, getAuthToken } from "@/services/auth-service"
import { useAppStore } from "@/store/app-store"

export function useSystemStatus() {
  const setStatus = useAppStore((s) => s.setStatus)
  const replaceWorkspaces = useAppStore((s) => s.replaceWorkspacesFromBackend)
  const replaceDocs = useAppStore((s) => s.replaceDocumentsFromBackend)
  const setCurrent = useAppStore((s) => s.setCurrentWorkspace)
  const current = useAppStore((s) => s.currentWorkspaceId)

  useEffect(() => {
    const syncNet = () => {
      const prev = useAppStore.getState().status
      setStatus({ ...prev, internetOnline: navigator.onLine })
    }
    window.addEventListener("online", syncNet)
    window.addEventListener("offline", syncNet)
    return () => {
      window.removeEventListener("online", syncNet)
      window.removeEventListener("offline", syncNet)
    }
  }, [setStatus])

  return useQuery({
    queryKey: ["system-status", Boolean(getAuthToken())],
    queryFn: async () => {
      try {
        const status = await fetchSystemStatus()
        if (!getAuthToken()) {
          setStatus({
            ...status,
            usingMock: true,
            message: "Chưa đăng nhập — đang hiển thị dữ liệu mô phỏng.",
          })
          return status
        }
        const session = await fetchCurrentSession()
        if (!session) {
          setStatus({
            ...status,
            usingMock: true,
            message: "Phiên đăng nhập đã hết hạn — vui lòng đăng nhập lại.",
          })
          return status
        }
        setStatus(status)
        const ws = await fetchWorkspaces()
        replaceWorkspaces(ws)
        const target = ws.find((w) => w.id === current)?.id ?? ws[0]?.id
        if (target) {
          if (!ws.some((w) => w.id === current)) setCurrent(target)
          const docs = await fetchDocuments(target)
          replaceDocs(docs)
        }
        return status
      } catch {
        setStatus({
          backendOnline: false,
          ollamaRunning: false,
          ollamaModels: [],
          internetOnline: navigator.onLine,
          usingMock: true,
          message: "Không kết nối được backend. Đang dùng dữ liệu mô phỏng.",
        })
        return null
      }
    },
    refetchInterval: 20000,
  })
}
