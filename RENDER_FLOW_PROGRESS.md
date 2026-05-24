# render-flow.html — Trạng thái & Context

> Cập nhật lần cuối: 2026-05-24  
> File đang làm: `D:\tool-render-video\render-flow.html`  
> Standalone HTML prototype — không build tools, toàn bộ CSS inline trong `<style>`.

---

## Tổng quan

Prototype 6 màn hình mô phỏng flow AI Clip Studio:  
`Input → Configure → Rendering → Results | Download | History`

---

## Trạng thái từng màn hình

| Screen | Tên | Trạng thái |
|--------|-----|------------|
| 1 | Input | ✅ Hoàn chỉnh |
| 2 | Configure | ✅ Hoàn chỉnh (redesign 2026-05-24) |
| 3 | Rendering | ✅ Hoàn chỉnh |
| 4 | Results | ✅ Hoàn chỉnh |
| 5 | Download | ✅ Hoàn chỉnh |
| 6 | History | ✅ Hoàn chỉnh |

---

## Topbar — 2 cấp

```
Row 1 (48px): [AI] Clip Studio  | Render  Download  History |  HQ  Fast
Row 2 (36px): [1] Input  [2] Configure  [3] Rendering  [4] Results
              (Row 2 ẩn khi đang ở Download hoặc History)
```

- `--topbar-h: 84px` (48 + 36)
- JS: `goSection('render'|'download'|'history')` — switch L1
- JS: `goTab(1-6)` — switch L2 + screens

---

## Screen 2 — Configure (redesign mới nhất)

**Layout:**
- **Left 44%** — `bg-900`, flex column, căn giữa, chứa preview + ratio chips
- **Right 56%** — scrollable, chứa settings + sticky CTA bar

**Preview box** (`id="preview-box"`):
- Kích thước mặc định **220×391px** (9:16)
- Thay đổi kích thước khi click ratio chip (có animation transition)
- Device frame: notch trên + home bar dưới (ẩn khi landscape)

**Ratio chips** (`id="ratio-strip"`): pill buttons bên dưới preview
```
9:16 → 220×391px  |  3:4 → 220×293px  |  4:5 → 220×275px
1:1  → 256×256px  |  16:9 → 356×200px
```

**Settings bên phải:**
1. Clip Duration (min/max sliders)
2. Video Style (4 cards: Dynamic / Clean / Cinematic / Auto)
3. Subtitle toggle + 4 style cards (Karaoke / Bold / Standard / Highlight) + Translate
4. Save Location
5. Sticky CTA: Back | `ratio · style · dur` | **Start Render →**

**Live preview updates khi:**
- Chọn ratio → box resize, notch/bar show/hide
- Chọn Video Style → background gradient thay đổi
- Chọn Subtitle style → overlay text thay đổi (karaoke/standard/highlight)
- Toggle subtitle off → overlay ẩn

---

## Screen 3 — Rendering

**Pattern:** `renderActivePanel → rdCard → aiInsightsPanel → renderRuntimeMount`

```
rdCard:
  [RENDERING badge] [Job title]  [Logs] [Cancel]
  Clip 1/3 — Cutting ... (rd-step)
  [seg-1][seg-2][seg-3]  ← segment bar
  0%  Calculating ETA...

aiInsightsPanel:
  AI DIRECTOR | Confidence 94%
  "Selected 3 viral-candidate segments..."

rdQueueScroll:
  rdQueueRow (part-1/2/3) — waiting/rendering/completed/failed
    ├ badge (data-state)
    ├ progress bar (prog-N)
    ├ stage text (stage-N)
    └ actions (actions-N, hidden until done)

abpToolbar (48px, border-top: primary):
  job title | meta | [progress bar] | msg | pct | badge
```

**JS simulation:** `startRenderSimulation()` → auto-runs khi `goTab(3)`
- Parts chạy theo `CLIP_DATA` delays
- `setPartState(n, state)` → update `rdQueueRow--*` class + badge `data-state`
- `finishPart(n)` → show actions, update seg bar, khi all done → unlock tab 4, auto goTab(4)
- `cancelRender()` → set `data-state="cancelled"` trên badges

---

## Screen 4 — Results

```
s4-hero:
  [✓ icon]  Render Complete
            3 clips ready to publish
            "How to Build Viral Content..." · 9:16 · CapCut Karaoke
  Tags: 🔥 Hook detected  💡 3 key insights  ⚡ High engagement window
  KPIs: [91 Top Score] [3 Clips] [2:08 Total]
  Buttons: New | Export All

s4-body:
  3x clip-card (data-aspect="9:16"):
    - thumb 240px, rank badge, score badge, duration, play overlay
    - score bar (colored by score)
    - emoji tags (🔥 Hook, 💡 Insight, 🎯 CTA, ⚡ Viral)
    - Save (primary) + Overflow (···) buttons
```

---

## Screen 5 — Download

```
downloadWorkspace:
  Header: "Download Videos" + batch status
  flowRail: 4 steps (1.Paste URLs / 2.Configure / 3.Download / 4.Done)
  dlInputBar: URL input + Add button
  downloadQueuePanel:
    4 rows: done / downloading / waiting / failed
    border-left colors: done=success, downloading=primary+pulse, waiting=primary-muted, failed=danger
```

**JS:** `addDlUrl()` — đọc input, toast, clear

---

## Screen 6 — History

```
historyWorkspace:
  Header: "Activity" + total count + Refresh
  historySummaryRail: 5 stat cards
  hwFilterBar: 7 filter chips (All / Render / Download / Completed / Partial / Failed / This week)
  hwBody → historyList:
    7x hwCard — completed/partial/failed/running/queued
    hwKindBadge: .render (blue) | .download (purple)
    hwStatusBadge: completed/partial/failed/running/queued
```

**JS:** `hwFilter(btn)` — toggle active chip

---

## CSS Design Tokens quan trọng

```css
--bg-900: #0a0a0c    --bg-850: #101014    --bg-800: #111116    --bg-750: #1c1c24
--primary: #4d7cff   --primary-muted: rgba(77,124,255,.15)   --primary-border: rgba(77,124,255,.35)
--secondary: #a855f7
--success: #22c55e   --warning: #f59e0b   --danger: #ef4444
--topbar-h: 84px     --topbar-r1: 48px    --topbar-r2: 36px
--font-ui: 'Inter'   --font-mono: 'JetBrains Mono'
```

---

## Các class pattern chính (để JS tham chiếu)

| Pattern | Cách dùng |
|---------|-----------|
| `rdBadge2[data-state]` | `running` / `completed` / `failed` / `cancelled` |
| `rdQueueRow--*` | `waiting` / `rendering` / `completed` / `failed` |
| `rdSegItem--*` | `waiting` / `rendering` / `completed` / `failed` |
| `downloadQueueRow.*` | `done` / `downloading` / `waiting` / `failed` |
| `hwCard.*` | `completed` / `partial` / `failed` / `running` / `queued` |
| `.ratio-chip.selected` | ratio picker (thay thế ratio-card cũ) |
| `.preview-box` | fixed px size, transition width+height |

---

## Những gì có thể làm thêm (backlog)

- [ ] Screen 3: Parts hiện chạy song song — có thể đổi thành sequential (part 2 chờ part 1 xong)
- [ ] Screen 4: Thêm timeline/waveform visualization cho clip cards
- [ ] Screen 2: `preview-dims` + `preview-platform` chưa hiển thị khi load lần đầu (chỉ update sau khi click chip) — fix bằng cách gọi `selectRatio(document.querySelector('.ratio-chip.selected'))` trong `DOMContentLoaded`
- [ ] Tổng thể: Responsive layout cho màn nhỏ hơn

---

## Cách mở và test

Mở thẳng file trong browser:
```
D:\tool-render-video\render-flow.html
```
Không cần server, không cần build. Lucide icons load từ CDN (`unpkg.com`), cần internet.
