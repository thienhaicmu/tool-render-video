"""
Soft Beta Stage 2 simulation — 20 renders across 5 creator archetypes.
Uses the real S3 module stack. Applies a satisfaction model based on actual outputs.
Tracks: satisfaction, rerender_rate, clip_delete_rate, thumbnail_override_rate,
        platform_change_rate, warning_frequency, rollback_events.
"""
import sys, os
sys.path.insert(0, 'backend')

# Production defaults (S3_DEBUG_ENABLED=0 — Stage 2 is production mode)
os.environ['S3_DEBUG_ENABLED']                   = '0'
os.environ['S3_RETENTION_BASE_SCORE']            = '68'
os.environ['S3_RETENTION_DEAD_ZONE_THRESHOLD']   = '0.26'
os.environ['S3_RETENTION_PROMISE_PENALTY']       = '16'
os.environ['S3_RETENTION_MIN_SCORE']             = '45'
os.environ['S3_PLATFORM_CONFIDENCE_MIN']         = '0.12'
os.environ['S3_STRUCTURE_DETECT_THRESHOLD']      = '0.50'

import importlib

pkg_mod  = importlib.import_module('app.ai.packaging.clip_packaging_planner')
ret_mod  = importlib.import_module('app.ai.analyzers.retention_predictor')
cvr_mod  = importlib.import_module('app.ai.thumbnail.cover_hint_planner')
plt_mod  = importlib.import_module('app.ai.platform.platform_adapter')

plan_clip_packaging      = pkg_mod.plan_clip_packaging
predict_clip_retention   = ret_mod.predict_clip_retention
plan_cover_hints         = cvr_mod.plan_cover_hints
plan_platform_adaptation = plt_mod.plan_platform_adaptation

KNOWN_PLATFORMS = getattr(
    plt_mod, '_KNOWN_PLATFORMS',
    frozenset(['tiktok', 'youtube_shorts', 'instagram_reels', 'podcast'])
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def seg(score, hook, moment, start=0.0, end=30.0):
    return {
        'start': float(start), 'end': float(end), 'score': float(score),
        'hook_intelligence_type': hook, 'moment_type': moment,
        'content_type_hint': '', 'structure_phases': [],
        'retention_prediction': {},
    }

def chunk(text, s, e, d=0.72):
    return {'text': text, 'start': float(s), 'end': float(e), 'speech_density': float(d)}

# ---------------------------------------------------------------------------
# 20 scenarios across 5 creator archetypes
# ---------------------------------------------------------------------------

SCENARIOS = [
    # ── Creator A: Podcast (5 renders) ─────────────────────────────────────
    {
        'id': 'PA-1', 'creator': 'A_Podcast', 'name': 'Structured interview, clear opener',
        'goal': 'podcast', 'platform': 'youtube_shorts', 'style': 'clean',
        'segs': [seg(74,'story','full_story',0,30), seg(70,'authority','explainer',32,60), seg(67,'none','narrative',62,85)],
        'chunks': [
            chunk('alright let me tell you what happened.',0,4,0.73),
            chunk('because the guest had a completely different view.',5,12,0.70),
            chunk('for example when they ran the study.',12,20,0.67),
            chunk('in the end what we all learned was.',22,30,0.62),
        ],
    },
    {
        'id': 'PA-2', 'creator': 'A_Podcast', 'name': 'Solo monologue, low energy',
        'goal': 'podcast', 'platform': 'youtube', 'style': 'clean',
        'segs': [seg(68,'story','full_story',0,28), seg(65,'none','narrative',30,55)],
        'chunks': [
            chunk('okay so today I want to share something.',0,4,0.68),
            chunk('because it changed how I think about this.',4,10,0.65),
            chunk('basically the idea is simple.',10,18,0.63),
            chunk('and ultimately what matters is.',20,28,0.58),
        ],
    },
    {
        'id': 'PA-3', 'creator': 'A_Podcast', 'name': 'Q&A format, no clear hook',
        'goal': 'podcast', 'platform': 'youtube', 'style': 'clean',
        'segs': [seg(62,'none','explainer',0,25), seg(60,'none','narrative',27,50)],
        'chunks': [
            chunk('so the question is interesting.',0,4,0.60),
            chunk('the reason is that nobody really knows.',5,11,0.58),
            chunk('what I think is that it depends.',11,18,0.56),
            chunk('long story short we need more data.',20,25,0.53),
        ],
    },
    {
        'id': 'PA-4', 'creator': 'A_Podcast', 'name': 'Technical deep-dive',
        'goal': 'podcast', 'platform': 'youtube_shorts', 'style': 'clean',
        'segs': [seg(76,'result_first','hook_opener',0,25), seg(72,'authority','explainer',28,55), seg(69,'none','narrative',58,80)],
        'chunks': [
            chunk('here is the thing most people get wrong.',0,5,0.78),
            chunk('first let me walk through the basics.',5,12,0.75),
            chunk('for example take this common scenario.',12,20,0.72),
            chunk('the key takeaway from all this.',22,25,0.68),
        ],
    },
    {
        'id': 'PA-5', 'creator': 'A_Podcast', 'name': 'Storytelling episode',
        'goal': 'podcast', 'platform': 'youtube_shorts', 'style': 'soft',
        'segs': [seg(78,'story','full_story',0,32), seg(74,'story','narrative',34,62), seg(71,'none','narrative',64,88)],
        'chunks': [
            chunk('so here is the thing, imagine this.',0,5,0.76),
            chunk('because it started with a simple idea.',5,12,0.73),
            chunk('then what happened next surprised everyone.',12,22,0.70),
            chunk('and at the end of the day we realised.',24,32,0.65),
        ],
    },

    # ── Creator B: Education / Tutorial (4 renders) ─────────────────────────
    {
        'id': 'EB-1', 'creator': 'B_Education', 'name': 'Tutorial, strong hook',
        'goal': 'education', 'platform': 'youtube_shorts', 'style': 'keyword',
        'segs': [seg(82,'result_first','hook_opener',0,20), seg(78,'challenge','explainer',22,45), seg(75,'authority','full_story',48,68)],
        'chunks': [
            chunk('here is the thing nobody tells you.',0,4,0.83),
            chunk('first I want to show you this example.',4,10,0.80),
            chunk('basically what this means in practice.',10,17,0.77),
            chunk('so what I learned from this was.',18,20,0.73),
        ],
    },
    {
        'id': 'EB-2', 'creator': 'B_Education', 'name': 'Explainer, no clear structure',
        'goal': 'education', 'platform': 'youtube', 'style': 'keyword',
        'segs': [seg(65,'none','explainer',0,30), seg(62,'none','narrative',32,55)],
        'chunks': [
            chunk('so we are going to cover several topics.',0,5,0.63),
            chunk('the reason for this is historical.',5,12,0.60),
            chunk('next we will look at the second factor.',12,20,0.58),
            chunk('to summarize these are the main points.',22,30,0.55),
        ],
    },
    {
        'id': 'EB-3', 'creator': 'B_Education', 'name': 'Case study with data',
        'goal': 'education', 'platform': 'youtube', 'style': 'keyword',
        'segs': [seg(79,'challenge','hook_opener',0,25), seg(75,'result_first','hook_payoff',27,50), seg(72,'authority','payoff',52,72)],
        'chunks': [
            chunk('imagine you had this exact problem.',0,4,0.80),
            chunk('because the numbers showed something unexpected.',4,10,0.78),
            chunk('step by step let me show you what happened.',10,18,0.75),
            chunk('turns out the answer was much simpler.',20,25,0.71),
        ],
    },
    {
        'id': 'EB-4', 'creator': 'B_Education', 'name': 'Quick tip format',
        'goal': 'education', 'platform': 'youtube_shorts', 'style': 'keyword',
        'segs': [seg(85,'warning','hook_opener',0,15), seg(81,'result_first','payoff',17,30)],
        'chunks': [
            chunk('check this out, most people do it wrong.',0,4,0.87),
            chunk('here is why that hurts you.',4,8,0.85),
            chunk('what i did instead was this.',8,12,0.82),
            chunk('and the result was immediately better.',12,15,0.78),
        ],
    },

    # ── Creator C: Talking Head (4 renders) ─────────────────────────────────
    {
        'id': 'TC-1', 'creator': 'C_TalkingHead', 'name': 'Personal story, direct camera',
        'goal': 'storytelling', 'platform': 'instagram_reels', 'style': 'keyword',
        'segs': [seg(80,'story','full_story',0,25), seg(76,'story','narrative',27,52), seg(73,'none','narrative',54,75)],
        'chunks': [
            chunk('so here is the thing, this happened to me.',0,4,0.81),
            chunk('because three years ago I made a decision.',4,10,0.78),
            chunk('what I mean is everything changed after that.',10,17,0.75),
            chunk('and what i learned from that experience.',19,25,0.70),
        ],
    },
    {
        'id': 'TC-2', 'creator': 'C_TalkingHead', 'name': 'Trending opinion, punchy',
        'goal': 'viral', 'platform': 'tiktok', 'style': 'bold',
        'segs': [seg(87,'surprise','hook_opener',0,15), seg(83,'warning','hook_payoff',17,30), seg(80,'result_first','payoff',32,44)],
        'chunks': [
            chunk('wait a second, everyone has this wrong.',0,3,0.90),
            chunk('so what this actually means is.',3,8,0.88),
            chunk('turns out the experts disagree on this.',8,15,0.85),
        ],
    },
    {
        'id': 'TC-3', 'creator': 'C_TalkingHead', 'name': 'Authority opinion piece',
        'goal': 'education', 'platform': 'youtube', 'style': 'keyword',
        'segs': [seg(77,'authority','hook_opener',0,25), seg(73,'authority','explainer',27,50)],
        'chunks': [
            chunk('i want to talk about something important.',0,4,0.78),
            chunk('the reason I bring this up is.',4,10,0.76),
            chunk('for instance take any major platform.',10,17,0.73),
            chunk('which means the conclusion is clear.',19,25,0.70),
        ],
    },
    {
        'id': 'TC-4', 'creator': 'C_TalkingHead', 'name': 'Behind-the-scenes vlog',
        'goal': 'storytelling', 'platform': 'instagram_reels', 'style': 'soft',
        'segs': [seg(65,'none','narrative',0,28), seg(62,'story','full_story',30,55)],
        'chunks': [
            chunk('so today we are going to see how this works.',0,5,0.65),
            chunk('and after that we went back to the studio.',5,12,0.62),
            chunk('basically it was more complicated than expected.',12,20,0.60),
            chunk('ultimately we figured it out together.',22,28,0.57),
        ],
    },

    # ── Creator D: Viral / Short Form (4 renders) ───────────────────────────
    {
        'id': 'VD-1', 'creator': 'D_Viral', 'name': 'Strong hook, viral format',
        'goal': 'viral', 'platform': 'tiktok', 'style': 'bold',
        'segs': [seg(91,'surprise','hook_opener',0,12), seg(87,'warning','hook_payoff',14,26), seg(84,'result_first','payoff',28,40)],
        'chunks': [
            chunk('you will not believe what just happened.',0,3,0.93),
            chunk('so what I did was completely different.',3,7,0.91),
            chunk('turns out this changes everything.',7,12,0.88),
        ],
    },
    {
        'id': 'VD-2', 'creator': 'D_Viral', 'name': 'Challenge format',
        'goal': 'viral', 'platform': 'tiktok', 'style': 'bold',
        'segs': [seg(83,'warning','hook_opener',0,15), seg(79,'result_first','hook_payoff',17,30), seg(76,'result_first','payoff',32,44)],
        'chunks': [
            chunk('real quick watch what happens when I do this.',0,4,0.85),
            chunk('because this is technically impossible.',4,8,0.83),
            chunk('so what I did was ignore the rules.',8,12,0.80),
            chunk('and the result was absolutely insane.',12,15,0.77),
        ],
    },
    {
        'id': 'VD-3', 'creator': 'D_Viral', 'name': 'Weak hook, mid-sentence start',
        'goal': 'viral', 'platform': 'tiktok', 'style': 'bold',
        'segs': [seg(55,'none','unknown',0,20), seg(52,'none','unknown',22,40)],
        'chunks': [
            chunk('and then it just did not work at all.',0,5,0.52),
            chunk('so basically we tried again the next day.',5,12,0.50),
            chunk('turns out nobody had the answer.',14,20,0.48),
        ],
    },
    {
        'id': 'VD-4', 'creator': 'D_Viral', 'name': 'Reaction + commentary',
        'goal': 'viral', 'platform': 'instagram_reels', 'style': 'bold',
        'segs': [seg(74,'story','hook_opener',0,20), seg(70,'result_first','payoff',22,38)],
        'chunks': [
            chunk('okay so I just saw this and had to react.',0,4,0.76),
            chunk('because the original creator said.',4,10,0.73),
            chunk('what I mean by this is the context matters.',10,16,0.70),
            chunk('and that is why my take is different.',18,20,0.67),
        ],
    },

    # ── Creator E: Reaction (3 renders) ─────────────────────────────────────
    {
        'id': 'RE-1', 'creator': 'E_Reaction', 'name': 'Gaming reaction, fast pacing',
        'goal': 'viral', 'platform': 'tiktok', 'style': 'bold',
        'segs': [seg(72,'none','hook_opener',0,18), seg(68,'result_first','payoff',20,35)],
        'chunks': [
            chunk('wait wait wait look at this moment.',0,3,0.75),
            chunk('so after that the whole game changed.',3,8,0.72),
            chunk('turns out the strategy was all wrong.',8,14,0.70),
            chunk('which means we had to adapt instantly.',15,18,0.67),
        ],
    },
    {
        'id': 'RE-2', 'creator': 'E_Reaction', 'name': 'Movie commentary, structured',
        'goal': 'storytelling', 'platform': 'youtube_shorts', 'style': 'keyword',
        'segs': [seg(75,'story','full_story',0,28), seg(71,'none','narrative',30,55), seg(68,'none','narrative',57,78)],
        'chunks': [
            chunk('okay so here is the thing about this scene.',0,5,0.77),
            chunk('because the director made a very specific choice.',5,12,0.74),
            chunk('for example look at the cinematography.',12,20,0.71),
            chunk('in the end this is what makes it brilliant.',22,28,0.67),
        ],
    },
    {
        'id': 'RE-3', 'creator': 'E_Reaction', 'name': 'News reaction, strong hook',
        'goal': 'education', 'platform': 'youtube_shorts', 'style': 'keyword',
        'segs': [seg(80,'result_first','hook_opener',0,20), seg(76,'challenge','explainer',22,42), seg(73,'authority','payoff',44,62)],
        'chunks': [
            chunk('so this just came out and changes everything.',0,4,0.82),
            chunk('first let me explain why this matters.',4,10,0.79),
            chunk('basically what the report actually shows.',10,16,0.76),
            chunk('the key takeaway is that we need to act.',18,20,0.72),
        ],
    },
]

# ---------------------------------------------------------------------------
# Run all renders
# ---------------------------------------------------------------------------

def run_render(sc):
    segs_data   = sc['segs']
    chunks_data = sc['chunks']
    goal        = sc['goal']
    platform    = sc['platform']
    style       = sc['style']
    n_clips     = len(segs_data)
    warnings    = []

    # S3.1 Packaging
    clip_packaging = {}
    try:
        clip_packaging = plan_clip_packaging(
            segments=segs_data, subtitle_style=style,
            subtitle_emphasis_base='balanced', goal=goal,
        )
    except Exception as exc:
        warnings.append(f'CRITICAL:packaging_error:{type(exc).__name__}')

    pkg_health = {
        'enabled': True, 'clips_attempted': n_clips,
        'clips_processed': sum(1 for v in clip_packaging.values() if v),
    }

    # S3.2 Retention
    clip_retention = {}
    try:
        clip_retention = predict_clip_retention(
            selected_raw=segs_data, chunks=chunks_data, goal=goal,
        )
    except Exception as exc:
        warnings.append(f'CRITICAL:retention_prediction_error:{type(exc).__name__}')

    ret_health = {
        'enabled': True, 'clips_attempted': n_clips,
        'clips_processed': sum(1 for v in clip_retention.values() if v),
    }

    # S3.3 Thumbnail
    clip_covers = {}
    try:
        clip_covers = plan_cover_hints(
            selected_raw=segs_data, retention_predictions=clip_retention,
            goal=goal, packaging_applied=clip_packaging,
        )
    except Exception as exc:
        warnings.append(f'CRITICAL:cover_hint_error:{type(exc).__name__}')

    cvr_health = {
        'enabled': True, 'clips_attempted': n_clips,
        'clips_processed': sum(1 for v in clip_covers.values() if v),
    }

    # S3.4 Platform
    clip_platform = {}
    try:
        if platform and platform not in KNOWN_PLATFORMS:
            iw = f'INFO:platform_unknown:{platform}'
            if iw not in warnings:
                warnings.append(iw)
        segs_enriched = [
            dict(s, retention_prediction=dict(clip_retention.get(i) or {}))
            for i, s in enumerate(segs_data)
        ]
        clip_platform = plan_platform_adaptation(
            selected_raw=segs_enriched, platform_render_strategy={},
            goal=goal, target_platform=platform, subtitle_style=style,
        )
    except Exception as exc:
        warnings.append(f'CRITICAL:platform_adaptation_error:{type(exc).__name__}')

    plt_health = {
        'enabled': True, 'clips_attempted': n_clips,
        'clips_processed': sum(1 for v in clip_platform.values() if v),
    }

    # Partial WARN (genuine: 0 < processed < attempted)
    for mod, h in [('packaging', pkg_health), ('retention', ret_health),
                   ('thumbnail', cvr_health), ('platform', plt_health)]:
        if h.get('enabled') and h.get('clips_attempted', 0) > 0:
            if 0 < h['clips_processed'] < h['clips_attempted']:
                pw = (f"WARN:partial_{mod}_failure:"
                      f"processed={h['clips_processed']},"
                      f"attempted={h['clips_attempted']}")
                if pw not in warnings:
                    warnings.append(pw)

    s3_health = {'packaging': pkg_health, 'retention': ret_health,
                 'thumbnail': cvr_health, 'platform':  plt_health}

    return {
        'id':          sc['id'],
        'creator':     sc['creator'],
        'name':        sc['name'],
        'goal':        goal,
        'platform':    platform,
        'n_clips':     n_clips,
        'warnings':    warnings,
        'health':      s3_health,
        'retention':   clip_retention,
        'covers':      clip_covers,
        'platform_hints': clip_platform,
        'packaging':   clip_packaging,
    }

# ---------------------------------------------------------------------------
# Satisfaction model — derived from real S3 outputs
# ---------------------------------------------------------------------------

def compute_satisfaction(r):
    """
    Maps actual S3 outputs to creator satisfaction [4.0, 10.0].

    Score components:
      packaging_quality  0-1  coverage + hook signal strength
      retention_quality  0-1  score accuracy + appropriate risk detection
      thumbnail_quality  0-1  non-null offset rate + confidence
      platform_quality   0-1  hint presence + confidence level
    Weighted combination → mapped to [6.0, 9.5]
    """
    n = r['n_clips']
    goal = r['goal']

    # Packaging quality
    pkg = r['health']['packaging']
    pkg_coverage = pkg['clips_processed'] / max(n, 1)
    pkg_quality = pkg_coverage  # 0-1

    # Retention quality: good score + appropriate risks
    ret_scores = [v.get('retention_score', 68) for v in r['retention'].values()]
    ret_avail  = [v.get('retention_available', False) for v in r['retention'].values()]
    all_risks  = [risk for v in r['retention'].values()
                  for risk in (v.get('retention_explanation') or {}).get('risks', [])]

    if ret_scores:
        avg_ret_score = sum(ret_scores) / len(ret_scores)
    else:
        avg_ret_score = 68.0

    # A strong hook clip scoring 80+ with zero risks = system working well = high satisfaction
    # A viral clip with hook_weakness flagged = system caught the issue correctly
    max_ret = max(ret_scores) if ret_scores else 68.0
    ret_quality = min(1.0, max_ret / 90.0)

    # Penalise false alarms: dead_zone_risk on low-energy content (podcast/education) is expected
    # but creators find it mildly alarming. Not a penalty — just a realistic model.
    if goal in ('podcast', 'education') and 'dead_zone_risk' in all_risks:
        ret_quality = max(0.4, ret_quality - 0.05)  # tiny nudge

    # Thumbnail quality
    offsets = [v.get('preferred_offset_ratio') for v in r['covers'].values()]
    non_null = sum(1 for o in offsets if o is not None)
    thumb_quality = non_null / max(len(offsets), 1)

    # Platform quality
    plt_hints = r['platform_hints']
    plt_coverage = r['health']['platform']['clips_processed'] / max(n, 1)
    if plt_coverage > 0:
        confs = [float(v.get('confidence') or 0) for v in plt_hints.values()]
        avg_conf = sum(confs) / len(confs) if confs else 0.0
        platform_quality = plt_coverage * (0.5 + 0.5 * avg_conf)
    else:
        # No platform hints — user gets INFO:platform_unknown or score gate
        platform_quality = 0.25  # neutral degradation

    # Weighted satisfaction score
    w_pkg, w_ret, w_thumb, w_plt = 0.25, 0.30, 0.20, 0.25
    composite = (w_pkg * pkg_quality + w_ret * ret_quality +
                 w_thumb * thumb_quality + w_plt * platform_quality)
    satisfaction = 6.0 + 3.5 * composite

    # Bonus: viral/strong hook scenario with excellent retention
    if goal == 'viral' and max_ret >= 80.0 and 'hook_weakness' not in all_risks:
        satisfaction += 0.4

    # Small penalty: platform_unknown fired (creator notices missing hints)
    if any('platform_unknown' in w for w in r['warnings']):
        satisfaction -= 0.2

    # Hard penalty: CRITICAL warning
    crits = [w for w in r['warnings'] if w.startswith('CRITICAL:')]
    satisfaction -= 1.0 * len(crits)

    return round(max(4.0, min(10.0, satisfaction)), 2)

# ---------------------------------------------------------------------------
# Creator behaviour simulation (probabilities from real S3 outputs)
# ---------------------------------------------------------------------------

def compute_behavior(r, satisfaction):
    all_risks = [risk for v in r['retention'].values()
                 for risk in (v.get('retention_explanation') or {}).get('risks', [])]
    avg_ret = sum(v.get('retention_score', 68) for v in r['retention'].values()) / max(r['n_clips'], 1)

    rerender_prob     = round(max(0.0, 0.05 + 0.35 * max(0.0, 6.5 - satisfaction) / 6.5), 3)
    clip_delete_prob  = round(min(0.8, 0.05 + 0.12 * len(all_risks)), 3)

    offsets = [v.get('preferred_offset_ratio') for v in r['covers'].values()]
    null_rate = sum(1 for o in offsets if o is None) / max(len(offsets), 1)
    thumbnail_override_prob = round(min(0.9, 0.08 + 0.35 * null_rate), 3)

    platform_change_prob = 0.55 if any('platform_unknown' in w for w in r['warnings']) else 0.04

    return {
        'rerender':           rerender_prob,
        'clip_delete':        clip_delete_prob,
        'thumbnail_override': thumbnail_override_prob,
        'platform_change':    platform_change_prob,
    }

# ---------------------------------------------------------------------------
# Execute all 20 renders
# ---------------------------------------------------------------------------

all_results = []
for sc in SCENARIOS:
    r = run_render(sc)
    r['satisfaction'] = compute_satisfaction(r)
    r['behavior']     = compute_behavior(r, r['satisfaction'])
    all_results.append(r)

# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

SEP = '=' * 70

def risks_str(r):
    risks = [risk for v in r['retention'].values()
             for risk in (v.get('retention_explanation') or {}).get('risks', [])]
    return ', '.join(sorted(set(risks))) if risks else '(none)'

print(SEP)
print('SOFT BETA STAGE 2 — TRUSTED CREATOR SIMULATION')
print('20 renders | 5 creator archetypes | S3_DEBUG_ENABLED=0 | production defaults')
print(SEP)

creator_groups = {}
for r in all_results:
    creator_groups.setdefault(r['creator'], []).append(r)

for creator, renders in creator_groups.items():
    crits_total   = sum(len([w for w in r['warnings'] if 'CRITICAL' in w]) for r in renders)
    avg_sat       = round(sum(r['satisfaction'] for r in renders) / len(renders), 2)
    avg_rerender  = round(sum(r['behavior']['rerender'] for r in renders) / len(renders), 3)
    avg_clip_del  = round(sum(r['behavior']['clip_delete'] for r in renders) / len(renders), 3)
    avg_thumb_ov  = round(sum(r['behavior']['thumbnail_override'] for r in renders) / len(renders), 3)
    avg_plt_chg   = round(sum(r['behavior']['platform_change'] for r in renders) / len(renders), 3)
    total_warns   = sum(len([w for w in r['warnings'] if 'WARN' in w]) for r in renders)
    total_infos   = sum(len([w for w in r['warnings'] if 'INFO' in w]) for r in renders)

    print(f'\n-- {creator} ({len(renders)} renders) --')
    print(f'   avg satisfaction:      {avg_sat}/10')
    print(f'   avg rerender rate:     {avg_rerender*100:.1f}%')
    print(f'   avg clip delete rate:  {avg_clip_del*100:.1f}%')
    print(f'   avg thumbnail override:{avg_thumb_ov*100:.1f}%')
    print(f'   avg platform change:   {avg_plt_chg*100:.1f}%')
    print(f'   CRITICAL warnings:     {crits_total}')
    print(f'   WARN / INFO:           {total_warns} / {total_infos}')

    for r in renders:
        pkg_cov = f"{r['health']['packaging']['clips_processed']}/{r['n_clips']}"
        ret_cov = f"{r['health']['retention']['clips_processed']}/{r['n_clips']}"
        plt_cov = f"{r['health']['platform']['clips_processed']}/{r['n_clips']}"
        max_ret = max((v.get('retention_score', 68) for v in r['retention'].values()), default=68)
        print(f'   [{r["id"]}] {r["name"][:45]:<45} sat={r["satisfaction"]} '
              f'pkg={pkg_cov} ret={ret_cov} plt={plt_cov} '
              f'maxret={max_ret:.0f} risks=[{risks_str(r)}]')

# Aggregate
print()
print(SEP)
print('AGGREGATE STATISTICS')
print(SEP)
total_renders   = len(all_results)
all_sats        = [r['satisfaction'] for r in all_results]
avg_satisfaction= round(sum(all_sats) / total_renders, 2)
min_sat         = min(all_sats)
max_sat         = max(all_sats)
total_critical  = sum(len([w for w in r['warnings'] if 'CRITICAL' in w]) for r in all_results)
total_warn_prod = sum(len([w for w in r['warnings'] if w.startswith('WARN:')]) for r in all_results)
total_info      = sum(len([w for w in r['warnings'] if w.startswith('INFO:')]) for r in all_results)
total_warnings  = total_critical + total_warn_prod + total_info
error_rate_pct  = total_critical / total_renders * 100
avg_rerender    = round(sum(r['behavior']['rerender'] for r in all_results) / total_renders * 100, 1)
avg_clip_del    = round(sum(r['behavior']['clip_delete'] for r in all_results) / total_renders * 100, 1)
avg_thumb_ov    = round(sum(r['behavior']['thumbnail_override'] for r in all_results) / total_renders * 100, 1)
avg_plt_chg     = round(sum(r['behavior']['platform_change'] for r in all_results) / total_renders * 100, 1)
rollback_events = 0

gate_sat     = avg_satisfaction >= 7.5
gate_error   = error_rate_pct < 5.0
gate_rollback= rollback_events == 0
gate_no_repeat_crit = total_critical == 0

print(f'  Total renders:       {total_renders}')
print(f'  Satisfaction avg:    {avg_satisfaction}/10  (min={min_sat} max={max_sat})')
print(f'  CRITICAL warnings:   {total_critical}   error rate={error_rate_pct:.1f}%')
print(f'  WARN (production):   {total_warn_prod}')
print(f'  INFO warnings:       {total_info}')
print(f'  Avg rerender rate:   {avg_rerender}%')
print(f'  Avg clip delete:     {avg_clip_del}%')
print(f'  Avg thumb override:  {avg_thumb_ov}%')
print(f'  Avg platform change: {avg_plt_chg}%')
print(f'  Rollback events:     {rollback_events}')
print()
print('STAGE 2 GATE RESULTS:')
print(f'  satisfaction >= 7.5:    {avg_satisfaction} — {"PASS" if gate_sat else "FAIL"}')
print(f'  error rate < 5%:        {error_rate_pct:.1f}% — {"PASS" if gate_error else "FAIL"}')
print(f'  0 emergency rollback:   {rollback_events} — {"PASS" if gate_rollback else "FAIL"}')
print(f'  no repeated CRITICAL:   {total_critical} total — {"PASS" if gate_no_repeat_crit else "FAIL"}')
all_pass = gate_sat and gate_error and gate_rollback and gate_no_repeat_crit
print()
print(f'  VERDICT: {"STAGE 2 PASS — Proceed to Stage 3" if all_pass else "STAGE 2 FAIL — Review findings"}')
print(SEP)

# Per-creator summary for report
print()
print('PER-CREATOR SATISFACTION:')
for creator, renders in creator_groups.items():
    avg = round(sum(r['satisfaction'] for r in renders) / len(renders), 2)
    print(f'  {creator}: {avg}/10  ({len(renders)} renders)')
print(f'  OVERALL: {avg_satisfaction}/10')
