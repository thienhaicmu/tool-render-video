"""A/B tốc độ + chất lượng cho pass micro-pacing GPU (MICRO_PACING_GPU=1).

Chạy trên MÁY CÓ NVENC để quyết định có bật MICRO_PACING_GPU mặc định
hay không. Trên máy không có NVENC, script tự phát hiện và dừng với
hướng dẫn (arm GPU không có ý nghĩa khi resolver rơi về libx264).

Cách chạy (trong venv backend, từ thư mục backend):

    python scripts/ab_micro_pacing.py                    # tự sinh clip test có khoảng lặng
    python scripts/ab_micro_pacing.py --input clip.mp4   # dùng clip thật (nên chọn clip nhiều khoảng lặng)

Script làm gì:
  1. Arm CPU:  MICRO_PACING_GPU=0 -> apply_micro_pacing -> đo thời gian.
  2. Arm GPU:  MICRO_PACING_GPU=1 -> apply_micro_pacing -> đo thời gian.
  3. So sánh: cùng số segment trim / tổng trim (bắt buộc khớp — cùng
     detection trên cùng input), duration output, SSIM + PSNR giữa 2
     output (2 file frame-aligned vì cùng filter graph keeps).
  4. In verdict gợi ý: SSIM All >= 0.98 thường là không phân biệt được
     bằng mắt; kiểm tra mắt 2 file output trước khi flip default.

Giữ nguyên tinh thần Contract #3: script chẩn đoán, không đụng pipeline.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import time
from pathlib import Path

# Console Windows mặc định cp1252 không in được tiếng Việt.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# Cho phép chạy `python scripts/ab_micro_pacing.py` từ thư mục backend.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.bin_paths import get_ffmpeg_bin  # noqa: E402
from app.features.render.engine.encoder.clip_ops import (  # noqa: E402
    _pacing_encode_flags,
    apply_micro_pacing,
)
from app.features.render.engine.encoder.ffmpeg_helpers import _probe_duration  # noqa: E402


def _synthesize_test_clip(out_path: Path, ffmpeg: str) -> None:
    """Sinh clip 25s: 3 đoạn pink-noise (giả giọng nói) xen 2 khoảng lặng 2s.

    Khoảng lặng 2s > ngưỡng dead-air 1.5s -> mỗi khoảng bị trim còn ~0.5s,
    tổng trim ~2s-3s > MICRO_PACING_MIN_TRIM_MS (500ms) -> nhánh re-encode
    chắc chắn kích hoạt ở cả 2 arm.
    """
    fc = (
        "anoisesrc=d=8:c=pink:a=0.5:r=44100[a1];"
        "anullsrc=d=2:r=44100:cl=mono[s1];"
        "anoisesrc=d=6:c=pink:a=0.5:r=44100[a2];"
        "anullsrc=d=2:r=44100:cl=mono[s2];"
        "anoisesrc=d=7:c=pink:a=0.5:r=44100[a3];"
        "[a1][s1][a2][s2][a3]concat=n=5:v=0:a=1[aout]"
    )
    cmd = [
        ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", "testsrc2=size=720x1280:rate=30:duration=25",
        "-filter_complex", fc,
        "-map", "0:v", "-map", "[aout]",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-c:a", "aac", "-b:a", "128k",
        "-pix_fmt", "yuv420p",
        str(out_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=300)


def _run_arm(label: str, gpu: str, input_path: Path, output_path: Path,
             content_type: str) -> tuple[dict, float, bool]:
    os.environ["MICRO_PACING_GPU"] = gpu
    flags, used_gpu = _pacing_encode_flags("h264", "auto")
    print(f"[{label}] encoder flags: {' '.join(flags)}  (used_gpu={used_gpu})")
    t0 = time.perf_counter()
    result = apply_micro_pacing(
        str(input_path), str(output_path),
        content_type=content_type,
        video_codec="h264", encoder_mode="auto",
    )
    elapsed = time.perf_counter() - t0
    print(f"[{label}] applied={result['applied']} segments={result['segments_trimmed']} "
          f"trim={result['total_trim_ms']}ms elapsed={elapsed:.1f}s")
    return result, elapsed, used_gpu


def _quality_metric(ffmpeg: str, a: Path, b: Path, lavfi: str, pattern: str) -> str:
    cmd = [ffmpeg, "-hide_banner", "-i", str(a), "-i", str(b),
           "-lavfi", lavfi, "-f", "null", "-"]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    for line in (proc.stderr or "").splitlines():
        m = re.search(pattern, line)
        if m:
            return m.group(0)
    return "(không parse được)"


def main() -> int:
    ap = argparse.ArgumentParser(description="A/B micro-pacing GPU vs CPU")
    ap.add_argument("--input", help="clip nguồn (mặc định: tự sinh clip test có khoảng lặng)")
    ap.add_argument("--content-type", default="vlog")
    ap.add_argument("--out-dir", default="output/ab_micro_pacing")
    args = ap.parse_args()

    ffmpeg = get_ffmpeg_bin()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.input:
        src = Path(args.input)
        if not src.exists():
            print(f"LỖI: không thấy input {src}")
            return 1
    else:
        src = out_dir / "ab_source.mp4"
        print(f"Sinh clip test có khoảng lặng: {src}")
        _synthesize_test_clip(src, ffmpeg)

    # Tiền kiểm: máy này có resolve ra NVENC không?
    os.environ["MICRO_PACING_GPU"] = "1"
    _, probe_gpu = _pacing_encode_flags("h264", "auto")
    if not probe_gpu:
        print()
        print("=" * 70)
        print("MÁY NÀY KHÔNG RESOLVE RA NVENC — arm GPU sẽ giống hệt arm CPU.")
        print("Chạy script này trên máy render có GPU NVIDIA + driver.")
        print("Vẫn chạy arm CPU để xác nhận nhánh re-encode hoạt động…")
        print("=" * 70)

    out_cpu = out_dir / "paced_cpu.mp4"
    out_gpu = out_dir / "paced_gpu.mp4"

    res_cpu, t_cpu, _ = _run_arm("CPU ", "0", src, out_cpu, args.content_type)
    if not res_cpu["applied"]:
        print("Arm CPU: applied=False — clip không đủ khoảng lặng để pacing. "
              "Chọn --input khác (nhiều khoảng lặng hơn) rồi chạy lại.")
        return 2

    if not probe_gpu:
        print(f"\nArm CPU OK: {out_cpu} ({t_cpu:.1f}s). Dừng — không có NVENC cho arm GPU.")
        return 2

    res_gpu, t_gpu, used_gpu = _run_arm("GPU ", "1", src, out_gpu, args.content_type)

    print()
    print("=" * 70)
    print("KẾT QUẢ A/B")
    print("=" * 70)
    same_trim = (res_cpu["segments_trimmed"] == res_gpu["segments_trimmed"]
                 and res_cpu["total_trim_ms"] == res_gpu["total_trim_ms"])
    print(f"Trim khớp 2 arm : {same_trim} "
          f"(cpu={res_cpu['total_trim_ms']}ms / gpu={res_gpu['total_trim_ms']}ms)")
    d_cpu, d_gpu = _probe_duration(str(out_cpu)), _probe_duration(str(out_gpu))
    print(f"Duration        : cpu={d_cpu}s gpu={d_gpu}s")
    print(f"Thời gian encode: cpu={t_cpu:.1f}s gpu={t_gpu:.1f}s "
          f"(nhanh hơn {t_cpu / max(t_gpu, 0.001):.1f}x)")
    sz_cpu, sz_gpu = out_cpu.stat().st_size, out_gpu.stat().st_size
    print(f"Kích thước      : cpu={sz_cpu:,}B gpu={sz_gpu:,}B")
    print("SSIM (gpu vs cpu):",
          _quality_metric(ffmpeg, out_gpu, out_cpu, "ssim", r"All:\s*[\d.]+.*"))
    print("PSNR (gpu vs cpu):",
          _quality_metric(ffmpeg, out_gpu, out_cpu, "psnr", r"average:\s*[\d.]+.*"))
    print()
    print("Gợi ý verdict: SSIM All >= 0.98 thường không phân biệt được bằng mắt.")
    print(f"KIỂM TRA MẮT 2 file trước khi flip default:\n  {out_cpu}\n  {out_gpu}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
