/* Warmup / readiness store.
   Reads from /api/warmup/status after boot (non-blocking).
   Screens subscribe to determine if render-critical tools are available.
   Never blocks unrelated flows — all values default to null (unknown).
*/

import { createStore } from './create-store.js';
import { systemApi } from '../api/system.js';

const store = createStore({
  loaded:           false,
  ffmpegAvailable:  null,   // null = unknown, true = ok, false = missing
  ytdlpAvailable:   null,
  whisperAvailable: null,
  gpuAvailable:     null,
  renderBlocked:    false,  // true only when FFmpeg is confirmed missing
});

async function load() {
  try {
    const data  = await systemApi.getWarmupStatus();
    const items = data?.items ?? data?.warmup_items ?? {};

    const get = (...keys) => {
      for (const k of keys) {
        const it = items[k];
        if (!it) continue;
        const s = String(it.status ?? it.state ?? '');
        if (s === 'ready' || s === 'ok'     || it.available === true)  return true;
        if (s === 'error' || s === 'failed' || it.available === false) return false;
      }
      return null;
    };

    const ffmpeg = get('ffmpeg');
    store.set({
      loaded:           true,
      ffmpegAvailable:  ffmpeg,
      ytdlpAvailable:   get('yt_dlp', 'ytdlp', 'yt-dlp'),
      whisperAvailable: get('whisper', 'whisperx'),
      gpuAvailable:     get('gpu', 'gpu_check', 'cuda'),
      renderBlocked:    ffmpeg === false,
    });
  } catch {
    // Warmup endpoint unavailable — fail open, never block
    store.set({ loaded: true });
  }
}

export const readinessStore = { ...store, load };
