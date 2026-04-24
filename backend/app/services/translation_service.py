import re
from pathlib import Path

_CHUNK_SIZE = 4500  # GoogleTranslator free limit ~5000 chars


def translate_text(text: str, source_language: str = "auto", target_language: str = "en") -> str:
    from deep_translator import GoogleTranslator
    text = str(text or "").strip()
    if not text:
        return text
    try:
        if len(text) <= _CHUNK_SIZE:
            result = GoogleTranslator(source=source_language, target=target_language).translate(text)
            return result or text
        chunks = _split_text_chunks(text, _CHUNK_SIZE)
        parts = []
        for chunk in chunks:
            t = GoogleTranslator(source=source_language, target=target_language).translate(chunk)
            parts.append(t or chunk)
        return " ".join(parts)
    except Exception as exc:
        raise RuntimeError(f"Translation failed ({source_language}→{target_language}): {exc}") from exc


def _split_text_chunks(text: str, max_size: int) -> list:
    words = text.split()
    chunks = []
    current: list = []
    current_len = 0
    for word in words:
        word_len = len(word)
        if current and current_len + 1 + word_len > max_size:
            chunks.append(" ".join(current))
            current = [word]
            current_len = word_len
        else:
            current.append(word)
            current_len += (1 if current_len else 0) + word_len
    if current:
        chunks.append(" ".join(current))
    return chunks


def translate_srt_file(
    input_srt_path,
    output_srt_path,
    target_language: str = "en",
) -> tuple:
    """Translate an SRT file in-place. Returns (output_path, failed_block_indices).

    failed_block_indices contains the 1-based SRT block numbers that fell back
    to original text due to a translation error. The caller should log these.
    """
    input_path = Path(input_srt_path)
    output_path = Path(output_srt_path)
    content = input_path.read_text(encoding="utf-8", errors="replace")
    blocks = re.split(r"\n{2,}", content.strip())
    translated_blocks = []
    failed_block_indices: list = []
    for block in blocks:
        lines = block.splitlines()
        if not lines:
            continue
        if len(lines) >= 2 and re.match(r"^\d+$", lines[0].strip()) and "-->" in lines[1]:
            index_line = lines[0]
            timestamp_line = lines[1]
            text = " ".join(l.strip() for l in lines[2:] if l.strip())
            if text:
                try:
                    text = translate_text(text, source_language="auto", target_language=target_language)
                except Exception:
                    # Keep original text; caller receives the block index so it can log.
                    try:
                        failed_block_indices.append(int(index_line.strip()))
                    except ValueError:
                        failed_block_indices.append(len(translated_blocks) + 1)
            translated_blocks.append(f"{index_line}\n{timestamp_line}\n{text}")
        else:
            translated_blocks.append(block)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n\n".join(translated_blocks) + "\n", encoding="utf-8")
    return output_path, failed_block_indices
