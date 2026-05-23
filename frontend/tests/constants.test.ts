/**
 * Constants tests
 * - SUBTITLE_STYLES has 10 items with correct values
 * - EFFECT_PRESETS has 6 items with correct values
 * - PLATFORMS has 3 items
 * - getQualityLabel edge values
 * - getQualityVariant edge values
 */
import { describe, it, expect } from 'vitest'
import {
  SUBTITLE_STYLES,
  EFFECT_PRESETS,
  PLATFORMS,
  ASPECT_RATIOS,
  QUALITY_MODES,
  RENDER_PROFILES,
  QUALITY_SCORE_THRESHOLDS,
  getQualityLabel,
  getQualityVariant,
} from '../src/lib/constants'

// ── SUBTITLE_STYLES ───────────────────────────────────────────────────────────

describe('SUBTITLE_STYLES', () => {
  it('has exactly 10 canonical presets', () => {
    expect(SUBTITLE_STYLES).toHaveLength(10)
  })

  it('contains all 10 documented values from §6.3', () => {
    const values = SUBTITLE_STYLES.map((s) => s.value)
    expect(values).toContain('tiktok_bounce_v1')
    expect(values).toContain('bold_cap')
    expect(values).toContain('story_clean_01')
    expect(values).toContain('viral_bold')
    expect(values).toContain('clean_pro')
    expect(values).toContain('boxed_caption')
    expect(values).toContain('viral')
    expect(values).toContain('clean')
    expect(values).toContain('story')
    expect(values).toContain('gaming')
  })

  it('does NOT include legacy alias pro_karaoke', () => {
    const values = SUBTITLE_STYLES.map((s) => s.value)
    expect(values).not.toContain('pro_karaoke')
  })

  it('does NOT include legacy alias viral_clean_montserrat', () => {
    const values = SUBTITLE_STYLES.map((s) => s.value)
    expect(values).not.toContain('viral_clean_montserrat')
  })

  it('every item has value and label', () => {
    SUBTITLE_STYLES.forEach((s) => {
      expect(s.value).toBeTruthy()
      expect(s.label).toBeTruthy()
    })
  })
})

// ── EFFECT_PRESETS ────────────────────────────────────────────────────────────

describe('EFFECT_PRESETS', () => {
  it('has exactly 6 presets', () => {
    expect(EFFECT_PRESETS).toHaveLength(6)
  })

  it('contains all 6 documented values from §6.4', () => {
    const values = EFFECT_PRESETS.map((e) => e.value)
    expect(values).toContain('slay_soft_01')
    expect(values).toContain('slay_pop_01')
    expect(values).toContain('story_clean_01')
    expect(values).toContain('social_bright')
    expect(values).toContain('cinematic_soft')
    expect(values).toContain('high_contrast')
  })

  it('default (first) preset is slay_soft_01', () => {
    expect(EFFECT_PRESETS[0].value).toBe('slay_soft_01')
  })
})

// ── PLATFORMS ─────────────────────────────────────────────────────────────────

describe('PLATFORMS', () => {
  it('has exactly 3 platforms', () => {
    expect(PLATFORMS).toHaveLength(3)
  })

  it('contains tiktok, youtube_shorts, instagram_reels', () => {
    const values = PLATFORMS.map((p) => p.value)
    expect(values).toContain('tiktok')
    expect(values).toContain('youtube_shorts')
    expect(values).toContain('instagram_reels')
  })
})

// ── ASPECT_RATIOS ─────────────────────────────────────────────────────────────

describe('ASPECT_RATIOS', () => {
  it('has exactly 5 ratios', () => {
    expect(ASPECT_RATIOS).toHaveLength(5)
  })

  it('contains all documented ratios from §6.2', () => {
    const values = ASPECT_RATIOS.map((a) => a.value)
    expect(values).toContain('9:16')
    expect(values).toContain('3:4')
    expect(values).toContain('1:1')
    expect(values).toContain('16:9')
    expect(values).toContain('4:3')
  })
})

// ── QUALITY_MODES ─────────────────────────────────────────────────────────────

describe('QUALITY_MODES', () => {
  it('has exactly 3 modes', () => {
    expect(QUALITY_MODES).toHaveLength(3)
  })

  it('contains standard_1080, high_1440, best_available', () => {
    const values = QUALITY_MODES.map((q) => q.value)
    expect(values).toContain('standard_1080')
    expect(values).toContain('high_1440')
    expect(values).toContain('best_available')
  })
})

// ── RENDER_PROFILES ───────────────────────────────────────────────────────────

describe('RENDER_PROFILES', () => {
  it('has exactly 4 profiles', () => {
    expect(RENDER_PROFILES).toHaveLength(4)
  })

  it('contains fast, balanced, quality, best', () => {
    const values = RENDER_PROFILES.map((r) => r.value)
    expect(values).toContain('fast')
    expect(values).toContain('balanced')
    expect(values).toContain('quality')
    expect(values).toContain('best')
  })
})

// ── getQualityLabel ───────────────────────────────────────────────────────────

describe('getQualityLabel', () => {
  it('returns "Good" for score exactly 85 (GOOD threshold)', () => {
    expect(getQualityLabel(85)).toBe('Good')
  })

  it('returns "Good" for score above 85', () => {
    expect(getQualityLabel(100)).toBe('Good')
    expect(getQualityLabel(90)).toBe('Good')
    expect(getQualityLabel(86)).toBe('Good')
  })

  it('returns "Needs Review" for score exactly 70', () => {
    expect(getQualityLabel(70)).toBe('Needs Review')
  })

  it('returns "Needs Review" for score 70-84', () => {
    expect(getQualityLabel(84)).toBe('Needs Review')
    expect(getQualityLabel(75)).toBe('Needs Review')
  })

  it('returns "Warning" for score exactly 50', () => {
    expect(getQualityLabel(50)).toBe('Warning')
  })

  it('returns "Warning" for score 50-69', () => {
    expect(getQualityLabel(69)).toBe('Warning')
    expect(getQualityLabel(55)).toBe('Warning')
  })

  it('returns "Poor" for score 49 (just below WARNING threshold)', () => {
    expect(getQualityLabel(49)).toBe('Poor')
  })

  it('returns "Poor" for score below 50', () => {
    expect(getQualityLabel(0)).toBe('Poor')
    expect(getQualityLabel(25)).toBe('Poor')
    expect(getQualityLabel(49)).toBe('Poor')
  })
})

// ── getQualityVariant ─────────────────────────────────────────────────────────

describe('getQualityVariant', () => {
  it('returns "success" for score >= 85', () => {
    expect(getQualityVariant(85)).toBe('success')
    expect(getQualityVariant(100)).toBe('success')
  })

  it('returns "warning" for score 70-84', () => {
    expect(getQualityVariant(70)).toBe('warning')
    expect(getQualityVariant(84)).toBe('warning')
  })

  it('returns "error" for score 50-69', () => {
    expect(getQualityVariant(50)).toBe('error')
    expect(getQualityVariant(69)).toBe('error')
  })

  it('returns "neutral" for score < 50', () => {
    expect(getQualityVariant(49)).toBe('neutral')
    expect(getQualityVariant(0)).toBe('neutral')
  })
})

// ── QUALITY_SCORE_THRESHOLDS ──────────────────────────────────────────────────

describe('QUALITY_SCORE_THRESHOLDS', () => {
  it('has GOOD = 85', () => {
    expect(QUALITY_SCORE_THRESHOLDS.GOOD).toBe(85)
  })

  it('has NEEDS_REVIEW = 70', () => {
    expect(QUALITY_SCORE_THRESHOLDS.NEEDS_REVIEW).toBe(70)
  })

  it('has WARNING = 50', () => {
    expect(QUALITY_SCORE_THRESHOLDS.WARNING).toBe(50)
  })
})
