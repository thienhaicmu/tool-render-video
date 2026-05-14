/* bestClipHero(clip, jobId)    — hero video wrapper HTML (stable container).
   heroHeaderHtml(clip, jobId)  — reward header: eyebrow + score + download CTA.
   heroMetaHtml(clip, jobId)    — meta strip: clip#, duration, reason, score pill.
   wireHeroVideo(container)     — attach error handler to existing <video>.
   updateHeroClip(container, clip, jobId) — surgically update header, src, meta
     without destroying <video> (preserves play state context).
*/

import { scorePill, scoreColor } from './score-badge.js';

export function bestClipHero(clip, jobId) {
  if (!clip || !jobId) {
    return `
      <div class="hero-empty">
        <div class="col gap-3" style="align-items:center;text-align:center">
          <div style="color:var(--color-text-faint);opacity:0.18;font-size:52px" aria-hidden="true">▷</div>
          <div class="text-body" style="color:var(--color-text-muted)">Select a clip to preview</div>
        </div>
      </div>
    `;
  }
  const url = _streamUrl(jobId, clip.partNo);
  return `
    <div class="hero-wrap col">
      <div id="hero-header" class="hero-reward-header">
        ${heroHeaderHtml(clip, jobId)}
      </div>
      <div class="hero-video-container">
        <video id="hero-video" class="hero-video"
          src="${url}" controls preload="metadata" muted
          style="width:100%;display:block;background:#000">
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

export function heroHeaderHtml(clip, jobId) {
  const url = _streamUrl(jobId, clip.partNo);
  return `
    <div class="row gap-3" style="align-items:center">
      <div class="col gap-1" style="min-width:0">
        <div class="hero-reward-eyebrow${clip.isBest ? '' : ' hero-reward-eyebrow--secondary'}">
          ${clip.isBest ? '<span aria-hidden="true">★</span>&nbsp;Best Clip' : `Clip&nbsp;${clip.partNo}`}
        </div>
        ${clip.isBest ? `<div class="text-body" style="color:var(--color-text-muted)">Recommended result</div>` : ''}
      </div>
      <span class="flex-1"></span>
      ${clip.score > 0 ? `
        <div class="hero-score-display">
          <span class="hero-score-number" style="color:${scoreColor(clip.score)}">${Math.round(clip.score)}</span>
          <span class="text-caption text-faint" style="display:block;text-align:right">score</span>
        </div>
      ` : ''}
      <a href="${url}" download="clip_${clip.partNo}.mp4" class="btn btn-primary">↓ Download</a>
    </div>
  `;
}

export function heroMetaHtml(clip, _jobId) {
  const rawDur = clip._raw?.duration
    ?? (clip._raw?.end_sec != null ? (clip._raw.end_sec - (clip._raw.start_sec ?? 0)) : 0);
  const dur = rawDur > 0 ? _fmtDur(rawDur) : null;
  return `
    <div class="row gap-3" style="align-items:center;padding:var(--sp-3) var(--sp-4)">
      <span class="text-caption text-faint">Clip ${clip.partNo}</span>
      ${dur ? `<span class="dur-badge">${dur}</span>` : ''}
      ${clip.rankingReason
        ? `<span class="hero-reason-text text-caption text-faint">${_esc(clip.rankingReason)}</span>`
        : '<span class="flex-1"></span>'}
      ${clip.score > 0 ? scorePill(clip.score) : ''}
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
  const vid    = container.querySelector('#hero-video');
  const err    = container.querySelector('#hero-video-err');
  const header = container.querySelector('#hero-header');
  const meta   = container.querySelector('#hero-meta');

  if (vid) {
    const newUrl = _streamUrl(jobId, clip.partNo);
    vid.style.display = '';
    if (err) err.style.display = 'none';
    vid.src = newUrl;
    vid.load();
  }
  if (header) header.innerHTML = heroHeaderHtml(clip, jobId);
  if (meta)   meta.innerHTML   = heroMetaHtml(clip, jobId);
}

function _streamUrl(jobId, partNo) {
  return `/api/jobs/${encodeURIComponent(jobId)}/parts/${partNo}/stream`;
}

function _fmtDur(sec) {
  const m = Math.floor(sec / 60);
  const s = String(Math.floor(sec % 60)).padStart(2, '0');
  return `${m}:${s}`;
}

function _esc(s) { return String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;'); }
