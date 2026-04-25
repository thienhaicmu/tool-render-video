
# Tong hop chuc nang project

## 1. Download + Prepare
- Nhan link YouTube hoac chon video local
- Tai video goc bang yt-dlp (YouTube mode)
- Upload video tu browser len server (Local mode, ho tro ca Electron va browser)
- Tao slug, doc title, duration, thumbnail
- Ho tro batch download nhieu YouTube URL cung luc

## 2. Scene + Segment
- Detect scene bang scenedetect
- Build segment theo scene
- Giu min clip 70s (tuy chinh duoc)
- Cho phep max clip 180/240s (tuy chinh duoc)
- Max export parts: gioi han so part xuat ra

## 3. Subtitle
- Tach audio tu video
- Transcribe bang Whisper (auto chon model)
- **Word-by-word subtitle**: dung `word_timestamps=True` de tach tung tu
- Tao SRT roi convert sang ASS subtitle
- **Font Bungee** (bundled, giong CapCut) cho tat ca style
- **Bounce animation**: hieu ung nhay tung tu voi `\fscx118\fscy118` -> `\fscx100\fscy100` trong 220ms
- 7 subtitle style: TikTok Bounce (32), Viral Clean (28), Viral Soft (26), Viral Pop (36), Viral Compact (30), Clean Bold (28), Story Clean (26)
- Chi add subtitle cho part co viral score cao (tuy chinh nguong)

## 4. Render Engine
- Cat raw clip bang ffmpeg
- **Motion-aware crop** bam chuyen dong subject (OpenCV)
  - `subject_detect_interval: 12`, `detect_scale: 0.35`
  - Compositing dung `INTER_AREA` (nhanh 3-4x so voi LANCZOS4)
- Scale ngang/doc tuy chinh (100/106 default)
- Burn subtitle ASS voi custom font directory
- Add title overlay (drawtext)
- **Smart FPS**: ffprobe source fps, khong bao gio upscale qua source fps
- **Reup Mode**: color enhance (eq), unsharp, hqdn3d (chi cho slow+ preset)
  - **Khong double-enhance**: effect filter va reup filter mutual exclusive
- **BGM mixing**: ho tro nhac nen voi volume tuy chinh
  - Fix `-vf` + `-filter_complex` conflict: merge video filter vao filter_complex graph khi co BGM
- Encode H.264/H.265 + AAC
- **NVENC auto-detection**: probe GPU encoder bang null encode test, fallback CPU
- **Tiered codec params** theo render profile:
  - veryslow/slower: `ref=5:me=umh:subme=9:analyse=all:trellis=2`
  - slow: `ref=4:me=hex:subme=7:trellis=1`
  - fast/balanced: `ref=3:me=hex:subme=6:trellis=0`
- Scale filter: lanczos cho slow+, bicubic cho fast
- CPU fallback khi NVENC fail (tu dong retry)

## 5. Scoring
- Cham viral heuristic
- Tinh priority rank
- Xuat ranking vao report

## 6. Progress Tracking
- Job status: queued/running/completed/failed
- Job stage: downloading/scene_detection/segment_building/rendering_part_x/writing_report/done
- Progress tong theo phan tram
- Progress tung part
- Pipeline visualization 7 node tren UI
- WebSocket realtime update
- **UI lock**: disable tat ca input khi render/upload dang chay

## 7. Upload
- Login profile rieng cho tung kenh bang Playwright
- Tinh schedule 07:00 va 17:00 (tuy chinh slot)
- Dry-run scheduler va upload report
- Ho tro proxy (direct/proxy mode)
- Auto include hashtags
- Caption AI: Smart Template, Ollama (local LLM), Claude API, Auto

## 8. Data & Reports
- SQLite luu jobs va job_parts
- Excel render_report.xlsx
- Excel upload_report.xlsx

## 9. UI / Desktop
- **Web app** chay tren browser (localhost)
- **Electron desktop app** voi native icon
- Favicon SVG + PNG 192x192
- Sidebar navigation: Render, Upload, Channels, Reports, Settings
- Source mode: YouTube Link hoac Local Video File
- YouTube batch queue (add/remove links)
- Channel management (create/reload)
- System settings: cleanup logs
- Warmup status indicator (model loading)
- **BGM controls**: chon file nhac nen, chinh volume
- **Render Profile**: Best/Quality/Balanced/Fast voi preset tuong ung
- **Render Device**: Auto detect NVENC, GPU, CPU
- **Smart FPS hint**: hien thi auto-cap to source fps
