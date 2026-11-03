import type {
  Activity,
  Conversation,
  Flashcard,
  KnowledgeDocument,
  Note,
  Notebook,
  Quiz,
  ResearchProject,
  Workspace,
} from "@/types"

const t = (daysAgo: number, hours = 10) => {
  const d = new Date()
  d.setDate(d.getDate() - daysAgo)
  d.setHours(hours, 20, 0, 0)
  return d.toISOString()
}

export const seedWorkspaces: Workspace[] = [
  {
    id: "ws_network",
    name: "Đồ án Mạng & An toàn thông tin",
    description: "Phân tích kiến trúc Zero Trust, so sánh perimeter defense và micro-segmentation.",
    category: "Đại học",
    icon: "shield-check",
    createdAt: t(10),
    updatedAt: t(0, 10),
  },
  {
    id: "ws_dsp",
    name: "Tài liệu Xử lý Tín hiệu Số (DSP)",
    description: "Bộ lọc FIR, IIR, biến đổi FFT và thuật toán tối ưu hóa phần cứng.",
    category: "Kỹ thuật",
    icon: "activity",
    createdAt: t(12),
    updatedAt: t(1, 14),
  },
  {
    id: "ws_japanese",
    name: "Ôn thi JLPT N2 & Từ vựng Tiếng Nhật",
    description: "Ngữ pháp Shinkanzen Master, từ vựng Mimi Kara Oboeru và đề thi mẫu.",
    category: "Ngoại ngữ",
    icon: "languages",
    createdAt: t(20),
    updatedAt: t(3, 11),
  },
  {
    id: "ws_research",
    name: "Nghiên cứu Thị trường & AI Agents",
    description: "Tổng hợp xu hướng Autonomous Agents, Multi-agent workflows và Hybrid RAG 2025.",
    category: "Nghiên cứu",
    icon: "bot",
    createdAt: t(18),
    updatedAt: t(7, 9),
  },
  {
    id: "ws_default",
    name: "Không gian mặc định",
    description: "Không gian làm việc riêng của bạn. Bắt đầu bằng việc tải tài liệu hoặc tạo cuộc trò chuyện AI mới.",
    category: "Cá nhân",
    icon: "folders",
    createdAt: t(0, 8),
    updatedAt: t(0, 8),
  },
  {
    id: "ws_course",
    name: "Học phần Trí tuệ nhân tạo",
    description: "Bài giảng, slide và ghi chú ôn tập giữa kỳ về Machine Learning và Deep Learning.",
    category: "Đại học",
    icon: "folders",
    createdAt: t(30),
    updatedAt: t(1, 16),
  },
  {
    id: "ws_personal",
    name: "Ghi chú cá nhân",
    description: "Ý tưởng, checklist và tài liệu đọc thêm.",
    category: "Cá nhân",
    icon: "folders",
    createdAt: t(40),
    updatedAt: t(4, 11),
  },
]

export const seedNotebooks: Notebook[] = [
  { id: "nb_papers", workspaceId: "ws_research", name: "Papers", createdAt: t(17) },
  { id: "nb_notes", workspaceId: "ws_research", name: "Ghi chú tổng hợp", createdAt: t(12) },
  { id: "nb_lectures", workspaceId: "ws_course", name: "Bài giảng", createdAt: t(28) },
  { id: "nb_exam", workspaceId: "ws_course", name: "Ôn thi", createdAt: t(10) },
  { id: "nb_inbox", workspaceId: "ws_personal", name: "Inbox", createdAt: t(39) },
]

const ragText = `Hybrid Retrieval-Augmented Generation (Hybrid RAG) kết hợp hai kênh truy xuất.

Kênh dense (vector search) mã hóa câu hỏi và đoạn văn thành vector ngữ nghĩa. Kênh này tốt khi người dùng diễn đạt bằng từ đồng nghĩa.

Kênh sparse (BM25 / FTS5) khớp từ khóa chính xác, tên riêng, mã hiệu và thuật ngữ kỹ thuật.

Reciprocal Rank Fusion (RRF) gộp hai danh sách xếp hạng. Sau đó Cross-Encoder Reranker chấm lại cặp (câu hỏi, đoạn văn) để loại nhiễu.

Câu trả lời cần gắn citation [1] với tên tài liệu, số trang và đoạn evidence. Nếu không đủ bằng chứng, hệ thống phải nêu rõ thay vì khẳng định.`

const privacyText = `Nguyên tắc Local-first: tài liệu cá nhân được lưu trên máy, không gửi ra ngoài khi chưa có xác nhận.

Local LLM (ví dụ Qwen 2.5 qua Ollama) dùng cho chế độ Local và làm fallback khi mất mạng.

Web Search chỉ bật khi người dùng chọn Web hoặc Hybrid, và nên có bước xác nhận trước khi gửi truy vấn ra Internet.

Offline không đồng nghĩa AI luôn sẵn sàng. Nếu Ollama chưa chạy, giao diện phải báo Local AI không khả dụng.`

export const seedDocuments: KnowledgeDocument[] = [
  {
    id: "doc_hybrid_rag",
    workspaceId: "ws_research",
    notebookId: "nb_papers",
    fileName: "Hybrid-RAG-Survey.pdf",
    fileType: "pdf",
    fileSize: 842_110,
    status: "ready",
    createdAt: t(2, 14),
    totalChunks: 48,
    pageCount: 12,
    extractedText: ragText,
    mock: true,
  },
  {
    id: "doc_citation",
    workspaceId: "ws_research",
    notebookId: "nb_notes",
    fileName: "Citation-and-Evidence.md",
    fileType: "md",
    fileSize: 12_440,
    status: "ready",
    createdAt: t(1, 11),
    totalChunks: 9,
    pageCount: 3,
    extractedText: ragText,
    mock: true,
  },
  {
    id: "doc_lecture",
    workspaceId: "ws_course",
    notebookId: "nb_lectures",
    fileName: "Bai-giang-07-Retrieval.pptx",
    fileType: "pptx",
    fileSize: 2_104_000,
    status: "indexing",
    createdAt: t(0, 8),
    totalChunks: 22,
    pageCount: 31,
    extractedText: "Retrieval: dense, sparse, hybrid. Rerank bằng cross-encoder.",
    mock: true,
  },
  {
    id: "doc_privacy",
    workspaceId: "ws_personal",
    notebookId: "nb_inbox",
    fileName: "Privacy-Local-First.docx",
    fileType: "docx",
    fileSize: 88_200,
    status: "ready",
    createdAt: t(5, 19),
    totalChunks: 14,
    pageCount: 6,
    extractedText: privacyText,
    mock: true,
  },
  {
    id: "doc_failed",
    workspaceId: "ws_course",
    notebookId: "nb_exam",
    fileName: "scan-low-quality.pdf",
    fileType: "pdf",
    fileSize: 3_200_100,
    status: "failed",
    createdAt: t(3, 9),
    totalChunks: 0,
    pageCount: 0,
    extractedText: "",
    mock: true,
  },
  {
    id: "doc_net_1",
    workspaceId: "ws_network",
    notebookId: null,
    fileName: "Zero-Trust-Architecture-NIST-SP800-207.pdf",
    fileType: "pdf",
    fileSize: 42_500_000,
    status: "ready",
    createdAt: t(10, 8),
    totalChunks: 64,
    pageCount: 58,
    extractedText: "Zero Trust Architecture assumes network locality is not sufficient for deciding trust.",
    mock: true,
  },
  {
    id: "doc_net_2",
    workspaceId: "ws_network",
    notebookId: null,
    fileName: "Micro-Segmentation-Guide.docx",
    fileType: "docx",
    fileSize: 18_200_000,
    status: "ready",
    createdAt: t(8, 14),
    totalChunks: 38,
    pageCount: 24,
    extractedText: "Micro-segmentation isolates workloads and reduces lateral movement in enterprise networks.",
    mock: true,
  },
  {
    id: "doc_net_3",
    workspaceId: "ws_network",
    notebookId: null,
    fileName: "Perimeter-Defense-vs-ZeroTrust.md",
    fileType: "md",
    fileSize: 2_400_000,
    status: "ready",
    createdAt: t(2, 9),
    totalChunks: 40,
    pageCount: 16,
    extractedText: "So sánh kiến trúc phòng thủ chu vi truyền thống và nguyên tắc Zero Trust.",
    mock: true,
  },
  {
    id: "doc_dsp_1",
    workspaceId: "ws_dsp",
    notebookId: null,
    fileName: "Digital-Signal-Processing-Proakis.pdf",
    fileType: "pdf",
    fileSize: 120_000_000,
    status: "ready",
    createdAt: t(12, 10),
    totalChunks: 180,
    pageCount: 240,
    extractedText: "FIR and IIR digital filter design, frequency analysis, and hardware DSP implementations.",
    mock: true,
  },
  {
    id: "doc_dsp_2",
    workspaceId: "ws_dsp",
    notebookId: null,
    fileName: "FFT-Cooley-Tukey-Algorithms.pptx",
    fileType: "pptx",
    fileSize: 45_000_000,
    status: "ready",
    createdAt: t(5, 11),
    totalChunks: 130,
    pageCount: 65,
    extractedText: "Fast Fourier Transform butterfly diagrams, computational complexity and SIMD vectorization.",
    mock: true,
  },
  {
    id: "doc_jp_1",
    workspaceId: "ws_japanese",
    notebookId: null,
    fileName: "Shinkanzen-Master-N2-Bunpou.pdf",
    fileType: "pdf",
    fileSize: 34_000_000,
    status: "ready",
    createdAt: t(20, 9),
    totalChunks: 55,
    pageCount: 85,
    extractedText: "JLPT N2 Grammar patterns, functional usage, and comparative exercise solutions.",
    mock: true,
  },
  {
    id: "doc_jp_2",
    workspaceId: "ws_japanese",
    notebookId: null,
    fileName: "Mimi-Kara-Oboeru-Goi-N2.docx",
    fileType: "docx",
    fileSize: 15_000_000,
    status: "ready",
    createdAt: t(14, 15),
    totalChunks: 40,
    pageCount: 42,
    extractedText: "1160 essential N2 vocabulary items with collocations and context sentences.",
    mock: true,
  },
  {
    id: "doc_agent_1",
    workspaceId: "ws_research",
    notebookId: null,
    fileName: "Autonomous-Agents-Survey-2025.pdf",
    fileType: "pdf",
    fileSize: 85_000_000,
    status: "ready",
    createdAt: t(7, 10),
    totalChunks: 210,
    pageCount: 110,
    extractedText: "Survey of Multi-Agent Systems, tool calling, memory management and verification loops.",
    mock: true,
  },
  {
    id: "doc_agent_2",
    workspaceId: "ws_research",
    notebookId: null,
    fileName: "Agentic-RAG-Workflows.pptx",
    fileType: "pptx",
    fileSize: 42_000_000,
    status: "ready",
    createdAt: t(4, 16),
    totalChunks: 150,
    pageCount: 52,
    extractedText: "Agentic RAG workflows combining self-reflection, query rewriting and hybrid vector retrieval.",
    mock: true,
  },
]

export const seedNotes: Note[] = [
  {
    id: "note_rrf",
    workspaceId: "ws_research",
    notebookId: "nb_notes",
    documentId: "doc_hybrid_rag",
    title: "RRF + Rerank",
    content: "RRF gộp rank, reranker lọc hallucination. Citation phải trỏ được chunk.",
    updatedAt: t(0, 15),
  },
  {
    id: "note_offline",
    workspaceId: "ws_personal",
    notebookId: "nb_inbox",
    documentId: "doc_privacy",
    title: "Checklist offline",
    content: "Ollama chạy? Index sẵn sàng? Web search tắt mặc định.",
    updatedAt: t(4, 12),
  },
]

export const seedConversations: Conversation[] = [
  {
    id: "conv_hybrid",
    workspaceId: "ws_research",
    title: "Hybrid RAG khác vector search thế nào?",
    updatedAt: t(0, 16),
    messages: [
      {
        id: "m1",
        role: "user",
        content: "Hybrid RAG khác vector search thuần túy ở điểm nào?",
        createdAt: t(0, 16),
        citations: [],
        modeRequested: "auto",
      },
      {
        id: "m2",
        role: "assistant",
        content:
          "Vector search chỉ dùng ngữ nghĩa dense. Hybrid RAG thêm BM25 để bắt từ khóa, rồi hợp nhất bằng RRF và lọc lại bằng reranker.[1][2]\n\nNhờ vậy tên riêng và thuật ngữ kỹ thuật ít bị trượt hơn so với chỉ dùng embedding.",
        createdAt: t(0, 16),
        citations: [
          {
            refId: 1,
            documentId: "doc_hybrid_rag",
            documentName: "Hybrid-RAG-Survey.pdf",
            pageNumber: 3,
            chunkIndex: 4,
            snippet:
              "Kênh sparse (BM25 / FTS5) khớp từ khóa chính xác, tên riêng, mã hiệu và thuật ngữ kỹ thuật.",
            sourceKind: "local",
            highlight: "BM25 / FTS5",
          },
          {
            refId: 2,
            documentId: "doc_hybrid_rag",
            documentName: "Hybrid-RAG-Survey.pdf",
            pageNumber: 5,
            chunkIndex: 8,
            snippet:
              "Reciprocal Rank Fusion (RRF) gộp hai danh sách xếp hạng. Sau đó Cross-Encoder Reranker chấm lại cặp (câu hỏi, đoạn văn).",
            sourceKind: "local",
            highlight: "Reciprocal Rank Fusion",
          },
        ],
        modeRequested: "auto",
        modeUsed: "local",
        engine: "mock_hybrid_rag",
      },
    ],
  },
  {
    id: "conv_privacy",
    workspaceId: "ws_personal",
    title: "Khi nào được gọi Web Search?",
    updatedAt: t(1, 20),
    messages: [
      {
        id: "m3",
        role: "user",
        content: "Khi nào hệ thống được phép tìm trên web?",
        createdAt: t(1, 20),
        citations: [],
        modeRequested: "local",
      },
      {
        id: "m4",
        role: "assistant",
        content:
          "Web Search chỉ dùng khi bạn chọn chế độ Web hoặc Hybrid, và nên xác nhận trước khi gửi dữ liệu ra ngoài.[1]\n\nChế độ Local chỉ đọc kho tri thức trên máy.",
        createdAt: t(1, 20),
        citations: [
          {
            refId: 1,
            documentId: "doc_privacy",
            documentName: "Privacy-Local-First.docx",
            pageNumber: 2,
            chunkIndex: 2,
            snippet:
              "Web Search chỉ bật khi người dùng chọn Web hoặc Hybrid, và nên có bước xác nhận trước khi gửi truy vấn ra Internet.",
            sourceKind: "local",
          },
        ],
        modeUsed: "local",
        engine: "mock_local",
      },
    ],
  },
]

export const seedResearch: ResearchProject[] = [
  {
    id: "rs_citation",
    workspaceId: "ws_research",
    title: "Độ tin cậy của citation trong RAG",
    question: "Làm sao để câu trả lời RAG không tạo cảm giác đã được kiểm chứng khi thiếu evidence?",
    documentIds: ["doc_hybrid_rag", "doc_citation"],
    allowWeb: false,
    mode: "local",
    status: "completed",
    step: 6,
    report: `## Tóm tắt điều hành
Hệ thống phải tách rõ ba trạng thái: có evidence tài liệu, có evidence web, và chưa đủ bằng chứng.

## Phát hiện chính
- Citation dạng [1] cần mở được đoạn văn, trang và chunk.
- Fallback Local không được gắn nhãn như đã xác minh web.

## So sánh nguồn
Survey Hybrid RAG mô tả RRF + reranker; ghi chú citation nhấn mạnh UI không được “giả lập đã kiểm chứng”.

## Điểm mâu thuẫn
Chưa có số liệu benchmark Ragas trong các tài liệu mẫu hiện có.

## Research gap
Thiếu quy ước ánh xạ citation LLM ([Tài liệu X]) sang ref_id ổn định.

## Kết luận
Citation Panel là lớp kiểm chứng, không phải trang trí.

## Tài liệu tham khảo
1. Hybrid-RAG-Survey.pdf, tr. 3–5
2. Citation-and-Evidence.md
`,
    createdAt: t(6),
    updatedAt: t(2, 18),
  },
]

export const seedQuizzes: Quiz[] = [
  {
    id: "quiz_rag",
    workspaceId: "ws_research",
    documentId: "doc_hybrid_rag",
    title: "Quiz Hybrid RAG",
    difficulty: "medium",
    submitted: false,
    answers: {},
    questions: [
      {
        id: "q1",
        prompt: "BM25 trong Hybrid RAG đóng vai trò gì?",
        options: [
          "Sinh câu trả lời từ LLM",
          "Truy xuất từ khóa / lexical",
          "Mã hóa dense embedding",
          "Lưu file PDF",
        ],
        answerIndex: 1,
        explanation: "BM25 là kênh sparse, khớp từ khóa.",
      },
      {
        id: "q2",
        prompt: "RRF dùng để làm gì?",
        options: [
          "Nén PDF",
          "Gộp bảng xếp hạng từ nhiều retriever",
          "Fine-tune LLM",
          "Mã hóa mật khẩu",
        ],
        answerIndex: 1,
        explanation: "Reciprocal Rank Fusion hợp nhất rank.",
      },
      {
        id: "q3",
        prompt: "Khi nào UI không được tuyên bố đã kiểm chứng?",
        options: [
          "Khi có citation và đoạn evidence",
          "Khi không có bằng chứng phù hợp",
          "Khi file là PDF",
          "Khi dùng dark mode",
        ],
        answerIndex: 1,
        explanation: "Thiếu evidence phải báo rõ, không giả lập đã xác minh.",
      },
    ],
  },
]

export const seedFlashcards: Flashcard[] = [
  {
    id: "fc1",
    workspaceId: "ws_research",
    documentId: "doc_hybrid_rag",
    front: "Dense retrieval",
    back: "Tìm đoạn gần nghĩa bằng vector embedding.",
    status: "new",
  },
  {
    id: "fc2",
    workspaceId: "ws_research",
    documentId: "doc_hybrid_rag",
    front: "Sparse retrieval",
    back: "BM25 / FTS5 khớp từ khóa.",
    status: "review",
  },
  {
    id: "fc3",
    workspaceId: "ws_research",
    documentId: "doc_hybrid_rag",
    front: "Reranker",
    back: "Cross-encoder chấm lại cặp query–passage.",
    status: "remembered",
  },
]

export const seedActivities: Activity[] = [
  { id: "a1", text: "Đã lập chỉ mục Hybrid-RAG-Survey.pdf", at: t(2, 14), kind: "document" },
  { id: "a2", text: "Hội thoại: Hybrid RAG khác vector search thế nào?", at: t(0, 16), kind: "chat" },
  { id: "a3", text: "Tạo workspace Nghiên cứu RAG", at: t(18), kind: "workspace" },
  { id: "a4", text: "Hoàn thành báo cáo citation", at: t(2, 18), kind: "research" },
]
