/**
 * EditorScreen — top-level editor panel with video preview + trim controls.
 * Phase 6.5: preview + UI-only trim (no backend mutations).
 */
import { useEffect, useState, useCallback } from 'react'
import { useEditorStore } from '@/stores/editorStore'
import { getJobParts } from '@/api/jobs'
import type { JobPart } from '@/types/api'
import { buildThumbnailUrl } from './editor.utils'
import { VideoPreview } from './VideoPreview'
import { TrimControls } from './TrimControls'
import { EditorMetadataPanel } from './EditorMetadataPanel'
import { EditorEmptyState } from './EditorEmptyState'
import { EditorLoadingState } from './EditorLoadingState'
import { EditorErrorState } from './EditorErrorState'
import './EditorScreen.css'

export function EditorScreen() {
  const selectedJobId = useEditorStore((s) => s.selectedJobId)
  const selectedPartNo = useEditorStore((s) => s.selectedPartNo)
  const mediaUrl = useEditorStore((s) => s.mediaUrl)
  const durationSec = useEditorStore((s) => s.durationSec)
  const trimStartSec = useEditorStore((s) => s.trimStartSec)
  const trimEndSec = useEditorStore((s) => s.trimEndSec)
  const isDirty = useEditorStore((s) => s.isDirty)
  const openEditor = useEditorStore((s) => s.openEditor)
  const setDuration = useEditorStore((s) => s.setDuration)
  const setTrim = useEditorStore((s) => s.setTrim)
  const resetTrim = useEditorStore((s) => s.resetTrim)

  const [parts, setParts] = useState<JobPart[]>([])
  const [loadingParts, setLoadingParts] = useState(false)
  const [partsError, setPartsError] = useState<string | null>(null)

  const fetchParts = useCallback(
    async (jobId: string) => {
      setLoadingParts(true)
      setPartsError(null)
      try {
        const data = await getJobParts(jobId)
        setParts(data)
      } catch (err) {
        setPartsError(err instanceof Error ? err.message : 'Failed to load parts')
      } finally {
        setLoadingParts(false)
      }
    },
    [],
  )

  useEffect(() => {
    if (!selectedJobId) {
      setParts([])
      setPartsError(null)
      return
    }
    void fetchParts(selectedJobId)
  }, [selectedJobId, fetchParts])

  if (!selectedJobId) {
    return <EditorEmptyState />
  }

  if (loadingParts) {
    return <EditorLoadingState />
  }

  if (partsError) {
    return (
      <EditorErrorState
        error={partsError}
        onRetry={() => void fetchParts(selectedJobId)}
      />
    )
  }

  // Determine thumbnail for current part
  const thumbnailUrl =
    selectedPartNo != null
      ? buildThumbnailUrl(selectedJobId, selectedPartNo)
      : undefined

  return (
    <div className="editor-screen">
      {/* Part selector — only shown if multiple parts */}
      {parts.length > 1 && (
        <div className="editor-part-selector" data-testid="part-selector">
          {parts.map((part) => {
            const isActive = part.part_no === selectedPartNo
            const isAvailable = part.status === 'done'
            return (
              <button
                key={part.part_no}
                className={`editor-part-btn${isActive ? ' active' : ''}`}
                disabled={!isAvailable}
                onClick={() => {
                  if (selectedJobId != null) {
                    openEditor(selectedJobId, part.part_no)
                  }
                }}
                data-testid={`part-btn-${part.part_no}`}
                title={!isAvailable ? `Part ${part.part_no}: ${part.status}` : undefined}
              >
                Clip {part.part_no}
              </button>
            )
          })}
        </div>
      )}

      <div className="editor-layout">
        {/* Main area: video + trim */}
        <div className="editor-main">
          {mediaUrl ? (
            <>
              <div className="editor-video-frame">
                <VideoPreview
                  src={mediaUrl}
                  poster={thumbnailUrl}
                  onDuration={setDuration}
                />
              </div>

              <TrimControls
                durationSec={durationSec}
                trimStartSec={trimStartSec}
                trimEndSec={trimEndSec}
                isDirty={isDirty}
                onTrimChange={setTrim}
                onReset={resetTrim}
              />
            </>
          ) : (
            <div
              style={{
                color: 'var(--color-text-secondary)',
                fontSize: 'var(--font-size-sm)',
                padding: 'var(--space-4)',
              }}
            >
              Select a part to preview.
            </div>
          )}
        </div>

        {/* Right rail: metadata */}
        <div className="editor-rail">
          {selectedPartNo != null && mediaUrl && (
            <EditorMetadataPanel
              jobId={selectedJobId}
              partNo={selectedPartNo}
              jobStatus={parts.find((p) => p.part_no === selectedPartNo)?.status}
              durationSec={durationSec}
              trimStartSec={trimStartSec}
              trimEndSec={trimEndSec}
              mediaUrl={mediaUrl}
            />
          )}
        </div>
      </div>
    </div>
  )
}
