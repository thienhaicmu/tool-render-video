from typing import List, Dict


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _score_scene(scene: Dict, idx: int, total: int) -> float:
    duration = float(scene["end"]) - float(scene["start"])
    if duration <= 0:
        return 0.0

    # Scene quality heuristic:
    # - scenes too short/too long are usually weak for short-video rhythm
    # - early parts get slight hook bias
    duration_score = max(0.0, 100.0 - abs(duration - 4.5) * 12.0)
    transition_raw = float(scene.get("transition_score", 1.0))
    transition_score = _clamp(transition_raw * 60.0, 20.0, 100.0)
    early_bonus = 8.0 if float(scene["start"]) < 90.0 else (4.0 if float(scene["start"]) < 180.0 else 0.0)
    position_stability = 100.0 - (idx / max(total, 1)) * 15.0

    return (duration_score * 0.45) + (transition_score * 0.35) + (position_stability * 0.20) + early_bonus


def _normalize_scenes(scenes: List[Dict], total_duration: float) -> List[Dict]:
    normalized = []
    for i, s in enumerate(sorted(scenes or [], key=lambda x: float(x.get("start", 0.0)))):
        st = max(0.0, float(s.get("start", 0.0)))
        ed = min(total_duration, float(s.get("end", st)))
        if ed <= st:
            continue
        normalized.append({"start": st, "end": ed, "transition_score": float(s.get("transition_score", 1.0)), "_idx": i})
    if not normalized:
        normalized = [{"start": 0.0, "end": total_duration, "transition_score": 0.0, "_idx": 0}]
    return normalized


def build_segments_from_scenes(scenes: List[Dict], total_duration: int, min_part_sec: int = 70, max_part_sec: int = 180):
    total = max(float(total_duration or 0), 0.0)
    if total <= 0:
        return []

    if min_part_sec > max_part_sec:
        min_part_sec, max_part_sec = max_part_sec, min_part_sec

    min_len = max(25.0, float(min_part_sec))
    max_len = max(min_len, float(max_part_sec))
    scenes_norm = _normalize_scenes(scenes, total)
    scored_scenes = []
    for i, s in enumerate(scenes_norm):
        q = _score_scene(s, i, len(scenes_norm))
        scored_scenes.append({**s, "scene_quality": q})

    qualities = sorted([s["scene_quality"] for s in scored_scenes])
    q50 = qualities[len(qualities) // 2]
    low_threshold = max(35.0, q50 * 0.55)

    kept = [s for s in scored_scenes if s["scene_quality"] >= low_threshold]
    if len(kept) < max(3, len(scored_scenes) // 3):
        keep_n = max(3, int(len(scored_scenes) * 0.6))
        kept = sorted(scored_scenes, key=lambda x: x["scene_quality"], reverse=True)[:keep_n]
        kept = sorted(kept, key=lambda x: x["start"])

    durations = [max(0.5, (s["end"] - s["start"])) for s in kept]
    avg_scene_dur = sum(durations) / max(len(durations), 1)
    target_scene_count = int(_clamp(min_len / max(avg_scene_dur, 0.5), 8.0, 24.0))
    target_len = min(max_len, max(min_len, avg_scene_dur * target_scene_count))

    segments: List[Dict] = []
    i = 0
    while i < len(kept):
        start_scene = kept[i]
        part_start = float(start_scene["start"])
        part_end = float(start_scene["end"])
        part_scenes = [start_scene]
        quality_sum = float(start_scene["scene_quality"])
        i += 1

        while i < len(kept):
            nxt = kept[i]
            nxt_end = float(nxt["end"])
            candidate_duration = nxt_end - part_start
            gap = float(nxt["start"]) - part_end

            # Keep transition continuity; if a big skipped gap appears, start new part.
            if gap > 8.0 and (part_end - part_start) >= (min_len * 0.7):
                break
            if candidate_duration > max_len:
                break

            part_scenes.append(nxt)
            part_end = nxt_end
            quality_sum += float(nxt["scene_quality"])
            i += 1

            current_duration = part_end - part_start
            if current_duration < min_len:
                continue

            avg_q = quality_sum / max(len(part_scenes), 1)
            next_q = float(kept[i]["scene_quality"]) if i < len(kept) else 0.0
            should_stop = (
                current_duration >= target_len
                or len(part_scenes) >= target_scene_count
                or (next_q < (avg_q * 0.72) and current_duration >= (min_len * 0.9))
            )
            if should_stop:
                break

        duration = part_end - part_start
        if duration < (min_len * 0.75) and segments:
            prev = segments[-1]
            merged_dur = float(part_end) - float(prev["start"])
            if merged_dur <= (max_len * 1.15):
                prev["end"] = round(part_end, 3)
                prev["duration_hint"] = round(merged_dur, 3)
                prev["scene_count"] = int(prev.get("scene_count", 0)) + len(part_scenes)
                prev["scene_quality_avg"] = round((float(prev.get("scene_quality_avg", 0.0)) + (quality_sum / max(len(part_scenes), 1))) / 2.0, 3)
                continue

        if part_end > part_start:
            segments.append({
                "start": round(part_start, 3),
                "end": round(part_end, 3),
                "duration_hint": round(part_end - part_start, 3),
                "scene_count": len(part_scenes),
                "scene_quality_avg": round(quality_sum / max(len(part_scenes), 1), 3),
            })

    cleaned = [seg for seg in segments if seg["end"] > seg["start"]]
    if not cleaned:
        cleaned = [{"start": 0.0, "end": round(total, 3), "duration_hint": round(total, 3), "scene_count": 1, "scene_quality_avg": 50.0}]
    return cleaned
