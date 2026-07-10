/**
 * Studio base layer (F0) — mode-agnostic design-system components shared by the
 * Story Studio (and, later, a migrated Content Studio). Import from here:
 *   import { StudioScreen, StudioCard, StudioField } from '@/components/studio'
 * All styling lives in studio.css and uses only styles/tokens.css variables.
 */
export { StudioScreen } from './StudioScreen'
export { StudioCard } from './StudioCard'
export { StudioField } from './StudioField'
export { StudioStepper } from './StudioStepper'
export { SegRow } from './SegRow'
export type { SegOption } from './SegRow'
export { RatioPicker } from './RatioPicker'
export type { RatioOption } from './RatioPicker'
