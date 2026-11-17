import { useEffect, useMemo, useRef, useState } from "react"
import { Link } from "react-router-dom"
import {
  ArrowLeft,
  ArrowRight,
  BookOpen,
  Check,
  ChevronLeft,
  ChevronRight,
  Clock,
  ExternalLink,
  Filter,
  Layers,
  ListChecks,
  Pencil,
  Plus,
  RotateCcw,
  Search,
  Sparkles,
  Trash2,
  X,
} from "lucide-react"
import { ConfirmDialog, NameDialog } from "@/components/common/NameDialog"
import { Badge, Button, Dialog, Input, Select, Textarea } from "@/components/ui"
import {
  deleteStudyArtifactApi,
  fetchStudyArtifactsApi,
  saveStudyArtifactApi,
  updateStudyArtifactApi,
  type StudyArtifactRecord,
} from "@/services/api"
import {
  generateStudyFlashcardDeckAsync,
  type StudySourceContext,
} from "@/services/study-service"
import { useAppStore } from "@/store/app-store"
import { cn } from "@/utils/cn"
import { nowIso, relativeTime, uid } from "@/utils/format"
import type {
  Flashcard,
  FlashcardDeck,
  FlashcardStyle,
  KnowledgeDocument,
} from "@/types"

const CARD_STYLE_META: Record<
  FlashcardStyle,
  { label: string; frontHeader: string; backHeader: string; hint: string }
> = {
  term_definition: {
    label: "Thuật ngữ – Định nghĩa",
    frontHeader: "Mặt trước · Thuật ngữ / Khái niệm",
    backHeader: "Mặt sau · Định nghĩa & Luận giải",
    hint: "Nhấn để xem định nghĩa",
  },
  vocabulary: {
    label: "Từ vựng – Nghĩa",
    frontHeader: "Mặt trước · Từ vựng",
    backHeader: "Mặt sau · Nghĩa tiếng Việt & Cách dùng",
    hint: "Nhấn để xem nghĩa",
  },
  qa: {
    label: "Câu hỏi – Trả lời",
    frontHeader: "Mặt trước · Câu hỏi",
    backHeader: "Mặt sau · Đáp án & Giải thích",
    hint: "Nhấn để xem đáp án",
  },
  cloze: {
    label: "Điền khuyết – Ghi nhớ",
    frontHeader: "Mặt trước · Điền vào chỗ trống",
    backHeader: "Mặt sau · Từ khóa & Ngữ cảnh",
    hint: "Nhấn để kiểm tra đáp án",
  },
}

const SRS_INTERVALS_DAYS = [1, 3, 7, 14, 30]

function computeNextIntervalDays(currentDays: number): number {
  for (const d of SRS_INTERVALS_DAYS) {
    if (d > currentDays) return d
  }
  return 30
}

function isCardDue(card: Flashcard, nowMs: number): boolean {
  if (card.status === "review" || card.status === "new") return true
  if (!card.nextReviewAt) return false
  const dueMs = Date.parse(card.nextReviewAt)
  return !Number.isNaN(dueMs) && dueMs <= nowMs
}

function smartCardPriority(card: Flashcard, nowMs: number): number {
  if (card.status === "review") return 0
  if (card.status === "remembered" && isCardDue(card, nowMs)) return 1
  if (card.status === "new") return 2
  return 3
}

function sortCardsSmart(cards: Flashcard[], nowMs: number): Flashcard[] {
  return [...cards].sort((a, b) => {
    const rankDiff = smartCardPriority(a, nowMs) - smartCardPriority(b, nowMs)
    if (rankDiff !== 0) return rankDiff
    const aDue = a.nextReviewAt ? Date.parse(a.nextReviewAt) : 0
    const bDue = b.nextReviewAt ? Date.parse(b.nextReviewAt) : 0
    return aDue - bDue
  })
}

function formatSrsBadge(card: Flashcard, nowMs: number): string {
  if (card.status === "review") return "Ưu tiên ôn lại"
  if (card.status === "new") return "Thẻ mới"
  if (card.nextReviewAt) {
    const dueMs = Date.parse(card.nextReviewAt)
    if (!Number.isNaN(dueMs)) {
      if (dueMs <= nowMs) return "Đến hạn ôn SRS"
      const daysLeft = Math.max(1, Math.ceil((dueMs - nowMs) / 86_400_000))
      return `Ôn lại sau ${daysLeft} ngày`
    }
  }
  return card.intervalDays ? `Chu kỳ ${card.intervalDays} ngày` : "Đã nhớ"
}

function mapArtifactToDeck(record: StudyArtifactRecord): FlashcardDeck | null {
  if (record.artifact_type !== "flashcard_deck") return null
  const data = (record.data ?? {}) as Record<string, unknown>
  const rawCards = Array.isArray(data.cards) ? (data.cards as Flashcard[]) : []
  const rawStyle = String(data.cardStyle ?? "term_definition")
  const cardStyle: FlashcardStyle =
    rawStyle === "qa" || rawStyle === "vocabulary" || rawStyle === "cloze"
      ? rawStyle
      : "term_definition"

  return {
    id: record.id,
    workspaceId: record.workspace_id,
    documentId: record.document_id ?? null,
    documentName: typeof data.documentName === "string" ? data.documentName : null,
    title: record.title || "Bộ thẻ Flashcards",
    cardStyle,
    focusPrompt: typeof data.focusPrompt === "string" ? data.focusPrompt : undefined,
    cards: rawCards.map((c, idx) => ({
      ...c,
      id: c.id || `${record.id}-c-${idx + 1}`,
      workspaceId: record.workspace_id,
      deckId: record.id,
      status: c.status === "remembered" || c.status === "review" ? c.status : "new",
    })),
    createdAt: record.created_at || nowIso(),
    updatedAt:
      typeof data.updatedAt === "string"
        ? data.updatedAt
        : record.created_at || nowIso(),
    lastStudiedAt: typeof data.lastStudiedAt === "string" ? data.lastStudiedAt : null,
    isMock: Boolean(data.isMock),
  }
}

function buildDeckArtifactPayload(deck: FlashcardDeck) {
  return {
    documentName: deck.documentName ?? null,
    cardStyle: deck.cardStyle,
    focusPrompt: deck.focusPrompt ?? "",
    cards: deck.cards,
    updatedAt: deck.updatedAt,
    lastStudiedAt: deck.lastStudiedAt ?? null,
    isMock: Boolean(deck.isMock),
  }
}

function CardEditorForm({
  initialCard,
  documents,
  defaultDocId,
  onClose,
  onSave,
}: {
  initialCard: Flashcard | null
  documents: KnowledgeDocument[]
  defaultDocId: string | null
  onClose: () => void
  onSave: (values: {
    front: string
    back: string
    example: string
    documentId: string | null
    pageNumber: number
  }) => void
}) {
  const [front, setFront] = useState(initialCard?.front ?? "")
  const [back, setBack] = useState(initialCard?.back ?? "")
  const [example, setExample] = useState(initialCard?.example ?? "")
  const [docId, setDocId] = useState(
    initialCard?.citation?.documentId ?? initialCard?.documentId ?? defaultDocId ?? "",
  )
  const [pageNumber, setPageNumber] = useState(
    String(initialCard?.citation?.pageNumber ?? 1),
  )

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault()
        if (!front.trim() || !back.trim()) return
        const parsedPage = Math.max(1, Number.parseInt(pageNumber, 10) || 1)
        onSave({
          front: front.trim(),
          back: back.trim(),
          example: example.trim(),
          documentId: docId || null,
          pageNumber: parsedPage,
        })
      }}
      className="space-y-3.5"
    >
      <div className="space-y-1.5">
        <label htmlFor="fc-edit-front" className="block text-xs font-medium text-[#647C79]">
          Mặt trước (Thuật ngữ / Câu hỏi / Từ vựng)
        </label>
        <Textarea
          id="fc-edit-front"
          required
          rows={2}
          value={front}
          onChange={(e) => setFront(e.target.value)}
          placeholder="Nhập nội dung mặt trước..."
          className="text-sm"
        />
      </div>

      <div className="space-y-1.5">
        <label htmlFor="fc-edit-back" className="block text-xs font-medium text-[#647C79]">
          Mặt sau (Định nghĩa / Đáp án / Nghĩa)
        </label>
        <Textarea
          id="fc-edit-back"
          required
          rows={3}
          value={back}
          onChange={(e) => setBack(e.target.value)}
          placeholder="Nhập nội dung mặt sau..."
          className="text-sm"
        />
      </div>

      <div className="space-y-1.5">
        <label htmlFor="fc-edit-example" className="block text-xs font-medium text-[#647C79]">
          Ví dụ minh họa / Ghi chú thêm (không bắt buộc)
        </label>
        <Textarea
          id="fc-edit-example"
          rows={2}
          value={example}
          onChange={(e) => setExample(e.target.value)}
          placeholder="VD: Câu ví dụ thực tế hoặc ngữ cảnh áp dụng..."
          className="text-xs"
        />
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <div className="sm:col-span-2 space-y-1.5">
          <label htmlFor="fc-edit-doc" className="block text-xs font-medium text-[#647C79]">
            Tài liệu nguồn liên kết
          </label>
          <Select
            id="fc-edit-doc"
            value={docId}
            onChange={(e) => setDocId(e.target.value)}
            className="text-xs"
          >
            <option value="">Không gắn tài liệu cụ thể</option>
            {documents.map((d) => (
              <option key={d.id} value={d.id}>
                {d.fileName}
              </option>
            ))}
          </Select>
        </div>

        <div className="space-y-1.5">
          <label htmlFor="fc-edit-page" className="block text-xs font-medium text-[#647C79]">
            Số trang
          </label>
          <Input
            id="fc-edit-page"
            type="number"
            min={1}
            value={pageNumber}
            onChange={(e) => setPageNumber(e.target.value)}
            className="text-xs"
          />
        </div>
      </div>

      <div className="flex justify-end gap-2 pt-2 border-t border-[#DCE7E4]">
        <Button type="button" variant="outline" size="sm" onClick={onClose}>
          Hủy
        </Button>
        <Button
          type="submit"
          size="sm"
          disabled={!front.trim() || !back.trim()}
          className="bg-[#087F73] hover:bg-[#076b61] text-white"
        >
          {initialCard ? "Lưu thay đổi" : "Thêm vào bộ thẻ"}
        </Button>
      </div>
    </form>
  )
}

export function FlashcardsSection({
  workspaceId,
  documents,
  selectedDocId,
  onSelectDocId,
  decks,
  useBackendHistory,
}: {
  workspaceId: string
  documents: KnowledgeDocument[]
  selectedDocId: string
  onSelectDocId: (docId: string) => void
  decks: FlashcardDeck[]
  useBackendHistory: boolean
}) {
  const flashcards = useAppStore((s) => s.flashcards)
  const upsertFlashcardDeck = useAppStore((s) => s.upsertFlashcardDeck)
  const deleteFlashcardDeck = useAppStore((s) => s.deleteFlashcardDeck)
  const replaceWorkspaceFlashcardDecks = useAppStore(
    (s) => s.replaceWorkspaceFlashcardDecks,
  )
  const toast = useAppStore((s) => s.toast)

  // Form tạo bộ thẻ AI
  const [focusPrompt, setFocusPrompt] = useState("")
  const [cardStyle, setCardStyle] = useState<FlashcardStyle>("term_definition")
  const [countPreset, setCountPreset] = useState<string>("10")
  const [customCount, setCustomCount] = useState<string>("12")
  const [isGenerating, setIsGenerating] = useState(false)
  const abortRef = useRef<AbortController | null>(null)

  // Danh sách bộ thẻ
  const [deckSearch, setDeckSearch] = useState("")
  const [deckFilter, setDeckFilter] = useState<"all" | "review" | "mastered">("all")
  const [activeDeckId, setActiveDeckId] = useState<string | null>(null)
  const [newDeckDialogOpen, setNewDeckDialogOpen] = useState(false)
  const [renameDeckTarget, setRenameDeckTarget] = useState<FlashcardDeck | null>(null)
  const [deckToDelete, setDeckToDelete] = useState<FlashcardDeck | null>(null)

  // State học bộ thẻ
  const [studyFilter, setStudyFilter] = useState<"all" | "review" | "remembered">("all")
  const [smartReview, setSmartReview] = useState(true)
  const [sessionOrderIds, setSessionOrderIds] = useState<string[] | null>(null)
  const [cardIndex, setCardIndex] = useState(0)
  const [flipped, setFlipped] = useState(false)
  const [manageMode, setManageMode] = useState(false)
  const [cardSearch, setCardSearch] = useState("")
  const [editingCardModal, setEditingCardModal] = useState<{
    mode: "create" | "edit"
    card: Flashcard | null
  } | null>(null)
  const [cardToDelete, setCardToDelete] = useState<Flashcard | null>(null)

  const legacyMigratedRef = useRef(false)
  const [nowTick, setNowTick] = useState(() => Date.now())

  useEffect(() => {
    return () => {
      abortRef.current?.abort()
    }
  }, [])

  // Đồng bộ danh sách bộ thẻ từ Backend (hoặc gom thẻ lẻ cũ khi offline)
  useEffect(() => {
    const legacyCards = flashcards.filter((f) => f.workspaceId === workspaceId)
    if (!useBackendHistory) {
      if (!legacyMigratedRef.current && decks.length === 0 && legacyCards.length > 0) {
        legacyMigratedRef.current = true
        const now = nowIso()
        Promise.resolve().then(() => {
          upsertFlashcardDeck({
            id: uid("deck"),
            workspaceId,
            documentId: legacyCards[0]?.documentId ?? null,
            documentName: "Bộ thẻ khởi tạo",
            title: "Bộ thẻ ghi nhớ tổng hợp",
            cardStyle: "term_definition",
            cards: legacyCards,
            createdAt: now,
            updatedAt: now,
            isMock: legacyCards.some((c) => Boolean(c.isMock)),
          })
        })
      }
      return
    }

    let active = true
    fetchStudyArtifactsApi(workspaceId, "flashcard_deck")
      .then((res) => {
        if (!active) return
        const mapped = (res.artifacts ?? [])
          .map(mapArtifactToDeck)
          .filter((item): item is FlashcardDeck => item !== null)
        replaceWorkspaceFlashcardDecks(workspaceId, mapped)
      })
      .catch(() => {
        // Giữ dữ liệu hiện có nếu mạng tạm lỗi
      })
    return () => {
      active = false
    }
  }, [
    workspaceId,
    useBackendHistory,
    replaceWorkspaceFlashcardDecks,
    flashcards,
    decks.length,
    upsertFlashcardDeck,
  ])

  const effectiveCount = useMemo(() => {
    const raw =
      countPreset === "custom" ? Number.parseInt(customCount, 10) : Number(countPreset)
    if (Number.isNaN(raw)) return 10
    return Math.min(Math.max(raw, 1), 40)
  }, [countPreset, customCount])

  const activeDeck = useMemo(
    () => (activeDeckId ? decks.find((d) => d.id === activeDeckId) ?? null : null),
    [decks, activeDeckId],
  )

  const needReviewDecksCount = useMemo(
    () =>
      decks.filter((d) =>
        d.cards.some((c) => c.status === "review" || isCardDue(c, nowTick)),
      ).length,
    [decks, nowTick],
  )

  const masteredDecksCount = useMemo(
    () =>
      decks.filter(
        (d) => d.cards.length > 0 && d.cards.every((c) => c.status === "remembered"),
      ).length,
    [decks],
  )

  const filteredDecks = useMemo(() => {
    const q = deckSearch.trim().toLowerCase()
    return decks.filter((d) => {
      if (deckFilter === "review") {
        const hasPending = d.cards.some(
          (c) => c.status === "review" || isCardDue(c, nowTick),
        )
        if (!hasPending) return false
      } else if (deckFilter === "mastered") {
        const isDone =
          d.cards.length > 0 && d.cards.every((c) => c.status === "remembered")
        if (!isDone) return false
      }
      if (!q) return true
      return (
        d.title.toLowerCase().includes(q) ||
        (d.documentName ?? "").toLowerCase().includes(q) ||
        (d.focusPrompt ?? "").toLowerCase().includes(q)
      )
    })
  }, [decks, deckFilter, deckSearch, nowTick])

  const persistUpdateDeck = async (updated: FlashcardDeck) => {
    const withTime: FlashcardDeck = {
      ...updated,
      updatedAt: nowIso(),
    }
    upsertFlashcardDeck(withTime)
    if (!useBackendHistory) return
    try {
      await updateStudyArtifactApi(workspaceId, withTime.id, {
        title: withTime.title,
        data: buildDeckArtifactPayload(withTime),
      })
    } catch {
      try {
        const res = await saveStudyArtifactApi(workspaceId, {
          document_id: withTime.documentId,
          artifact_type: "flashcard_deck",
          title: withTime.title,
          data: buildDeckArtifactPayload(withTime),
        })
        const synced = mapArtifactToDeck(res.artifact)
        if (synced) {
          deleteFlashcardDeck(withTime.id)
          upsertFlashcardDeck(synced)
          if (activeDeckId === withTime.id) {
            setActiveDeckId(synced.id)
          }
        }
      } catch {
        // Giữ trong local store nếu tạm mất kết nối
      }
    }
  }

  const startStudySession = (
    deck: FlashcardDeck,
    filter: "all" | "review" | "remembered",
    useSmart: boolean,
    openManage = false,
  ) => {
    const nowMs = Date.now()
    setNowTick(nowMs)
    const ordered = useSmart ? sortCardsSmart(deck.cards, nowMs) : deck.cards
    setSessionOrderIds(ordered.map((c) => c.id))
    setStudyFilter(filter)
    setCardIndex(0)
    setFlipped(false)
    setManageMode(openManage)
    setCardSearch("")
    setActiveDeckId(deck.id)
  }

  const handleGenerateDeck = async () => {
    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller
    setIsGenerating(true)

    const activeDoc = selectedDocId
      ? documents.find((d) => d.id === selectedDocId) ?? null
      : null
    const ctx: StudySourceContext = {
      workspaceId,
      notebook: null,
      document: activeDoc,
      documentsInScope: activeDoc ? [activeDoc] : documents,
    }

    try {
      const generatedDeck = await generateStudyFlashcardDeckAsync(
        ctx,
        effectiveCount,
        focusPrompt,
        cardStyle,
        controller.signal,
      )
      if (controller.signal.aborted) return

      let savedDeck = generatedDeck
      if (useBackendHistory) {
        try {
          const res = await saveStudyArtifactApi(workspaceId, {
            document_id: generatedDeck.documentId,
            artifact_type: "flashcard_deck",
            title: generatedDeck.title,
            data: buildDeckArtifactPayload(generatedDeck),
          })
          const mapped = mapArtifactToDeck(res.artifact)
          if (mapped) savedDeck = mapped
        } catch {
          // Giữ deck trong store local
        }
      }

      upsertFlashcardDeck(savedDeck)
      startStudySession(savedDeck, "all", smartReview, false)

      toast({
        title: savedDeck.isMock
          ? `Đã tạo bộ "${savedDeck.title}" (Mô phỏng)`
          : `Đã tạo bộ ${savedDeck.cards.length} thẻ bằng AI`,
        description: `Kiểu thẻ: ${CARD_STYLE_META[savedDeck.cardStyle].label}`,
        tone: savedDeck.isMock ? "info" : "success",
      })
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") return
      const msg = err instanceof Error && err.message ? err.message : "Vui lòng thử lại sau."
      toast({ title: "Không thể tạo bộ Flashcards", description: msg, tone: "error" })
    } finally {
      if (abortRef.current === controller) {
        abortRef.current = null
        setIsGenerating(false)
      }
    }
  }

  const handleCreateManualDeck = async (title: string) => {
    const activeDoc = selectedDocId
      ? documents.find((d) => d.id === selectedDocId) ?? null
      : null
    const now = nowIso()
    const draft: FlashcardDeck = {
      id: uid("deck"),
      workspaceId,
      documentId: activeDoc?.id ?? null,
      documentName: activeDoc?.fileName ?? null,
      title,
      cardStyle,
      cards: [],
      createdAt: now,
      updatedAt: now,
      isMock: false,
    }

    let saved = draft
    if (useBackendHistory) {
      try {
        const res = await saveStudyArtifactApi(workspaceId, {
          document_id: draft.documentId,
          artifact_type: "flashcard_deck",
          title: draft.title,
          data: buildDeckArtifactPayload(draft),
        })
        const mapped = mapArtifactToDeck(res.artifact)
        if (mapped) saved = mapped
      } catch {
        // Fallback local store
      }
    }

    upsertFlashcardDeck(saved)
    startStudySession(saved, "all", smartReview, true)
    setEditingCardModal({ mode: "create", card: null })
    toast({ title: `Đã tạo bộ thẻ "${saved.title}"`, tone: "success" })
  }

  const handleConfirmDeleteDeck = async () => {
    if (!deckToDelete) return
    const target = deckToDelete
    try {
      if (useBackendHistory) {
        await deleteStudyArtifactApi(workspaceId, target.id)
      }
      deleteFlashcardDeck(target.id)
      if (activeDeckId === target.id) {
        setActiveDeckId(null)
      }
      setDeckToDelete(null)
      toast({ title: `Đã xóa bộ thẻ "${target.title}"`, tone: "info" })
    } catch (err) {
      const msg = err instanceof Error && err.message ? err.message : "Vui lòng thử lại sau."
      toast({ title: "Không thể xóa bộ thẻ", description: msg, tone: "error" })
    }
  }

  // Danh sách thẻ theo thứ tự phiên học & tab lọc hiện tại
  const orderedSessionCards = useMemo(() => {
    if (!activeDeck) return []
    const byId = new Map(activeDeck.cards.map((c) => [c.id, c]))
    const result: Flashcard[] = []
    if (sessionOrderIds && sessionOrderIds.length > 0) {
      for (const id of sessionOrderIds) {
        const c = byId.get(id)
        if (c) {
          result.push(c)
          byId.delete(id)
        }
      }
    }
    for (const c of byId.values()) {
      result.push(c)
    }
    return result
  }, [activeDeck, sessionOrderIds])

  const filteredStudyCards = useMemo(() => {
    return orderedSessionCards.filter((c) => {
      if (studyFilter === "review") return c.status === "review"
      if (studyFilter === "remembered") return c.status === "remembered"
      return true
    })
  }, [orderedSessionCards, studyFilter])

  const safeCardIdx =
    filteredStudyCards.length > 0
      ? Math.min(cardIndex, filteredStudyCards.length - 1)
      : 0
  const currentCard = filteredStudyCards[safeCardIdx] ?? null

  // Hỗ trợ phím tắt lật / chuyển thẻ khi đang học
  useEffect(() => {
    if (
      !activeDeck ||
      !currentCard ||
      manageMode ||
      editingCardModal ||
      renameDeckTarget ||
      deckToDelete ||
      cardToDelete
    ) {
      return
    }
    const total = filteredStudyCards.length
    if (total === 0) return

    const onKeyDown = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement | null)?.tagName
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return
      if (e.code === "Space") {
        e.preventDefault()
        setFlipped((v) => !v)
      } else if (e.key === "ArrowLeft") {
        e.preventDefault()
        setFlipped(false)
        setCardIndex((prev) => (prev - 1 + total) % total)
      } else if (e.key === "ArrowRight") {
        e.preventDefault()
        setFlipped(false)
        setCardIndex((prev) => (prev + 1) % total)
      }
    }
    window.addEventListener("keydown", onKeyDown)
    return () => window.removeEventListener("keydown", onKeyDown)
  }, [
    activeDeck,
    currentCard,
    manageMode,
    editingCardModal,
    renameDeckTarget,
    deckToDelete,
    cardToDelete,
    filteredStudyCards.length,
  ])

  const handleMarkCardStatus = async (
    card: Flashcard,
    outcome: "remembered" | "review",
  ) => {
    if (!activeDeck) return
    const nowMs = Date.now()
    setNowTick(nowMs)
    const now = new Date(nowMs).toISOString()

    const nextInterval =
      outcome === "remembered"
        ? computeNextIntervalDays(card.intervalDays ?? 0)
        : 0
    const nextReviewAt =
      outcome === "remembered"
        ? new Date(nowMs + nextInterval * 86_400_000).toISOString()
        : now

    const updatedCards = activeDeck.cards.map((c) =>
      c.id === card.id
        ? {
            ...c,
            status: outcome,
            reviewCount: (c.reviewCount ?? 0) + 1,
            intervalDays: nextInterval,
            lastReviewedAt: now,
            nextReviewAt,
          }
        : c,
    )

    const nextLenAfterFilter = updatedCards.filter((c) => {
      if (studyFilter === "review") return c.status === "review"
      if (studyFilter === "remembered") return c.status === "remembered"
      return true
    }).length

    setFlipped(false)
    if (nextLenAfterFilter === 0) {
      setCardIndex(0)
    } else if (
      (studyFilter === "review" && outcome === "remembered") ||
      (studyFilter === "remembered" && outcome === "review")
    ) {
      setCardIndex((prev) => Math.min(prev, nextLenAfterFilter - 1))
    } else {
      setCardIndex((prev) => (prev + 1) % nextLenAfterFilter)
    }

    await persistUpdateDeck({
      ...activeDeck,
      cards: updatedCards,
      lastStudiedAt: now,
    })
  }

  const handleSaveCardForm = async (values: {
    front: string
    back: string
    example: string
    documentId: string | null
    pageNumber: number
  }) => {
    if (!activeDeck || !editingCardModal) return
    const linkedDoc = values.documentId
      ? documents.find((d) => d.id === values.documentId) ?? null
      : null

    const nextCitation = linkedDoc
      ? {
          documentId: linkedDoc.id,
          documentName: linkedDoc.fileName,
          pageNumber: values.pageNumber,
          chunkIndex: editingCardModal.card?.citation?.chunkIndex ?? 0,
          snippet: editingCardModal.card?.citation?.snippet,
        }
      : null

    if (editingCardModal.mode === "edit" && editingCardModal.card) {
      const targetId = editingCardModal.card.id
      const updatedCards = activeDeck.cards.map((c) =>
        c.id === targetId
          ? {
              ...c,
              front: values.front,
              back: values.back,
              example: values.example || undefined,
              documentId: values.documentId,
              citation: nextCitation,
            }
          : c,
      )
      setEditingCardModal(null)
      await persistUpdateDeck({ ...activeDeck, cards: updatedCards })
      toast({ title: "Đã cập nhật thẻ Flashcard", tone: "success" })
      return
    }

    const newCard: Flashcard = {
      id: uid("fc"),
      workspaceId,
      deckId: activeDeck.id,
      documentId: values.documentId,
      front: values.front,
      back: values.back,
      example: values.example || undefined,
      cardStyle: activeDeck.cardStyle,
      citation: nextCitation,
      status: "new",
      reviewCount: 0,
      intervalDays: 0,
      isMock: false,
    }
    const updatedCards = [newCard, ...activeDeck.cards]
    setSessionOrderIds((prev) => [newCard.id, ...(prev ?? [])])
    setCardIndex(0)
    setFlipped(false)
    setEditingCardModal(null)
    await persistUpdateDeck({ ...activeDeck, cards: updatedCards })
    toast({ title: "Đã thêm thẻ mới vào bộ", tone: "success" })
  }

  const handleConfirmDeleteCard = async () => {
    if (!activeDeck || !cardToDelete) return
    const remaining = activeDeck.cards.filter((c) => c.id !== cardToDelete.id)
    setCardToDelete(null)
    setFlipped(false)
    setCardIndex((prev) => Math.max(0, Math.min(prev, remaining.length - 1)))
    await persistUpdateDeck({ ...activeDeck, cards: remaining })
    toast({ title: "Đã xóa thẻ khỏi bộ", tone: "info" })
  }

  const handleDeduplicateCards = async () => {
    if (!activeDeck) return
    const seen = new Map<string, Flashcard>()
    const deduped: Flashcard[] = []
    let removed = 0
    for (const card of activeDeck.cards) {
      const key = card.front.trim().toLowerCase().replace(/\s+/g, " ")
      if (!seen.has(key)) {
        seen.set(key, card)
        deduped.push(card)
      } else {
        removed += 1
      }
    }
    if (removed === 0) {
      toast({ title: "Không có thẻ trùng lặp trong bộ này", tone: "info" })
      return
    }
    setCardIndex(0)
    await persistUpdateDeck({ ...activeDeck, cards: deduped })
    toast({ title: `Đã loại bỏ ${removed} thẻ trùng lặp`, tone: "success" })
  }

  // ============================================================================
  // CHẾ ĐỘ CHI TIẾT BỘ THẺ: HỌC THẺ / QUẢN LÝ & CHỈNH SỬA THẺ
  // ============================================================================
  if (activeDeck) {
    const totalCards = activeDeck.cards.length
    const rememberedCount = activeDeck.cards.filter(
      (c) => c.status === "remembered",
    ).length
    const reviewCount = activeDeck.cards.filter((c) => c.status === "review").length
    const dueCount = activeDeck.cards.filter((c) => isCardDue(c, nowTick)).length
    const styleMeta = CARD_STYLE_META[activeDeck.cardStyle]

    const searchQ = cardSearch.trim().toLowerCase()
    const managedCards = activeDeck.cards.filter((c) => {
      if (!searchQ) return true
      return (
        c.front.toLowerCase().includes(searchQ) ||
        c.back.toLowerCase().includes(searchQ) ||
        (c.example ?? "").toLowerCase().includes(searchQ)
      )
    })

    const matchedDoc = currentCard?.citation?.documentId
      ? documents.find((d) => d.id === currentCard.citation?.documentId)
      : undefined
    const citationHref =
      currentCard?.citation?.documentId && matchedDoc && !matchedDoc.mock
        ? `/documents/${currentCard.citation.documentId}?page=${currentCard.citation.pageNumber ?? 1}${
            currentCard.citation.chunkIndex != null
              ? `&chunk=${currentCard.citation.chunkIndex}`
              : ""
          }`
        : null

    return (
      <div className="space-y-5">
        {/* Header bộ thẻ (thiết kế sạch, cân đối theo ảnh minh họa) */}
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between border-b border-[#DCE7E4] pb-4">
          <div className="min-w-0 space-y-1">
            <button
              type="button"
              onClick={() => setActiveDeckId(null)}
              className="inline-flex items-center gap-1.5 text-xs font-semibold text-[#087F73] hover:underline"
            >
              <ArrowLeft className="h-3.5 w-3.5" />
              Danh sách bộ thẻ
            </button>

            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-lg sm:text-xl font-bold text-[#172B29] break-words">
                {activeDeck.title}
              </h2>
              <button
                type="button"
                onClick={() => setRenameDeckTarget(activeDeck)}
                className="rounded-lg p-1 text-[#647C79] hover:bg-[#F1F6F5] hover:text-[#172B29]"
                title="Đổi tên bộ thẻ"
                aria-label="Đổi tên bộ thẻ"
              >
                <Pencil className="h-3.5 w-3.5" />
              </button>
              <Badge tone="accent">{styleMeta.label}</Badge>
              {activeDeck.isMock ? <Badge tone="neutral">Mô phỏng</Badge> : null}
            </div>

            <p className="text-xs text-[#647C79]">
              {totalCards} thẻ · {activeDeck.documentName || "Toàn bộ workspace"}
              {dueCount > 0 ? ` · ${dueCount} thẻ đến hạn ôn SRS` : ""}
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2 shrink-0">
            <Button
              variant="outline"
              size="sm"
              className="rounded-full"
              leftIcon={<Plus className="h-3.5 w-3.5" />}
              onClick={() => setEditingCardModal({ mode: "create", card: null })}
            >
              Thêm thẻ
            </Button>
            <Button
              variant={manageMode ? "default" : "outline"}
              size="sm"
              className={cn(
                "rounded-full",
                manageMode ? "bg-[#087F73] text-white hover:bg-[#076b61]" : "",
              )}
              leftIcon={<ListChecks className="h-3.5 w-3.5" />}
              onClick={() => setManageMode((v) => !v)}
            >
              {manageMode ? "Quay lại học thẻ" : `Quản lý thẻ (${totalCards})`}
            </Button>
            {!manageMode && totalCards > 0 ? (
              <Button
                variant="outline"
                size="sm"
                className="rounded-full"
                leftIcon={<RotateCcw className="h-3.5 w-3.5" />}
                onClick={() => startStudySession(activeDeck, studyFilter, smartReview, false)}
              >
                Học lại
              </Button>
            ) : null}
          </div>
        </div>

        {/* 3 khối chỉ số tiến độ (KPI strip nâng cấp từ ảnh minh họa) */}
        <div className="grid grid-cols-3 gap-3">
          <div className="rounded-2xl border border-[#DCE7E4] bg-[#F9FCFB] px-4 py-3 text-center">
            <div className="text-xl sm:text-2xl font-bold text-[#172B29]">{totalCards}</div>
            <div className="mt-0.5 text-[11px] font-medium text-[#647C79]">Tổng thẻ</div>
          </div>
          <div className="rounded-2xl border border-emerald-200/80 bg-emerald-50/50 px-4 py-3 text-center">
            <div className="text-xl sm:text-2xl font-bold text-emerald-700">
              {rememberedCount}
            </div>
            <div className="mt-0.5 text-[11px] font-medium text-emerald-800/80">
              Đã nhớ{totalCards > 0 ? ` (${Math.round((rememberedCount / totalCards) * 100)}%)` : ""}
            </div>
          </div>
          <div className="rounded-2xl border border-amber-200/80 bg-amber-50/50 px-4 py-3 text-center">
            <div className="text-xl sm:text-2xl font-bold text-amber-800">{reviewCount}</div>
            <div className="mt-0.5 text-[11px] font-medium text-amber-900/80">Cần ôn</div>
          </div>
        </div>

        {manageMode ? (
          /* CHẾ ĐỘ QUẢN LÝ, SỬA, XÓA & LỌC TRÙNG THẺ TRONG BỘ */
          <div className="space-y-4">
            <div className="flex flex-col gap-2.5 sm:flex-row sm:items-center sm:justify-between">
              <div className="relative flex-1 max-w-md">
                <Search className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-[#647C79]" />
                <Input
                  value={cardSearch}
                  onChange={(e) => setCardSearch(e.target.value)}
                  placeholder="Tìm kiếm theo mặt trước, mặt sau hoặc ví dụ..."
                  className="h-9 pl-8 text-xs bg-white"
                />
              </div>

              <div className="flex flex-wrap items-center gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  leftIcon={<Filter className="h-3.5 w-3.5" />}
                  onClick={() => void handleDeduplicateCards()}
                >
                  Lọc thẻ trùng lặp
                </Button>
                <Button
                  size="sm"
                  leftIcon={<Plus className="h-3.5 w-3.5" />}
                  onClick={() => setEditingCardModal({ mode: "create", card: null })}
                  className="bg-[#087F73] hover:bg-[#076b61] text-white"
                >
                  + Thêm thẻ
                </Button>
              </div>
            </div>

            {managedCards.length === 0 ? (
              <p className="rounded-2xl border border-dashed border-[#DCE7E4] bg-[#F9FCFB] px-4 py-8 text-center text-xs text-[#647C79]">
                {totalCards === 0
                  ? "Bộ thẻ này chưa có thẻ nào. Hãy bấm + Thêm thẻ để tạo."
                  : "Không tìm thấy thẻ nào khớp với từ khóa tìm kiếm."}
              </p>
            ) : (
              <div className="space-y-2.5">
                {managedCards.map((card, idx) => (
                  <div
                    key={card.id}
                    className="rounded-xl border border-[#DCE7E4] bg-white p-4 transition-colors hover:border-[#087F73]/40 space-y-2"
                  >
                    <div className="flex flex-wrap items-start justify-between gap-2">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="inline-flex h-5 min-w-5 items-center justify-center rounded-md bg-[#F1F6F5] px-1.5 text-[11px] font-bold text-[#172B29]">
                          #{idx + 1}
                        </span>
                        <Badge
                          tone={
                            card.status === "remembered"
                              ? "success"
                              : card.status === "review"
                                ? "warning"
                                : "neutral"
                          }
                        >
                          {card.status === "remembered"
                            ? "Đã nhớ"
                            : card.status === "review"
                              ? "Cần ôn"
                              : "Thẻ mới"}
                        </Badge>
                        {card.citation?.documentName ? (
                          <span className="text-[11px] text-[#647C79]">
                            {card.citation.documentName} · Trang {card.citation.pageNumber ?? 1}
                          </span>
                        ) : null}
                      </div>

                      <div className="flex items-center gap-1">
                        <Button
                          variant="ghost"
                          size="sm"
                          className="h-7 px-2 text-xs text-[#647C79] hover:text-[#087F73]"
                          leftIcon={<Pencil className="h-3 w-3" />}
                          onClick={() => setEditingCardModal({ mode: "edit", card })}
                        >
                          Sửa
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-7 w-7 text-[#647C79] hover:text-red-600"
                          onClick={() => setCardToDelete(card)}
                          aria-label="Xóa thẻ"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </Button>
                      </div>
                    </div>

                    <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 pt-1">
                      <div className="rounded-lg bg-[#F9FCFB] px-3 py-2 border border-[#DCE7E4]/60">
                        <div className="text-[10px] font-bold uppercase tracking-wider text-[#647C79]">
                          Mặt trước
                        </div>
                        <p className="mt-0.5 text-sm font-semibold text-[#172B29] break-words">
                          {card.front}
                        </p>
                      </div>
                      <div className="rounded-lg bg-[#F4FAF9] px-3 py-2 border border-[#DCE7E4]/60">
                        <div className="text-[10px] font-bold uppercase tracking-wider text-[#087F73]">
                          Mặt sau
                        </div>
                        <p className="mt-0.5 text-sm text-[#172B29] break-words">{card.back}</p>
                        {card.example ? (
                          <p className="mt-1 text-[11px] italic text-[#647C79]">
                            Ví dụ: {card.example}
                          </p>
                        ) : null}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        ) : (
          /* CHẾ ĐỘ HỌC FLASHCARDS NÂNG CAO */
          <div className="space-y-4">
            {/* Thanh Segmented Tabs (Tất cả / Cần ôn / Đã nhớ) + Bật/tắt Ôn tập thông minh */}
            <div className="flex flex-col gap-2.5 sm:flex-row sm:items-center sm:justify-between">
              <div className="grid flex-1 grid-cols-3 rounded-full bg-[#F1F6F5] p-1">
                {(
                  [
                    { id: "all", label: `Tất cả (${totalCards})` },
                    { id: "review", label: `Cần ôn (${reviewCount})` },
                    { id: "remembered", label: `Đã nhớ (${rememberedCount})` },
                  ] as const
                ).map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => {
                      setStudyFilter(item.id)
                      setCardIndex(0)
                      setFlipped(false)
                    }}
                    className={cn(
                      "rounded-full px-3 py-1.5 text-xs font-semibold transition-all",
                      studyFilter === item.id
                        ? "bg-white text-[#172B29] shadow-xs"
                        : "text-[#647C79] hover:text-[#172B29]",
                    )}
                  >
                    {item.label}
                  </button>
                ))}
              </div>

              <button
                type="button"
                onClick={() => {
                  const next = !smartReview
                  setSmartReview(next)
                  startStudySession(activeDeck, studyFilter, next, false)
                }}
                className={cn(
                  "inline-flex items-center justify-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-medium transition-colors shrink-0",
                  smartReview
                    ? "border-[#087F73]/40 bg-[#E6F3F1] text-[#087F73]"
                    : "border-[#DCE7E4] bg-white text-[#647C79] hover:text-[#172B29]",
                )}
                title="Ưu tiên thẻ đánh dấu Cần ôn và thẻ đến hạn Spaced Repetition lên đầu"
              >
                <Clock className="h-3.5 w-3.5" />
                <span>Ôn thông minh SRS: {smartReview ? "Bật" : "Tắt"}</span>
              </button>
            </div>

            {!currentCard ? (
              <div className="rounded-2xl border border-dashed border-[#DCE7E4] bg-[#F9FCFB] px-6 py-10 text-center space-y-3">
                <p className="text-sm font-semibold text-[#172B29]">
                  {totalCards === 0
                    ? "Bộ thẻ này chưa có thẻ nào."
                    : studyFilter === "review"
                      ? "Tuyệt vời! Bạn đã ôn hết các thẻ Cần ôn."
                      : "Chưa có thẻ nào ở trạng thái Đã nhớ."}
                </p>
                <div className="flex flex-wrap items-center justify-center gap-2">
                  {totalCards === 0 ? (
                    <Button
                      size="sm"
                      leftIcon={<Plus className="h-3.5 w-3.5" />}
                      onClick={() => setEditingCardModal({ mode: "create", card: null })}
                      className="bg-[#087F73] hover:bg-[#076b61] text-white"
                    >
                      Thêm thẻ đầu tiên
                    </Button>
                  ) : (
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => {
                        setStudyFilter("all")
                        setCardIndex(0)
                        setFlipped(false)
                      }}
                    >
                      Xem tất cả thẻ
                    </Button>
                  )}
                </div>
              </div>
            ) : (
              <div className="mx-auto max-w-2xl space-y-4">
                {/* Bộ đếm + thanh tiến trình phiên học */}
                <div className="space-y-1.5">
                  <div className="flex items-center justify-between text-xs text-[#647C79]">
                    <span>
                      Thẻ{" "}
                      <strong className="text-[#172B29]">
                        {safeCardIdx + 1} / {filteredStudyCards.length}
                      </strong>
                    </span>
                    <span className="inline-flex items-center gap-1.5 text-[11px]">
                      <Clock className="h-3 w-3 text-[#087F73]" />
                      {formatSrsBadge(currentCard, nowTick)}
                    </span>
                  </div>
                  <div className="h-1.5 w-full overflow-hidden rounded-full bg-[#EAF2F0]">
                    <div
                      className="h-full rounded-full bg-[#087F73] transition-all duration-300"
                      style={{
                        width: `${Math.round(((safeCardIdx + 1) / filteredStudyCards.length) * 100)}%`,
                      }}
                    />
                  </div>
                </div>

                {/* Khung thẻ Flashcard lật tương tác */}
                <div
                  role="button"
                  tabIndex={0}
                  onClick={() => setFlipped((v) => !v)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      e.preventDefault()
                      setFlipped((v) => !v)
                    }
                  }}
                  className={cn(
                    "group relative flex min-h-[270px] sm:min-h-[300px] w-full cursor-pointer flex-col justify-between rounded-3xl border-2 p-5 sm:p-7 transition-all duration-200 select-none",
                    flipped
                      ? "border-[#087F73] bg-gradient-to-b from-[#F4FAF9] to-white shadow-md shadow-[#087F73]/10"
                      : "border-[#DCE7E4] bg-white shadow-xs hover:border-[#087F73]/50 hover:shadow-md",
                  )}
                >
                  {/* Hàng trên của thẻ: Trạng thái · Nhãn mặt thẻ · Nút sửa/xóa nhanh */}
                  <div className="flex items-center justify-between gap-2">
                    <Badge
                      tone={
                        currentCard.status === "remembered"
                          ? "success"
                          : currentCard.status === "review"
                            ? "warning"
                            : "neutral"
                      }
                    >
                      {currentCard.status === "remembered"
                        ? "Đã nhớ"
                        : currentCard.status === "review"
                          ? "Cần ôn"
                          : "Mới"}
                    </Badge>

                    <span
                      className={cn(
                        "rounded-full px-3 py-1 text-[10px] sm:text-[11px] font-bold uppercase tracking-wider",
                        flipped
                          ? "bg-[#087F73] text-white"
                          : "bg-[#F1F6F5] text-[#647C79]",
                      )}
                    >
                      {flipped ? styleMeta.backHeader : styleMeta.frontHeader}
                    </span>

                    <div
                      className="flex items-center gap-1"
                      onClick={(e) => e.stopPropagation()}
                    >
                      <button
                        type="button"
                        onClick={() =>
                          setEditingCardModal({ mode: "edit", card: currentCard })
                        }
                        className="rounded-lg p-1.5 text-[#647C79] hover:bg-[#F1F6F5] hover:text-[#087F73]"
                        title="Chỉnh sửa thẻ này"
                        aria-label="Chỉnh sửa thẻ này"
                      >
                        <Pencil className="h-3.5 w-3.5" />
                      </button>
                      <button
                        type="button"
                        onClick={() => setCardToDelete(currentCard)}
                        className="rounded-lg p-1.5 text-[#647C79] hover:bg-red-50 hover:text-red-600"
                        title="Xóa thẻ này"
                        aria-label="Xóa thẻ này"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  </div>

                  {/* Nội dung chính giữa thẻ */}
                  <div className="my-auto py-4 text-center space-y-3">
                    <p
                      className={cn(
                        "font-bold leading-relaxed text-[#172B29] break-words",
                        flipped ? "text-base sm:text-xl" : "text-xl sm:text-2xl",
                      )}
                    >
                      {flipped ? currentCard.back : currentCard.front}
                    </p>

                    {flipped && currentCard.example ? (
                      <div className="mx-auto max-w-lg rounded-xl border border-[#DCE7E4] bg-white/90 px-3.5 py-2 text-xs text-[#647C79]">
                        <span className="font-semibold text-[#087F73]">Ví dụ / Ngữ cảnh: </span>
                        <span className="text-[#172B29]">{currentCard.example}</span>
                      </div>
                    ) : null}

                    {flipped && currentCard.citation?.documentName ? (
                      <div
                        className="flex items-center justify-center pt-1"
                        onClick={(e) => e.stopPropagation()}
                      >
                        {citationHref ? (
                          <Link
                            to={citationHref}
                            className="inline-flex items-center gap-1.5 rounded-full border border-[#DCE7E4] bg-white px-3 py-1 text-[11px] font-medium text-[#087F73] hover:bg-[#E6F3F1] transition-colors"
                          >
                            <BookOpen className="h-3 w-3" />
                            <span>
                              {currentCard.citation.documentName} · Trang{" "}
                              {currentCard.citation.pageNumber ?? 1}
                            </span>
                            <ExternalLink className="h-3 w-3" />
                          </Link>
                        ) : (
                          <span className="inline-flex items-center gap-1.5 rounded-full border border-[#DCE7E4] bg-white px-3 py-1 text-[11px] text-[#647C79]">
                            <BookOpen className="h-3 w-3" />
                            <span>
                              {currentCard.citation.documentName} · Trang{" "}
                              {currentCard.citation.pageNumber ?? 1}
                            </span>
                          </span>
                        )}
                      </div>
                    ) : null}
                  </div>

                  {/* Dòng gợi ý lật dưới cùng */}
                  <div className="flex items-center justify-center gap-1.5 text-[11px] text-[#647C79]">
                    <RotateCcw className="h-3 w-3" />
                    <span>
                      {flipped
                        ? "Nhấn để quay lại mặt trước (hoặc phím Space)"
                        : `${styleMeta.hint} (hoặc phím Space)`}
                    </span>
                  </div>
                </div>

                {/* Thanh điều khiển dưới cùng (theo đúng bố cục ảnh minh họa nhưng sắc nét hơn) */}
                <div className="flex flex-wrap items-center justify-between gap-2 pt-1">
                  <Button
                    variant="outline"
                    size="sm"
                    className="rounded-full px-4"
                    leftIcon={<ChevronLeft className="h-3.5 w-3.5" />}
                    onClick={() => {
                      setFlipped(false)
                      setCardIndex(
                        (i) =>
                          (i - 1 + filteredStudyCards.length) % filteredStudyCards.length,
                      )
                    }}
                  >
                    Trước
                  </Button>

                  <div className="flex items-center gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      leftIcon={<RotateCcw className="h-3.5 w-3.5" />}
                      onClick={() => void handleMarkCardStatus(currentCard, "review")}
                      className="rounded-full border-amber-300 bg-white px-4 text-amber-800 hover:bg-amber-50"
                    >
                      Cần ôn
                    </Button>
                    <Button
                      size="sm"
                      leftIcon={<Check className="h-3.5 w-3.5" />}
                      onClick={() => void handleMarkCardStatus(currentCard, "remembered")}
                      className="rounded-full bg-[#087F73] px-5 text-white shadow-xs hover:bg-[#076b61]"
                    >
                      Đã nhớ
                    </Button>
                  </div>

                  <Button
                    variant="outline"
                    size="sm"
                    className="rounded-full px-4"
                    onClick={() => {
                      setFlipped(false)
                      setCardIndex((i) => (i + 1) % filteredStudyCards.length)
                    }}
                  >
                    <span>Tiếp</span>
                    <ChevronRight className="ml-1 h-3.5 w-3.5" />
                  </Button>
                </div>
              </div>
            )}
          </div>
        )}

        {/* Modal Thêm / Sửa thẻ Flashcard */}
        <Dialog
          open={Boolean(editingCardModal)}
          title={
            editingCardModal?.mode === "edit"
              ? "Chỉnh sửa thẻ Flashcard"
              : "Thêm thẻ mới vào bộ"
          }
          onClose={() => setEditingCardModal(null)}
          size="md"
        >
          {editingCardModal ? (
            <CardEditorForm
              key={editingCardModal.card?.id ?? "new"}
              initialCard={editingCardModal.card}
              documents={documents}
              defaultDocId={activeDeck.documentId}
              onClose={() => setEditingCardModal(null)}
              onSave={(values) => void handleSaveCardForm(values)}
            />
          ) : null}
        </Dialog>

        <NameDialog
          open={Boolean(renameDeckTarget)}
          title="Đổi tên bộ thẻ"
          initialName={renameDeckTarget?.title ?? ""}
          confirmLabel="Lưu tên"
          onClose={() => setRenameDeckTarget(null)}
          onSubmit={(name) => {
            if (!renameDeckTarget) return
            void persistUpdateDeck({ ...renameDeckTarget, title: name })
            toast({ title: "Đã cập nhật tên bộ thẻ", tone: "success" })
          }}
        />

        <ConfirmDialog
          open={Boolean(cardToDelete)}
          title="Xóa thẻ khỏi bộ?"
          description={`Bạn có chắc muốn xóa thẻ "${cardToDelete?.front ?? ""}" không?`}
          onClose={() => setCardToDelete(null)}
          onConfirm={() => void handleConfirmDeleteCard()}
        />
      </div>
    )
  }

  // ============================================================================
  // CHẾ ĐỘ DANH SÁCH BỘ THẺ (DECKS VIEW) + FORM TẠO FLASHCARDS AI
  // ============================================================================
  return (
    <div className="space-y-6">
      {/* Tiêu đề mục Flashcards AI */}
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-bold text-[#172B29]">Flashcards AI</h2>
          <p className="mt-0.5 text-xs text-[#647C79]">
            Quản lý các bộ thẻ ghi nhớ độc lập theo chủ đề, kiểu thẻ và chế độ ôn tập thông minh SRS.
          </p>
        </div>
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-[#F1F6F5] text-[#087F73]">
          <Layers className="h-4.5 w-4.5" />
        </div>
      </div>

      {/* Form tạo bộ thẻ mới được căn chỉnh rõ ràng */}
      <div className="rounded-2xl border border-[#DCE7E4] bg-[#FBFDFC] p-5 space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 className="text-sm font-bold text-[#172B29]">Tạo bộ Flashcards mới</h3>
          <Button
            type="button"
            variant="outline"
            size="sm"
            leftIcon={<Plus className="h-3.5 w-3.5" />}
            onClick={() => setNewDeckDialogOpen(true)}
            className="h-8 text-xs"
          >
            Tạo bộ thủ công
          </Button>
        </div>

        <div className="space-y-1.5">
          <label
            htmlFor="fc-focus-input"
            className="block text-xs font-medium text-[#647C79]"
          >
            Chủ đề / Tên bộ thẻ (không bắt buộc)
          </label>
          <Input
            id="fc-focus-input"
            value={focusPrompt}
            disabled={isGenerating}
            onChange={(e) => setFocusPrompt(e.target.value)}
            placeholder="VD: Từ vựng N3 – Bài 1, Ngữ pháp chương 2..."
            className="bg-white"
          />
        </div>

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <div className="space-y-1.5">
            <label
              htmlFor="fc-doc-select"
              className="block text-xs font-medium text-[#647C79]"
            >
              Tài liệu nguồn
            </label>
            <Select
              id="fc-doc-select"
              disabled={isGenerating}
              value={selectedDocId}
              onChange={(e) => onSelectDocId(e.target.value)}
              className="bg-white text-xs"
            >
              <option value="">Tất cả tài liệu ({documents.length})</option>
              {documents.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.fileName}
                </option>
              ))}
            </Select>
          </div>

          <div className="space-y-1.5">
            <label
              htmlFor="fc-style-select"
              className="block text-xs font-medium text-[#647C79]"
            >
              Kiểu thẻ Flashcard
            </label>
            <Select
              id="fc-style-select"
              disabled={isGenerating}
              value={cardStyle}
              onChange={(e) => setCardStyle(e.target.value as FlashcardStyle)}
              className="bg-white text-xs"
            >
              <option value="term_definition">Thuật ngữ – Định nghĩa</option>
              <option value="vocabulary">Từ vựng – Nghĩa</option>
              <option value="qa">Câu hỏi – Trả lời</option>
              <option value="cloze">Điền khuyết – Ghi nhớ</option>
            </Select>
          </div>

          <div className="space-y-1.5">
            <label
              htmlFor="fc-count-select"
              className="block text-xs font-medium text-[#647C79]"
            >
              Số lượng thẻ
            </label>
            <Select
              id="fc-count-select"
              disabled={isGenerating}
              value={countPreset}
              onChange={(e) => setCountPreset(e.target.value)}
              className="bg-white text-xs"
            >
              <option value="5">5 thẻ</option>
              <option value="10">10 thẻ</option>
              <option value="15">15 thẻ</option>
              <option value="20">20 thẻ</option>
              <option value="30">30 thẻ</option>
              <option value="custom">Tùy chọn số thẻ...</option>
            </Select>
          </div>

          {countPreset === "custom" ? (
            <div className="space-y-1.5">
              <label
                htmlFor="fc-custom-count-input"
                className="block text-xs font-medium text-[#647C79]"
              >
                Nhập số thẻ (1–40)
              </label>
              <Input
                id="fc-custom-count-input"
                type="number"
                min={1}
                max={40}
                disabled={isGenerating}
                value={customCount}
                onChange={(e) => setCustomCount(e.target.value)}
                className="bg-white text-xs"
              />
            </div>
          ) : (
            <div className="hidden lg:block" />
          )}
        </div>

        <div className="flex items-center justify-end gap-2 pt-1">
          {isGenerating ? (
            <Button
              type="button"
              variant="outline"
              size="sm"
              leftIcon={<X className="h-3.5 w-3.5" />}
              onClick={() => {
                abortRef.current?.abort()
                abortRef.current = null
                setIsGenerating(false)
                toast({ title: "Đã hủy tạo Flashcards AI", tone: "info" })
              }}
            >
              Hủy
            </Button>
          ) : null}
          <Button
            size="sm"
            leftIcon={<Sparkles className="h-3.5 w-3.5" />}
            loading={isGenerating}
            onClick={() => void handleGenerateDeck()}
            className="bg-[#087F73] hover:bg-[#076b61] text-white"
          >
            {isGenerating
              ? `Đang tạo ${effectiveCount} thẻ...`
              : `Tạo ${effectiveCount} Flashcards AI`}
          </Button>
        </div>
      </div>

      {/* Danh sách Bộ thẻ của tôi */}
      <div className="space-y-3">
        <div className="flex flex-col gap-2.5 sm:flex-row sm:items-center sm:justify-between">
          <h3 className="text-sm font-bold text-[#172B29]">
            Bộ thẻ của tôi ({decks.length})
          </h3>

          <div className="flex flex-wrap items-center gap-2">
            {decks.length >= 2 ? (
              <div className="relative w-full sm:w-52">
                <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-[#647C79]" />
                <Input
                  value={deckSearch}
                  onChange={(e) => setDeckSearch(e.target.value)}
                  placeholder="Tìm bộ thẻ..."
                  className="h-8 pl-8 text-xs"
                />
              </div>
            ) : null}

            <div className="inline-flex rounded-full border border-[#DCE7E4] bg-white p-0.5 text-xs">
              {(
                [
                  { id: "all", label: `Tất cả (${decks.length})` },
                  { id: "review", label: `Cần ôn (${needReviewDecksCount})` },
                  { id: "mastered", label: `Đã thuộc (${masteredDecksCount})` },
                ] as const
              ).map((item) => (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => setDeckFilter(item.id)}
                  className={cn(
                    "rounded-full px-3 py-1 font-medium transition-colors",
                    deckFilter === item.id
                      ? "bg-[#172B29] text-white"
                      : "text-[#647C79] hover:text-[#172B29]",
                  )}
                >
                  {item.label}
                </button>
              ))}
            </div>
          </div>
        </div>

        {decks.length === 0 ? (
          <p className="rounded-xl border border-dashed border-[#DCE7E4] bg-[#F9FCFB] px-4 py-6 text-center text-xs text-[#647C79]">
            Chưa có bộ thẻ Flashcards nào trong workspace này. Hãy chọn tài liệu, kiểu thẻ và số lượng ở khung trên để tạo bộ thẻ đầu tiên.
          </p>
        ) : filteredDecks.length === 0 ? (
          <p className="rounded-xl border border-dashed border-[#DCE7E4] bg-[#F9FCFB] px-4 py-6 text-center text-xs text-[#647C79]">
            Không có bộ thẻ nào phù hợp bộ lọc hiện tại.
          </p>
        ) : (
          <div className="grid grid-cols-1 gap-3.5 md:grid-cols-2">
            {filteredDecks.map((deck) => {
              const total = deck.cards.length
              const remembered = deck.cards.filter(
                (c) => c.status === "remembered",
              ).length
              const review = deck.cards.filter((c) => c.status === "review").length
              const due = deck.cards.filter((c) => isCardDue(c, nowTick)).length
              const progressPct = total > 0 ? Math.round((remembered / total) * 100) : 0

              return (
                <div
                  key={deck.id}
                  className="flex flex-col justify-between rounded-2xl border border-[#DCE7E4] bg-white p-4 transition-all hover:border-[#087F73]/40 hover:shadow-xs space-y-3"
                >
                  <div className="space-y-2">
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0 space-y-1">
                        <h4 className="text-sm font-bold text-[#172B29] line-clamp-1">
                          {deck.title}
                        </h4>
                        <div className="flex flex-wrap items-center gap-1.5">
                          <Badge tone="accent">
                            {CARD_STYLE_META[deck.cardStyle].label}
                          </Badge>
                          {deck.isMock ? <Badge tone="neutral">Mô phỏng</Badge> : null}
                          {review > 0 ? (
                            <Badge tone="warning">{review} Cần ôn</Badge>
                          ) : due > 0 ? (
                            <Badge tone="neutral">{due} đến hạn ôn</Badge>
                          ) : total > 0 && remembered === total ? (
                            <Badge tone="success">Đã thuộc hết</Badge>
                          ) : null}
                        </div>
                      </div>

                      <div className="flex items-center gap-0.5 shrink-0">
                        <Button
                          type="button"
                          variant="ghost"
                          size="icon"
                          className="h-7 w-7 text-[#647C79] hover:text-[#087F73]"
                          onClick={() => setRenameDeckTarget(deck)}
                          aria-label={`Đổi tên ${deck.title}`}
                        >
                          <Pencil className="h-3.5 w-3.5" />
                        </Button>
                        <Button
                          type="button"
                          variant="ghost"
                          size="icon"
                          className="h-7 w-7 text-[#647C79] hover:text-red-600"
                          onClick={() => setDeckToDelete(deck)}
                          aria-label={`Xóa bộ thẻ ${deck.title}`}
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </Button>
                      </div>
                    </div>

                    <p className="text-xs text-[#647C79] line-clamp-1">
                      {total} thẻ · {deck.documentName || "Toàn bộ workspace"}
                    </p>

                    <div className="space-y-1">
                      <div className="flex items-center justify-between text-[11px] text-[#647C79]">
                        <span>
                          Đã nhớ{" "}
                          <strong className="text-[#172B29]">
                            {remembered}/{total}
                          </strong>
                        </span>
                        <span>{progressPct}%</span>
                      </div>
                      <div className="h-1.5 w-full overflow-hidden rounded-full bg-[#EAF2F0]">
                        <div
                          className="h-full rounded-full bg-[#087F73] transition-all"
                          style={{ width: `${progressPct}%` }}
                        />
                      </div>
                    </div>
                  </div>

                  <div className="flex flex-wrap items-center justify-between gap-2 pt-1 border-t border-[#DCE7E4]/60">
                    <span className="text-[11px] text-[#647C79]">
                      {deck.lastStudiedAt
                        ? `Học ${relativeTime(deck.lastStudiedAt)}`
                        : `Tạo ${relativeTime(deck.createdAt)}`}
                    </span>

                    <div className="flex items-center gap-1.5">
                      <Button
                        variant="outline"
                        size="sm"
                        className="h-8 text-xs"
                        onClick={() => startStudySession(deck, "all", smartReview, true)}
                      >
                        Quản lý thẻ
                      </Button>
                      <Button
                        size="sm"
                        className="h-8 bg-[#087F73] hover:bg-[#076b61] text-white text-xs"
                        onClick={() => startStudySession(deck, "all", smartReview, false)}
                      >
                        <span>Học ngay</span>
                        <ArrowRight className="h-3.5 w-3.5" />
                      </Button>
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>

      <NameDialog
        open={newDeckDialogOpen}
        title="Tạo bộ thẻ Flashcard thủ công"
        description="Đặt tên bộ thẻ mới theo bài học hoặc chuyên đề để dễ quản lý và ôn tập."
        initialName=""
        confirmLabel="Tạo bộ thẻ"
        onClose={() => setNewDeckDialogOpen(false)}
        onSubmit={(name) => void handleCreateManualDeck(name)}
      />

      <NameDialog
        open={Boolean(renameDeckTarget)}
        title="Đổi tên bộ thẻ"
        initialName={renameDeckTarget?.title ?? ""}
        confirmLabel="Lưu tên"
        onClose={() => setRenameDeckTarget(null)}
        onSubmit={(name) => {
          if (!renameDeckTarget) return
          void persistUpdateDeck({ ...renameDeckTarget, title: name })
          toast({ title: "Đã cập nhật tên bộ thẻ", tone: "success" })
        }}
      />

      <ConfirmDialog
        open={Boolean(deckToDelete)}
        title="Xóa bộ thẻ Flashcards?"
        description={`Bạn có chắc muốn xóa bộ "${deckToDelete?.title ?? ""}" cùng toàn bộ ${
          deckToDelete?.cards.length ?? 0
        } thẻ bên trong?`}
        onClose={() => setDeckToDelete(null)}
        onConfirm={() => void handleConfirmDeleteDeck()}
      />
    </div>
  )
}
