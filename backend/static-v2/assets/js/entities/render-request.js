/* buildRenderRequest(draft) → RenderRequest payload for POST /api/render/process.
   validateRenderDraft(draft) → { valid, errors[] }
   Only sends fields that were intentionally set; backend defaults fill the rest.
*/

const VALID_ASPECT_RATIOS  = new Set(['9:16', '1:1', '3:4', '16:9']);
const VALID_SUBTITLE_STYLES = new Set(['viral_bold', 'clean_pro', 'boxed_caption', 'pro_karaoke']);
const VALID_REFRAME_MODES  = new Set(['center', 'motion', 'subject']);

export function validateRenderDraft(draft) {
  const errors = [];
  if (!draft.editSessionId && !draft.youtubeUrl && !draft.sourceVideoPath) {
    errors.push('Source required: prepare a source first or provide a YouTube URL.');
  }
  if (!draft.outputDir) {
    errors.push('Output directory is required.');
  }
  if (draft.minPartSec != null && draft.maxPartSec != null &&
      Number(draft.minPartSec) > Number(draft.maxPartSec)) {
    errors.push('Min clip duration must be ≤ max clip duration.');
  }
  return { valid: errors.length === 0, errors };
}

export function buildRenderRequest(draft) {
  const req = {};

  // Source
  if (draft.sourceMode)      req.source_mode       = draft.sourceMode;
  if (draft.youtubeUrl)      req.youtube_url        = draft.youtubeUrl;
  if (draft.sourceVideoPath) req.source_video_path  = draft.sourceVideoPath;
  if (draft.editSessionId)   req.edit_session_id    = draft.editSessionId;
  if (draft.outputDir)       req.output_dir         = draft.outputDir;

  // Clip generation
  if (draft.minPartSec  != null) req.min_part_sec    = Number(draft.minPartSec);
  if (draft.maxPartSec  != null) req.max_part_sec    = Number(draft.maxPartSec);
  if (draft.maxExportParts != null) req.max_export_parts = Number(draft.maxExportParts);
  if (draft.aspectRatio && VALID_ASPECT_RATIOS.has(draft.aspectRatio)) {
    req.aspect_ratio = draft.aspectRatio;
  }

  // Subtitle
  if (draft.subtitleEnabled != null) req.add_subtitle = draft.subtitleEnabled;
  if (draft.subtitleStyle && VALID_SUBTITLE_STYLES.has(draft.subtitleStyle)) {
    req.subtitle_style = draft.subtitleStyle;
  }

  // Camera
  if (draft.reframeMode && VALID_REFRAME_MODES.has(draft.reframeMode)) {
    req.reframe_mode = draft.reframeMode;
  }
  if (draft.motionAwareCrop != null) req.motion_aware_crop = draft.motionAwareCrop;

  // AI
  if (draft.aiEnabled != null)           req.ai_director_enabled        = draft.aiEnabled;
  if (draft.aiInfluenceEnabled != null)  req.ai_render_influence_enabled = draft.aiInfluenceEnabled;

  // Render profile
  if (draft.renderProfile) req.render_profile = draft.renderProfile;

  return req;
}
