/**
 * AdvancedSection — ai_director_enabled, hook_overlay_enabled, remotion_hook_intro,
 * render_profile, min_part_sec, max_part_sec, title_overlay_text.
 */
import React from 'react'
import { FormField } from './FormField'
import { RENDER_PROFILES } from '../../../lib/constants'
import type { RenderFormState, RenderFormErrors } from '../RenderForm.types'

interface AdvancedSectionProps {
  state: RenderFormState
  errors: RenderFormErrors
  onChange: (field: keyof RenderFormState, value: string | boolean | number) => void
}

export function AdvancedSection({ state, errors, onChange }: AdvancedSectionProps) {
  return (
    <section style={sectionStyle}>
      <h3 style={headingStyle}>Advanced</h3>

      <FormField label="AI Director">
        <label style={toggleLabelStyle}>
          <input
            type="checkbox"
            checked={state.ai_director_enabled}
            onChange={(e) => onChange('ai_director_enabled', e.target.checked)}
            style={{ marginRight: '8px' }}
            data-testid="ai-director-toggle"
          />
          <span>Let AI optimize pacing, captions, hooks, and visual energy</span>
        </label>
      </FormField>

      {state.ai_director_enabled && (
        <>
          <FormField label="AI Analyzer Mode">
            <div style={modeTabsStyle}>
              {(['local', 'cloud', 'hybrid'] as const).map((m) => (
                <button
                  key={m}
                  type="button"
                  onClick={() => onChange('ai_analysis_mode', m)}
                  style={{
                    ...modeTabStyle,
                    ...(state.ai_analysis_mode === m ? modeTabActiveStyle : {}),
                  }}
                  data-testid={`ai-mode-${m}`}
                >
                  {m === 'local' ? 'Local' : m === 'cloud' ? 'Cloud' : 'Hybrid'}
                </button>
              ))}
            </div>
            <p style={modeDescStyle}>
              {state.ai_analysis_mode === 'local' && 'Offline only — no API cost, fastest.'}
              {state.ai_analysis_mode === 'cloud' && 'Cloud result only — best quality, uses API quota.'}
              {state.ai_analysis_mode === 'hybrid' && '70% cloud + 30% local — recommended balance.'}
            </p>
          </FormField>

          {(state.ai_analysis_mode === 'cloud' || state.ai_analysis_mode === 'hybrid') && (
            <>
              <FormField label="Provider">
                <div style={modeTabsStyle}>
                  {(['groq', 'openai'] as const).map((p) => (
                    <button
                      key={p}
                      type="button"
                      onClick={() => onChange('ai_cloud_provider', p)}
                      style={{
                        ...modeTabStyle,
                        ...(state.ai_cloud_provider === p ? modeTabActiveStyle : {}),
                      }}
                      data-testid={`ai-provider-${p}`}
                    >
                      {p === 'groq' ? 'Groq (Free)' : 'OpenAI'}
                    </button>
                  ))}
                </div>
              </FormField>

              <FormField label="API Key" hint="Stored in memory only — not saved to disk">
                <input
                  type="password"
                  value={state.ai_cloud_api_key}
                  onChange={(e) => onChange('ai_cloud_api_key', e.target.value)}
                  placeholder={state.ai_cloud_provider === 'groq' ? 'gsk_...' : 'sk-...'}
                  style={{ ...inputStyle, width: '100%', borderColor: 'var(--color-border)' }}
                  aria-label="Cloud API Key"
                  data-testid="ai-cloud-api-key-input"
                />
              </FormField>

              <FormField label="Model" hint="Optional — leave blank for provider default">
                <input
                  type="text"
                  value={state.ai_cloud_model}
                  onChange={(e) => onChange('ai_cloud_model', e.target.value)}
                  placeholder={
                    state.ai_cloud_provider === 'groq'
                      ? 'llama-3.3-70b-versatile'
                      : 'gpt-4o-mini'
                  }
                  style={{ ...inputStyle, width: '100%', borderColor: 'var(--color-border)' }}
                  aria-label="Cloud Model"
                  data-testid="ai-cloud-model-input"
                />
              </FormField>
            </>
          )}

          <FormField label="Hook Overlay">
            <label style={toggleLabelStyle}>
              <input
                type="checkbox"
                checked={state.hook_overlay_enabled}
                onChange={(e) => onChange('hook_overlay_enabled', e.target.checked)}
                style={{ marginRight: '8px' }}
                data-testid="hook-overlay-toggle"
              />
              <span>Enable hook overlay graphics at clip start</span>
            </label>
          </FormField>

          <FormField label="Remotion Hook Intro">
            <label style={toggleLabelStyle}>
              <input
                type="checkbox"
                checked={state.remotion_hook_intro}
                onChange={(e) => onChange('remotion_hook_intro', e.target.checked)}
                style={{ marginRight: '8px' }}
                data-testid="remotion-hook-intro-toggle"
              />
              <span>Use animated Remotion intro sequence for hooks</span>
            </label>
          </FormField>
        </>
      )}

      <FormField label="Render Profile">
        <select
          value={state.render_profile}
          onChange={(e) => onChange('render_profile', e.target.value)}
          style={selectStyle}
          aria-label="Render Profile"
          data-testid="render-profile-select"
        >
          {RENDER_PROFILES.map((p) => (
            <option key={p.value} value={p.value}>
              {p.label}
            </option>
          ))}
        </select>
      </FormField>

      <div style={rowStyle}>
        <FormField
          label="Min Part Duration (sec)"
          error={errors.min_part_sec}
          hint="Minimum: 5s"
        >
          <input
            type="number"
            value={state.min_part_sec}
            onChange={(e) => onChange('min_part_sec', parseInt(e.target.value, 10) || 5)}
            min={5}
            max={300}
            style={{
              ...inputStyle,
              borderColor: errors.min_part_sec ? 'var(--color-error)' : 'var(--color-border)',
            }}
            aria-label="Min Part Duration"
            data-testid="min-part-sec-input"
          />
        </FormField>

        <FormField
          label="Max Part Duration (sec)"
          error={errors.max_part_sec}
          hint="Maximum: 300s"
        >
          <input
            type="number"
            value={state.max_part_sec}
            onChange={(e) => onChange('max_part_sec', parseInt(e.target.value, 10) || 60)}
            min={5}
            max={300}
            style={{
              ...inputStyle,
              borderColor: errors.max_part_sec ? 'var(--color-error)' : 'var(--color-border)',
            }}
            aria-label="Max Part Duration"
            data-testid="max-part-sec-input"
          />
        </FormField>
      </div>

      <FormField
        label="Title Overlay Text"
        hint="Optional — displayed as a text overlay on the rendered clip"
      >
        <input
          type="text"
          value={state.title_overlay_text}
          onChange={(e) => onChange('title_overlay_text', e.target.value)}
          placeholder="Optional title text..."
          style={{ ...inputStyle, width: '100%', borderColor: 'var(--color-border)' }}
          aria-label="Title Overlay Text"
          data-testid="title-overlay-text-input"
        />
      </FormField>
    </section>
  )
}

const sectionStyle: React.CSSProperties = {
  marginBottom: 'var(--space-6)',
}

const headingStyle: React.CSSProperties = {
  fontSize: 'var(--font-size-base)',
  fontWeight: 'var(--font-weight-semibold)' as unknown as number,
  color: 'var(--color-text-primary)',
  margin: '0 0 var(--space-4) 0',
  paddingBottom: 'var(--space-2)',
  borderBottom: '1px solid var(--color-border)',
}

const toggleLabelStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  fontSize: 'var(--font-size-sm)',
  color: 'var(--color-text-primary)',
  cursor: 'pointer',
}

const rowStyle: React.CSSProperties = {
  display: 'grid',
  gridTemplateColumns: '1fr 1fr',
  gap: 'var(--space-4)',
}

const selectStyle: React.CSSProperties = {
  padding: '8px 12px',
  fontSize: 'var(--font-size-base)',
  color: 'var(--color-text-primary)',
  backgroundColor: 'var(--color-bg-elevated)',
  border: '1px solid var(--color-border)',
  borderRadius: 'var(--radius-md)',
  outline: 'none',
  cursor: 'pointer',
  fontFamily: 'var(--font-family-base)',
}

const inputStyle: React.CSSProperties = {
  padding: '8px 12px',
  fontSize: 'var(--font-size-base)',
  color: 'var(--color-text-primary)',
  backgroundColor: 'var(--color-bg-elevated)',
  border: '1px solid',
  borderRadius: 'var(--radius-md)',
  outline: 'none',
  boxSizing: 'border-box',
  fontFamily: 'var(--font-family-base)',
}

const modeTabsStyle: React.CSSProperties = {
  display: 'flex',
  gap: '4px',
}

const modeTabStyle: React.CSSProperties = {
  flex: 1,
  padding: '6px 12px',
  fontSize: 'var(--font-size-sm)',
  color: 'var(--color-text-secondary)',
  backgroundColor: 'var(--color-bg-elevated)',
  border: '1px solid var(--color-border)',
  borderRadius: 'var(--radius-md)',
  cursor: 'pointer',
  fontFamily: 'var(--font-family-base)',
  fontWeight: 500,
}

const modeTabActiveStyle: React.CSSProperties = {
  color: '#fff',
  backgroundColor: 'var(--color-accent)',
  borderColor: 'var(--color-accent)',
}

const modeDescStyle: React.CSSProperties = {
  fontSize: 'var(--font-size-xs)',
  color: 'var(--color-text-secondary)',
  margin: '4px 0 0 0',
}
