import { useState } from "react"
import {
  Copy,
  FileText,
  FolderOpen,
  Globe,
  HardDrive,
  MoreHorizontal,
  Moon,
  Plus,
  RefreshCw,
  Sparkles,
  Sun,
  Trash2,
} from "lucide-react"
import { PageHeader } from "@/components/common/PageHeader"
import {
  Alert,
  Badge,
  Button,
  Dialog,
  DropdownMenu,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  EmptyState,
  FormField,
  Input,
  Select,
  SelectDropdown,
  Skeleton,
  SkeletonLines,
  StatusBadge,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
  Textarea,
  Tooltip,
} from "@/components/ui"
import { useAppStore } from "@/store/app-store"
import { DESIGN_TOKENS } from "@/utils/tokens"
import type { DocumentStatus } from "@/types"

const PIPELINE_DEMO_STATUSES: DocumentStatus[] = [
  "uploaded",
  "extracting",
  "cleaning",
  "chunking",
  "embedding",
  "indexing",
  "ready",
  "failed",
]

const AI_MODE_OPTIONS = [
  {
    value: "auto",
    label: "Auto (Tự động định tuyến)",
    description: "Ưu tiên kho tri thức cục bộ trước khi đề xuất mở rộng",
    icon: <Sparkles className="h-3.5 w-3.5" />,
  },
  {
    value: "local",
    label: "Local (Chỉ đọc tài liệu trên máy)",
    description: "Không gửi dữ liệu ra Internet",
    icon: <HardDrive className="h-3.5 w-3.5" />,
  },
  {
    value: "hybrid",
    label: "Hybrid (Kho cục bộ + Web Search)",
    description: "Kết hợp BM25, Vector và nguồn Web có xác nhận",
    icon: <Globe className="h-3.5 w-3.5" />,
  },
  {
    value: "disabled-mode",
    label: "Cloud Enterprise (Chưa kích hoạt)",
    description: "Tuỳ chọn minh họa trạng thái disabled",
    disabled: true,
  },
]

export function DesignSystemPage() {
  const theme = useAppStore((s) => s.theme)
  const setTheme = useAppStore((s) => s.setTheme)
  const toast = useAppStore((s) => s.toast)

  const [dialogOpen, setDialogOpen] = useState(false)
  const [customSelectVal, setCustomSelectVal] = useState("local")
  const [nativeSelectVal, setNativeSelectVal] = useState("hybrid_rag")
  const [loadingDemo, setLoadingDemo] = useState(false)
  const [dismissedAlert, setDismissedAlert] = useState(false)

  const palette = theme === "dark" ? DESIGN_TOKENS.colors.dark : DESIGN_TOKENS.colors.light

  const triggerLoadingDemo = () => {
    setLoadingDemo(true)
    window.setTimeout(() => {
      setLoadingDemo(false)
      toast({
        title: "Đã hoàn tất tác vụ mô phỏng",
        description: "Trạng thái loading của Button đã kết thúc.",
        tone: "success",
      })
    }, 1200)
  }

  return (
    <div className="mx-auto max-w-5xl px-4 py-8 md:px-8">
      <PageHeader
        breadcrumb={["Hệ thống", "Design System"]}
        title="Notion-Inspired Design System"
        description="Bộ quy chuẩn giao diện Notion-inspired Minimal Workspace: nền #FFFFFF, sidebar #F7F7F5, hover #F1F1EF, active #EDEDEB, chữ chính #191919, đường viền mảnh 1px #E9E9E7 và accent tiết chế #D97757."
        actions={
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              leftIcon={theme === "light" ? <Moon className="h-3.5 w-3.5" /> : <Sun className="h-3.5 w-3.5" />}
              onClick={() => setTheme(theme === "light" ? "dark" : "light")}
            >
              {theme === "light" ? "Chuyển sang Dark Mode" : "Chuyển sang Light Mode"}
            </Button>
          </div>
        }
      />

      {/* 1. DESIGN TOKENS */}
      <section className="mb-10 border-t border-line pt-6">
        <div className="mb-4">
          <h2 className="text-lg font-semibold">1. Design Tokens ({theme === "light" ? "Light Mode" : "Dark Mode"})</h2>
          <p className="text-xs text-muted">
            Main background #FFFFFF, Sidebar #F7F7F5, Hover #F1F1EF, Active #EDEDEB, Primary text #191919, Secondary text #787774, Border #E9E9E7, Accent tùy chọn #D97757.
          </p>
        </div>

        <div className="grid gap-px border border-line bg-line sm:grid-cols-2 lg:grid-cols-3">
          {Object.entries(palette).map(([key, token]) => (
            <div key={key} className="flex items-center gap-3 bg-bg p-3">
              <span
                className="h-9 w-9 shrink-0 rounded-md border border-line"
                style={{ backgroundColor: `var(${token.cssVar})` }}
              />
              <div className="min-w-0">
                <p className="truncate text-xs font-medium text-ink">{token.label}</p>
                <p className="font-mono text-[11px] text-muted">
                  {token.value} · {token.cssVar}
                </p>
              </div>
            </div>
          ))}
        </div>

        <div className="mt-6 grid gap-6 md:grid-cols-2">
          <div>
            <h3 className="mb-2 text-xs font-medium uppercase tracking-wide text-muted">Typography Scale (Inter / Geist)</h3>
            <div className="divide-y divide-line border-y border-line">
              {DESIGN_TOKENS.typography.sizes.map((item) => (
                <div key={item.name} className="flex items-baseline justify-between py-2 text-xs">
                  <span className="font-medium text-ink">{item.name}</span>
                  <span className="font-mono text-muted">
                    {item.size} · w{item.weight} · lh {item.lineHeight}
                  </span>
                </div>
              ))}
            </div>
          </div>

          <div>
            <h3 className="mb-2 text-xs font-medium uppercase tracking-wide text-muted">Spacing & Border Radius</h3>
            <div className="divide-y divide-line border-y border-line">
              {DESIGN_TOKENS.spacing.map((s) => (
                <div key={s.token} className="flex items-center justify-between py-1.5 text-xs">
                  <span className="font-mono text-ink">{s.token} ({s.value})</span>
                  <span className="text-muted">{s.usage}</span>
                </div>
              ))}
              {DESIGN_TOKENS.radius.map((r) => (
                <div key={r.token} className="flex items-center justify-between py-1.5 text-xs">
                  <span className="font-mono text-ink">{r.token} ({r.value})</span>
                  <span className="text-muted">{r.usage}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* 2. BUTTONS & INTERACTIVE STATES */}
      <section className="mb-10 border-t border-line pt-6">
        <h2 className="mb-1 text-lg font-semibold">2. Button & Trạng thái tương tác</h2>
        <p className="mb-4 text-xs text-muted">
          Hỗ trợ đầy đủ các biến thể, kích thước và trạng thái hover, focus-visible, loading, disabled, success, warning, error.
        </p>

        <div className="space-y-4">
          <div>
            <p className="mb-2 text-xs font-medium text-muted">Variants</p>
            <div className="flex flex-wrap items-center gap-2">
              <Button variant="default" leftIcon={<Plus className="h-3.5 w-3.5" />}>
                Primary Accent
              </Button>
              <Button variant="secondary">Secondary</Button>
              <Button variant="outline">Outline</Button>
              <Button variant="ghost">Ghost</Button>
              <Button variant="success">Success</Button>
              <Button variant="warning">Warning</Button>
              <Button variant="danger" leftIcon={<Trash2 className="h-3.5 w-3.5" />}>
                Danger
              </Button>
            </div>
          </div>

          <div>
            <p className="mb-2 text-xs font-medium text-muted">Sizes & Interactive States (Loading / Disabled)</p>
            <div className="flex flex-wrap items-center gap-2">
              <Button size="xs" variant="outline">Size XS</Button>
              <Button size="sm" variant="outline">Size SM</Button>
              <Button size="md" variant="outline">Size MD</Button>
              <Button size="lg" variant="outline">Size LG</Button>
              <Button loading={loadingDemo} onClick={triggerLoadingDemo}>
                {loadingDemo ? "Đang xử lý..." : "Nhấn thử Loading"}
              </Button>
              <Button loading variant="outline">
                Đang tải tĩnh
              </Button>
              <Button disabled variant="default">
                Disabled Primary
              </Button>
              <Button disabled variant="outline">
                Disabled Outline
              </Button>
            </div>
          </div>
        </div>
      </section>

      {/* 3. INPUT, TEXTAREA & VALIDATION STATES */}
      <section className="mb-10 border-t border-line pt-6">
        <h2 className="mb-1 text-lg font-semibold">3. Input, Textarea & Validation States</h2>
        <p className="mb-4 text-xs text-muted">
          Đường viền mảnh #E9E9E7, đổi viền tím #6B63C8 khi focus và phản hồi rõ ràng theo trạng thái dữ liệu.
        </p>

        <div className="grid gap-4 sm:grid-cols-2">
          <FormField label="Mặc định (Default)" hint="Có thể nhập" message="Nhấn vào ô để kiểm tra focus ring màu nhấn.">
            <Input defaultValue="Nghiên cứu Hybrid RAG" placeholder="Nhập tên workspace..." />
          </FormField>

          <FormField label="Vô hiệu hóa (Disabled)" message="Không cho phép chỉnh sửa khi đang khóa.">
            <Input disabled value="qwen2.5:3b (Chỉ đọc)" />
          </FormField>

          <FormField
            label="Thành công (Success)"
            state="success"
            message="Đường dẫn kho lưu trữ hợp lệ và có quyền ghi."
          >
            <Input state="success" defaultValue="./sourcecode/backend/data" />
          </FormField>

          <FormField
            label="Cảnh báo (Warning)"
            state="warning"
            message="Mô hình embedding chưa được tải về máy cục bộ."
          >
            <Input state="warning" defaultValue="BAAI/bge-m3" />
          </FormField>

          <FormField
            label="Báo lỗi (Error)"
            state="error"
            message="Định dạng tệp .exe không nằm trong danh sách cho phép."
          >
            <Input state="error" defaultValue="unknown-installer.exe" />
          </FormField>

          <FormField label="Textarea (Ghi chú tài liệu)" hint="Markdown hỗ trợ">
            <Textarea
              rows={3}
              defaultValue="Reciprocal Rank Fusion (RRF) kết hợp kết quả từ BM25 và Vector Search trước khi qua bước Cross-Encoder Reranker."
            />
          </FormField>
        </div>
      </section>

      {/* 4. SELECT & DROPDOWN + 7. DROPDOWN MENU */}
      <section className="mb-10 border-t border-line pt-6">
        <h2 className="mb-1 text-lg font-semibold">4. Select, Custom Dropdown & Dropdown Menu</h2>
        <p className="mb-4 text-xs text-muted">
          Hỗ trợ cả Native Select chuẩn hóa lẫn Custom SelectDropdown có mô tả chi tiết và DropdownMenu hành động.
        </p>

        <div className="grid gap-4 sm:grid-cols-3">
          <FormField label="Native Select" message={`Giá trị đang chọn: ${nativeSelectVal}`}>
            <Select value={nativeSelectVal} onChange={(e) => setNativeSelectVal(e.target.value)}>
              <option value="hybrid_rag">Workspace: Nghiên cứu RAG</option>
              <option value="ai_course">Workspace: Học phần Trí tuệ nhân tạo</option>
              <option value="personal">Workspace: Ghi chú cá nhân</option>
            </Select>
          </FormField>

          <FormField label="Custom SelectDropdown" message={`Chế độ đang chọn: ${customSelectVal}`}>
            <SelectDropdown
              value={customSelectVal}
              options={AI_MODE_OPTIONS}
              onChange={setCustomSelectVal}
            />
          </FormField>

          <FormField label="Dropdown Menu (Action Menu)" message="Hỗ trợ phím Escape và click ra ngoài để đóng.">
            <div>
              <DropdownMenu
                align="start"
                trigger={
                  <Button variant="outline" leftIcon={<MoreHorizontal className="h-4 w-4" />}>
                    Mở menu thao tác
                  </Button>
                }
              >
                <DropdownMenuLabel>Tài liệu</DropdownMenuLabel>
                <DropdownMenuItem
                  icon={<FileText className="h-3.5 w-3.5" />}
                  shortcut="Enter"
                  onClick={() => toast({ title: "Đã chọn: Mở trình đọc nguồn", tone: "info" })}
                >
                  Mở trình đọc nguồn
                </DropdownMenuItem>
                <DropdownMenuItem
                  icon={<Copy className="h-3.5 w-3.5" />}
                  shortcut="Ctrl+C"
                  onClick={() => toast({ title: "Đã sao chép mã trích dẫn [1]", tone: "success" })}
                >
                  Sao chép trích dẫn
                </DropdownMenuItem>
                <DropdownMenuItem icon={<RefreshCw className="h-3.5 w-3.5" />} disabled>
                  Chạy lại indexing (Disabled)
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem
                  tone="danger"
                  icon={<Trash2 className="h-3.5 w-3.5" />}
                  shortcut="Del"
                  onClick={() => toast({ title: "Đã chọn thao tác xóa (mô phỏng)", tone: "warning" })}
                >
                  Xóa khỏi workspace
                </DropdownMenuItem>
              </DropdownMenu>
            </div>
          </FormField>
        </div>
      </section>

      {/* 5. BADGE & TOOLTIP & DIALOG */}
      <section className="mb-10 border-t border-line pt-6">
        <h2 className="mb-1 text-lg font-semibold">5. Badge, Tooltip & Dialog</h2>
        <p className="mb-4 text-xs text-muted">
          Badge phân biệt rõ trạng thái tài liệu trong pipeline RAG; Tooltip và Dialog tối giản không lạm dụng đổ bóng.
        </p>

        <div className="space-y-4">
          <div>
            <p className="mb-2 text-xs font-medium text-muted">Semantic Badges</p>
            <div className="flex flex-wrap gap-2">
              <Badge tone="neutral" dot>Neutral / Local</Badge>
              <Badge tone="accent" dot>Warm Accent (#D97757)</Badge>
              <Badge tone="success" dot>Success / Ready</Badge>
              <Badge tone="warning" dot>Warning / Mock</Badge>
              <Badge tone="error" dot>Error / Failed</Badge>
            </div>
          </div>

          <div>
            <p className="mb-2 text-xs font-medium text-muted">Document Pipeline Status Badges</p>
            <div className="flex flex-wrap gap-2">
              {PIPELINE_DEMO_STATUSES.map((st) => (
                <StatusBadge key={st} status={st} />
              ))}
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-3 pt-2">
            <Tooltip content="Hiển thị phía trên (Top)" side="top">
              <Button variant="outline" size="sm">Tooltip Top</Button>
            </Tooltip>
            <Tooltip content="Hiển thị phía dưới (Bottom)" side="bottom">
              <Button variant="outline" size="sm">Tooltip Bottom</Button>
            </Tooltip>
            <Tooltip content="Hiển thị bên phải (Right)" side="right">
              <Button variant="outline" size="sm">Tooltip Right</Button>
            </Tooltip>
            <Button variant="default" size="sm" onClick={() => setDialogOpen(true)}>
              Mở Dialog mẫu
            </Button>
          </div>
        </div>

        <Dialog
          open={dialogOpen}
          title="Xác nhận cấu hình truy vấn ngoài"
          description="Dialog sử dụng đường viền 1px tinh gọn, hỗ trợ phím Escape hoặc nhấn nền mờ để đóng."
          onClose={() => setDialogOpen(false)}
          footer={
            <>
              <Button variant="outline" onClick={() => setDialogOpen(false)}>
                Hủy
              </Button>
              <Button
                onClick={() => {
                  setDialogOpen(false)
                  toast({ title: "Đã lưu xác nhận trên Dialog", tone: "success" })
                }}
              >
                Đồng ý
              </Button>
            </>
          }
        >
          <p className="text-sm text-ink">
            Khi bật chế độ <strong>Web</strong> hoặc <strong>Hybrid</strong>, câu hỏi có thể được gửi tới dịch vụ tìm kiếm bên ngoài. Tài liệu gốc trong máy vẫn được giữ cục bộ.
          </p>
        </Dialog>
      </section>

      {/* 6. TABS, TABLE, SKELETON & EMPTY STATE */}
      <section className="mb-10 border-t border-line pt-6">
        <h2 className="mb-1 text-lg font-semibold">6. Tabs, Table, Skeleton & Empty State</h2>
        <p className="mb-4 text-xs text-muted">
          Chuyển đổi giữa bảng dữ liệu chuẩn Notion, trạng thái đang tải (Skeleton) và trạng thái rỗng (Empty State).
        </p>

        <Tabs defaultValue="table">
          <TabsList variant="underline">
            <TabsTrigger value="table">Table (Bảng dữ liệu)</TabsTrigger>
            <TabsTrigger value="skeleton">Skeleton (Đang tải)</TabsTrigger>
            <TabsTrigger value="empty">Empty State (Trạng thái trống)</TabsTrigger>
            <TabsTrigger value="disabled" disabled>
              Tab Disabled
            </TabsTrigger>
          </TabsList>

          <TabsContent value="table">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Tài liệu</TableHead>
                  <TableHead>Định dạng</TableHead>
                  <TableHead>Số chunk</TableHead>
                  <TableHead>Nguồn dữ liệu</TableHead>
                  <TableHead>Trạng thái</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                <TableRow>
                  <TableCell className="font-medium">Hybrid-RAG-Survey.pdf</TableCell>
                  <TableCell className="uppercase text-muted">PDF</TableCell>
                  <TableCell>48 chunks</TableCell>
                  <TableCell><Badge tone="warning">Dữ liệu mô phỏng</Badge></TableCell>
                  <TableCell><StatusBadge status="ready" /></TableCell>
                </TableRow>
                <TableRow>
                  <TableCell className="font-medium">Bai-giang-07-Retrieval.pptx</TableCell>
                  <TableCell className="uppercase text-muted">PPTX</TableCell>
                  <TableCell>22 chunks</TableCell>
                  <TableCell><Badge tone="warning">Dữ liệu mô phỏng</Badge></TableCell>
                  <TableCell><StatusBadge status="indexing" /></TableCell>
                </TableRow>
                <TableRow>
                  <TableCell className="font-medium">scan-low-quality.pdf</TableCell>
                  <TableCell className="uppercase text-muted">PDF</TableCell>
                  <TableCell>0 chunks</TableCell>
                  <TableCell><Badge tone="warning">Dữ liệu mô phỏng</Badge></TableCell>
                  <TableCell><StatusBadge status="failed" /></TableCell>
                </TableRow>
              </TableBody>
            </Table>
          </TabsContent>

          <TabsContent value="skeleton">
            <div className="space-y-4 rounded-lg border border-line p-4">
              <div className="flex items-center gap-3">
                <Skeleton className="h-9 w-9 rounded-lg" />
                <div className="flex-1 space-y-2">
                  <Skeleton className="h-4 w-48" />
                  <Skeleton className="h-3 w-32" />
                </div>
              </div>
              <SkeletonLines lines={4} />
            </div>
          </TabsContent>

          <TabsContent value="empty">
            <EmptyState
              compact
              icon={<FolderOpen className="h-4 w-4" />}
              title="Chưa có tài liệu nào trong notebook này"
              description="Tải lên PDF, DOCX, PPTX, TXT hoặc Markdown để bắt đầu trích xuất văn bản và tạo chỉ mục."
              action={
                <Button size="sm" leftIcon={<Plus className="h-3.5 w-3.5" />}>
                  Tải tài liệu đầu tiên
                </Button>
              }
            />
          </TabsContent>
        </Tabs>
      </section>

      {/* 7. ALERT & TOAST */}
      <section className="border-t border-line pt-6">
        <h2 className="mb-1 text-lg font-semibold">7. Alert & Toast Notifications</h2>
        <p className="mb-4 text-xs text-muted">
          Thông báo trạng thái rõ ràng, trung thực về tình trạng kết nối Backend, Local LLM và dữ liệu mô phỏng.
        </p>

        <div className="space-y-3">
          {!dismissedAlert ? (
            <Alert
              tone="accent"
              title="Định hướng minh bạch trạng thái AI"
              description="Hệ thống luôn phân biệt rõ kết quả từ kho tài liệu thật với dữ liệu mô phỏng khi Backend chưa chạy."
              onDismiss={() => setDismissedAlert(true)}
            />
          ) : null}
          <Alert
            tone="info"
            title="Thông tin (Info)"
            description="Đang sử dụng bộ nhớ cục bộ của trình duyệt để lưu cấu hình giao diện."
          />
          <Alert
            tone="success"
            title="Hoàn tất (Success)"
            description="Đã kiểm tra cấu trúc Design System và đồng bộ Light/Dark Mode."
          />
          <Alert
            tone="warning"
            title="Cảnh báo (Warning — Dữ liệu mô phỏng)"
            description="Backend chưa kết nối — các câu trả lời mẫu chỉ phục vụ kiểm thử giao diện, không phải kết quả từ Local LLM."
          />
          <Alert
            tone="error"
            title="Lỗi xử lý (Error)"
            description="Không thể trích xuất văn bản từ tệp PDF bị hỏng hoặc chỉ chứa ảnh scan chưa OCR."
          />
        </div>

        <div className="mt-4 flex flex-wrap gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() =>
              toast({
                title: "Thông báo Info",
                description: "Đã lưu trạng thái bộ lọc tạm thời.",
                tone: "info",
              })
            }
          >
            Bắn Toast Info
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() =>
              toast({
                title: "Thành công",
                description: "Đã cập nhật ghi chú vào notebook.",
                tone: "success",
              })
            }
          >
            Bắn Toast Success
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() =>
              toast({
                title: "Cảnh báo chế độ mô phỏng",
                description: "Backend hiện đang offline, dữ liệu chỉ lưu cục bộ.",
                tone: "warning",
              })
            }
          >
            Bắn Toast Warning
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() =>
              toast({
                title: "Lỗi kết nối API",
                description: "Không thể kết nối tới máy chủ tại cổng 8000.",
                tone: "error",
              })
            }
          >
            Bắn Toast Error
          </Button>
        </div>
      </section>
    </div>
  )
}
