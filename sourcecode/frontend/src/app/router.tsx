import { Navigate, Route, Routes } from "react-router-dom"
import { AppShell } from "@/components/layout/AppShell"
import { PlaceholderPage } from "@/components/common/PlaceholderPage"
import { WelcomePage } from "@/features/welcome/WelcomePage"
import { WorkspaceHubPage } from "@/features/workspaces/WorkspaceHubPage"
import { WorkspaceDetailPage } from "@/features/workspaces/WorkspaceDetailPage"
import { NotebookDetailPage } from "@/features/workspaces/NotebookDetailPage"
import { DocumentsPage } from "@/features/documents/DocumentsPage"
import { ChatPage } from "@/features/chat/ChatPage"
import { SourceViewerPage } from "@/features/source-viewer/SourceViewerPage"
import { StudyToolsPage } from "@/features/study-tools/StudyToolsPage"
import { SettingsPage } from "@/features/settings/SettingsPage"
import { DesignSystemPage } from "@/features/design-system/DesignSystemPage"
import { LoginPage } from "@/features/auth/LoginPage"

export function AppRouter() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />


      {/* Trang giới thiệu Welcome / Landing Page */}
      <Route path="/" element={<WelcomePage />} />
      <Route path="/welcome" element={<WelcomePage />} />


      {/* Workspace Hub (Dashboard) - Trang danh sách không gian làm việc */}
      <Route path="/hub" element={<WorkspaceHubPage />} />
      <Route path="/knowledge" element={<Navigate to="/hub" replace />} />

      {/* Workspace Studio - Không gian làm việc chuyên sâu khi chọn một Workspace */}
      <Route element={<AppShell />}>
        <Route path="/dashboard" element={<Navigate to="/chat" replace />} />
        <Route path="/studio" element={<ChatPage />} />
        <Route path="/chat" element={<ChatPage />} />
        <Route path="/chat/:conversationId" element={<ChatPage />} />
        <Route path="/knowledge/:workspaceId" element={<WorkspaceDetailPage />} />
        <Route path="/knowledge/:workspaceId/notebooks/:notebookId" element={<NotebookDetailPage />} />
        <Route path="/documents" element={<DocumentsPage />} />
        <Route path="/documents/:documentId" element={<SourceViewerPage />} />
        <Route path="/study" element={<StudyToolsPage />} />
        <Route path="/research" element={<Navigate to="/chat" replace />} />
        <Route path="/research/:projectId" element={<Navigate to="/chat" replace />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="/design-system" element={<DesignSystemPage />} />
        <Route path="/placeholder" element={<PlaceholderPage />} />
        <Route path="*" element={<PlaceholderPage />} />
      </Route>
    </Routes>
  )
}
