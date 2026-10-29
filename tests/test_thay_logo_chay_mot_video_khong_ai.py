"""Lệnh `thay-logo chay` KHÔNG với tới AI vòng hai / lộ trình — box mồi do người dùng đưa vào là đủ.

AI vòng hai (`gan_moc_ai`) và lộ trình (`theo_lo_trinh`) chỉ chạy khi `duong_ong.xu_ly_video(..., neo_ai=[...])` nhận mốc khác rỗng;
CLI không có tham số nào để truyền chúng. Test thứ hai chứng minh bản vá giả có răng: gọi thẳng với `neo_ai` thì nổ.
Thêm: mã thoát + file báo cáo của CLI, và các đường lỗi đầu vào.
"""
import json

import pytest

cv2 = pytest.importorskip("cv2")

from thay_logo_tong_hop import tao_clip  # noqa: E402

from thay_logo import cli, duong_ong  # noqa: E402
from thay_logo.box_moi import BoxMoi  # noqa: E402
from thay_logo.ffmpeg import tim_ffmpeg  # noqa: E402

FFMPEG = tim_ffmpeg()
pytestmark = pytest.mark.skipif(FFMPEG is None, reason="không tìm thấy ffmpeg")


class _ChamAI(Exception):
    pass


def _cam(*_a, **_k):
    raise _ChamAI("đường AI vòng hai bị gọi")


@pytest.fixture
def cam_ai(monkeypatch):
    monkeypatch.setattr(duong_ong, "gan_moc_ai", _cam)
    monkeypatch.setattr(duong_ong, "theo_lo_trinh", _cam)


@pytest.fixture(scope="module")
def clip_file(tmp_path_factory):
    d = tmp_path_factory.mktemp("khong_ai")
    clip = tao_clip(n=40)
    p = d / "goc.mp4"
    out = cv2.VideoWriter(str(p), cv2.VideoWriter_fourcc(*"mp4v"), 30.0, (360, 640))
    for i in range(40):
        out.write(cv2.cvtColor(clip.nguon.doc(i), cv2.COLOR_GRAY2BGR))
    out.release()
    return clip, p


def _ghi_boxes(clip, tmp_path, **k):
    boxes = tmp_path / "boxes.json"
    boxes.write_text(json.dumps([{"khung": b.khung, "x": b.x, "y": b.y, "w": b.w, "h": b.h, "cum": b.cum}
                                 for b in clip.box_moi(khung=(5, 12, 20, 28, 35), **k)]))
    return boxes


def test_cli_chay_render_ma_khong_goi_ai(cam_ai, clip_file, tmp_path, capsys):
    clip, p = clip_file
    boxes = _ghi_boxes(clip, tmp_path, cum=1)
    rc = cli.main(["chay", str(p), "--boxes", str(boxes), "--out", str(tmp_path / "ra.mp4"), "--ffmpeg", FFMPEG])
    kq = json.loads(capsys.readouterr().out)
    assert rc == cli.MA_DA_THAY and kq["trang_thai"] == "render", kq
    assert (tmp_path / "ra.mp4").exists() and (tmp_path / "ra_bao_cao" / "ket_qua.json").exists()
    assert cv2.imread(kq["anh_truoc"]) is not None and cv2.imread(kq["anh_sau"]) is not None


def test_cli_box_dong_lenh_tuong_duong_file(clip_file, tmp_path, capsys):
    clip, p = clip_file
    args = [f"{b.khung}:{b.x},{b.y},{b.w},{b.h}" for b in clip.box_moi(khung=(5, 12, 20, 28, 35))]
    rc = cli.main(["chay", str(p), "--out", str(tmp_path / "ra.mp4"), "--ffmpeg", FFMPEG] + sum((["--box", a] for a in args), []))
    assert rc == cli.MA_DA_THAY, capsys.readouterr()


def test_cli_khong_chac_thi_ma_2_va_khong_ghi_file(clip_file, tmp_path, capsys):
    clip, p = clip_file
    b = clip.box_gia(5)
    rc = cli.main(["chay", str(p), "--box", f"{b.khung}:{b.x},{b.y},{b.w},{b.h}", "--out", str(tmp_path / "ra.mp4"), "--ffmpeg", FFMPEG])
    kq = json.loads(capsys.readouterr().out)
    assert rc == cli.MA_KHONG_THAY and kq["trang_thai"] == "cho_nguoi" and kq["ly_do"]
    assert not (tmp_path / "ra.mp4").exists()


@pytest.mark.parametrize("box", ["0:1000,10,50,20", "999:10,10,50,20"])
def test_cli_box_ngoai_video_bao_loi_ro(clip_file, tmp_path, capsys, box):
    _, p = clip_file
    rc = cli.main(["chay", str(p), "--box", box, "--out", str(tmp_path / "ra.mp4"), "--ffmpeg", FFMPEG])
    assert rc == cli.MA_LOI and "LỖI" in capsys.readouterr().err


def test_cli_khong_ghi_de_video_goc(clip_file, capsys):
    clip, p = clip_file
    b = clip.box_moi(khung=(5,))[0]
    rc = cli.main(["chay", str(p), "--box", f"5:{b.x},{b.y},{b.w},{b.h}", "--out", str(p), "--ffmpeg", FFMPEG])
    assert rc == cli.MA_LOI and "trùng video gốc" in capsys.readouterr().err


def test_box_chuoi_sai_khuon():
    with pytest.raises(Exception, match="KHUNG:X,Y,W,H"):
        cli.doc_box_chuoi("5:10,10,50")


def test_ban_va_gia_co_rang_khi_truyen_neo_ai(cam_ai, clip_file):
    clip, _ = clip_file
    boxes = clip.box_moi(khung=(5, 12, 20, 28, 35), cum=1)
    with pytest.raises(_ChamAI):
        duong_ong.xu_ly_video(clip.nguon, boxes, neo_ai=[BoxMoi(20, *clip.hop_that[20], nguon="agy", cum=1)])
