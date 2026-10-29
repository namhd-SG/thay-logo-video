"""Lệnh `thay-logo`.

- `web`       : ĐƯỜNG CHÍNH — mở trang web trên máy (http://127.0.0.1:8790): đưa video vào → agy tự tìm logo cũ (hoặc khoanh tay)
                → chạy → duyệt trước/sau → tải về.
- `chay`      : dòng lệnh, 1 video vào ⇒ 1 video đã thay logo ra (+ thư mục báo cáo). Box mồi từ --box/--boxes hoặc --tu-tim (agy).
- `chon-box`  : mở cửa sổ, kéo khung quanh logo cũ trên vài khung hình ⇒ ghi file box JSON.
- `xuat-khung`: xuất ảnh vài khung (kèm số khung) để tự đo toạ độ khi máy không mở được cửa sổ.

Mã thoát của `chay`: 0 = đã thay và ghi file ra · 2 = KHÔNG thay (chưa đủ chắc, giữ nguyên gốc, xem `ly_do`) · 1 = lỗi.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from .box_moi import BoxMoi
from .ffmpeg import loi_ffmpeg, tim_ffmpeg

MA_DA_THAY, MA_LOI, MA_KHONG_THAY = 0, 1, 2
_MAU_BOX = re.compile(r"^\s*(\d+)\s*:\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*$")


def doc_box_chuoi(s: str) -> BoxMoi:
    """`KHUNG:X,Y,W,H` (điểm ảnh, gốc toạ độ góc trên-trái) ⇒ BoxMoi nguồn "tay"."""
    m = _MAU_BOX.match(s)
    if not m:
        raise argparse.ArgumentTypeError(f"box sai khuôn '{s}' — đúng khuôn là KHUNG:X,Y,W,H, ví dụ 30:40,420,120,36")
    k, x, y, w, h = (int(v) for v in m.groups())
    if w < 4 or h < 4:
        raise argparse.ArgumentTypeError(f"box '{s}' quá nhỏ (rộng/cao phải ≥ 4 px)")
    return BoxMoi(k, x, y, w, h, nguon="tay")


def doc_box_json(duong_dan: Path) -> list[BoxMoi]:
    """File JSON: danh sách {"khung", "x", "y", "w", "h"} (+ "cum" tuỳ chọn: cùng số = cùng một logo cũ)."""
    du_lieu = json.loads(Path(duong_dan).read_text(encoding="utf-8"))
    if not isinstance(du_lieu, list):
        raise ValueError(f"{duong_dan}: phải là danh sách box JSON")
    boxes = []
    for i, b in enumerate(du_lieu):
        try:
            boxes.append(BoxMoi(int(b["khung"]), int(b["x"]), int(b["y"]), int(b["w"]), int(b["h"]),
                                nguon=str(b.get("nguon", "tay")), cum=None if b.get("cum") is None else int(b["cum"])))
        except (KeyError, TypeError, ValueError) as e:
            raise ValueError(f"{duong_dan}: box thứ {i} sai khuôn ({e}); cần khung, x, y, w, h") from e
    return boxes


def _kiem_box_trong_video(boxes: list[BoxMoi], rong: int, cao: int, so_khung: int) -> None:
    for b in boxes:
        if not 0 <= b.khung < so_khung:
            raise ValueError(f"box ở khung {b.khung} nằm ngoài video (video có {so_khung} khung: 0…{so_khung - 1})")
        if b.x < 0 or b.y < 0 or b.x + b.w > rong or b.y + b.h > cao:
            raise ValueError(f"box khung {b.khung} ({b.x},{b.y},{b.w},{b.h}) tràn khỏi khung hình {rong}x{cao}")


def _chon_khung(so_khung: int, fps: float, giay: list[float] | None, so_mau: int) -> list[int]:
    if giay:
        return sorted({min(so_khung - 1, max(0, round(g * fps))) for g in giay})
    so_mau = max(1, min(so_mau, so_khung))
    return sorted({round((i + 0.5) * so_khung / so_mau) for i in range(so_mau)})


def lenh_chay(a: argparse.Namespace) -> int:
    from . import nhat_ky
    from .nguon_khung import NguonKhungVideo
    from .xu_ly_video import xu_ly

    video, dau_ra = Path(a.video).resolve(), Path(a.out).resolve()
    if not video.is_file():
        print(f"LỖI: không thấy video {video}", file=sys.stderr)
        return MA_LOI
    if dau_ra == video:
        print("LỖI: --out trùng video gốc; tool không bao giờ ghi đè gốc, hãy chọn tên khác", file=sys.stderr)
        return MA_LOI
    ffmpeg = a.ffmpeg or tim_ffmpeg()
    loi = loi_ffmpeg(ffmpeg)
    if loi:
        print(f"LỖI: {loi}", file=sys.stderr)
        return MA_LOI
    try:
        boxes = list(a.box or []) + (doc_box_json(Path(a.boxes)) if a.boxes else [])
        nguon = NguonKhungVideo(str(video))
        if not boxes and a.tu_tim:
            from .agy_dinh_vi import LoiAgy, model_agy, tim_box
            print(f"Đang nhờ agy tìm logo cũ (model {model_agy(a.agy_model)})…", file=sys.stderr)
            try:
                boxes, _ = tim_box(nguon, lenh=a.agy, model=a.agy_model)
            except LoiAgy as e:
                print(f"LỖI: {e.ly_do}", file=sys.stderr)
                return MA_LOI
            print(f"  agy thấy {len(boxes)} box mồi", file=sys.stderr)
        if not boxes:
            print("LỖI: cần box mồi: --box / --boxes (tạo bằng `thay-logo chon-box`), hoặc --tu-tim để agy tự tìm.", file=sys.stderr)
            return MA_LOI
        _kiem_box_trong_video(boxes, nguon.rong, nguon.cao, nguon.so_khung())
    except (ValueError, OSError) as e:
        print(f"LỖI: {e}", file=sys.stderr)
        return MA_LOI
    bao_cao = Path(a.bao_cao).resolve() if a.bao_cao else dau_ra.with_name(dau_ra.stem + "_bao_cao")
    bao_cao.mkdir(parents=True, exist_ok=True)
    dau_ra.parent.mkdir(parents=True, exist_ok=True)
    print(f"Đang xử lý {video.name}: {nguon.rong}x{nguon.cao}, {nguon.so_khung()} khung, {len(boxes)} box mồi…", file=sys.stderr)
    conn = nhat_ky.mo(bao_cao / "nhat_ky.db")
    try:
        kq = xu_ly(str(video), boxes, str(dau_ra), conn, bao_cao, nguon_video=str(video), ffmpeg=ffmpeg,
                   logo=a.logo, luong=a.luong, crf=a.crf)
        hang = dict(conn.execute("SELECT * FROM tl_video WHERE id=?", (kq["video_log_id"],)).fetchone())
    except Exception as e:  # noqa: BLE001 — lỗi đã ghi vào nhật ký; ở đây báo cho người dùng
        print(f"LỖI: {type(e).__name__}: {e}", file=sys.stderr)
        return MA_LOI
    finally:
        conn.close()
    ket_qua = {"trang_thai": kq["trang_thai"], "dau_ra": kq["dau_ra"], "ly_do": kq["ly_do"] or None,
               "thu_muc_bao_cao": str(bao_cao), "anh_truoc": hang.get("duong_dan_truoc"), "anh_sau": hang.get("duong_dan_sau"),
               "anh_soi": hang.get("duong_dan_sheet"), "track": hang.get("duong_dan_track"),
               "giay_xu_ly": hang.get("giay_xu_ly"), "vet_bi_bo": kq["vet_bi_bo"]}
    (bao_cao / "ket_qua.json").write_text(json.dumps(ket_qua, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(ket_qua, ensure_ascii=False, indent=2))
    if kq["trang_thai"] == "render":
        print(f"XONG: đã ghi {dau_ra}", file=sys.stderr)
        return MA_DA_THAY
    print("KHÔNG THAY: tool chưa đủ chắc nên giữ nguyên video gốc (không ghi file ra). Lý do ở trường `ly_do`; "
          "thử thêm box mồi ở các khung khác (xem README › Lỗi thường gặp).", file=sys.stderr)
    return MA_KHONG_THAY


def lenh_chon_box(a: argparse.Namespace) -> int:
    import cv2

    from .nguon_khung import NguonKhungVideo
    nguon = NguonKhungVideo(a.video)
    cap = cv2.VideoCapture(a.video)
    ds_khung = _chon_khung(nguon.so_khung(), nguon.fps or 30.0, a.giay, a.so_khung)
    boxes: list[dict] = []
    try:
        for k in ds_khung:
            cap.set(cv2.CAP_PROP_POS_FRAMES, k)
            ok, f = cap.read()
            if not ok:
                continue
            ten = f"Khung {k} - keo khung quanh logo cu, Enter = luu, c = bo qua khung nay"
            try:
                x, y, w, h = (int(v) for v in cv2.selectROI(ten, f, showCrosshair=True, fromCenter=False))
            except cv2.error as e:
                print("LỖI: OpenCV trên máy này không mở được cửa sổ (bản 'headless'?). Cài `opencv-python` (xem README) hoặc dùng "
                      f"`thay-logo xuat-khung` để tự đo toạ độ. Chi tiết: {e}", file=sys.stderr)
                return MA_LOI
            cv2.destroyWindow(ten)
            if w >= 4 and h >= 4:
                boxes.append({"khung": k, "x": x, "y": y, "w": w, "h": h})
                print(f"  khung {k}: {x},{y},{w},{h}", file=sys.stderr)
    finally:
        cap.release()
        cv2.destroyAllWindows()
    if not boxes:
        print("Không có box nào được chọn — file box KHÔNG được ghi.", file=sys.stderr)
        return MA_LOI
    Path(a.out).write_text(json.dumps(boxes, indent=2), encoding="utf-8")
    print(f"Đã ghi {len(boxes)} box vào {a.out}", file=sys.stderr)
    return 0


def lenh_xuat_khung(a: argparse.Namespace) -> int:
    import cv2

    from .nguon_khung import NguonKhungVideo
    nguon = NguonKhungVideo(a.video)
    ds_khung = _chon_khung(nguon.so_khung(), nguon.fps or 30.0, a.giay, a.so_khung)
    d = Path(a.thu_muc)
    d.mkdir(parents=True, exist_ok=True)
    cap = cv2.VideoCapture(a.video)
    try:
        for k in ds_khung:
            cap.set(cv2.CAP_PROP_POS_FRAMES, k)
            ok, f = cap.read()
            if ok:
                p = d / f"khung_{k:06d}.png"
                cv2.imwrite(str(p), f)
                print(f"  {p}  (khung {k}, {f.shape[1]}x{f.shape[0]})", file=sys.stderr)
    finally:
        cap.release()
    print(f"Video: {nguon.rong}x{nguon.cao}, {nguon.fps:.3f} fps, {nguon.so_khung()} khung. Số khung nằm trong tên file.", file=sys.stderr)
    return 0


def lenh_web(a: argparse.Namespace) -> int:
    from .agy_dinh_vi import model_agy, tim_lenh_agy
    from .web_app import chay_may_chu

    ffmpeg = a.ffmpeg or tim_ffmpeg()
    loi = loi_ffmpeg(ffmpeg)
    if loi:
        print(f"LỖI: {loi}", file=sys.stderr)
        return MA_LOI
    agy = None if a.khong_agy else tim_lenh_agy(a.agy)
    if not a.khong_agy and agy is None:
        print("Lưu ý: không tìm thấy agy ⇒ tắt tự tìm, video mới sẽ chờ bạn khoanh tay (xem README › Cài agy).", file=sys.stderr)
    chay_may_chu(Path(a.data), ffmpeg, a.cong, not a.khong_mo, agy_lenh=agy, agy_model=model_agy(a.agy_model))
    return 0


def _them_tham_so_agy(p: argparse.ArgumentParser) -> None:
    p.add_argument("--agy", metavar="LENH", help="đường dẫn lệnh agy (mặc định: tự tìm, hoặc biến THAY_LOGO_AGY)")
    p.add_argument("--agy-model", metavar="MODEL", help="model agy (mặc định gemini-3.8-flash-low, hoặc THAY_LOGO_AGY_MODEL)")


def tao_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="thay-logo", description="Thay logo/watermark trong video bằng logo của bạn.")
    sub = ap.add_subparsers(dest="lenh", required=True)

    w = sub.add_parser("web", help="mở trang web trên máy (đường chính)")
    w.add_argument("--cong", type=int, default=8790, help="cổng (mặc định 8790)")
    w.add_argument("--data", default="data", help="thư mục chứa video + kết quả (mặc định ./data)")
    w.add_argument("--khong-mo", action="store_true", help="không tự mở trình duyệt")
    w.add_argument("--khong-agy", action="store_true", help="tắt tự tìm bằng agy — mọi video chờ khoanh tay")
    w.add_argument("--ffmpeg", help="đường dẫn ffmpeg (mặc định: tự tìm, hoặc biến THAY_LOGO_FFMPEG)")
    _them_tham_so_agy(w)
    w.set_defaults(ham=lenh_web)

    c = sub.add_parser("chay", help="1 video vào ⇒ 1 video đã thay logo ra")
    c.add_argument("video", help="video gốc (mp4/mov…); không bị sửa")
    c.add_argument("--out", required=True, help="đường dẫn video ra (mp4)")
    c.add_argument("--box", action="append", type=doc_box_chuoi, metavar="KHUNG:X,Y,W,H",
                   help="box mồi quanh logo cũ ở một khung; lặp lại nhiều lần (nên 3–6 box ở các khung khác nhau)")
    c.add_argument("--boxes", metavar="FILE.json", help="file box mồi (do `chon-box` ghi ra)")
    c.add_argument("--tu-tim", action="store_true", help="không có box ⇒ nhờ agy tự tìm logo cũ")
    _them_tham_so_agy(c)
    c.add_argument("--logo", metavar="FILE.png", help="logo mới, PNG có nền trong suốt (mặc định: logo mẫu đi kèm)")
    c.add_argument("--bao-cao", metavar="THU_MUC", help="thư mục báo cáo (mặc định: <tên video ra>_bao_cao cạnh video ra)")
    c.add_argument("--crf", type=int, default=18, help="chất lượng H.264, 0–51, thấp = nét + nặng hơn (mặc định 18)")
    c.add_argument("--luong", type=int, default=2, help="số luồng CPU (mặc định 2)")
    c.add_argument("--ffmpeg", help="đường dẫn ffmpeg (mặc định: tự tìm, hoặc biến THAY_LOGO_FFMPEG)")
    c.set_defaults(ham=lenh_chay)

    for ten, ham, giup in (("chon-box", lenh_chon_box, "mở cửa sổ để kéo khung quanh logo cũ ⇒ file box JSON"),
                           ("xuat-khung", lenh_xuat_khung, "xuất ảnh vài khung để tự đo toạ độ box")):
        p = sub.add_parser(ten, help=giup)
        p.add_argument("video")
        p.add_argument("--giay", type=float, nargs="+", metavar="GIAY", help="lấy khung ở các giây này (vd: --giay 1 3.5 7)")
        p.add_argument("--so-khung", type=int, default=5, help="nếu không có --giay: lấy chừng này khung rải đều (mặc định 5)")
        if ten == "chon-box":
            p.add_argument("--out", default="boxes.json", help="file box ghi ra (mặc định boxes.json)")
        else:
            p.add_argument("--thu-muc", default="khung_xuat", help="thư mục ghi ảnh (mặc định khung_xuat)")
        p.set_defaults(ham=ham)
    return ap


def main(argv: list[str] | None = None) -> int:
    a = tao_parser().parse_args(argv)
    return a.ham(a)


if __name__ == "__main__":
    sys.exit(main())
