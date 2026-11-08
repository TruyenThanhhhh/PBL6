import { Link } from "react-router-dom"

export function WelcomePage() {
  return (
    <div className="min-h-screen bg-surface-cream text-slate-800 antialiased font-sans selection:bg-brand-200 selection:text-brand-900 scroll-smooth">
      {/* BEGIN: MainHeader */}
      <header className="sticky top-0 z-50 bg-surface-cream/80 backdrop-blur-md border-b border-slate-200/60 transition-all duration-300">
        <div className="max-w-7xl mx-auto px-6 lg:px-12 h-20 flex items-center justify-between">
          {/* Brand Logo */}
          <Link
            to="/"
            className="flex items-center gap-3 group focus:outline-none focus:ring-2 focus:ring-brand-500 rounded-full py-1 pr-2"
          >
            <div className="w-8 h-8 rounded-full bg-brand-500 flex items-center justify-center text-white shadow-md shadow-brand-500/20 group-hover:scale-105 transition-transform">
              {/* Motivo Asterisk Icon */}
              <svg className="w-4 h-4 fill-current" viewBox="0 0 24 24" aria-hidden="true">
                <path d="M12 2a1 1 0 0 1 1 1v6.2l4.38-4.38a1 1 0 1 1 1.42 1.42L14.42 10.6l6.2.02a1 1 0 0 1 0 2l-6.2-.02 4.38 4.38a1 1 0 0 1-1.42 1.42L13 14.02V20.2a1 1 0 0 1-2 0v-6.18l-4.38 4.38a1 1 0 1 1-1.42-1.42l4.38-4.38-6.2-.02a1 1 0 1 1 0-2l6.2.02-4.38-4.38a1 1 0 0 1 1.42-1.42L11 8.82V3a1 1 0 0 1 1-1Z" />
              </svg>
            </div>
            <div className="flex items-baseline">
              <span className="text-2xl font-bold tracking-tight text-slate-900">motivo</span>
              <span className="text-2xl font-semibold text-brand-600">.rag</span>
            </div>
          </Link>

          {/* Right Action CTAs */}
          <div className="flex items-center gap-4">
            <Link
              to="/login"
              className="hidden sm:inline-block text-[15px] font-medium text-slate-700 hover:text-slate-900 px-3 py-2 transition-colors"
            >
              Đăng nhập
            </Link>
            <Link
              to="/hub"
              className="inline-flex items-center gap-2 px-5 py-2.5 rounded-full bg-slate-950 text-white text-[14px] font-medium shadow-pill hover:bg-slate-800 active:scale-95 transition-all"
            >
              <span>Bắt đầu ngay</span>
              <svg
                className="w-4 h-4 text-brand-300"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                viewBox="0 0 24 24"
                aria-hidden="true"
              >
                <path d="M14 5l7 7m0 0l-7 7m7-7H3" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </Link>
          </div>
        </div>
      </header>
      {/* END: MainHeader */}

      {/* BEGIN: HeroSection */}
      <section className="relative pt-12 pb-20 lg:pt-16 lg:pb-32 overflow-hidden" data-purpose="hero-container">
        <div className="max-w-7xl mx-auto px-6 lg:px-12">
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-12 lg:gap-8 items-center">
            {/* Left Column: Copy & Actions */}
            <div className="lg:col-span-7 space-y-7 z-10">
              {/* Badge */}
              <div className="inline-flex items-center gap-2.5 px-3.5 py-1.5 rounded-full bg-brand-50 border border-brand-200/80 shadow-xs">
                <span className="flex h-2 w-2 relative">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-brand-400 opacity-75"></span>
                  <span className="relative inline-flex rounded-full h-2 w-2 bg-brand-500"></span>
                </span>
                <span className="text-xs font-semibold uppercase tracking-wider text-brand-700">
                  Local AI Engine v0.9.4
                </span>
                <span className="text-xs text-slate-500 font-normal">| Hoàn toàn riêng tư trên máy của bạn</span>
              </div>

              {/* Main Hero Heading */}
              <h1 className="text-4xl sm:text-6xl lg:text-[68px] font-bold text-slate-950 tracking-tight leading-[1.08]">
                Tư duy sâu sắc hơn, <br />
                cùng nhau. <br />
                <span className="font-serif-italic text-brand-600 font-normal">Đạt hiệu quả vượt trội.</span>
              </h1>

              {/* Subtitle */}
              <p className="text-lg sm:text-xl text-slate-600 max-w-xl font-normal leading-relaxed">
                Không gian làm việc tri thức AI cá nhân với Hybrid RAG &amp; Local LLM, bảo mật 100% trên thiết bị của bạn.
              </p>

              {/* Buttons Group */}
              <div className="pt-2 flex flex-wrap items-center gap-4 sm:gap-5">
                <Link
                  to="/hub"
                  className="inline-flex items-center gap-3 px-7 py-4 rounded-full bg-slate-950 text-white font-medium text-base hover:bg-slate-800 transition-all shadow-lg shadow-slate-950/15 group"
                >
                  <span>Trải nghiệm miễn phí</span>
                  <svg
                    className="w-4 h-4 text-brand-400 group-hover:translate-x-1 transition-transform"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    viewBox="0 0 24 24"
                    aria-hidden="true"
                  >
                    <path d="M14 5l7 7m0 0l-7 7m7-7H3" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                </Link>

                <a
                  href="#features"
                  className="inline-flex items-center gap-2 px-6 py-4 rounded-full bg-white border border-slate-200 text-slate-700 font-medium text-base hover:bg-slate-50 hover:border-slate-300 transition-all"
                >
                  <span>Tìm hiểu kiến trúc</span>
                </a>
              </div>
            </div>

            {/* Right Column: Motivo 3D Glass Artwork Composition */}
            <div className="lg:col-span-5 relative flex items-center justify-center min-h-[440px] sm:min-h-[520px]">
              {/* Outer Decorative Subtle Ring */}
              <div className="absolute w-[420px] h-[420px] rounded-full border border-teal-100/80 -z-10 animate-pulse"></div>
              {/* Glass Disk (Đĩa thủy tinh lớn phía sau) */}
              <div className="absolute w-80 h-80 rounded-full glass-disk -top-4 right-2 sm:right-6"></div>
              {/* Fluted Prism Glass Column (Lăng kính sọc đứng) */}
              <div className="absolute w-36 h-80 rounded-2xl glass-prism -top-2 right-12 sm:right-20 rotate-6"></div>
              {/* Glass Arch Shape (Vòm kính ngọc bích phía trước) */}
              <div className="absolute bottom-6 right-8 w-44 h-48 rounded-t-full glass-arch z-20 flex items-center justify-center">
                <div className="w-24 h-28 rounded-t-full bg-white/30 backdrop-blur-xs border border-white/40"></div>
              </div>
              {/* Sphere 1 (Quả cầu ngọc bích chính ở giữa) */}
              <div className="relative z-30 w-44 h-44 rounded-full glass-orb -translate-x-12 translate-y-8 flex items-center justify-center">
                <div className="w-8 h-8 rounded-full bg-white/40 blur-[2px]"></div>
              </div>
              {/* Floating Badge / Micro card */}
              <div className="absolute top-10 right-0 z-40 bg-white/90 backdrop-blur-md p-4 rounded-2xl border border-slate-100 shadow-xl max-w-[190px]">
                <div className="flex items-center justify-between mb-2">
                  <span className="w-2 h-2 rounded-full bg-brand-500"></span>
                  <svg
                    className="w-3.5 h-3.5 text-slate-400"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                    aria-hidden="true"
                  >
                    <path d="M7 17L17 7M17 7H7M17 7V17" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" />
                  </svg>
                </div>
                <p className="text-xs font-semibold text-slate-800 leading-snug">
                  Toàn bộ dữ liệu của bạn, trong luồng làm việc hoàn hảo.
                </p>
              </div>
              {/* Small Floating Mini Orb */}
              <div className="absolute bottom-2 left-6 z-20 w-16 h-16 rounded-full bg-gradient-to-tr from-brand-300 to-white shadow-lg opacity-90 blur-[0.5px]"></div>
            </div>
          </div>
        </div>
      </section>
      {/* END: HeroSection */}

      {/* BEGIN: MetricBar */}
      <section className="max-w-7xl mx-auto px-6 lg:px-12 -mt-4 mb-24" data-purpose="metrics-counter-bar">
        <div className="bg-white rounded-3xl p-6 sm:p-8 border border-slate-200/80 shadow-soft grid grid-cols-2 md:grid-cols-4 gap-6 lg:gap-8 divide-y sm:divide-y-0 sm:divide-x divide-slate-100">
          {/* Metric 1 */}
          <div className="flex items-center gap-4 pt-4 sm:pt-0 sm:px-4 first:pt-0 first:px-0">
            <div className="w-12 h-12 rounded-2xl bg-brand-50 text-brand-600 flex items-center justify-center shrink-0 border border-brand-100">
              <svg className="w-6 h-6" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24" aria-hidden="true">
                <path
                  d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            </div>
            <div>
              <div className="text-2xl lg:text-3xl font-bold tracking-tight text-slate-900">100%</div>
              <div className="text-xs sm:text-sm text-slate-500 font-medium">Offline &amp; On-Device</div>
            </div>
          </div>

          {/* Metric 2 */}
          <div className="flex items-center gap-4 pt-4 sm:pt-0 sm:px-4">
            <div className="w-12 h-12 rounded-2xl bg-brand-50 text-brand-600 flex items-center justify-center shrink-0 border border-brand-100">
              <svg className="w-6 h-6" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24" aria-hidden="true">
                <path
                  d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            </div>
            <div>
              <div className="text-2xl lg:text-3xl font-bold tracking-tight text-slate-900">0%</div>
              <div className="text-xs sm:text-sm text-slate-500 font-medium">Rò rỉ dữ liệu Internet</div>
            </div>
          </div>

          {/* Metric 3 */}
          <div className="flex items-center gap-4 pt-4 sm:pt-0 sm:px-4">
            <div className="w-12 h-12 rounded-2xl bg-brand-50 text-brand-600 flex items-center justify-center shrink-0 border border-brand-100">
              <svg className="w-6 h-6" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24" aria-hidden="true">
                <path d="M13 10V3L4 14h7v7l9-11h-7z" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </div>
            <div>
              <div className="text-2xl lg:text-3xl font-bold tracking-tight text-slate-900">&lt; 18ms</div>
              <div className="text-xs sm:text-sm text-slate-500 font-medium">Truy xuất Qdrant Vector</div>
            </div>
          </div>

          {/* Metric 4 */}
          <div className="flex items-center gap-4 pt-4 sm:pt-0 sm:px-4">
            <div className="w-12 h-12 rounded-2xl bg-brand-50 text-brand-600 flex items-center justify-center shrink-0 border border-brand-100">
              <svg className="w-6 h-6" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24" aria-hidden="true">
                <path
                  d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            </div>
            <div>
              <div className="text-2xl lg:text-3xl font-bold tracking-tight text-slate-900">50k+</div>
              <div className="text-xs sm:text-sm text-slate-500 font-medium">Nhà nghiên cứu tin cậy</div>
            </div>
          </div>
        </div>
      </section>
      {/* END: MetricBar */}

      {/* BEGIN: FeatureShowcase */}
      <section
        className="py-16 lg:py-24 bg-surface-subtle border-y border-slate-200/60"
        data-purpose="features-comparison"
        id="features"
      >
        <div className="max-w-7xl mx-auto px-6 lg:px-12">
          <div className="max-w-3xl mx-auto text-left space-y-4 mb-12">
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-brand-50 border border-brand-200/80 text-[11px] font-semibold tracking-wider text-brand-700 uppercase">
              <span className="w-1.5 h-1.5 rounded-full bg-brand-500"></span>
              Kiến trúc đột phá
            </div>
            <h2 className="text-3xl sm:text-4xl lg:text-5xl font-bold text-slate-950 tracking-tight leading-tight">
              Tất cả công cụ bạn cần,
              <br />
              <span className="font-serif-italic text-brand-600 font-normal">kết nối mượt mà.</span>
            </h2>
            <p className="text-base sm:text-lg text-slate-600 font-normal leading-relaxed pt-1">
              Lập kế hoạch, cộng tác và biến mọi văn bản kỹ thuật dày cộm thành câu trả lời chính xác trong tích tắc.
            </p>
          </div>

          <div className="max-w-3xl mx-auto space-y-4">
            {/* Feature 1 */}
            <div className="group relative flex items-start gap-5 p-5 sm:p-6 rounded-2xl bg-white border border-slate-200/80 shadow-xs hover:border-brand-400 hover:shadow-soft transition-all duration-300">
              <div className="w-12 h-12 rounded-xl bg-brand-50 text-brand-600 border border-brand-100/80 flex items-center justify-center shrink-0 group-hover:scale-105 group-hover:bg-brand-100 transition-all">
                <svg className="w-6 h-6" fill="none" stroke="currentColor" strokeWidth="1.8" viewBox="0 0 24 24" aria-hidden="true">
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z"
                  />
                </svg>
              </div>
              <div className="flex-1">
                <div className="flex items-center justify-between gap-4">
                  <div className="flex flex-wrap items-center gap-2.5">
                    <h3 className="text-base sm:text-lg font-semibold text-slate-900 group-hover:text-brand-700 transition-colors">
                      Hybrid RAG thông minh
                    </h3>
                    <span className="px-2 py-0.5 rounded-full text-[11px] font-medium bg-brand-50 text-brand-700 border border-brand-200/60">
                      BM25 + BGE
                    </span>
                  </div>
                  <svg
                    className="w-5 h-5 text-slate-400 group-hover:text-brand-600 group-hover:translate-x-1 transition-all shrink-0"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    viewBox="0 0 24 24"
                    aria-hidden="true"
                  >
                    <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
                  </svg>
                </div>
                <p className="text-xs sm:text-sm text-slate-600 mt-2 leading-relaxed">
                  Kết hợp BM25 Keyword Search, Vector Search và BGE-Reranker để loại bỏ ảo giác (Hallucination) tuyệt đối.
                </p>
              </div>
            </div>

            {/* Feature 2 */}
            <div className="group relative flex items-start gap-5 p-5 sm:p-6 rounded-2xl bg-white border border-slate-200/80 shadow-xs hover:border-brand-400 hover:shadow-soft transition-all duration-300">
              <div className="w-12 h-12 rounded-xl bg-brand-50 text-brand-600 border border-brand-100/80 flex items-center justify-center shrink-0 group-hover:scale-105 group-hover:bg-brand-100 transition-all">
                <svg className="w-6 h-6" fill="none" stroke="currentColor" strokeWidth="1.8" viewBox="0 0 24 24" aria-hidden="true">
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"
                  />
                </svg>
              </div>
              <div className="flex-1">
                <div className="flex items-center justify-between gap-4">
                  <div className="flex flex-wrap items-center gap-2.5">
                    <h3 className="text-base sm:text-lg font-semibold text-slate-900 group-hover:text-brand-700 transition-colors">
                      Quyền riêng tư &amp; Zero-Knowledge
                    </h3>
                    <span className="px-2 py-0.5 rounded-full text-[11px] font-medium bg-brand-50 text-brand-700 border border-brand-200/60">
                      AES-256
                    </span>
                  </div>
                  <svg
                    className="w-5 h-5 text-slate-400 group-hover:text-brand-600 group-hover:translate-x-1 transition-all shrink-0"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    viewBox="0 0 24 24"
                    aria-hidden="true"
                  >
                    <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
                  </svg>
                </div>
                <p className="text-xs sm:text-sm text-slate-600 mt-2 leading-relaxed">
                  Dữ liệu chỉ nằm trong ổ cứng của bạn. Mã hóa AES-256 nội bộ, không telemetry ẩn danh, không huấn luyện lại AI.
                </p>
              </div>
            </div>

            {/* Feature 3 */}
            <div className="group relative flex items-start gap-5 p-5 sm:p-6 rounded-2xl bg-white border border-slate-200/80 shadow-xs hover:border-brand-400 hover:shadow-soft transition-all duration-300">
              <div className="w-12 h-12 rounded-xl bg-brand-50 text-brand-600 border border-brand-100/80 flex items-center justify-center shrink-0 group-hover:scale-105 group-hover:bg-brand-100 transition-all">
                <svg className="w-6 h-6" fill="none" stroke="currentColor" strokeWidth="1.8" viewBox="0 0 24 24" aria-hidden="true">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z" />
                </svg>
              </div>
              <div className="flex-1">
                <div className="flex items-center justify-between gap-4">
                  <div className="flex flex-wrap items-center gap-2.5">
                    <h3 className="text-base sm:text-lg font-semibold text-slate-900 group-hover:text-brand-700 transition-colors">
                      Tương thích Ollama &amp; LM Studio
                    </h3>
                    <span className="px-2 py-0.5 rounded-full text-[11px] font-medium bg-brand-50 text-brand-700 border border-brand-200/60">
                      Local Models
                    </span>
                  </div>
                  <svg
                    className="w-5 h-5 text-slate-400 group-hover:text-brand-600 group-hover:translate-x-1 transition-all shrink-0"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    viewBox="0 0 24 24"
                    aria-hidden="true"
                  >
                    <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
                  </svg>
                </div>
                <p className="text-xs sm:text-sm text-slate-600 mt-2 leading-relaxed">
                  Một chạm để chuyển đổi mô hình từ Llama 3, Mistral NeMo, Gemma 2 đến DeepSeek-Coder ngay tại máy.
                </p>
              </div>
            </div>
          </div>
        </div>
      </section>
      {/* END: FeatureShowcase */}

      {/* BEGIN: MainFooter */}
      <footer className="bg-white border-t border-slate-200/70 pt-16 pb-12" data-purpose="site-footer">
        <div className="max-w-7xl mx-auto px-6 lg:px-12">
          {/* Top Columns */}
          <div className="grid grid-cols-2 md:grid-cols-5 gap-8 pb-14 border-b border-slate-100">
            {/* Brand Info */}
            <div className="col-span-2 space-y-4">
              <div className="flex items-center gap-2.5">
                <div className="w-7 h-7 rounded-full bg-brand-500 flex items-center justify-center text-white">
                  <svg className="w-3.5 h-3.5 fill-current" viewBox="0 0 24 24" aria-hidden="true">
                    <path d="M12 2a1 1 0 0 1 1 1v6.2l4.38-4.38a1 1 0 1 1 1.42 1.42L14.42 10.6l6.2.02a1 1 0 0 1 0 2l-6.2-.02 4.38 4.38a1 1 0 0 1-1.42 1.42L13 14.02V20.2a1 1 0 0 1-2 0v-6.18l-4.38 4.38a1 1 0 1 1-1.42-1.42l4.38-4.38-6.2-.02a1 1 0 1 1 0-2l6.2.02-4.38-4.38a1 1 0 0 1 1.42-1.42L11 8.82V3a1 1 0 0 1 1-1Z" />
                  </svg>
                </div>
                <span className="text-xl font-bold tracking-tight text-slate-900">
                  motivo<span className="text-brand-600">.rag</span>
                </span>
              </div>
              <p className="text-xs sm:text-sm text-slate-500 max-w-sm font-normal leading-relaxed">
                Không gian làm việc thông minh thế hệ mới dành cho các nhà nghiên cứu, sinh viên và lập trình viên mong muốn làm chủ dữ liệu cá nhân.
              </p>
              {/* Social Icons */}
              <div className="flex items-center gap-4 pt-2 text-slate-400">
                <a aria-label="X Twitter" className="hover:text-slate-700 transition-colors" href="https://x.com" target="_blank" rel="noreferrer">
                  <svg className="w-4 h-4 fill-current" viewBox="0 0 24 24" aria-hidden="true">
                    <path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z" />
                  </svg>
                </a>
                <a aria-label="GitHub" className="hover:text-slate-700 transition-colors" href="https://github.com" target="_blank" rel="noreferrer">
                  <svg className="w-4 h-4 fill-current" viewBox="0 0 24 24" aria-hidden="true">
                    <path
                      clipRule="evenodd"
                      d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.53 1.032 1.53 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z"
                      fillRule="evenodd"
                    />
                  </svg>
                </a>
                <a aria-label="Discord" className="hover:text-slate-700 transition-colors" href="https://discord.com" target="_blank" rel="noreferrer">
                  <svg className="w-4 h-4 fill-current" viewBox="0 0 24 24" aria-hidden="true">
                    <path d="M20.317 4.37a19.791 19.791 0 0 0-4.885-1.515.074.074 0 0 0-.079.037c-.21.375-.444.864-.608 1.25a18.27 18.27 0 0 0-5.487 0 12.64 12.64 0 0 0-.617-1.25.077.077 0 0 0-.079-.037A19.736 19.736 0 0 0 3.677 4.37a.07.07 0 0 0-.032.027C.533 9.046-.32 13.58.099 18.057a.082.082 0 0 0 .031.057 19.9 19.9 0 0 0 5.993 3.03.078.078 0 0 0 .084-.028c.462-.63.874-1.295 1.226-1.994.021-.041.001-.09-.041-.106a13.107 13.107 0 0 1-1.872-.892.077.077 0 0 1-.008-.128 10.2 10.2 0 0 0 .372-.292.074.074 0 0 1 .077-.01c3.929 1.793 8.18 1.793 12.061 0a.074.074 0 0 1 .078.01c.12.098.246.198.373.292a.077.077 0 0 1-.006.127 12.299 12.299 0 0 1-1.873.894.077.077 0 0 0-.041.107c.36.698.772 1.362 1.225 1.993a.076.076 0 0 0 .084.028 19.839 19.839 0 0 0 6.002-3.03.077.077 0 0 0 .032-.054c.5-5.177-.838-9.674-3.549-13.66a.061.061 0 0 0-.031-.028zM8.02 15.33c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.956-2.419 2.157-2.419 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.956 2.418-2.157 2.418zm7.975 0c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.955-2.419 2.157-2.419 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.946 2.418-2.157 2.418z" />
                  </svg>
                </a>
              </div>
            </div>

            {/* Links Column 1 */}
            <div className="space-y-3">
              <h5 className="text-xs font-semibold uppercase tracking-wider text-slate-900">Sản Phẩm</h5>
              <ul className="space-y-2 text-xs sm:text-sm text-slate-600">
                <li>
                  <a className="hover:text-brand-600 transition-colors" href="#features">
                    Tính năng RAG
                  </a>
                </li>
                <li>
                  <a className="hover:text-brand-600 transition-colors" href="#features">
                    Tích hợp Ollama
                  </a>
                </li>
                <li>
                  <a className="hover:text-brand-600 transition-colors" href="#features">
                    Qdrant Vector DB
                  </a>
                </li>
                <li>
                  <span className="text-slate-400">Changelog v0.9.4</span>
                </li>
              </ul>
            </div>

            {/* Links Column 2 */}
            <div className="space-y-3">
              <h5 className="text-xs font-semibold uppercase tracking-wider text-slate-900">Tài Liệu &amp; Nguồn</h5>
              <ul className="space-y-2 text-xs sm:text-sm text-slate-600">
                <li>
                  <a className="hover:text-brand-600 transition-colors" href="https://github.com" target="_blank" rel="noreferrer">
                    Hướng dẫn cài đặt
                  </a>
                </li>
                <li>
                  <a className="hover:text-brand-600 transition-colors" href="#features">
                    Kiến trúc Zero-Knowledge
                  </a>
                </li>
                <li>
                  <a className="hover:text-brand-600 transition-colors" href="http://127.0.0.1:8000/docs" target="_blank" rel="noreferrer">
                    API Docs (Swagger)
                  </a>
                </li>
                <li>
                  <a className="hover:text-brand-600 transition-colors" href="https://discord.com" target="_blank" rel="noreferrer">
                    Cộng đồng Discord
                  </a>
                </li>
              </ul>
            </div>

            {/* Links Column 3 */}
            <div className="space-y-3">
              <h5 className="text-xs font-semibold uppercase tracking-wider text-slate-900">Pháp Lý</h5>
              <ul className="space-y-2 text-xs sm:text-sm text-slate-600">
                <li>
                  <span className="text-slate-600">Quyền riêng tư &amp; Mã hóa</span>
                </li>
                <li>
                  <span className="text-slate-600">Giấy phép MIT</span>
                </li>
                <li>
                  <span className="text-slate-600">Điều khoản sử dụng</span>
                </li>
                <li>
                  <a className="hover:text-brand-600 transition-colors" href="mailto:support@motivo.ai">
                    Liên hệ hỗ trợ
                  </a>
                </li>
              </ul>
            </div>
          </div>

          {/* Bottom Credits */}
          <div className="pt-8 flex flex-col sm:flex-row items-center justify-between text-xs text-slate-500 gap-4">
            <div>
              © 2025 Motivo.rag studio. Kiến trúc Local NotebookLM &amp; Trợ lý cá nhân mã nguồn mở.
            </div>
            <div className="flex items-center gap-6">
              <span className="inline-flex items-center gap-1.5 text-slate-600">
                <span className="w-2 h-2 rounded-full bg-emerald-500"></span>
                Cổng kết nối Qdrant: Sẵn sàng
              </span>
              <span className="text-slate-600">Bảo mật Zero-Cloud</span>
            </div>
          </div>
        </div>
      </footer>
      {/* END: MainFooter */}
    </div>
  )
}
