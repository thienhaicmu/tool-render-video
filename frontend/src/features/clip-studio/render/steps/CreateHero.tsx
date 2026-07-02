/**
 * CreateHero - P2.4: the Create screen's empty state (hero drop zone),
 * extracted verbatim from RenderWorkflow. Pure presentation: file intake
 * goes through onAddPaths/onBrowse; the queued banner and prepare error
 * are passed in as rendered nodes/strings.
 */
import React from 'react'
import type { Lang } from '../../ClipStudio'

export function CreateHero({ lang, prepareError, queuedInfo, onAddPaths, onBrowse }: {
  lang: Lang
  prepareError: string | null
  queuedInfo: React.ReactNode
  onAddPaths: (paths: string[]) => void
  onBrowse: () => void
}) {
  return (
    <div className="step-screen active">
            <div className="src-screen">
              {/* Atmospheric background — violet/pink blobs + grid */}
              <div className="src-bg" aria-hidden="true">
                <div className="src-bg-blob src-bg-blob-1" />
                <div className="src-bg-blob src-bg-blob-2" />
                <div className="src-bg-grid" />
              </div>

              <div className="src-content">
                {/* Eyebrow chip + hero */}
                <div className="src-hero">
                  <span className="src-eyebrow">
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M12 3l2.4 5.6L20 11l-5.6 2.4L12 19l-2.4-5.6L4 11l5.6-2.4z"/>
                    </svg>
                    {lang === 'VI' ? 'AI sẵn sàng' : 'AI ready to clip'}
                  </span>
                  <h1 className="src-hero-title">
                    {lang === 'VI'
                      ? <>Cắt video dài thành <span className="src-grad-word">clip viral</span>.</>
                      : <>Turn long videos into <span className="src-grad-word">viral clips</span>.</>}
                  </h1>
                  <p className="src-hero-sub">
                    {lang === 'VI'
                      ? 'Thả file lên đây — AI sẽ phân tích, chọn khoảnh khắc hay nhất và xuất clip sẵn sàng cho TikTok, Reels và Shorts.'
                      : 'Drop a file and let AI pick the best moments. Ready for TikTok, Reels and Shorts in minutes.'}
                  </p>
                </div>

                {/* Drop zone — illustrated · S3.4 multi-file drag-drop */}
                <div
                  className="src-cards"
                  onDragOver={(e) => {
                    e.preventDefault()
                    e.dataTransfer.dropEffect = 'copy'
                  }}
                  onDrop={(e) => {
                    e.preventDefault()
                    const files = Array.from(e.dataTransfer.files || [])
                    if (files.length === 0) return
                    // Electron exposes the absolute path on File.path; pure-
                    // web browsers don't, so we fall back to the filename
                    // (which the backend will reject — instructive for the
                    // user). dragData.files cannot supply a Vietnamese
                    // localised error here because we don't know lang at
                    // closure time; the validator inside handleStartRender
                    // surfaces it on submit.
                    const paths = files
                      .map((f) => (f as File & { path?: string }).path || f.name)
                      .filter((p) => p && p.length > 0)
                    onAddPaths(paths)
                  }}
                >
                  <button
                    type="button"
                    className="src-card highlight"
                    onClick={onBrowse}
                  >
                    <div className="src-illu" aria-hidden="true">
                      <svg width="120" height="96" viewBox="0 0 120 96" fill="none" xmlns="http://www.w3.org/2000/svg">
                        <defs>
                          <linearGradient id="gradFrame" x1="0" y1="0" x2="1" y2="1">
                            <stop offset="0" stopColor="#8b5cf6"/>
                            <stop offset="1" stopColor="#ec4899"/>
                          </linearGradient>
                          <linearGradient id="gradPlay" x1="0" y1="0" x2="1" y2="0">
                            <stop offset="0" stopColor="#ffffff" stopOpacity="0.95"/>
                            <stop offset="1" stopColor="#ffffff" stopOpacity="0.85"/>
                          </linearGradient>
                          <filter id="dropGlow" x="-20%" y="-20%" width="140%" height="140%">
                            <feGaussianBlur stdDeviation="2"/>
                          </filter>
                        </defs>
                        {/* Back frame */}
                        <rect x="14" y="20" width="68" height="50" rx="10" fill="url(#gradFrame)" opacity="0.30" transform="rotate(-8 48 45)"/>
                        {/* Middle frame */}
                        <rect x="22" y="14" width="72" height="56" rx="11" fill="url(#gradFrame)" opacity="0.55" transform="rotate(-3 58 42)"/>
                        {/* Top frame with play */}
                        <rect x="30" y="10" width="78" height="62" rx="12" fill="url(#gradFrame)"/>
                        <circle cx="69" cy="41" r="18" fill="rgba(255,255,255,0.16)"/>
                        <path d="M64 33l14 8-14 8z" fill="url(#gradPlay)"/>
                        {/* Sparkles */}
                        <g fill="#fff" opacity="0.9">
                          <path d="M104 18l1.5 3.5L109 23l-3.5 1.5L104 28l-1.5-3.5L99 23l3.5-1.5z"/>
                          <path d="M16 70l1 2.4L19.4 73.4l-2.4 1L16 76.8l-1-2.4L12.6 73.4l2.4-1z"/>
                          <circle cx="110" cy="50" r="1.6"/>
                          <circle cx="8" cy="32" r="1.4"/>
                        </g>
                      </svg>
                    </div>
                    <div className="src-card-body">
                      <div className="src-card-title">
                        {lang === 'VI' ? 'Thả file vào đây' : 'Drop your video here'}
                      </div>
                      <div className="src-card-desc">
                        {lang === 'VI' ? 'hoặc bấm để chọn từ máy' : 'or click to browse your computer'}
                      </div>
                    </div>
                    <div className="src-card-meta">
                      <span className="src-card-badge">MP4 · MOV · MKV · WEBM</span>
                      <span className="src-card-dot" aria-hidden="true">·</span>
                      <span className="src-card-hint">{lang === 'VI' ? 'Khuyến nghị ≤ 4K · 2 GB' : 'Recommended ≤ 4K · 2 GB'}</span>
                    </div>
                    <div className="src-card-shine" aria-hidden="true" />
                  </button>
                </div>

                {/* Platform support row */}
                <div className="src-platforms">
                  <span className="src-platforms-label">
                    {lang === 'VI' ? 'Sẵn sàng đăng lên' : 'Ready to publish on'}
                  </span>
                  <div className="src-platforms-list">
                    <span className="src-platform" data-p="youtube">
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><path d="M23 12s0-3.7-.5-5.5c-.3-1-1-1.8-2-2C18.7 4 12 4 12 4s-6.7 0-8.5.5c-1 .2-1.7 1-2 2C1 8.3 1 12 1 12s0 3.7.5 5.5c.3 1 1 1.8 2 2 1.8.5 8.5.5 8.5.5s6.7 0 8.5-.5c1-.2 1.7-1 2-2 .5-1.8.5-5.5.5-5.5zM10 15.5v-7l6 3.5-6 3.5z"/></svg>
                      YouTube
                    </span>
                    <span className="src-platform" data-p="tiktok">
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><path d="M16 3v3.4a5 5 0 0 0 4 3.4v3.6a8.6 8.6 0 0 1-4-1.2v7c0 3.5-2.7 5.8-6 5.8-3 0-5.5-2.4-5.5-5.4S7 14 10 14c.5 0 1 .1 1.5.2v3.5c-.5-.2-1-.3-1.5-.3-1.2 0-2.2 1-2.2 2.2 0 1.2 1 2.2 2.2 2.2 1.3 0 2.5-.9 2.5-2.4V3H16z"/></svg>
                      TikTok
                    </span>
                    <span className="src-platform" data-p="instagram">
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2c2.7 0 3 0 4.1.1 1 0 1.6.2 2 .3.5.2.9.4 1.3.8.4.4.6.8.8 1.3.1.4.3 1 .3 2C20.6 7.6 20.6 8 20.6 12s0 4.4-.1 5.5c0 1-.2 1.6-.3 2-.2.5-.4.9-.8 1.3-.4.4-.8.6-1.3.8-.4.1-1 .3-2 .3-1.1.1-1.4.1-4.1.1s-3 0-4.1-.1c-1 0-1.6-.2-2-.3-.5-.2-.9-.4-1.3-.8-.4-.4-.6-.8-.8-1.3-.1-.4-.3-1-.3-2-.1-1.1-.1-1.4-.1-5.4s0-4.4.1-5.5c0-1 .2-1.6.3-2 .2-.5.4-.9.8-1.3.4-.4.8-.6 1.3-.8.4-.1 1-.3 2-.3C8.6 2 9 2 12 2zm0 5a5 5 0 1 0 0 10 5 5 0 0 0 0-10zm6.4-.3a1.2 1.2 0 1 0-2.4 0 1.2 1.2 0 0 0 2.4 0zM12 9.2a2.8 2.8 0 1 1 0 5.6 2.8 2.8 0 0 1 0-5.6z"/></svg>
                      Instagram
                    </span>
                    <span className="src-platform" data-p="facebook">
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><path d="M22 12a10 10 0 1 0-11.6 9.9V15h-2.5v-3h2.5V9.8c0-2.5 1.5-3.9 3.8-3.9 1.1 0 2.2.2 2.2.2v2.5h-1.3c-1.2 0-1.6.8-1.6 1.6V12h2.8l-.5 3h-2.3v6.9A10 10 0 0 0 22 12z"/></svg>
                      Facebook
                    </span>
                  </div>
                </div>

                {/* What happens next — visual step preview */}
                <div className="src-next">
                  <div className="src-next-head">{lang === 'VI' ? 'Các bước tiếp theo' : 'What happens next'}</div>
                  <ol className="src-next-list">
                    <li className="src-next-item">
                      <span className="src-next-num">2</span>
                      <div className="src-next-text">
                        <div className="src-next-title">{lang === 'VI' ? 'Thiết lập' : 'Configure'}</div>
                        <div className="src-next-desc">{lang === 'VI' ? 'Chọn preset, tỷ lệ, kiểu phụ đề' : 'Pick preset, ratio, subtitle style'}</div>
                      </div>
                    </li>
                    <li className="src-next-sep" aria-hidden="true">
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M9 6l6 6-6 6"/>
                      </svg>
                    </li>
                    <li className="src-next-item">
                      <span className="src-next-num">3</span>
                      <div className="src-next-text">
                        <div className="src-next-title">{lang === 'VI' ? 'AI render' : 'AI render'}</div>
                        <div className="src-next-desc">{lang === 'VI' ? 'AI phân tích & cắt clip' : 'AI analyzes & cuts clips'}</div>
                      </div>
                    </li>
                    <li className="src-next-sep" aria-hidden="true">
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M9 6l6 6-6 6"/>
                      </svg>
                    </li>
                    <li className="src-next-item">
                      <span className="src-next-num">4</span>
                      <div className="src-next-text">
                        <div className="src-next-title">{lang === 'VI' ? 'Kết quả' : 'Results'}</div>
                        <div className="src-next-desc">{lang === 'VI' ? 'Tải clip về để đăng' : 'Export & publish-ready'}</div>
                      </div>
                    </li>
                  </ol>
                </div>

                {prepareError && (
                  <div className="src-error">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <circle cx="12" cy="12" r="10"/>
                      <path d="M12 8v4M12 16h.01"/>
                    </svg>
                    <span>{prepareError}</span>
                  </div>
                )}
              </div>
            </div>
            <div className="screen-footer">
              <div className="screen-footer-info">{queuedInfo}</div>
            </div>
        </div>
  )
}
