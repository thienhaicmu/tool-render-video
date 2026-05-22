_WIDE_CHARS = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789@#$%&Wm")
_NARROW_CHARS = frozenset("fijlrt!|,.'\":;-")


def _approx_visual_width(text: str) -> float:
    """Estimate rendered character-width in em units for line-break decisions.

    Uppercase and wide glyphs are counted as 1.3, narrow glyphs as 0.6, rest 1.0.
    This avoids purely word-count-based breaks that under-count wide uppercase text.
    """
    total = 0.0
    for ch in text:
        if ch in _WIDE_CHARS:
            total += 1.3
        elif ch in _NARROW_CHARS:
            total += 0.6
        elif ch == " ":
            total += 0.45
        else:
            total += 1.0
    return total


def _break_by_visual_width(text: str, max_em: float = 18.0, max_lines: int = 2) -> str:
    """Insert newlines to keep subtitle lines within max_em visual width.

    When max_lines=2 (default), splits at the visual midpoint to produce
    balanced two-line captions instead of greedy word-count wrapping.
    Returns text unchanged when it already fits or already has a newline.
    """
    if "\n" in text:
        # Already line-broken: enforce max_lines cap only
        parts = text.split("\n")
        if len(parts) <= max_lines:
            return text
        return "\n".join(parts[:max_lines])

    total_w = _approx_visual_width(text)
    if total_w <= max_em:
        return text

    words = text.split()
    if len(words) <= 1:
        return text

    if max_lines == 2:
        # Find split point closest to visual midpoint
        half = total_w / 2.0
        cum = 0.0
        best_idx = 1
        best_dist = float("inf")
        for i, word in enumerate(words):
            cum += _approx_visual_width(word + " ")
            dist = abs(cum - half)
            if dist < best_dist:
                best_dist = dist
                best_idx = i + 1
        return " ".join(words[:best_idx]) + "\n" + " ".join(words[best_idx:])

    # General greedy wrap for max_lines > 2
    lines: list[str] = []
    current: list[str] = []
    current_w = 0.0
    for word in words:
        ww = _approx_visual_width(word + " ")
        if current and current_w + ww > max_em and len(lines) < max_lines - 1:
            lines.append(" ".join(current))
            current = [word]
            current_w = ww
        else:
            current.append(word)
            current_w += ww
    if current:
        lines.append(" ".join(current))
    return "\n".join(lines)
