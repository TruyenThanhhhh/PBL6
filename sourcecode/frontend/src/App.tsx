import { useEffect } from "react"
import { BrowserRouter } from "react-router-dom"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { AppRouter } from "@/app/router"
import { Toasts } from "@/components/common/Toasts"
import { useAppStore } from "@/store/app-store"

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 0, refetchOnWindowFocus: false } },
})

function ThemeAndToastProvider({ children }: { children: React.ReactNode }) {
  const theme = useAppStore((s) => s.theme)

  useEffect(() => {
    document.documentElement.classList.toggle("dark", theme === "dark")
  }, [theme])

  return (
    <>
      {children}
      <Toasts />
    </>
  )
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <ThemeAndToastProvider>
          <AppRouter />
        </ThemeAndToastProvider>
      </BrowserRouter>
    </QueryClientProvider>
  )
}
