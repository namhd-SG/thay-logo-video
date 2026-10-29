"""Trang web: đưa video vào → (agy tìm | khoanh tay) → chạy → duyệt → tải về, trên video TỔNG HỢP. Worker gọi đồng bộ trong test."""
import io
import json

import pytest

cv2 = pytest.importorskip("cv2")
from fastapi.testclient import TestClient  # noqa: E402
from thay_logo_tong_hop import tao_clip  # noqa: E402

from thay_logo import agy_dinh_vi, web_hang_doi  # noqa: E402
from thay_logo.drive_cong_khai import LinkKhongHopLe, ma_file_drive  # noqa: E402
from thay_logo.ffmpeg import tim_ffmpeg  # noqa: E402
from thay_logo.render import LOGO_MAC_DINH  # noqa: E402
from thay_logo.web_app import tao_app  # noqa: E402

FFMPEG = tim_ffmpeg()
pytestmark = pytest.mark.skipif(FFMPEG is None, reason="không tìm thấy ffmpeg")
KHUNG_MOI = (5, 12, 20, 28, 35)


@pytest.fixture(scope="module")
def clip_mp4(tmp_path_factory):
    clip = tao_clip(n=40)
    p = tmp_path_factory.mktemp("web") / "mau.mp4"
    out = cv2.VideoWriter(str(p), cv2.VideoWriter_fourcc(*"mp4v"), 30.0, (360, 640))
    for i in range(40):
        out.write(cv2.cvtColor(clip.nguon.doc(i), cv2.COLOR_GRAY2BGR))
    out.release()
    return clip, p.read_bytes()


def _app(tmp_path, **k):
    app = tao_app(tmp_path / "data", FFMPEG, chay_worker=False, **k)
    hd = app.state.hang_doi
    return TestClient(app), hd, web_hang_doi.Worker(hd, ffmpeg=FFMPEG, agy_lenh=k.get("agy_lenh"))


def _tai_len(c, du_lieu, ten="mau.mp4"):
    r = c.post("/api/videos", files={"file": (ten, io.BytesIO(du_lieu), "video/mp4")})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _mot_luot(worker, hd):
    viec = hd._nhan_viec()
    assert viec is not None
    (worker.tim if viec["trang_thai"] == "dang_tim" else worker.xu_ly)(viec)


def _boxes(clip, cum=None):
    return [{"khung": i, "x": clip.hop_that[i][0], "y": clip.hop_that[i][1], "w": clip.hop_that[i][2], "h": clip.hop_that[i][3],
             "cum": cum} for i in KHUNG_MOI]


def test_vong_khoanh_tay_toi_tai_ve(tmp_path, clip_mp4):
    clip, du_lieu = clip_mp4
    c, hd, worker = _app(tmp_path)
    assert c.get("/").status_code == 200 and "Thay logo" in c.get("/").text
    vid = _tai_len(c, du_lieu)
    v = c.get("/api/trang-thai").json()
    assert v["agy_bat"] is False and v["videos"][0]["trang_thai"] == "cho_khoanh" and v["videos"][0]["so_khung"] == 40
    assert "duong_dan_goc" not in v["videos"][0]  # không lộ đường dẫn đĩa ra trang
    r = c.get(f"/api/videos/{vid}/khung/20.jpg")
    assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg"
    assert c.get(f"/api/videos/{vid}/khung/40.jpg").status_code == 404
    assert c.post(f"/api/videos/{vid}/chay").status_code == 400  # chưa khoanh
    assert c.put(f"/api/videos/{vid}/boxes", json={"boxes": [{"khung": 5, "x": 350, "y": 10, "w": 40, "h": 20}]}).status_code == 400
    assert c.put(f"/api/videos/{vid}/boxes", json={"boxes": _boxes(clip)}).status_code == 204
    assert c.post(f"/api/videos/{vid}/chay").status_code == 202
    _mot_luot(worker, hd)
    v = hd.lay(vid)
    assert v["trang_thai"] == "xong" and v["luot"] == 1, v
    for ten in ("truoc", "sau", "soi"):
        assert c.get(f"/api/videos/{vid}/anh/{ten}").status_code == 200
    r = c.get(f"/api/videos/{vid}/ra.mp4?tai=1")
    assert r.status_code == 200 and "attachment" in r.headers["content-disposition"] and "mau_thay_logo.mp4" in r.headers["content-disposition"]
    assert c.post(f"/api/videos/{vid}/danh-gia", json={"gia_tri": "dat"}).status_code == 204 and hd.lay(vid)["danh_gia"] == "dat"
    assert c.post(f"/api/videos/{vid}/danh-gia", json={"gia_tri": "tot"}).status_code == 400
    # chạy lại (khoanh thêm) ⇒ lượt 2, đánh giá cũ bị xoá
    assert c.post(f"/api/videos/{vid}/chay").status_code == 202 and hd.lay(vid)["danh_gia"] is None
    _mot_luot(worker, hd)
    assert hd.lay(vid)["luot"] == 2 and (hd.thu_muc_luot(vid, 1) / "ra.mp4").exists()
    assert c.delete(f"/api/videos/{vid}").status_code == 204 and not hd.thu_muc_video(vid).exists()


def test_box_gia_thi_khong_chac_va_khong_ghi_video(tmp_path, clip_mp4):
    clip, du_lieu = clip_mp4
    c, hd, worker = _app(tmp_path)
    vid = _tai_len(c, du_lieu)
    b = clip.box_gia(5)
    c.put(f"/api/videos/{vid}/boxes", json={"boxes": [{"khung": 5, "x": b.x, "y": b.y, "w": b.w, "h": b.h}]})
    c.post(f"/api/videos/{vid}/chay")
    _mot_luot(worker, hd)
    v = hd.lay(vid)
    assert v["trang_thai"] == "khong_chac" and v["loi"] and not (hd.thu_muc_luot(vid, 1) / "ra.mp4").exists()
    assert c.get(f"/api/videos/{vid}/ra.mp4").status_code == 404


def test_agy_thay_thi_tu_chay_khong_thay_thi_cho_khoanh(tmp_path, clip_mp4, monkeypatch):
    clip, du_lieu = clip_mp4
    c, hd, worker = _app(tmp_path, agy_lenh="agy-gia")
    from thay_logo.box_moi import BoxMoi
    monkeypatch.setattr(agy_dinh_vi, "tim_box", lambda nguon, **k: ([BoxMoi(**b, nguon="agy") for b in _boxes(clip, cum=0)], False))
    vid = _tai_len(c, du_lieu)
    assert hd.lay(vid)["trang_thai"] == "cho_tim"
    _mot_luot(worker, hd)  # tìm
    v = hd.lay(vid)
    assert v["trang_thai"] == "cho_chay" and len(v["boxes"]) == 5 and v["boxes"][0]["nguon"] == "agy"
    _mot_luot(worker, hd)  # chạy
    assert hd.lay(vid)["trang_thai"] == "xong"

    def truot(nguon, **k):
        raise agy_dinh_vi.LoiAgy("model_khong_nhan")
    monkeypatch.setattr(agy_dinh_vi, "tim_box", truot)
    vid2 = _tai_len(c, du_lieu, "b.mp4")
    _mot_luot(worker, hd)
    v2 = hd.lay(vid2)
    assert v2["trang_thai"] == "cho_khoanh" and "model" in v2["loi"]
    assert c.post(f"/api/videos/{vid2}/tim").status_code == 202 and hd.lay(vid2)["trang_thai"] == "cho_tim"


def test_tai_len_file_khong_phai_video(tmp_path):
    c, hd, _ = _app(tmp_path)
    assert c.post("/api/videos", files={"file": ("a.txt", io.BytesIO(b"x"), "text/plain")}).status_code == 400
    assert c.post("/api/videos", files={"file": ("hong.mp4", io.BytesIO(b"khong phai video"), "video/mp4")}).status_code == 400
    assert hd.tat_ca() == []  # file hỏng không để lại thẻ rác


def test_doi_logo_va_ve_logo_mau(tmp_path):
    c, hd, _ = _app(tmp_path)
    assert c.post("/api/logo", files={"file": ("x.png", io.BytesIO(b"khong phai png"), "image/png")}).status_code == 400
    import numpy as np
    rgb = np.zeros((20, 40, 3), np.uint8)
    _, khong_alpha = cv2.imencode(".png", rgb)
    assert c.post("/api/logo", files={"file": ("x.png", io.BytesIO(khong_alpha.tobytes()), "image/png")}).status_code == 400
    assert c.post("/api/logo", files={"file": ("x.png", io.BytesIO(LOGO_MAC_DINH.read_bytes()), "image/png")}).status_code == 204
    assert hd.logo_tuy_chinh.is_file() and c.get("/api/trang-thai").json()["logo_tuy_chinh"] is True
    assert c.delete("/api/logo").status_code == 204 and not hd.logo_tuy_chinh.exists()


def test_khoi_dong_lai_tra_viec_dang_chay_ve_hang(tmp_path, clip_mp4):
    clip, du_lieu = clip_mp4
    c, hd, _ = _app(tmp_path)
    vid = _tai_len(c, du_lieu)
    c.put(f"/api/videos/{vid}/boxes", json={"boxes": _boxes(clip)})
    c.post(f"/api/videos/{vid}/chay")
    hd._nhan_viec()
    assert hd.lay(vid)["trang_thai"] == "dang_chay"
    hd2 = web_hang_doi.HangDoi(tmp_path / "data")
    assert hd2.lay(vid)["trang_thai"] == "cho_chay"


@pytest.mark.parametrize("link, ma", [
    ("https://drive.google.com/file/d/1AbCdEfGhIjKlMnOpQrStUvWxYz012345/view?usp=sharing", "1AbCdEfGhIjKlMnOpQrStUvWxYz012345"),
    ("https://drive.google.com/open?id=1AbCdEfGhIjKlMnOpQrStUvWxYz012345", "1AbCdEfGhIjKlMnOpQrStUvWxYz012345"),
    ("1AbCdEfGhIjKlMnOpQrStUvWxYz012345", "1AbCdEfGhIjKlMnOpQrStUvWxYz012345"),
])
def test_ma_file_drive(link, ma):
    assert ma_file_drive(link) == ma


@pytest.mark.parametrize("link", ["https://drive.google.com/drive/folders/1AbCdEfGhIjKlMnOpQrStUvWxYz012345",
                                  "https://example.com/file/d/1AbCdEfGhIjKlMnOpQrStUvWxYz012345", "abc"])
def test_link_drive_sai(link):
    with pytest.raises(LinkKhongHopLe):
        ma_file_drive(link)


def test_khong_phuc_vu_file_ngoai_data(tmp_path, clip_mp4):
    _, du_lieu = clip_mp4
    c, hd, _ = _app(tmp_path)
    vid = _tai_len(c, du_lieu)
    hd.cap_nhat(vid, trang_thai="xong", ket_qua=json.dumps({"anh_truoc": "/etc/hosts", "dau_ra": "/etc/hosts"}))
    assert c.get(f"/api/videos/{vid}/anh/truoc").status_code == 404
    assert c.get(f"/api/videos/{vid}/ra.mp4").status_code == 404
