/* bestClipHero(clip, jobId) — hero video wrapper HTML (stable container).
   heroMetaHtml(clip, jobId)  — only the meta strip (for surgical updates).
   wireHeroVideo(container)   — attach error handler to existing video element.
   updateHeroClip(container, clip, jobId) — surgically update src + meta without
     destroying the <video> element (preserves play state context).
*/

import { scorePill } from './score-badge.js';

export function bestClipHero(clip, jobId) {
  if (!clip || !jobId) {
    return `
      <div class="hero-empty col" style="align-items:center;justify-content:center;gap:var(--sp-3)">
        <div style="color:var(--color-text-faint);opacity:0.28;font-size:44px">▷</div>
        <div class="text-caption text-faint">Select a clip to preview</div>
      </div>
    `;
  }
  const url = _streamUrl(jobId, clip.partNo);
  return `
    <div class="hero-wrap col gap-0">
      <div class="hero-video-container">
        <video id="hero-video" class="hero-video"
          src="${url}" controls preload="metadata" muted
          style="width:100%;display:block;max-height:420px;object-fit:contain;background:#000">
        </video>
        <div id="hero-video-err" class="hero-video-err" style="display:none">
          <div class="text-caption" style="color:var(--color-failed)">Preview unavailable</div>
          <a href="${url}" target="_blank" class="text-caption" style="color:var(--color-accent)">Direct link ↗</a>
        </div>
      </div>
      <div id="hero-meta" class="hero-meta">
        ${heroMetaHtml(clip, jobId)}
      </div>
    </div>
  `;
}

export function heroMetaHtml(clip, jobId) {
  const url = _streamUrl(jobId, clip.partNo);
  return `
    <div class="row gap-2" style="align-items:center;padding:var(--sp-3)">
      ${clip.isBest ? `<span class="best-label">BEST</span>` : ''}
      <span class="text-caption text-faint">Part ${clip.partNo}</span>
      ${clip.score > 0 ? scorePill(clip.score) : ''}
      <span class="flex-1"></span>
      <a href="${url}" download="part_${clip.partNo}.mp4" class="btn btn-secondary btn-sm">↓ Download</a>
    </div>
  `;
}

export function wireHeroVideo(container) {
  const vid = container.querySelector('#hero-video');
  const err = container.querySelector('#hero-video-err');
  if (!vid || !err) return;
  vid.addEventListener('error', () => {
    if (vid.src && !vid.src.endsWith(window.location.pathname)) {
      vid.style.display = 'none';
      err.style.display = 'flex';
    }
  });
}

export function updateHeroClip(container, clip, jobId) {
  if (!container || !clip || !jobId) return;
  const vid  = container.querySelector('#hero-video');
  const err  = container.querySelector('#hero-video-err');
  const meta = container.querySelector('#hero-meta');

  if (vid) {
    const newUrl = _streamUrl(jobId, clip.partNo);
    vid.style.display = '';
    if (err) err.style.display = 'none';
    vid.src = newUrl;
    vid.load();
  }
  if (meta) meta.innerHTML = heroMetaHtml(clip, jobId);
}

function _streamUrl(jobId, partNo) {
  return `/api/jobs/${encodeURIComponent(jobId)}/parts/${partNo}/stream`;
}
