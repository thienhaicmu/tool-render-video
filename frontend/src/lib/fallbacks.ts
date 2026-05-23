import type { AIPlanCardData } from '../adapters/studioAdapters'
import type { ReviewCardData } from '../features/studio/types'

export const SAMPLE_AI_PLAN: AIPlanCardData[] = [
  {
    title: 'Hook Opening',
    confidence: 87,
    reasoning: 'Hook identified at 0:04. Strong visual cut predicted to retain audience.',
    impact: '+12% watch duration',
    tags: ['hook', '0:04', 'high retention'],
  },
  {
    title: 'Climax Moment',
    confidence: 74,
    reasoning: 'Peak energy moment at 1:32. AI markers indicate high engagement.',
    impact: '+8% completion rate',
    tags: ['climax', '1:32', 'energy peak'],
  },
  {
    title: 'Call-to-Action Close',
    confidence: 61,
    reasoning: 'Strong verbal CTA detected at 3:48. Subtitle density peaks here.',
    impact: '+5% conversion signal',
    tags: ['cta', '3:48', 'verbal'],
  },
]

export const MOCK_REVIEW_CARDS: ReviewCardData[] = [
  {
    id: 'clip-1',
    title: 'Hook Opening',
    confidence: 87,
    reasoning: 'Strong visual cut at 0:04 predicted to retain early audience attention.',
    impact: '↑ +12% retention',
    previewTag: '0:04 – 0:42',
    clipLabel: 'Clip 1 of 3',
  },
  {
    id: 'clip-2',
    title: 'Climax Moment',
    confidence: 74,
    reasoning: 'Peak energy at 1:32. AI markers show high engagement probability.',
    impact: '↑ +8% completion rate',
    previewTag: '1:28 – 2:05',
    clipLabel: 'Clip 2 of 3',
  },
  {
    id: 'clip-3',
    title: 'Call-to-Action Close',
    confidence: 61,
    reasoning: 'Verbal CTA at 3:48. Subtitle density peaks. Strong conversion signal.',
    impact: '↑ +5% conversion',
    previewTag: '3:44 – 4:10',
    clipLabel: 'Clip 3 of 3',
  },
]
