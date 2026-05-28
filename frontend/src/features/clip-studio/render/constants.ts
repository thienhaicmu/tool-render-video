import type { Ratio } from './types'

export const PRESETS = [
  { id: 'viral',   icon: '🔥', name: 'VIRAL SHORT',  desc: 'TikTok · 9:16 · Bounce sub',  platform: 'tiktok'          as const },
  { id: 'gaming',  icon: '🎮', name: 'GAMING HYPE',   desc: 'YT Short · 9:16 · Gaming sub', platform: 'youtube_shorts'  as const },
  { id: 'clean',   icon: '✨', name: 'CLEAN STORY',   desc: 'Reels · 9:16 · Clean Pro sub', platform: 'instagram_reels' as const },
  { id: 'podcast', icon: '🎙', name: 'PODCAST CLIP',  desc: 'All platforms · Karaoke',       platform: 'tiktok'          as const },
]

export const STYLES = [
  { id: 'slay_soft_01',   ico: '✨', label: 'SOFT'    },
  { id: 'slay_pop_01',    ico: '⚡', label: 'POP'     },
  { id: 'story_clean_01', ico: '🎬', label: 'CLEAN'   },
  { id: 'social_bright',  ico: '💥', label: 'BRIGHT'  },
  { id: 'cinematic_soft', ico: '🎥', label: 'CINEMA'  },
  { id: 'high_contrast',  ico: '⬜', label: 'BOLD'    },
]

export const RATIO_INFO: Record<Ratio, { label: string; sub: string; api: string }> = {
  r916: { label: '9:16', sub: '1080×1920', api: '9:16' },
  r34:  { label: '3:4',  sub: '1080×1440', api: '3:4'  },
  r45:  { label: '4:5',  sub: '1080×1350', api: '4:5'  },
  r11:  { label: '1:1',  sub: '1080×1080', api: '1:1'  },
  r169: { label: '16:9', sub: '1920×1080', api: '16:9' },
}

export const SUB_STYLE_GROUPS = [
  { label: 'Minimal', set: 'clean_pro',        ids: ['clean_pro', 'story_clean_01'] },
  { label: 'Karaoke', set: 'tiktok_bounce_v1', ids: ['tiktok_bounce_v1', 'viral_bold'] },
  { label: 'Emphasis', set: 'bold_cap',         ids: ['bold_cap', 'boxed_caption', 'gaming'] },
]

export const QUALITY_MAP = [
  { v: 'fast'    as const, l: '720p'  },
  { v: 'quality' as const, l: '1080p' },
  { v: 'best'    as const, l: '2K'    },
]
