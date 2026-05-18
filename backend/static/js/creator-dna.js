/* =========================================================
   creator-dna.js — UP20: Creator Style DNA
   Infers a lightweight editorial identity from real creator
   behavior already tracked in UP12 (subtitle taste) and
   UP18 (variant + platform feedback). No new raw tracking.
   No ML. No embeddings. No cloud sync.

   Three DNA dimensions derived from existing preference signals:
     hook_forward       — aggressive/TikTok pattern
     clean_visual       — story_first/Instagram/clean-sub pattern
     narrative_structure — story_first preference

   Confidence gate: 10+ meaningful actions (UP12 sessions +
   UP18 sessions) before any nudge is applied.

   Storage: creator_dna_v1 — last computed snapshot only.
   Hierarchy: manual > taste > feedback > DNA > platform > default
   ========================================================= */
'use strict';

window.CreatorDNA = (() => {

  const LS_KEY          = 'creator_dna_v1';
  const DNA_MIN_ACTIONS = 10;   // meaningful actions before DNA activates

  // Subtitle styles associated with a "clean visual" editing identity
  const CLEAN_STYLES = ['story_clean_01', 'minimal_clean', 'clean_karaoke'];

  // ── Compute DNA dimensions from UP12 + UP18 preference data ──────────────
  function _computeContext() {
    const tastePrefs    = typeof CreatorTaste    !== 'undefined' ? CreatorTaste.getPreferences()    : {};
    const feedbackPrefs = typeof CreatorFeedback !== 'undefined' ? CreatorFeedback.getPreferences() : {};

    // "Meaningful actions" = subtitle renders (UP12 sessions) + platform renders (UP18 sessions)
    const action_count = (tastePrefs.sessions || 0) + (feedbackPrefs.sessions || 0);
    if (action_count < DNA_MIN_ACTIONS) {
      return { confident: false, action_count };
    }

    const variantPref  = feedbackPrefs.variantPreference?.variant   || null;
    const platformPref = feedbackPrefs.platformPreference?.platform || null;
    const subtitlePref = tastePrefs.subtitleStyle?.style            || null;

    // hook_forward: 0.0 / 0.5 / 1.0
    //   0.5 → one of: aggressive variant preference OR TikTok platform preference
    //   1.0 → both signals present
    const hookCount    = (variantPref  === 'aggressive' ? 1 : 0)
                       + (platformPref === 'tiktok'     ? 1 : 0);
    const hook_forward = _r2(hookCount / 2);

    // clean_visual: 0.0 / 0.33 / 0.67 / 1.0
    //   signals: story_first variant + instagram_reels platform + clean subtitle style
    const cleanCount   = (variantPref  === 'story_first'           ? 1 : 0)
                       + (platformPref === 'instagram_reels'        ? 1 : 0)
                       + (CLEAN_STYLES.includes(subtitlePref)       ? 1 : 0);
    const clean_visual = _r2(cleanCount / 3);

    // narrative_structure: 0.0 / 1.0 — story_first variant preference
    const narrative_structure = variantPref === 'story_first' ? 1.0 : 0.0;

    return {
      confident:           true,
      action_count,
      hook_forward,
      clean_visual,
      narrative_structure,
    };
  }

  function _r2(v) { return Math.round(v * 100) / 100; }

  // ── Public: DNA context for render payload ────────────────────────────────
  function getDNAContext() {
    const ctx = _computeContext();
    // Snapshot to localStorage for explainability — not a primary data source
    try { localStorage.setItem(LS_KEY, JSON.stringify({ ...ctx, ts: Date.now() })); } catch (_) {}
    return ctx;
  }

  // ── Public: would this context trigger a nudge? ───────────────────────────
  function getAppliedHint(ctx) {
    const c = ctx || {};
    if (!c.confident) return null;
    const fires = (c.hook_forward          >= 0.5)
               || (c.clean_visual          >= 0.67)
               || (c.narrative_structure   >= 1.0);
    return fires ? 'Adapted to recent creator style' : null;
  }

  // ── Public: lifecycle ─────────────────────────────────────────────────────
  function init() {
    getDNAContext();  // snapshot current state; no UI side effects
  }

  function reset() {
    try { localStorage.removeItem(LS_KEY); } catch (_) {}
  }

  return { init, getDNAContext, getAppliedHint, reset };

})();
