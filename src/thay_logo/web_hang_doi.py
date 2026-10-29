"""Hàng đợi cục bộ cho trang web: SQLite trong thư mục data + MỘT luồng worker nền xử lý lần lượt từng video.

Vòng đời một video (giống bản gốc: máy tự tìm trước, người khoanh là đường dự phòng):
  dang_tai (chỉ khi dán link) → cho_tim → dang_tim (agy tìm logo cũ) ─┬─ thấy ⇒ cho_chay → dang_chay → xong | khong_chac | loi
                                                                       └─ không thấy / agy trượt / máy không có agy ⇒ cho_khoanh
  cho_khoanh → [người khoanh + bấm Chạy] → cho_chay → …
  `xong` / `khong_chac` / `loi` đều khoanh thêm + chạy lại được (lượt mới, kết quả cũ giữ trong thư mục lượt cũ).

Mỗi video chạy trong TIẾN TRÌNH CON (`python -m thay_logo.cli chay …`): lỗi native của OpenCV không kéo sập máy chủ web, RAM trả
lại hệ điều hành khi xong, và có trần thời gian cứng. Tắt máy chủ giữa chừng ⇒ lần mở sau video `dang_chay` tự quay về `cho_chay`.
"""
from __future__ import annotations

import json
import logging
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
from pathlib import Path

log = logging.getLogger("thay_logo.web")

TRAN_GIAY_MOT_VIDEO = 2 * 3600  # trần thời gian một lượt xử lý; quá ⇒ `loi`
NHIP_QUET_GIAY = 1.0

_LUOC_DO = """
CREATE TABLE IF NOT EXISTS videos (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ten TEXT NOT NULL,
  duong_dan_goc TEXT,
  rong INTEGER, cao INTEGER, fps REAL, so_khung INTEGER,
  trang_thai TEXT NOT NULL,
  boxes TEXT NOT NULL DEFAULT '[]',
  luot INTEGER NOT NULL DEFAULT 0,
  ket_qua TEXT,
  loi TEXT,
  danh_gia TEXT,
  tao_luc REAL NOT NULL,
  cap_nhat REAL NOT NULL
);
"""
COT_TRA_VE = ("id", "ten", "rong", "cao", "fps", "so_khung", "trang_thai", "boxes", "luot", "ket_qua", "loi", "danh_gia", "tao_luc")


class HangDoi:
    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.db = self.data_dir / "thay_logo.db"
        self._khoa = threading.Lock()
        with self._mo() as c:
            c.executescript(_LUOC_DO)
            c.execute("UPDATE videos SET trang_thai='cho_chay', cap_nhat=? WHERE trang_thai='dang_chay'", (time.time(),))
            c.execute("UPDATE videos SET trang_thai='cho_tim', cap_nhat=? WHERE trang_thai='dang_tim'", (time.time(),))
            c.execute("UPDATE videos SET trang_thai='loi', loi='Máy chủ tắt khi đang tải video về', cap_nhat=? "
                      "WHERE trang_thai='dang_tai'", (time.time(),))

    def _mo(self) -> sqlite3.Connection:
        c = sqlite3.connect(self.db, timeout=30, isolation_level=None)
        c.row_factory = sqlite3.Row
        return c

    # ---- đường dẫn -------------------------------------------------------------------------------------------------------------
    def thu_muc_video(self, vid: int) -> Path:
        return self.data_dir / "videos" / str(vid)

    def thu_muc_luot(self, vid: int, luot: int) -> Path:
        return self.thu_muc_video(vid) / f"luot{luot}"

    @property
    def logo_tuy_chinh(self) -> Path:
        return self.data_dir / "logo.png"

    # ---- đọc / ghi -------------------------------------------------------------------------------------------------------------
    def tao(self, ten: str, trang_thai: str) -> int:
        now = time.time()
        with self._mo() as c:
            return c.execute("INSERT INTO videos(ten, trang_thai, tao_luc, cap_nhat) VALUES (?,?,?,?)",
                             (ten, trang_thai, now, now)).lastrowid

    def cap_nhat(self, vid: int, **truong) -> None:
        truong["cap_nhat"] = time.time()
        cot = ", ".join(f"{k}=?" for k in truong)
        with self._mo() as c:
            c.execute(f"UPDATE videos SET {cot} WHERE id=?", (*truong.values(), vid))

    def lay(self, vid: int) -> dict | None:
        with self._mo() as c:
            r = c.execute("SELECT * FROM videos WHERE id=?", (vid,)).fetchone()
        return self._ra_dict(r) if r else None

    def tat_ca(self) -> list[dict]:
        with self._mo() as c:
            return [self._ra_dict(r) for r in c.execute("SELECT * FROM videos ORDER BY id DESC")]

    def xoa(self, vid: int) -> None:
        with self._mo() as c:
            c.execute("DELETE FROM videos WHERE id=?", (vid,))
        shutil.rmtree(self.thu_muc_video(vid), ignore_errors=True)

    @staticmethod
    def _ra_dict(r: sqlite3.Row) -> dict:
        d = {k: r[k] for k in COT_TRA_VE}
        d["boxes"] = json.loads(d["boxes"] or "[]")
        d["ket_qua"] = json.loads(d["ket_qua"]) if d["ket_qua"] else None
        d["duong_dan_goc"] = r["duong_dan_goc"]
        return d

    def xep_hang_chay(self, vid: int) -> None:
        """Đưa video vào hàng chạy (lượt mới). Đang chạy thì không đụng."""
        with self._khoa, self._mo() as c:
            c.execute("UPDATE videos SET trang_thai='cho_chay', loi=NULL, danh_gia=NULL, cap_nhat=? "
                      "WHERE id=? AND trang_thai!='dang_chay'", (time.time(), vid))

    def xep_hang_tim(self, vid: int) -> None:
        """Nhờ agy tìm (lại) logo cũ. Đang tìm/chạy thì không đụng."""
        with self._khoa, self._mo() as c:
            c.execute("UPDATE videos SET trang_thai='cho_tim', loi=NULL, cap_nhat=? "
                      "WHERE id=? AND trang_thai NOT IN ('dang_chay', 'dang_tim', 'dang_tai')", (time.time(), vid))

    def _nhan_viec(self) -> dict | None:
        """Việc cũ nhất trong `cho_tim` + `cho_chay` (một hàng chung, đúng thứ tự người đưa vào)."""
        with self._khoa, self._mo() as c:
            r = c.execute("SELECT * FROM videos WHERE trang_thai IN ('cho_tim', 'cho_chay') ORDER BY cap_nhat, id LIMIT 1").fetchone()
            if r is None:
                return None
            if r["trang_thai"] == "cho_tim":
                c.execute("UPDATE videos SET trang_thai='dang_tim', cap_nhat=? WHERE id=?", (time.time(), r["id"]))
            else:
                c.execute("UPDATE videos SET trang_thai='dang_chay', luot=luot+1, cap_nhat=? WHERE id=?", (time.time(), r["id"]))
        return self.lay(r["id"])


class Worker:
    """Một luồng nền, xử lý tuần tự (OpenCV + ffmpeg đã ăn nhiều CPU; chạy song song chỉ làm mọi video chậm đi)."""

    def __init__(self, hang_doi: HangDoi, *, ffmpeg: str, luong: int = 2, agy_lenh: str | None = None,
                 agy_model: str | None = None):
        self.hd, self.ffmpeg, self.luong = hang_doi, ffmpeg, luong
        self.agy_lenh, self.agy_model = agy_lenh, agy_model
        self._dung = threading.Event()
        self._luong: threading.Thread | None = None
        self._con: subprocess.Popen | None = None

    def start(self) -> None:
        self._luong = threading.Thread(target=self._vong, name="thay-logo-worker", daemon=True)
        self._luong.start()

    def stop(self, timeout: float = 10.0) -> None:
        self._dung.set()
        con = self._con
        if con is not None and con.poll() is None:
            con.terminate()
        if self._luong is not None:
            self._luong.join(timeout)

    def _vong(self) -> None:
        while not self._dung.is_set():
            try:
                viec = self.hd._nhan_viec()
                if viec is None:
                    self._dung.wait(NHIP_QUET_GIAY)
                    continue
                (self.tim if viec["trang_thai"] == "dang_tim" else self.xu_ly)(viec)
            except Exception:  # noqa: BLE001 — worker không được chết vì một video
                log.exception("worker: lỗi ngoài dự kiến")
                self._dung.wait(NHIP_QUET_GIAY)

    def tim(self, v: dict) -> None:
        """agy tìm logo cũ. Thấy ⇒ lưu box (nguồn agy) và tự xếp hàng chạy; không ⇒ `cho_khoanh` kèm lý do (người khoanh tay)."""
        from .agy_dinh_vi import LoiAgy, tim_box
        from .nguon_khung import NguonKhungVideo
        vid = v["id"]
        try:
            boxes, man_ket = tim_box(NguonKhungVideo(v["duong_dan_goc"]), lenh=self.agy_lenh, model=self.agy_model)
        except LoiAgy as e:
            log.info("video %s: agy không cho box (%s)", vid, e.ma)
            self.hd.cap_nhat(vid, trang_thai="cho_khoanh", loi=e.ly_do)
            return
        except Exception as e:  # noqa: BLE001 — lỗi đọc video… ⇒ vẫn cho người khoanh
            log.exception("video %s: lỗi khi tìm bằng agy", vid)
            self.hd.cap_nhat(vid, trang_thai="cho_khoanh", loi=f"Lỗi khi tự tìm: {type(e).__name__} — hãy khoanh tay.")
            return
        log.info("video %s: agy thấy %d box (màn kết cuối: %s)", vid, len(boxes), man_ket)
        self.hd.cap_nhat(vid, boxes=json.dumps([{"khung": b.khung, "x": b.x, "y": b.y, "w": b.w, "h": b.h, "cum": b.cum,
                                                 "nguon": "agy"} for b in boxes]), loi=None)
        self.hd.xep_hang_chay(vid)

    def xu_ly(self, v: dict) -> None:
        vid, luot = v["id"], v["luot"]
        d = self.hd.thu_muc_luot(vid, luot)
        d.mkdir(parents=True, exist_ok=True)
        (d / "boxes.json").write_text(json.dumps(v["boxes"]), encoding="utf-8")
        cmd = [sys.executable, "-m", "thay_logo.cli", "chay", v["duong_dan_goc"], "--boxes", str(d / "boxes.json"),
               "--out", str(d / "ra.mp4"), "--bao-cao", str(d / "bao_cao"), "--ffmpeg", self.ffmpeg, "--luong", str(self.luong)]
        if self.hd.logo_tuy_chinh.is_file():
            cmd += ["--logo", str(self.hd.logo_tuy_chinh)]
        log.info("video %s lượt %s: bắt đầu", vid, luot)
        try:
            self._con = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            out, err = self._con.communicate(timeout=TRAN_GIAY_MOT_VIDEO)
            rc = self._con.returncode
        except subprocess.TimeoutExpired:
            self._con.kill()
            self._con.communicate()
            self.hd.cap_nhat(vid, trang_thai="loi", loi=f"Quá {TRAN_GIAY_MOT_VIDEO // 60} phút mà chưa xong — đã dừng.")
            return
        finally:
            self._con = None
        if self._dung.is_set() and rc != 0:
            self.hd.cap_nhat(vid, trang_thai="cho_chay")  # bị dừng vì tắt máy chủ ⇒ lần sau chạy lại
            return
        try:
            kq = json.loads(out)
        except ValueError:
            kq = None
        if rc == 0 and kq:
            self.hd.cap_nhat(vid, trang_thai="xong", ket_qua=json.dumps(kq, ensure_ascii=False), loi=None)
        elif rc == 2 and kq:
            self.hd.cap_nhat(vid, trang_thai="khong_chac", ket_qua=json.dumps(kq, ensure_ascii=False), loi=kq.get("ly_do"))
        else:
            dong = [x for x in (err or "").strip().splitlines() if x.strip()]
            self.hd.cap_nhat(vid, trang_thai="loi", loi=(dong[-1] if dong else f"tiến trình xử lý thoát mã {rc}")[:500])
        log.info("video %s lượt %s: rc=%s", vid, luot, rc)
