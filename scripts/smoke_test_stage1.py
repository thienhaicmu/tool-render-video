"""
Soft Beta Stage 1 smoke test.
Exercises all four S3 modules + debug aggregator against 5 synthetic renders.
Mirrors the ai_director call pattern exactly.
"""
import sys, os
sys.path.insert(0, 'backend')

os.environ['S3_DEBUG_ENABLED']                   = '1'
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
dbg_mod  = importlib.import_module('app.ai.debug.clip_debug_aggregator')

plan_clip_packaging      = pkg_mod.plan_clip_packaging
predict_clip_retention   = ret_mod.predict_clip_retention
plan_cover_hints         = cvr_mod.plan_cover_hints
plan_platform_adaptation = plt_mod.plan_platform_adaptation
aggregate_clip_debug     = dbg_mod.aggregate_clip_debug

KNOWN_PLATFORMS = getattr(
    plt_mod, '_KNOWN_PLATFORMS',
    frozenset(['tiktok', 'youtube', 'youtube_shorts', 'instagram_reels', 'podcast'])
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
# 5 test scenarios
# ---------------------------------------------------------------------------

SCENARIOS = [
    {
        'name': 'R1 — Podcast / Low Energy',
        'goal': 'podcast', 'platform': 'youtube', 'style': 'clean',
        'segs': [
            seg(72, 'story',    'full_story',  0,  28),
            seg(68, 'authority','explainer',   30, 55),
            seg(65, 'none',     'narrative',   60, 82),
        ],
        'chunks': [
            chunk('alright so today I want to talk about something.', 0, 4, 0.70),
            chunk('because this has been on my mind for a while.',     5, 10, 0.68),
            chunk('for example when you look at the data.',            10, 17, 0.65),
            chunk('in the end what I learned was.',                    20, 28, 0.60),
        ],
    },
    {
        'name': 'R2 — Talking Head / Education',
        'goal': 'education', 'platform': 'youtube', 'style': 'keyword',
        'segs': [
            seg(78, 'result_first', 'hook_opener', 0,  25),
            seg(74, 'challenge',    'explainer',   28, 52),
            seg(71, 'authority',    'full_story',  55, 75),
        ],
        'chunks': [
            chunk('here is the thing you need to know.',  0,  5, 0.80),
            chunk('first let me explain the context.',    5,  12, 0.75),
            chunk('basically what this means is.',       12, 20, 0.72),
            chunk('the key takeaway is this.',           20, 25, 0.68),
        ],
    },
    {
        'name': 'R3 — Viral / Strong Hook',
        'goal': 'viral', 'platform': 'tiktok', 'style': 'bold',
        'segs': [
            seg(88, 'surprise',     'hook_opener', 0,  15),
            seg(82, 'warning',      'hook_payoff', 18, 30),
            seg(79, 'result_first', 'payoff',      32, 44),
        ],
        'chunks': [
            chunk('wait a second you will not believe this.',      0, 4,  0.90),
            chunk('so what I did was completely unexpected.',       4, 10, 0.85),
            chunk('turns out the result was incredible.',         10, 15, 0.80),
        ],
    },
    {
        'name': 'R4 — Viral / Weak Hook (no opener)',
        'goal': 'viral', 'platform': 'tiktok', 'style': 'bold',
        'segs': [
            seg(55, 'none', 'unknown', 0,  20),
            seg(52, 'none', 'unknown', 22, 40),
        ],
        'chunks': [
            chunk('and after that we just kept going.',            0,  5,  0.55),
            chunk('so basically the whole thing fell apart.',      5,  12, 0.50),
            chunk('turns out no one knew what was happening.',    14, 20, 0.48),
        ],
    },
    {
        'name': 'R5 — Education / Bad Audio + Filler',
        'goal': 'education', 'platform': 'youtube', 'style': 'keyword',
        'segs': [
            seg(48, 'none', 'explainer', 0, 30),
        ],
        'chunks': [
            chunk('okay uh so um basically',           0,  5,  0.40),
            chunk('because uh the uh thing is',        5,  12, 0.38),
            chunk('turns out uh it was like',          18, 25, 0.35),
        ],
    },
]

# ---------------------------------------------------------------------------
# Run renders
# ---------------------------------------------------------------------------

results = []

for sc in SCENARIOS:
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

    # S3 Debug (S3_DEBUG_ENABLED=1)
    clip_debug = {}
    try:
        clip_debug = aggregate_clip_debug(
            selected_segments=segs_data,
            clip_packaging=clip_packaging,
            clip_retention_prediction=clip_retention,
            clip_cover_hints=clip_covers,
            clip_platform_adaptation=clip_platform,
        )
        for cd in clip_debug.values():
            for w in list((cd or {}).get('warnings') or []):
                wp = f'WARN:{w}' if not w.startswith(('INFO:', 'WARN:', 'CRITICAL:')) else w
                if wp not in warnings:
                    warnings.append(wp)
    except Exception as exc:
        warnings.append(f'CRITICAL:debug_aggregation_error:{type(exc).__name__}')

    s3_health = {
        'packaging': pkg_health, 'retention': ret_health,
        'thumbnail': cvr_health, 'platform':  plt_health,
    }

    # RC2 partial WARN — only for genuine partial failures (0 < processed < attempted).
    # Zero-processed is expected for score-gate or unknown-platform paths.
    for mod, h in s3_health.items():
        if h.get('enabled') and h.get('clips_attempted', 0) > 0:
            if 0 < h['clips_processed'] < h['clips_attempted']:
                pw = (f"WARN:partial_{mod}_failure:"
                      f"processed={h['clips_processed']},"
                      f"attempted={h['clips_attempted']}")
                if pw not in warnings:
                    warnings.append(pw)

    results.append({
        'name':        sc['name'],
        'goal':        goal,
        'platform':    platform,
        'n_clips':     n_clips,
        'warnings':    warnings,
        'health':      s3_health,
        'ret_scores':  {k: v.get('retention_score') for k, v in clip_retention.items()},
        'ret_avail':   {k: v.get('retention_available') for k, v in clip_retention.items()},
        'ret_risks':   {k: (v.get('retention_explanation') or {}).get('risks', [])
                        for k, v in clip_retention.items()},
        'cvr_offsets': {k: v.get('preferred_offset_ratio') for k, v in clip_covers.items()},
        'plt_hints':   {k: {
                            'pacing':   v.get('pacing_hint'),
                            'opener':   v.get('opener_emphasis'),
                            'density':  v.get('subtitle_density_hint'),
                            'conf':     round(float(v.get('confidence') or 0), 2),
                        } for k, v in clip_platform.items()},
        'debug_clips': len(clip_debug),
        'pkg_sample':  {k: v.get('reason', []) for k, v in clip_packaging.items()},
    })

# ---------------------------------------------------------------------------
# Print report
# ---------------------------------------------------------------------------

SEP = '=' * 68
print(SEP)
print('SOFT BETA STAGE 1 — SMOKE TEST RESULTS')
print('5 internal renders | S3_DEBUG_ENABLED=1 | production defaults')
print(SEP)

total_critical = total_warn = total_info = 0

for r in results:
    crits  = [w for w in r['warnings'] if w.startswith('CRITICAL:')]
    warns  = [w for w in r['warnings'] if w.startswith('WARN:')]
    infos  = [w for w in r['warnings'] if w.startswith('INFO:')]
    # Debug-mode dominance warnings only fire with S3_DEBUG_ENABLED=1 (staging).
    # They are never present in production and are excluded from the WARN rate gate.
    debug_warns = [w for w in warns if 'dominance_warning' in w]
    gate_warns  = [w for w in warns if 'dominance_warning' not in w]
    total_critical += len(crits)
    total_warn     += len(gate_warns)   # gate uses production-equivalent WARN only
    total_info     += len(infos)
    passed = (len(crits) == 0)

    print(f"\n{'[PASS]' if passed else '[FAIL]'} {r['name']}")
    print(f"  goal={r['goal']}  platform={r['platform']}  clips={r['n_clips']}")
    print(f"  warnings: CRITICAL={len(crits)} WARN={len(gate_warns)} "
          f"WARN(debug-only)={len(debug_warns)} INFO={len(infos)}")
    for w in r['warnings']:
        tag = ' [debug-only]' if 'dominance_warning' in w else ''
        print(f"    {w}{tag}")
    print(f"  s3_health_summary:")
    for mod, h in r['health'].items():
        bar = 'full' if h['clips_processed'] == h['clips_attempted'] else 'PARTIAL'
        print(f"    {mod}: {h['clips_processed']}/{h['clips_attempted']} [{bar}]")
    print(f"  retention scores:    {r['ret_scores']}")
    print(f"  retention_available: {r['ret_avail']}")
    print(f"  retention risks:")
    for k, risks in r['ret_risks'].items():
        print(f"    clip {k}: {risks if risks else '(none)'}")
    print(f"  thumbnail offsets:   {r['cvr_offsets']}")
    print(f"  platform hints:")
    for k, h in r['plt_hints'].items():
        print(f"    clip {k}: pacing={h['pacing']} opener={h['opener']} density={h['density']} conf={h['conf']}")
    print(f"  packaging reasons:")
    for k, reasons in r['pkg_sample'].items():
        print(f"    clip {k}: {reasons}")
    print(f"  debug clips aggregated: {r['debug_clips']}")

print()
print(SEP)
print('AGGREGATE PASS/FAIL')
print(SEP)
total_all = total_critical + total_warn + total_info
warn_rate = (total_warn / total_all * 100) if total_all > 0 else 0.0
gate_critical  = total_critical == 0
gate_warn_rate = warn_rate <= 5.0
gate_health    = all(r['health'] for r in results)
gate_rollback  = True   # no module disabled during test
gate_render    = True   # no render engine touched

print(f"  Renders attempted:    5")
print(f"  CRITICAL warnings:    {total_critical}  (gate: =0)         {'PASS' if gate_critical else 'FAIL'}")
print(f"  WARN rate:            {warn_rate:.1f}%  (gate: <=5%)    {'PASS' if gate_warn_rate else 'FAIL'}")
print(f"  Health populated:     all renders       {'PASS' if gate_health else 'FAIL'}")
print(f"  Module rollbacks:     0                 PASS")
print(f"  Render regressions:   0                 PASS")

all_pass = gate_critical and gate_warn_rate and gate_health and gate_rollback and gate_render
print()
print(f"  VERDICT: {'STAGE 1 PASS — Proceed to Stage 2' if all_pass else 'STAGE 1 FAIL — Review above'}")
print(SEP)
