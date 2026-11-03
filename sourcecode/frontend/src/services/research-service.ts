import type { AIMode, KnowledgeDocument } from "@/types"

export interface ResearchPipelineStep {
  step: number
  label: string
  description: string
}

export const RESEARCH_PIPELINE_STEPS: ResearchPipelineStep[] = [
  {
    step: 1,
    label: "Xác định câu hỏi",
    description: "Chuẩn hóa phạm vi và tiêu chí đánh giá của câu hỏi nghiên cứu.",
  },
  {
    step: 2,
    label: "Thu thập nguồn",
    description: "Tập hợp các tài liệu đã chọn trong Workspace / Notebook.",
  },
  {
    step: 3,
    label: "Truy xuất bằng chứng",
    description: "Lọc các đoạn trích liên quan từ văn bản tài liệu.",
  },
  {
    step: 4,
    label: "Tổng hợp",
    description: "Đối chiếu luận điểm, điểm tương đồng và mâu thuẫn giữa các nguồn.",
  },
  {
    step: 5,
    label: "Tạo báo cáo",
    description: "Hoàn thiện báo cáo học thuật 8 phần kèm danh mục tham chiếu.",
  },
]

export interface ReportSectionHeading {
  id: string
  title: string
}

export const REPORT_SECTIONS: ReportSectionHeading[] = [
  { id: "sec-executive-summary", title: "1. Executive Summary" },
  { id: "sec-research-question", title: "2. Research Question" },
  { id: "sec-key-findings", title: "3. Key Findings" },
  { id: "sec-comparison", title: "4. Comparison" },
  { id: "sec-contradictions", title: "5. Contradictions" },
  { id: "sec-research-gaps", title: "6. Research Gaps" },
  { id: "sec-conclusion", title: "7. Conclusion" },
  { id: "sec-references", title: "8. References" },
]

/**
 * Tạo báo cáo nghiên cứu chuẩn 8 phần (đánh dấu rõ là dữ liệu mô phỏng khi chưa có Backend Research API)
 */
export function buildSimulatedResearchReport(params: {
  question: string
  selectedDocs: KnowledgeDocument[]
  allowWeb: boolean
  mode: AIMode
}): string {
  const { question, selectedDocs, allowWeb, mode } = params
  const docRefs =
    selectedDocs.length > 0
      ? selectedDocs
          .map(
            (d, i) =>
              `${i + 1}. [${i + 1}] **${d.fileName}** (${d.fileType.toUpperCase()} · ${d.pageCount} trang · ${d.totalChunks} chunks)`,
          )
          .join("\n")
      : "1. Chưa có tài liệu cục bộ nào được gắn trực tiếp vào dự án này."

  const firstCitationTag = selectedDocs.length > 0 ? " [1]" : ""
  const secondCitationTag = selectedDocs.length > 1 ? " [2]" : firstCitationTag

  return `## 1. Executive Summary

Báo cáo này tổng hợp các bằng chứng xoay quanh câu hỏi nghiên cứu đã đặt ra, dựa trên **${selectedDocs.length} tài liệu cục bộ** được chọn trong kho tri thức${firstCitationTag}.

> **Trạng thái minh bạch:** Báo cáo dưới đây được tạo từ dịch vụ **mô phỏng (Mock Research Service)** để phục vụ cấu trúc đọc, điều hướng mục lục và kiểm chứng nguồn trên giao diện — chưa chạy pipeline RAG/LLM hay Web Search thực tế từ máy chủ.

## 2. Research Question

**Câu hỏi trọng tâm:** ${question}

- **Chế độ AI yêu cầu:** \`${mode.toUpperCase()}\`
- **Cho phép mở rộng Web Search:** ${allowWeb ? "Có (Lưu cấu hình UI — chưa gọi Web API thật)" : "Không (Chỉ dùng nguồn nội bộ)"}

## 3. Key Findings

- **Kết hợp đa kênh truy xuất:** Việc phối hợp truy xuất ngữ nghĩa (Dense Vector) và khớp từ khóa (BM25) giúp giảm tỷ lệ bỏ sót thuật ngữ kỹ thuật cũng như tên riêng${firstCitationTag}.
- **Kiểm chứng bằng chứng trực tiếp:** Mỗi nhận định trong báo cáo học thuật cần gắn tham chiếu ổn định tới tài liệu gốc để người đọc đối chiếu nguyên văn${secondCitationTag}.
- **Kiểm soát phạm vi nguồn:** Giới hạn nguồn theo từng Workspace hoặc Notebook giúp loại bỏ nhiễu từ các tài liệu không cùng chủ đề.

## 4. Comparison

| Nguồn tài liệu | Vai trò trong nghiên cứu | Mức độ sẵn sàng |
| :--- | :--- | :--- |
${
  selectedDocs.length > 0
    ? selectedDocs
        .map(
          (d, idx) =>
            `| [${idx + 1}] \`${d.fileName}\` | Cung cấp bằng chứng nội bộ (${d.totalChunks} chunks) | \`${d.status}\` |`,
        )
        .join("\n")
    : "| Chưa chọn tài liệu | Cần bổ sung tài liệu vào dự án | — |"
}

## 5. Contradictions

- Giữa ưu tiên **tốc độ phản hồi tức thời** và **độ chính xác qua bước Cross-Encoder Reranking**: tăng số lượng ứng viên rerank giúp cải thiện độ chính xác nhưng làm tăng độ trễ suy luận trên thiết bị cục bộ${firstCitationTag}.
- Chưa phát hiện mâu thuẫn nội dung trực tiếp giữa các đoạn văn bản đã trích xuất trong phạm vi mẫu hiện tại.

## 6. Research Gaps

- Cần số liệu thực nghiệm định lượng (ví dụ: Context Precision, Faithfulness) trên tập dữ liệu thực tế khi Backend RAG hoàn tất tích hợp.
- Cần cơ chế ánh xạ byte-offset chi tiết từ bộ parser PDF để tô sáng chính xác từng cụm từ trên trang tài liệu gốc${secondCitationTag}.

## 7. Conclusion

Khung nghiên cứu kết hợp tài liệu nội bộ có kiểm chứng nguồn mang lại cấu trúc làm việc rõ ràng, minh bạch. Khi dịch vụ Backend Research được kết nối, các mục trên sẽ được điền tự động từ kết quả truy xuất và tổng hợp thực tế.

## 8. References

${docRefs}
`
}
