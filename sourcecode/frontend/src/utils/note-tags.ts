import type { Note } from "@/types"

export const SUGGESTED_NOTE_TAGS = [
  "#QuanTrong",
  "#CanOnTap",
  "#LyThuyet",
  "#BaiTap",
  "#DeThi",
  "#CongThuc",
] as const

const INLINE_TAG_RE = /(?:^|[\s(])(#[\p{L}\p{N}][\p{L}\p{N}_-]{0,39})/gu

/** Chuẩn hóa một chuỗi tag thành dạng #TenTag hợp lệ (hoặc null nếu rỗng). */
export function normalizeNoteTag(raw: string): string | null {
  const cleaned = (raw || "")
    .trim()
    .replace(/^#+/, "")
    .replace(/[^\p{L}\p{N}_-]+/gu, "")
    .slice(0, 40)
  if (!cleaned) return null
  return `#${cleaned}`
}

/** Tách các #hashtag viết trực tiếp trong nội dung hoặc tiêu đề (không bắt # Heading Markdown). */
export function extractInlineNoteTags(text: string): string[] {
  if (!text) return []
  const seen = new Map<string, string>()
  for (const match of text.matchAll(INLINE_TAG_RE)) {
    const normalized = normalizeNoteTag(match[1])
    if (!normalized) continue
    const key = normalized.toLowerCase()
    if (!seen.has(key)) seen.set(key, normalized)
  }
  return Array.from(seen.values())
}

/** Gộp tag tường minh của ghi chú và #hashtag nội tuyến, loại bỏ trùng lặp theo không phân biệt hoa/thường. */
export function mergeNoteTags(explicitTags?: string[] | null, textForHashtags = ""): string[] {
  const seen = new Map<string, string>()
  for (const raw of explicitTags ?? []) {
    const normalized = normalizeNoteTag(raw)
    if (!normalized) continue
    const key = normalized.toLowerCase()
    if (!seen.has(key)) seen.set(key, normalized)
  }
  for (const inlineTag of extractInlineNoteTags(textForHashtags)) {
    const key = inlineTag.toLowerCase()
    if (!seen.has(key)) seen.set(key, inlineTag)
  }
  return Array.from(seen.values())
}

export function getNoteTags(note: Pick<Note, "tags" | "title" | "content">): string[] {
  return mergeNoteTags(note.tags, `${note.title || ""} ${note.content || ""}`)
}
