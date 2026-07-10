#!/usr/bin/env python3
"""
fetch_free_bgm.py — nạp thư viện nhạc nền FREE cho Story Mode.

Đọc ``bgm_manifest.json`` (mood → danh sách track có URL + license) và tải mỗi
track vào ``BGM_DIR/{mood}/`` — đúng cấu trúc mà ``core.config._pick_bgm_file`` và
Story v2 (``mixer.build_scene_bgm_track``) quét. Tổng hợp phần ghi công của các
track CC-BY vào ``BGM_DIR/ATTRIBUTION.txt``.

Thiết kế BEST-EFFORT: một URL hỏng/404 → bỏ qua + báo, không dừng. Idempotent:
track đã có thì bỏ qua (trừ khi --force). Chỉ dùng thư viện chuẩn (urllib) —
không thêm dependency.

BẢN QUYỀN:
  • CC0        → dùng tự do, KHÔNG cần ghi công.
  • CC-BY      → BẮT BUỘC ghi công tác giả. Script ghi sẵn ATTRIBUTION.txt; khi
                 đăng video nên đưa credit đó vào phần mô tả.
Seed hiện tại là nhạc Kevin MacLeod (incompetech.com, CC BY 3.0). URL chỉ là gợi ý
— tự sửa/mở rộng bgm_manifest.json rồi chạy lại.

Dùng:
  python scripts/fetch_free_bgm.py                # tải tất cả mood theo manifest
  python scripts/fetch_free_bgm.py --mood epic    # chỉ 1 mood
  python scripts/fetch_free_bgm.py --dry-run      # chỉ liệt kê, không tải
  python scripts/fetch_free_bgm.py --force        # tải lại cả track đã có
  python scripts/fetch_free_bgm.py --manifest /path/to/other.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from pathlib import Path

try:  # Windows console mặc định cp1252 — ép utf-8 để in được tiếng Việt/ký hiệu.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

_UA = "Mozilla/5.0 (StoryBGMFetcher; +offline-render-studio)"
_MIN_BYTES = 50 * 1024                 # <50KB → coi như lỗi/redirect HTML, bỏ
_AUDIO_EXTS = (".mp3", ".wav", ".m4a", ".ogg", ".flac")


def _bgm_dir(target: str = "bundled") -> Path:
    """Thư mục đích tải nhạc.

    target="bundled" (mặc định) → BUNDLED_BGM_DIR (assets/bgm trong REPO, được
    git-track → tải 1 lần, commit, khỏi tải lại). target="user" → BGM_DIR của
    người dùng (APP_DATA_DIR/bgm). Fallback tính tay nếu import config lỗi."""
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/
        from app.core.config import BGM_DIR, BUNDLED_BGM_DIR
        return Path(BUNDLED_BGM_DIR if target == "bundled" else BGM_DIR)
    except Exception:
        root = Path(__file__).resolve().parents[2]  # repo root
        return (root / "assets" / "bgm") if target == "bundled" else (root / "data" / "bgm")


def _safe_name(title: str, url: str) -> str:
    ext = next((e for e in _AUDIO_EXTS if url.lower().split("?")[0].endswith(e)), ".mp3")
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", (title or "track").strip()).strip("_") or "track"
    return f"{stem}{ext}"


def _download(url: str, dest: Path) -> "tuple[bool, str]":
    try:
        req = urllib.request.Request(url, headers={"User-Agent": _UA})
        with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310 (trusted manifest)
            data = resp.read()
        if len(data) < _MIN_BYTES:
            return False, f"quá nhỏ ({len(data)} bytes) — có thể redirect/HTML"
        dest.write_bytes(data)
        return True, f"{len(data) // 1024} KB"
    except Exception as exc:
        return False, str(exc)


def main() -> int:
    ap = argparse.ArgumentParser(description="Tải thư viện nhạc nền free cho Story Mode")
    ap.add_argument("--manifest", default=str(Path(__file__).with_name("bgm_manifest.json")))
    ap.add_argument("--mood", default="", help="chỉ tải 1 mood")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true", help="tải lại cả track đã tồn tại")
    ap.add_argument("--target", choices=["bundled", "user"], default="bundled",
                    help="bundled=assets/bgm trong repo (mặc định); user=APP_DATA_DIR/bgm")
    args = ap.parse_args()

    try:
        manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
        moods = manifest.get("moods") or {}
    except Exception as exc:
        print(f"[LỖI] không đọc được manifest: {exc}")
        return 2

    bgm_dir = _bgm_dir(args.target)
    print(f"Target ({args.target}) = {bgm_dir}")
    if args.mood:
        moods = {args.mood: moods.get(args.mood, [])}

    got = skipped = failed = 0
    attributions: list[str] = []

    for mood, tracks in moods.items():
        if not tracks:
            continue
        mood_dir = bgm_dir / mood
        for tr in tracks:
            url = (tr.get("url") or "").strip()
            title = (tr.get("title") or "track").strip()
            lic = (tr.get("license") or "").strip().upper()
            if not url:
                continue
            dest = mood_dir / _safe_name(title, url)
            label = f"[{mood}] {title} ({lic or '?'})"
            if lic.startswith("CC-BY"):
                attributions.append(
                    f"- \"{title}\" — {tr.get('author', 'Unknown')} — {lic} — {tr.get('source', url)}")
            if args.dry_run:
                print(f"  DRY  {label} -> {dest.name}")
                continue
            if dest.exists() and dest.stat().st_size >= _MIN_BYTES and not args.force:
                print(f"  SKIP {label} (đã có)")
                skipped += 1
                continue
            mood_dir.mkdir(parents=True, exist_ok=True)
            ok, info = _download(url, dest)
            if ok:
                print(f"  OK   {label} -> {dest.name} ({info})")
                got += 1
            else:
                print(f"  FAIL {label}: {info}")
                failed += 1

    # Ghi công CC-BY (append-safe: viết đè bản tổng hợp mới nhất).
    if attributions and not args.dry_run:
        try:
            bgm_dir.mkdir(parents=True, exist_ok=True)
            (bgm_dir / "ATTRIBUTION.txt").write_text(
                "Ghi công nhạc nền (CC-BY — bắt buộc credit khi đăng video)\n"
                "=========================================================\n\n"
                + "\n".join(sorted(set(attributions))) + "\n",
                encoding="utf-8")
            print(f"\nĐã ghi {bgm_dir / 'ATTRIBUTION.txt'}")
        except Exception as exc:
            print(f"[cảnh báo] không ghi được ATTRIBUTION.txt: {exc}")

    print(f"\nTổng: tải {got} · bỏ qua {skipped} · lỗi {failed}")
    if failed and not args.dry_run:
        print("Một số URL lỗi/404 — sửa link trong bgm_manifest.json rồi chạy lại, "
              "hoặc tự thả file .mp3 vào BGM_DIR/{mood}/.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
