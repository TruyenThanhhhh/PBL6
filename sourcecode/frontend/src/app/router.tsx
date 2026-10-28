import { Navigate, Route, Routes } from "react-router-dom"
import { AppShell } from "@/components/layout/AppShell"
import { PlaceholderPage } from "@/components/common/PlaceholderPage"
import { DashboardPage } from "@/features/dashboard/DashboardPage"
import { KnowledgeBasePage } from "@/features/workspaces/KnowledgeBasePage"
import { WorkspaceDetailPage } from "@/features/workspaces/WorkspaceDetailPage"
import { NotebookDetailPage } from "@/features/workspaces/NotebookDetailPage"
import { DocumentsPage } from "@/features/documents/DocumentsPage"
import { ChatPage } from "@/features/chat/ChatPage"
import { SourceViewerPage } from "@/features/source-viewer/SourceViewerPage"
import { StudyToolsPage } from "@/features/study-tools/StudyToolsPage"
import { SettingsPage } from "@/features/settings/SettingsPage"
import { DesignSystemPage } from "@/features/design-system/DesignSystemPage"

export function AppRouter() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="/dashboard" element={<DashboardPage />} />
        <Route path="/chat" element={<ChatPage />} />
        <Route path="/chat/:conversationId" element={<ChatPage />} />
        <Route path="/knowledge" element={<KnowledgeBasePage />} />
        <Route path="/knowledge/:workspaceId" element={<WorkspaceDetailPage />} />
        <Route path="/knowledge/:workspaceId/notebooks/:notebookId" element={<NotebookDetailPage />} />
        <Route path="/documents" element={<DocumentsPage />} />
        <Route path="/documents/:documentId" element={<SourceViewerPage />} />
        <Route path="/study" element={<StudyToolsPage />} />
        <Route path="/research" element={<Navigate to="/dashboard" replace />} />
        <Route path="/research/:projectId" element={<Navigate to="/dashboard" replace />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="/design-system" element={<DesignSystemPage />} />
        <Route path="/placeholder" element={<PlaceholderPage />} />
        <Route path="*" element={<PlaceholderPage />} />
      </Route>
    </Routes>
  )
}
