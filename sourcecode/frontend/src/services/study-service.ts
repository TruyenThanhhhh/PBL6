import type {
  Flashcard,
  KnowledgeDocument,
  MindmapNode,
  Notebook,
  Quiz,
  QuizQuestion,
  StudyTask,
} from "@/types"
import { uid } from "@/utils/format"

export type StudyToolId = "summary" | "notes" | "quiz" | "flashcards" | "mindmap" | "plan"

export interface StudySourceContext {
  workspaceId: string
  notebook: Notebook | null
  document: KnowledgeDocument | null
  documentsInScope: KnowledgeDocument[]
}

/**
 * Tạo bản tóm tắt có cấu trúc Markdown từ tài liệu hoặc notebook đã chọn (dữ liệu mô phỏng khi chưa có AI backend)
 */
export function generateStudySummary(
  ctx: StudySourceContext,
  focusPrompt?: string,
): { title: string; markdown: string; isMock: boolean } {
  const sourceName =
    ctx.document?.fileName ??
    (ctx.notebook ? `Notebook: ${ctx.notebook.name}` : "Toàn bộ tài liệu trong Workspace")

  const docs = ctx.document ? [ctx.document] : ctx.documentsInScope
  const rawParagraphs = docs
    .flatMap((d) => d.extractedText.split(/\n\n+/))
    .map((p) => p.trim())
    .filter(Boolean)

  if (rawParagraphs.length === 0) {
    return {
      title: `Tóm tắt · ${sourceName}`,
      markdown: `Chưa có văn bản trích xuất từ nguồn **${sourceName}**. Hãy chọn một tài liệu ở trạng thái *Sẵn sàng (Ready)* để tạo bản tóm tắt.`,
      isMock: true,
    }
  }

  const focusNote = focusPrompt?.trim()
    ? `\n> **Trọng tâm yêu cầu:** ${focusPrompt.trim()}\n`
    : ""

  const bulletPoints = rawParagraphs
    .slice(0, 5)
    .map((p, i) => `${i + 1}. ${p}`)
    .join("\n")

  const markdown = `## Tóm tắt nội dung: ${sourceName}
${focusNote}
### Các luận điểm chính trích từ nguồn
${bulletPoints}

### Ghi chú ôn tập nhanh
- Đối chiếu các khái niệm cốt lõi trực tiếp với đoạn trích gốc trong **Source Viewer**.
- Chuyển hóa các ý chính phía trên thành **Flashcard** hoặc **Quiz** để tự kiểm tra.

*Lưu ý: Bản tóm tắt được tổng hợp từ văn bản đã trích xuất ở chế độ mô phỏng cục bộ (chưa gọi LLM sinh tóm tắt mới).*`

  return {
    title: `Tóm tắt · ${sourceName}`,
    markdown,
    isMock: true,
  }
}

/**
 * Tạo bài Quiz trắc nghiệm từ tài liệu nguồn
 */
export function generateStudyQuiz(
  ctx: StudySourceContext,
  difficulty: "easy" | "medium" | "hard",
  questionCount: number,
): Quiz {
  const sourceLabel =
    ctx.document?.fileName ?? ctx.notebook?.name ?? "Kho tri thức"

  const questionBank: Omit<QuizQuestion, "id">[] = [
    {
      prompt: "Mục tiêu chính của việc kết hợp Dense Retrieval và Sparse Retrieval (BM25) trong Hybrid RAG là gì?",
      options: [
        "Giảm kích thước tệp PDF gốc khi lưu trữ",
        "Bắt được cả ngữ nghĩa tương đồng lẫn từ khóa, tên riêng và mã kỹ thuật chính xác",
        "Thay thế hoàn toàn bước chia đoạn (Chunking)",
        "Tự động dịch tài liệu sang ngôn ngữ khác",
      ],
      answerIndex: 1,
      explanation:
        "Dense vector nắm ý nghĩa tổng quát, trong khi BM25 khớp chính xác từ khóa và thuật ngữ đặc thù.",
    },
    {
      prompt: "Reciprocal Rank Fusion (RRF) thực hiện nhiệm vụ nào trong pipeline truy xuất?",
      options: [
        "Hợp nhất bảng xếp hạng kết quả từ nhiều bộ truy xuất khác nhau",
        "Trích xuất văn bản từ hình ảnh quét (OCR)",
        "Mã hóa mật khẩu người dùng",
        "Xóa các tài liệu trùng lặp trong workspace",
      ],
      answerIndex: 0,
      explanation:
        "RRF tính điểm hợp nhất dựa trên thứ hạng (rank) của từng đoạn văn ở kênh Dense và kênh Sparse.",
    },
    {
      prompt: "Vì sao câu trả lời AI cần đi kèm Citation trỏ tới đúng trang và chunk?",
      options: [
        "Để làm giao diện nhiều màu sắc hơn",
        "Để người dùng kiểm chứng trực tiếp bằng chứng gốc và phát hiện suy diễn sai (hallucination)",
        "Để tăng tốc độ tải trang web",
        "Để tự động xóa tài liệu sau khi đọc",
      ],
      answerIndex: 1,
      explanation:
        "Citation gắn với trang và chunk giúp đối chiếu câu trả lời với tài liệu gốc một cách minh bạch.",
    },
    {
      prompt: "Theo nguyên tắc Local-first, khi nào hệ thống mới gửi truy vấn ra nguồn Web bên ngoài?",
      options: [
        "Mọi lúc ngay cả khi người dùng chọn chế độ Local",
        "Chỉ khi người dùng chủ động chọn chế độ Web hoặc Hybrid và cấp quyền",
        "Ngay khi vừa tải tệp lên trình duyệt",
        "Khi người dùng đổi giao diện sang Dark Mode",
      ],
      answerIndex: 1,
      explanation:
        "Chế độ Local giữ dữ liệu hoàn toàn nội bộ; Web Search chỉ kích hoạt khi được chọn và cho phép.",
    },
    {
      prompt: "Vai trò của Cross-Encoder Reranker sau bước hợp nhất RRF là gì?",
      options: [
        "Chấm điểm lại mức độ liên quan trực tiếp giữa câu hỏi và từng đoạn văn để lọc nhiễu",
        "Nén toàn bộ cơ sở dữ liệu thành tệp ZIP",
        "Tạo giao diện bảng biểu Markdown",
        "Đổi tên tài liệu tự động",
      ],
      answerIndex: 0,
      explanation:
        "Cross-Encoder đánh giá sâu cặp (query, passage) để giữ lại các đoạn bằng chứng sát nhất trước khi đưa vào LLM.",
    },
  ]

  const count = Math.min(Math.max(questionCount, 1), questionBank.length)
  const questions: QuizQuestion[] = questionBank.slice(0, count).map((q) => ({
    ...q,
    id: uid("qq"),
  }))

  return {
    id: uid("quiz"),
    workspaceId: ctx.workspaceId,
    documentId: ctx.document?.id ?? null,
    title: `Quiz · ${sourceLabel}`,
    difficulty,
    questions,
    answers: {},
    submitted: false,
    isMock: true,
  }
}

/**
 * Sinh bộ thẻ Flashcards mới từ tài liệu đã chọn
 */
export function generateStudyFlashcards(ctx: StudySourceContext): Flashcard[] {
  const docId = ctx.document?.id ?? null
  const docName = ctx.document?.fileName ?? "Tài liệu"
  const raw = ctx.document?.extractedText ?? ""
  const sentences = raw
    .split(/\n+/)
    .map((s) => s.trim())
    .filter((s) => s.length > 25)

  if (sentences.length >= 2) {
    return sentences.slice(0, 3).map((line, idx) => ({
      id: uid("fc"),
      workspaceId: ctx.workspaceId,
      documentId: docId,
      front: `Ý chính #${idx + 1} trong ${docName}`,
      back: line,
      status: "new" as const,
      isMock: true,
    }))
  }

  return [
    {
      id: uid("fc"),
      workspaceId: ctx.workspaceId,
      documentId: docId,
      front: `Vai trò của RRF trong ${docName}`,
      back: "Hợp nhất thứ hạng từ Dense Search và BM25 trước khi đưa qua Reranker.",
      status: "new",
      isMock: true,
    },
    {
      id: uid("fc"),
      workspaceId: ctx.workspaceId,
      documentId: docId,
      front: "Điều kiện kiểm chứng Citation",
      back: "Citation phải gắn với ID tài liệu ổn định, số trang và đoạn trích (snippet).",
      status: "new",
      isMock: true,
    },
  ]
}

/**
 * Tạo cấu trúc cây Mindmap phân cấp từ tài liệu nguồn
 */
export function buildMindmapFromContext(ctx: StudySourceContext): MindmapNode {
  const rootLabel =
    ctx.document?.fileName.replace(/\.[^.]+$/, "") ??
    ctx.notebook?.name ??
    "Kiến trúc Tri thức"

  const paragraphs = (ctx.document?.extractedText ?? "")
    .split(/\n\n+/)
    .map((p) => p.trim())
    .filter(Boolean)

  if (paragraphs.length >= 3) {
    return {
      id: "root",
      label: rootLabel,
      detail: "Cấu trúc phân cấp trích từ tài liệu nguồn (Mô phỏng)",
      children: paragraphs.slice(0, 4).map((p, idx) => {
        const words = p.split(/\s+/)
        const shortTitle = words.slice(0, 6).join(" ") + (words.length > 6 ? "..." : "")
        return {
          id: `node-${idx + 1}`,
          label: `${idx + 1}. ${shortTitle}`,
          detail: p,
          children: [
            {
              id: `node-${idx + 1}-a`,
              label: `Đoạn trích #${idx + 1}`,
              detail: p.slice(0, 140),
            },
          ],
        }
      }),
    }
  }

  return {
    id: "root",
    label: rootLabel,
    detail: "Sơ đồ phân cấp khái niệm cốt lõi (Mô phỏng)",
    children: [
      {
        id: "n-retrieval",
        label: "1. Truy xuất đa kênh (Hybrid Retrieval)",
        children: [
          {
            id: "n-dense",
            label: "Dense Vector Search",
            detail: "Mã hóa ngữ nghĩa, xử lý từ đồng nghĩa và câu hỏi tự nhiên.",
          },
          {
            id: "n-sparse",
            label: "Sparse BM25 / FTS5",
            detail: "Khớp từ khóa chính xác, tên riêng và ký hiệu kỹ thuật.",
          },
        ],
      },
      {
        id: "n-fusion",
        label: "2. Hợp nhất & Xếp hạng (Fusion & Rerank)",
        children: [
          {
            id: "n-rrf",
            label: "Reciprocal Rank Fusion (RRF)",
            detail: "Gộp danh sách xếp hạng từ hai kênh truy xuất.",
          },
          {
            id: "n-reranker",
            label: "Cross-Encoder Reranker",
            detail: "Chấm điểm sâu cặp (câu hỏi, đoạn văn) để loại bỏ nhiễu.",
          },
        ],
      },
      {
        id: "n-verify",
        label: "3. Kiểm chứng nguồn (Citation & Evidence)",
        children: [
          {
            id: "n-cite",
            label: "Tham chiếu [1], [2] ổn định",
            detail: "Liên kết tới đúng tài liệu, số trang và chunk ID.",
          },
        ],
      },
    ],
  }
}

/**
 * Sinh danh sách nhiệm vụ Kế hoạch học tập (Study Plan) từ nguồn đã chọn
 */
export function generateStudyPlanTasks(ctx: StudySourceContext): StudyTask[] {
  const docId = ctx.document?.id ?? null
  const label = ctx.document?.fileName ?? ctx.notebook?.name ?? "Workspace hiện tại"

  return [
    {
      id: uid("st"),
      workspaceId: ctx.workspaceId,
      documentId: docId,
      title: `Đọc và rà soát bản tóm tắt của "${label}"`,
      dueDate: "2026-10-29",
      completed: false,
      isMock: true,
    },
    {
      id: uid("st"),
      workspaceId: ctx.workspaceId,
      documentId: docId,
      title: `Tạo ghi chú tổng hợp các khái niệm quan trọng từ "${label}"`,
      dueDate: "2026-10-31",
      completed: false,
      isMock: true,
    },
    {
      id: uid("st"),
      workspaceId: ctx.workspaceId,
      documentId: docId,
      title: `Hoàn thành bài Quiz và ôn lại các thẻ Flashcard cần nhớ`,
      dueDate: "2026-11-03",
      completed: false,
      isMock: true,
    },
  ]
}
