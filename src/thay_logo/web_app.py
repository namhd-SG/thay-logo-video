"""Trang web chạy trên máy (127.0.0.1): đưa video vào → khoanh logo cũ → chạy nền → duyệt trước/sau → tải về.

Không đăng nhập, không mạng ngoài (trừ khi người dùng dán link Drive công khai). Mọi dữ liệu nằm trong thư mục `data`.
"""
from __future__ import annotations

import json
import logging
import re
import shutil
import threading
from contextlib import asynccontextmanager
from pathlib import Path

import cv2
from fastapi import FastAPI, File, HTTPException, Response, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import render
from .web_hang_doi import HangDoi, Worker

log = logging.getLogger("thay_logo.web")
TINH = Path(__file__).resolve().parent / "web_tinh"
DUOI_VIDEO = {".mp4", ".mov", ".m4v", ".mkv", ".webm", ".avi"}
TRAN_LOGO_BYTE = 10 * 1024 * 1024
TRANG_THAI_SUA_DUOC = {"cho_khoanh", "xong", "khong_chac", "loi"}  # được khoanh lại / chạy lại


class Box(BaseModel):
    khung: int
    x: int
    y: int
    w: int
    h: int
    cum: int | None = None
    nguon: str = "tay"  # "agy" | "tay" — chỉ để hiển thị; lõi không phân biệt


class DsBox(BaseModel):
    boxes: list[Box]


class DanhGia(BaseModel):
    gia_tri: str  # "dat" | "hong" | ""


class LinkDrive(BaseModel):
    link: str


def _ten_an_toan(ten: str) -> str:
    goc = Path(ten or "video").name
    return re.sub(r"[^\w.\- ]+", "_", goc).strip() or "video"


def do_video(p: Path) -> dict:
    """Mở được bằng OpenCV + có ≥1 khung ⇒ thông số; không thì ValueError (thông điệp cho người dùng)."""
    cap = cv2.VideoCapture(str(p))
    try:
        if not cap.isOpened():
            raise ValueError("không mở được file này như một video")
        rong, cao = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = float(cap.get(cv2.CAP_PROP_FPS) or 30.0)
        n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        ok, _ = cap.read()
    finally:
        cap.release()
    if not ok or rong <= 0 or cao <= 0 or n <= 0:
        raise ValueError("video không đọc được khung hình nào")
    return {"rong": rong, "cao": cao, "fps": round(fps, 3), "so_khung": n}


def tao_app(data_dir: Path, ffmpeg: str, *, chay_worker: bool = True, agy_lenh: str | None = None,
            agy_model: str | None = None) -> FastAPI:
    """`agy_lenh` None ⇒ không tự tìm: video mới vào thẳng `cho_khoanh` (người khoanh tay)."""
    hd = HangDoi(data_dir)
    worker = Worker(hd, ffmpeg=ffmpeg, agy_lenh=agy_lenh, agy_model=agy_model)
    trang_thai_moi = "cho_tim" if agy_lenh else "cho_khoanh"

    @asynccontextmanager
    async def vong_doi(_app):
        if chay_worker:
            worker.start()
        yield
        worker.stop()

    app = FastAPI(title="Thay logo", lifespan=vong_doi)
    app.state.hang_doi = hd

    def _video(vid: int) -> dict:
        v = hd.lay(vid)
        if v is None:
            raise HTTPException(404, "không có video này")
        return v

    def _file_trong_data(p: str | None) -> Path:
        """Chỉ phục vụ file nằm TRONG thư mục data (đường dẫn lấy từ DB, nhưng vẫn chặn đi ra ngoài)."""
        if not p:
            raise HTTPException(404, "chưa có file")
        f = Path(p).resolve()
        if not f.is_file() or not f.is_relative_to(hd.data_dir.resolve()):
            raise HTTPException(404, "chưa có file")
        return f

    def _nhan_video_moi(vid: int, p: Path) -> None:
        try:
            hd.cap_nhat(vid, duong_dan_goc=str(p), trang_thai=trang_thai_moi, **do_video(p))
        except ValueError as e:
            hd.cap_nhat(vid, trang_thai="loi", loi=str(e))

    # ---- trang + trạng thái ----------------------------------------------------------------------------------------------------
    @app.get("/")
    def trang_chu():
        return FileResponse(TINH / "index.html")

    @app.get("/api/trang-thai")
    def trang_thai():
        ds = hd.tat_ca()
        for v in ds:
            v.pop("duong_dan_goc", None)
        return {"videos": ds, "logo_tuy_chinh": hd.logo_tuy_chinh.is_file(), "agy_bat": bool(agy_lenh)}

    # ---- đưa video vào ---------------------------------------------------------------------------------------------------------
    @app.post("/api/videos", status_code=201)
    def tai_len(file: UploadFile = File(...)):
        ten = _ten_an_toan(file.filename)
        duoi = Path(ten).suffix.lower()
        if duoi not in DUOI_VIDEO:
            raise HTTPException(400, f"'{ten}' không phải video ({', '.join(sorted(DUOI_VIDEO))})")
        vid = hd.tao(ten, "dang_tai")
        d = hd.thu_muc_video(vid)
        d.mkdir(parents=True, exist_ok=True)
        p = d / f"goc{duoi}"
        with p.open("wb") as f:
            shutil.copyfileobj(file.file, f, 1024 * 1024)
        _nhan_video_moi(vid, p)
        v = hd.lay(vid)
        if v["trang_thai"] == "loi":
            hd.xoa(vid)
            raise HTTPException(400, f"'{ten}': {v['loi']}")
        return {"id": vid}

    @app.post("/api/videos/drive", status_code=202)
    def tu_drive(body: LinkDrive):
        from .drive_cong_khai import LinkKhongHopLe, ma_file_drive, tai_file_drive
        try:
            ma = ma_file_drive(body.link)
        except LinkKhongHopLe as e:
            raise HTTPException(400, str(e)) from e
        vid = hd.tao(f"drive-{ma[:10]}", "dang_tai")

        def tai():
            try:
                p, ten = tai_file_drive(ma, hd.thu_muc_video(vid))
                hd.cap_nhat(vid, ten=_ten_an_toan(ten))
                _nhan_video_moi(vid, p)
            except Exception as e:  # noqa: BLE001 — lỗi tải hiện trên thẻ video
                hd.cap_nhat(vid, trang_thai="loi", loi=f"Không tải được từ Drive: {e}"[:500])
        threading.Thread(target=tai, name=f"drive-{vid}", daemon=True).start()
        return {"id": vid}

    # ---- khoanh + chạy ---------------------------------------------------------------------------------------------------------
    @app.get("/api/videos/{vid}/khung/{khung}.jpg")
    def anh_khung(vid: int, khung: int):
        v = _video(vid)
        if not v["so_khung"] or not 0 <= khung < v["so_khung"]:
            raise HTTPException(404, "khung ngoài video")
        cap = cv2.VideoCapture(_file_trong_data(v["duong_dan_goc"]).as_posix())
        try:
            cap.set(cv2.CAP_PROP_POS_FRAMES, khung)
            ok, f = cap.read()
        finally:
            cap.release()
        if not ok:
            raise HTTPException(404, "không đọc được khung này")
        _, buf = cv2.imencode(".jpg", f, [cv2.IMWRITE_JPEG_QUALITY, 90])
        return Response(buf.tobytes(), media_type="image/jpeg", headers={"Cache-Control": "max-age=3600"})

    @app.put("/api/videos/{vid}/boxes", status_code=204, response_model=None)
    def luu_box(vid: int, body: DsBox):
        v = _video(vid)
        if v["trang_thai"] not in TRANG_THAI_SUA_DUOC:
            raise HTTPException(409, "video đang chạy — chờ xong rồi khoanh lại")
        for b in body.boxes:
            if not 0 <= b.khung < v["so_khung"]:
                raise HTTPException(400, f"box ở khung {b.khung} nằm ngoài video")
            if b.w < 4 or b.h < 4 or b.x < 0 or b.y < 0 or b.x + b.w > v["rong"] or b.y + b.h > v["cao"]:
                raise HTTPException(400, f"box khung {b.khung} quá nhỏ hoặc tràn khỏi khung hình")
        hd.cap_nhat(vid, boxes=json.dumps([b.model_dump() for b in body.boxes]))

    @app.post("/api/videos/{vid}/chay", status_code=202, response_model=None)
    def chay(vid: int):
        v = _video(vid)
        if not v["boxes"]:
            raise HTTPException(400, "chưa khoanh logo cũ ở khung nào")
        if v["trang_thai"] not in TRANG_THAI_SUA_DUOC:
            raise HTTPException(409, "video đang chạy hoặc đang tải")
        hd.xep_hang_chay(vid)

    @app.post("/api/videos/{vid}/tim", status_code=202, response_model=None)
    def tim_lai(vid: int):
        if not agy_lenh:
            raise HTTPException(400, "máy này chưa bật agy — hãy khoanh tay")
        if _video(vid)["trang_thai"] not in TRANG_THAI_SUA_DUOC:
            raise HTTPException(409, "video đang tìm hoặc đang chạy")
        hd.xep_hang_tim(vid)

    # ---- kết quả ---------------------------------------------------------------------------------------------------------------
    @app.get("/api/videos/{vid}/anh/{ten}")
    def anh_ket_qua(vid: int, ten: str):
        kq = _video(vid)["ket_qua"] or {}
        khoa = {"truoc": "anh_truoc", "sau": "anh_sau", "soi": "anh_soi"}.get(ten)
        if khoa is None:
            raise HTTPException(404, "không có ảnh này")
        return FileResponse(_file_trong_data(kq.get(khoa)), headers={"Cache-Control": "no-cache"})

    @app.get("/api/videos/{vid}/ra.mp4")
    def video_ra(vid: int, tai: int = 0):
        v = _video(vid)
        f = _file_trong_data((v["ket_qua"] or {}).get("dau_ra"))
        ten = f"{Path(v['ten']).stem}_thay_logo.mp4"
        return FileResponse(f, media_type="video/mp4", filename=ten if tai else None,
                            content_disposition_type="attachment" if tai else "inline")

    @app.get("/api/videos/{vid}/goc")
    def video_goc(vid: int):
        return FileResponse(_file_trong_data(_video(vid)["duong_dan_goc"]))

    @app.post("/api/videos/{vid}/danh-gia", status_code=204, response_model=None)
    def danh_gia(vid: int, body: DanhGia):
        if body.gia_tri not in ("dat", "hong", ""):
            raise HTTPException(400, "đánh giá chỉ là dat / hong")
        if _video(vid)["trang_thai"] != "xong":
            raise HTTPException(409, "chỉ duyệt được video đã thay xong")
        hd.cap_nhat(vid, danh_gia=body.gia_tri or None)

    @app.delete("/api/videos/{vid}", status_code=204, response_model=None)
    def xoa(vid: int):
        if _video(vid)["trang_thai"] == "dang_chay":
            raise HTTPException(409, "video đang chạy — chờ xong rồi xoá")
        hd.xoa(vid)

    # ---- logo ------------------------------------------------------------------------------------------------------------------
    @app.get("/api/logo.png")
    def logo():
        p = hd.logo_tuy_chinh if hd.logo_tuy_chinh.is_file() else render.LOGO_MAC_DINH
        return FileResponse(p, media_type="image/png", headers={"Cache-Control": "no-cache"})

    @app.post("/api/logo", status_code=204, response_model=None)
    def doi_logo(file: UploadFile = File(...)):
        du_lieu = file.file.read(TRAN_LOGO_BYTE + 1)
        if len(du_lieu) > TRAN_LOGO_BYTE:
            raise HTTPException(400, "logo quá 10 MB")
        tam = hd.data_dir / "logo.tam.png"
        tam.write_bytes(du_lieu)
        try:
            render.doc_logo(tam)  # cùng hàm lúc render: PNG có kênh alpha, có điểm ảnh không trong suốt
        except Exception as e:  # noqa: BLE001
            tam.unlink(missing_ok=True)
            raise HTTPException(400, "logo phải là ảnh PNG có nền trong suốt (kênh alpha)") from e
        tam.replace(hd.logo_tuy_chinh)

    @app.delete("/api/logo", status_code=204, response_model=None)
    def ve_logo_mau():
        hd.logo_tuy_chinh.unlink(missing_ok=True)

    app.mount("/tinh", StaticFiles(directory=TINH), name="tinh")
    return app


def cong_dang_ban(cong: int) -> bool:
    """Có chương trình nào đang giữ cổng này không. SO_REUSEADDR giống uvicorn: cổng vừa nhả (TIME_WAIT
    sau khi tắt tool) vẫn tính là rảnh, chỉ cổng đang có máy chủ khác lắng nghe mới tính là bận.
    Thử kết nối trước: trên macOS, SO_REUSEADDR bind được 127.0.0.1 cả khi máy chủ khác nghe ở 0.0.0.0."""
    import socket

    try:
        socket.create_connection(("127.0.0.1", cong), timeout=0.5).close()
        return True
    except OSError:
        pass
    with socket.socket() as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(("127.0.0.1", cong))
        except OSError:
            return True
    return False


def chay_may_chu(data_dir: Path, ffmpeg: str, cong: int, mo_trinh_duyet: bool, *, agy_lenh: str | None,
                 agy_model: str | None) -> None:
    import uvicorn

    if cong_dang_ban(cong):  # cổng bận ⇒ nói rõ cách đổi, thay vì để uvicorn in lỗi khó hiểu
        raise SystemExit(f"LỖI: cổng {cong} đang bị chương trình khác dùng (hoặc thay-logo web đang mở ở cửa sổ khác). "
                         f"Chạy lại với cổng khác: thay-logo web --cong {cong + 1}")
    app = tao_app(data_dir, ffmpeg, agy_lenh=agy_lenh, agy_model=agy_model)
    url = f"http://127.0.0.1:{cong}"
    agy = f"BẬT ({agy_lenh}, model {agy_model})" if agy_lenh else "TẮT — video mới chờ bạn khoanh tay"
    print(f"\n  Thay logo đang chạy: {url}\n  Dữ liệu: {Path(data_dir).resolve()}\n  Tự tìm logo bằng agy: {agy}\n"
          "  Dừng: bấm Ctrl+C\n", flush=True)
    if mo_trinh_duyet:
        import webbrowser
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    uvicorn.run(app, host="127.0.0.1", port=cong, log_level="warning")
