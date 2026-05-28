/**
 * RenderForm — the main render configuration form.
 * Sections: Source, Output, Creative Direction, Subtitle, Advanced.
 */
import { useState, useCallback } from 'react'
import { useRenderStore } from '../../stores/renderStore'
import { useUIStore } from '../../stores/uiStore'
import { ApiError } from '../../api/client'
import { validateRenderForm, isFormValid, buildRenderPayload } from './RenderForm.schema'
import type { RenderFormState, RenderFormErrors } from './RenderForm.types'
import { SourceSection } from './components/SourceSection'
import { OutputSection } from './components/OutputSection'
import { CreativeSection } from './components/CreativeSection'
import { FrameSection } from './components/FrameSection'
import { SubtitleSection } from './components/SubtitleSection'
import { AdvancedSection } from './components/AdvancedSection'
import { SummaryCard } from './components/SummaryCard'
import './RenderForm.css'

export const DEFAULT_FORM_STATE: RenderFormState = {
  source_mode: 'local',
  source_video_path: '',
  output_dir: '',
  target_platform: 'youtube_shorts',
  aspect_ratio: '3:4',
  subtitle_style: 'tiktok_bounce_v1',
  effect_preset: 'slay_soft_01',
  render_profile: 'quality',
  min_part_sec: 15,
  max_part_sec: 60,
  max_export_parts: 3,
  add_subtitle: true,
  ai_director_enabled: true,
  hook_overlay_enabled: true,
  remotion_hook_intro: true,
  title_overlay_text: '',
  playback_speed: 1.0,
  motion_aware_crop: false,
  reframe_mode: 'subject',
  frame_scale_x: 100,
  frame_scale_y: 106,
  ai_target_market: 'us',
  ai_analysis_mode: 'hybrid',
  ai_cloud_provider: 'groq',
  ai_cloud_api_key: '',
  ai_cloud_model: '',
}

interface RenderFormProps {
  onSubmitSuccess?: (jobId: string) => void
}

export function RenderForm({ onSubmitSuccess }: RenderFormProps) {
  const [formState, setFormState] = useState<RenderFormState>(DEFAULT_FORM_STATE)
  const [errors, setErrors] = useState<RenderFormErrors>({})
  const [isSubmitting, setIsSubmitting] = useState(false)

  const submitRender = useRenderStore((s) => s.submitRender)
  const addNotification = useUIStore((s) => s.addNotification)
  const setActivePanel = useUIStore((s) => s.setActivePanel)

  const handleChange = useCallback(
    (field: keyof RenderFormState, value: string | boolean | number) => {
      setFormState((prev) => ({ ...prev, [field]: value }))
      // Clear error for the changed field
      setErrors((prev) => {
        if (field in prev) {
          const next = { ...prev }
          delete next[field as keyof RenderFormErrors]
          return next
        }
        return prev
      })
    },
    [],
  )

  const handleSubmit = useCallback(async () => {
    const validationErrors = validateRenderForm(formState)
    setErrors(validationErrors)
    if (!isFormValid(validationErrors)) return

    setIsSubmitting(true)
    try {
      const payload = buildRenderPayload(formState)
      const jobId = await submitRender(payload)
      addNotification({
        type: 'success',
        title: `Render job started: ${jobId}`,
      })
      setActivePanel('history')
      onSubmitSuccess?.(jobId)
    } catch (err) {
      const message =
        err instanceof ApiError ? err.message : 'Render failed — please try again'
      addNotification({ type: 'error', title: message })
    } finally {
      setIsSubmitting(false)
    }
  }, [formState, submitRender, addNotification, setActivePanel, onSubmitSuccess])

  const currentErrors = validateRenderForm(formState)
  const formIsValid = isFormValid(currentErrors)

  return (
    <div className="render-form-layout">
      {/* Left: form sections */}
      <div className="render-form-main">
        <SourceSection state={formState} errors={errors} onChange={handleChange} />
        <OutputSection state={formState} errors={errors} onChange={handleChange} />
        <CreativeSection state={formState} onChange={handleChange} />
        <FrameSection state={formState} onChange={handleChange} />
        <SubtitleSection state={formState} onChange={handleChange} />
        <AdvancedSection state={formState} errors={errors} onChange={handleChange} />
      </div>

      {/* Right: summary card */}
      <div className="render-form-sidebar">
        <SummaryCard
          state={formState}
          isValid={formIsValid}
          isSubmitting={isSubmitting}
          onSubmit={handleSubmit}
        />
      </div>
    </div>
  )
}
