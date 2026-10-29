"""Sinh dữ liệu mẫu TỔNG HỢP cho README/thử tay: không dùng video hay logo của ai.

Ghi ra (cạnh file này):
- `video_mau.mp4`   : 6 giây, 540x960, 30 fps, nền màu chuyển động + chữ "OLD LOGO" trắng bán trong suốt trôi chậm + tiếng bíp.
- `boxes_mau.json`  : box mồi đúng vị trí logo cũ ở 5 khung (dùng cho `thay-logo chay --boxes`).
Và logo mẫu `src/thay_logo/tai_nguyen/logo_mau.png` (PNG có alpha) nếu gọi với `--logo`.

Chạy: python vi_du/tao_du_lieu_mau.py [--logo]
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from thay_logo.ffmpeg import tim_ffmpeg  # noqa: E402

THU_MUC = Path(__file__).resolve().parent
RONG, CAO, FPS, SO_KHUNG = 540, 960, 30, 180
FONT = cv2.FONT_HERSHEY_SIMPLEX
KHUNG_MOI = (15, 50, 90, 130, 165)


def _mat_na_chu(chu: str, scale: float, day: int) -> np.ndarray:
    (tw, th), base = cv2.getTextSize(chu, FONT, scale, day)
    m = np.zeros((th + base + 4, tw + 4), np.uint8)
    cv2.putText(m, chu, (2, th + 2), FONT, scale, 255, day, cv2.LINE_AA)
    return m.astype(np.float32) / 255.0


def _nen(rng: np.random.Generator, i: int) -> np.ndarray:
    yy, xx = np.mgrid[0:CAO, 0:RONG].astype(np.float32)
    song = np.sin((xx + 7 * i) / 41.0) * np.cos((yy - 5 * i) / 57.0)
    kenh = [70 + 50 * song + 0.05 * yy, 90 + 40 * np.cos((xx - 4 * i) / 63.0) + 0.03 * xx, 110 + 45 * song[::-1, :]]
    g = np.stack(kenh, axis=2) + rng.normal(0, 6, (CAO, RONG, 3))
    # vật thể động = vệt sáng mờ (không viền, không chữ) trôi qua — nội dung thật mà tool KHÔNG được đụng.
    # Cố ý không dùng hình đặc viền sắc: agy dễ gọi nhầm hình phẳng kiểu "icon" là logo.
    cx, cy = 270 + 150 * np.sin(i / 20), 300 + 80 * np.cos(i / 15)
    vet = np.exp(-((xx - cx) ** 2 + (yy - cy) ** 2) / (2 * 55.0 ** 2))[:, :, None]
    return g * (1 - 0.6 * vet) + np.array([60, 190, 240], np.float32) * 0.6 * vet


def tao_video() -> None:
    rng = np.random.default_rng(7)
    wm = _mat_na_chu("OLD LOGO", 1.1, 3)
    h, w = wm.shape
    hop: list[tuple[int, int, int, int]] = []
    with tempfile.TemporaryDirectory() as tam:
        cam = Path(tam) / "cam.mp4"
        out = cv2.VideoWriter(str(cam), cv2.VideoWriter_fourcc(*"mp4v"), FPS, (RONG, CAO))
        for i in range(SO_KHUNG):
            g = _nen(rng, i)
            x, y = 60 + i, 700 + i // 3  # logo cũ trôi chậm sang phải và xuống
            vung = g[y:y + h, x:x + w]
            a = wm[:, :, None] * 0.45
            vung[:] = (1 - a) * vung + a * 255.0
            hop.append((x, y, w, h))
            out.write(np.clip(g, 0, 255).astype(np.uint8))
        out.release()
        ffmpeg = tim_ffmpeg()
        if not ffmpeg:
            sys.exit("không tìm thấy ffmpeg")
        subprocess.run([ffmpeg, "-nostdin", "-y", "-loglevel", "error", "-i", str(cam), "-f", "lavfi", "-i",
                        f"sine=frequency=440:duration={SO_KHUNG / FPS}", "-c:v", "libx264", "-crf", "30", "-preset", "slow", "-pix_fmt", "yuv420p",
                        "-c:a", "aac", "-b:a", "48k", "-shortest", str(THU_MUC / "video_mau.mp4")], check=True)
    boxes = [{"khung": k, "x": hop[k][0], "y": hop[k][1], "w": hop[k][2], "h": hop[k][3]} for k in KHUNG_MOI]
    (THU_MUC / "boxes_mau.json").write_text(json.dumps(boxes, indent=2) + "\n", encoding="utf-8")
    print(f"đã ghi {THU_MUC / 'video_mau.mp4'} và {THU_MUC / 'boxes_mau.json'}")


def tao_logo() -> None:
    """Tấm nền xám bo góc bán trong suốt + chữ "NEW LOGO" trắng — cùng kiểu 'chữ trên tấm nền' để che vết tô lấp."""
    rong, cao, r = 600, 140, 40
    img = np.zeros((cao, rong, 4), np.uint8)
    nen = np.zeros((cao, rong), np.uint8)
    cv2.rectangle(nen, (r, 0), (rong - r, cao - 1), 255, -1)
    cv2.rectangle(nen, (0, r), (rong - 1, cao - r), 255, -1)
    for cx, cy in ((r, r), (rong - r - 1, r), (r, cao - r - 1), (rong - r - 1, cao - r - 1)):
        cv2.circle(nen, (cx, cy), r, 255, -1, cv2.LINE_AA)
    img[:, :, :3] = 110
    img[:, :, 3] = (nen.astype(np.float32) * 0.75).astype(np.uint8)
    chu = np.zeros((cao, rong), np.uint8)
    (tw, th), _ = cv2.getTextSize("NEW LOGO", FONT, 2.6, 8)
    cv2.putText(chu, "NEW LOGO", ((rong - tw) // 2, (cao + th) // 2), FONT, 2.6, 255, 8, cv2.LINE_AA)
    m = chu > 0
    img[m, :3] = 255
    img[:, :, 3] = np.maximum(img[:, :, 3], chu)
    dich = Path(__file__).resolve().parents[1] / "src" / "thay_logo" / "tai_nguyen" / "logo_mau.png"
    dich.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(dich), img)
    print(f"đã ghi {dich}")


if __name__ == "__main__":
    if "--logo" in sys.argv:
        tao_logo()
    tao_video()
