"""Tìm ffmpeg: biến môi trường THAY_LOGO_FFMPEG (đường dẫn file) trước, rồi PATH, rồi vài chỗ cài phổ biến."""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

_CHO_PHO_BIEN = ("/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg", "/usr/bin/ffmpeg", "C:/ffmpeg/bin/ffmpeg.exe")


def tim_ffmpeg() -> str | None:
    tu_env = os.environ.get("THAY_LOGO_FFMPEG")
    if tu_env and Path(tu_env).is_file():
        return tu_env
    tren_path = shutil.which("ffmpeg")
    if tren_path:
        return tren_path
    return next((p for p in _CHO_PHO_BIEN if Path(p).is_file()), None)


def loi_ffmpeg(ffmpeg: str | None) -> str | None:
    """None nếu ffmpeg dùng được (chạy được + có bộ mã hoá libx264); không thì câu báo lỗi kèm lệnh cài."""
    cai = "cài bằng: brew install ffmpeg (hoặc đặt THAY_LOGO_FFMPEG=/duong/dan/ffmpeg)"
    if not ffmpeg:
        return f"không tìm thấy ffmpeg — {cai}"
    try:
        out = subprocess.run([ffmpeg, "-hide_banner", "-encoders"], capture_output=True, text=True, timeout=30).stdout
    except (OSError, subprocess.TimeoutExpired) as e:
        return f"không chạy được {ffmpeg} ({type(e).__name__}) — {cai}"
    if "libx264" not in out:
        return f"ffmpeg ở {ffmpeg} thiếu bộ mã hoá libx264 — {cai}"
    return None
