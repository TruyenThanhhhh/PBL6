import type { Conversation, KnowledgeDocument, Note, Notebook } from "@/types"

export interface NotebookStats {
  documentCount: number
  noteCount: number
  /** Mốc mới nhất giữa ngày tạo notebook, tài liệu và ghi chú bên trong nó. */
  updatedAt: string
}

export type NotebookSort = "updated" | "name" | "documents"

export function getNotebookStats(
  notebook: Notebook,
  documents: KnowledgeDocument[],
  notes: Note[],
): NotebookStats {
  const docs = documents.filter((d) => d.notebookId === notebook.id)
  const ownNotes = notes.filter((n) => n.notebookId === notebook.id)
  const stamps = [notebook.createdAt, ...docs.map((d) => d.createdAt), ...ownNotes.map((n) => n.updatedAt)]
  return {
    documentCount: docs.length,
    noteCount: ownNotes.length,
    updatedAt: stamps.reduce((a, b) => (a > b ? a : b)),
  }
}

export function sortNotebookRows<T extends { notebook: Notebook; stats: NotebookStats }>(
  rows: T[],
  sort: NotebookSort,
): T[] {
  return [...rows].sort((a, b) => {
    if (sort === "name") return a.notebook.name.localeCompare(b.notebook.name, "vi")
    if (sort === "documents") return b.stats.documentCount - a.stats.documentCount
    return b.stats.updatedAt.localeCompare(a.stats.updatedAt)
  })
}

export function normalizeName(name: string) {
  return name.trim().toLocaleLowerCase("vi")
}

export function hasDuplicateName(existing: string[], candidate: string) {
  const target = normalizeName(candidate)
  return existing.some((name) => normalizeName(name) === target)
}

export interface WorkspaceCounts {
  notebooks: number
  documents: number
  notes: number
  conversations: number
}

export function getWorkspaceCounts(
  workspaceId: string,
  data: {
    notebooks: Notebook[]
    documents: KnowledgeDocument[]
    notes: Note[]
    conversations: Conversation[]
  },
): WorkspaceCounts {
  return {
    notebooks: data.notebooks.filter((n) => n.workspaceId === workspaceId).length,
    documents: data.documents.filter((d) => d.workspaceId === workspaceId).length,
    notes: data.notes.filter((n) => n.workspaceId === workspaceId).length,
    conversations: data.conversations.filter((c) => c.workspaceId === workspaceId).length,
  }
}

export function describeWorkspaceDeletion(counts: WorkspaceCounts) {
  return `Sẽ xóa khỏi giao diện: ${counts.notebooks} notebook, ${counts.documents} tài liệu, ${counts.notes} ghi chú, ${counts.conversations} hội thoại cùng quiz, flashcard và dự án nghiên cứu thuộc workspace. Tệp đã tải lên máy chủ (nếu có) không bị xóa. Thao tác này không thể hoàn tác.`
}
