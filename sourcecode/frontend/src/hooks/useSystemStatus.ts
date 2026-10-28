import { useEffect } from "react"
import { useQuery } from "@tanstack/react-query"
import { fetchDocuments, fetchSystemStatus, fetchWorkspaces } from "@/services/api"
import { useAppStore } from "@/store/app-store"

export function useSystemStatus() {
  const setStatus = useAppStore((s) => s.setStatus)
  const mergeWorkspaces = useAppStore((s) => s.mergeWorkspacesFromBackend)
  const replaceDocs = useAppStore((s) => s.replaceDocumentsFromBackend)
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
    queryKey: ["system-status"],
    queryFn: async () => {
      try {
        const status = await fetchSystemStatus()
        setStatus(status)
        const ws = await fetchWorkspaces()
        mergeWorkspaces(ws)
        const target = ws.find((w) => w.id === current)?.id ?? ws[0]?.id
        if (target) {
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
