import type {
  Citation,
  EvidenceItem,
  KnowledgeDocument,
  SourceDescriptor,
} from "@/types"

/**
 * Interface chuẩn bị cho việc lấy nội dung nguồn và đoạn trích từ Backend
 */
export interface SourceBackendAdapter {
  getDocumentById: (documentId: string) => Promise<KnowledgeDocument | null>
  getDocumentChunks: (
    documentId: string,
    page?: number,
  ) => Promise<Array<{ chunkId: string; pageNumber: number; content: string }>>
}

/**
 * Chuẩn hóa thông tin Evidence từ một Citation và danh sách tài liệu hiện có.
 * Ánh xạ dựa trên `sourceId` / `documentId` ổn định thay vì vị trí hiển thị.
 */
export function resolveCitationEvidence(
  citation: Citation,
  documents: KnowledgeDocument[],
): EvidenceItem {
  const stableId = citation.sourceId ?? citation.documentId ?? citation.url ?? `ref-${citation.refId}`

  if (citation.sourceKind === "web" || (!citation.documentId && citation.url)) {
    const source: SourceDescriptor = {
      id: stableId,
      title: citation.documentName || citation.url || "Nguồn Web",
      kind: "web",
      url: citation.url,
      exists: Boolean(citation.url || citation.snippet),
      isMock: citation.isMock ?? true,
    }

    return {
      citation,
      source,
      pageNumber: null,
      chunkId: null,
      snippet: citation.snippet,
      hasExactOffset: false,
    }
  }

  const matchedDoc = citation.documentId
    ? documents.find((d) => d.id === citation.documentId)
    : undefined

  const source: SourceDescriptor = matchedDoc
    ? {
        id: matchedDoc.id,
        title: matchedDoc.fileName,
        kind: "local",
        fileType: matchedDoc.fileType,
        workspaceId: matchedDoc.workspaceId,
        notebookId: matchedDoc.notebookId,
        exists: true,
        isMock: Boolean(matchedDoc.mock ?? citation.isMock),
      }
    : {
        id: stableId,
        title: citation.documentName || "Tài liệu không còn tồn tại",
        kind: "local",
        exists: false,
        isMock: Boolean(citation.isMock ?? true),
      }

  const chunkId =
    citation.chunkIndex != null ? `chunk-${citation.chunkIndex}` : null

  return {
    citation,
    source,
    pageNumber: citation.pageNumber,
    chunkId,
    snippet: citation.snippet,
    hasExactOffset: Boolean(citation.highlight && matchedDoc?.extractedText?.includes(citation.highlight)),
  }
}

/**
 * Tạo đường dẫn điều hướng sang Source Viewer kèm thông tin định vị nguồn và hội thoại gốc
 */
export function buildSourceViewerHref(
  citation: Citation,
  conversationId?: string,
): string | null {
  if (!citation.documentId) return null
  const params = new URLSearchParams()
  params.set("cite", String(citation.refId))
  if (citation.pageNumber != null) params.set("page", String(citation.pageNumber))
  if (citation.chunkIndex != null) params.set("chunk", String(citation.chunkIndex))
  if (conversationId) params.set("fromChat", conversationId)
  return `/documents/${citation.documentId}?${params.toString()}`
}

/**
 * Chia văn bản trích xuất của tài liệu thành các đoạn (chunks) có ID ổn định
 */
export interface ParsedDocumentChunk {
  id: string
  index: number
  page: number
  content: string
}

export function parseDocumentChunks(doc: KnowledgeDocument | undefined): ParsedDocumentChunk[] {
  if (!doc?.extractedText?.trim()) return []
  const parts = doc.extractedText.split(/\n\n+/).filter((p) => p.trim().length > 0)
  return parts.map((content, idx) => ({
    id: `chunk-${idx + 1}`,
    index: idx + 1,
    page: Math.min(Math.max(doc.pageCount || 1, 1), Math.floor(idx / 2) + 1),
    content: content.trim(),
  }))
}
