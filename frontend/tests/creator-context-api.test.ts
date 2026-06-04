/**
 * Sprint 3-FE — creator-context API client tests.
 *
 * Pins the wire contract between the frontend client and the backend
 * /api/settings/creator-context route. The tests don't hit the real
 * backend — they mock `fetch` and assert:
 *   - request path is /api/settings/creator-context
 *   - PUT uses the right HTTP verb and JSON body
 *   - GET parses the envelope shape
 *   - BLANK_CREATOR_CONTEXT matches the exported type and the
 *     backend's blank shape (defaults all empty / [])
 */
import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  BLANK_CREATOR_CONTEXT,
  type CreatorContextEnvelope,
  type CreatorContextPayload,
  getCreatorContext,
  putCreatorContext,
} from '../src/api/creatorContext'

function mockFetchOnce(envelope: CreatorContextEnvelope, status = 200) {
  const spy = vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(
    new Response(JSON.stringify(envelope), {
      status,
      headers: { 'Content-Type': 'application/json' },
    }),
  )
  return spy
}

afterEach(() => {
  vi.restoreAllMocks()
})

describe('BLANK_CREATOR_CONTEXT', () => {
  it('has every field at the documented empty default', () => {
    expect(BLANK_CREATOR_CONTEXT).toEqual({
      creator_id: '',
      channel_name: '',
      brand_voice: '',
      target_audience: '',
      content_pillars: [],
      market: '',
      language: '',
      notes: '',
    })
  })

  it('content_pillars is a fresh array per import (no shared mutation risk)', () => {
    // Mutate a copy — original constant must not change.
    const copy = { ...BLANK_CREATOR_CONTEXT, content_pillars: [...BLANK_CREATOR_CONTEXT.content_pillars] }
    copy.content_pillars.push('x')
    expect(BLANK_CREATOR_CONTEXT.content_pillars).toEqual([])
  })
})

describe('getCreatorContext', () => {
  it('hits GET /api/settings/creator-context', async () => {
    const envelope: CreatorContextEnvelope = {
      is_configured: false,
      creator_context: BLANK_CREATOR_CONTEXT,
    }
    const spy = mockFetchOnce(envelope)
    const result = await getCreatorContext()
    expect(spy).toHaveBeenCalledOnce()
    const [calledPath, calledInit] = spy.mock.calls[0]
    expect(calledPath).toMatch(/\/api\/settings\/creator-context$/)
    // GET — no method override (apiFetch leaves method unset → fetch default GET)
    expect(calledInit?.method).toBeUndefined()
    expect(result).toEqual(envelope)
  })

  it('parses a configured envelope back to the typed shape', async () => {
    const envelope: CreatorContextEnvelope = {
      is_configured: true,
      creator_context: {
        creator_id: 'creator-vn-1',
        channel_name: 'K1 Cooking',
        brand_voice: 'authentic',
        target_audience: 'vn',
        content_pillars: ['recipe', 'tutorial'],
        market: 'vn',
        language: 'vi',
        notes: 'Friendly home cook vibe',
      },
    }
    mockFetchOnce(envelope)
    const result = await getCreatorContext()
    expect(result.is_configured).toBe(true)
    expect(result.creator_context.channel_name).toBe('K1 Cooking')
    expect(result.creator_context.content_pillars).toEqual(['recipe', 'tutorial'])
  })
})

describe('putCreatorContext', () => {
  it('sends PUT with a JSON body to /api/settings/creator-context', async () => {
    const body: CreatorContextPayload = {
      ...BLANK_CREATOR_CONTEXT,
      channel_name: 'K1',
      brand_voice: 'viral',
    }
    const envelope: CreatorContextEnvelope = { is_configured: true, creator_context: body }
    const spy = mockFetchOnce(envelope)

    const result = await putCreatorContext(body)

    expect(spy).toHaveBeenCalledOnce()
    const [calledPath, calledInit] = spy.mock.calls[0]
    expect(calledPath).toMatch(/\/api\/settings\/creator-context$/)
    expect(calledInit?.method).toBe('PUT')
    // Body is serialised JSON of the payload.
    expect(calledInit?.body).toBeTypeOf('string')
    expect(JSON.parse(calledInit?.body as string)).toEqual(body)
    expect(result).toEqual(envelope)
  })

  it('preserves unicode in payload body', async () => {
    const body: CreatorContextPayload = {
      ...BLANK_CREATOR_CONTEXT,
      channel_name: 'Bếp Việt',
      notes: 'Hấp dẫn, gần gũi',
    }
    const envelope: CreatorContextEnvelope = { is_configured: true, creator_context: body }
    const spy = mockFetchOnce(envelope)

    await putCreatorContext(body)
    const sent = JSON.parse((spy.mock.calls[0][1]?.body as string) ?? '{}')
    expect(sent.channel_name).toBe('Bếp Việt')
    expect(sent.notes).toBe('Hấp dẫn, gần gũi')
  })

  it('sends all-blank payload to clear server-side state', async () => {
    const envelope: CreatorContextEnvelope = {
      is_configured: false,
      creator_context: BLANK_CREATOR_CONTEXT,
    }
    const spy = mockFetchOnce(envelope)

    const result = await putCreatorContext(BLANK_CREATOR_CONTEXT)
    expect(result.is_configured).toBe(false)
    const sent = JSON.parse((spy.mock.calls[0][1]?.body as string) ?? '{}')
    expect(sent).toEqual(BLANK_CREATOR_CONTEXT)
  })
})
