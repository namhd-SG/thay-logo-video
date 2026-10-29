"""`--logo` thật sự đổi logo được dán: hai logo khác hẳn nhau ⇒ vùng logo của hai video ra khác nhau; ngoài vùng thì như nhau.
Đối chứng: chạy lại cùng một logo ⇒ vùng logo gần như trùng (khác biệt chỉ do mã hoá)."""
import json

import numpy as np
import pytest

cv2 = pytest.importorskip("cv2")
from thay_logo_tong_hop import tao_clip  # noqa: E402

from thay_logo import cli  # noqa: E402
from thay_logo.ffmpeg import tim_ffmpeg  # noqa: E402

FFMPEG = tim_ffmpeg()
pytestmark = pytest.mark.skipif(FFMPEG is None, reason="không tìm thấy ffmpeg")


def _logo(p, mau_bgr):
    img = np.zeros((40, 160, 4), np.uint8)
    img[:, :, :3] = mau_bgr
    img[:, :, 3] = 255
    cv2.imwrite(str(p), img)
    return p


@pytest.fixture(scope="module")
def ca(tmp_path_factory):
    d = tmp_path_factory.mktemp("logo")
    clip = tao_clip(n=40)
    goc = d / "goc.mp4"
    out = cv2.VideoWriter(str(goc), cv2.VideoWriter_fourcc(*"mp4v"), 30.0, (360, 640))
    for i in range(40):
        out.write(cv2.cvtColor(clip.nguon.doc(i), cv2.COLOR_GRAY2BGR))
    out.release()
    boxes = d / "boxes.json"
    boxes.write_text(json.dumps([{"khung": i, "x": clip.hop_that[i][0], "y": clip.hop_that[i][1], "w": clip.hop_that[i][2],
                                  "h": clip.hop_that[i][3]} for i in (5, 12, 20, 28, 35)]))
    return clip, d, goc, boxes


def _chay(d, goc, boxes, logo, ten):
    rc = cli.main(["chay", str(goc), "--boxes", str(boxes), "--out", str(d / f"{ten}.mp4"), "--logo", str(logo), "--ffmpeg", FFMPEG,
                   "--bao-cao", str(d / f"{ten}_bc")])
    assert rc == cli.MA_DA_THAY
    cap = cv2.VideoCapture(str(d / f"{ten}.mp4"))
    cap.set(cv2.CAP_PROP_POS_FRAMES, 20)
    ok, f = cap.read()
    cap.release()
    assert ok
    return f.astype(int)


def test_hai_logo_khac_nhau_cho_ra_vung_logo_khac_nhau(ca, capsys):
    clip, d, goc, boxes = ca
    do = _chay(d, goc, boxes, _logo(d / "do.png", (0, 0, 255)), "do")
    xanh = _chay(d, goc, boxes, _logo(d / "xanh.png", (255, 0, 0)), "xanh")
    do2 = _chay(d, goc, boxes, d / "do.png", "do2")
    capsys.readouterr()
    x, y, w, h = clip.hop_that[20]
    vung = (slice(y + 4, y + h - 4), slice(x + 4, x + w - 4))
    # logo đỏ: kênh R (BGR[2]) trội; logo xanh dương: kênh B trội
    assert do[vung][:, :, 2].mean() > do[vung][:, :, 0].mean() + 60
    assert xanh[vung][:, :, 0].mean() > xanh[vung][:, :, 2].mean() + 60
    assert np.abs(do[vung] - xanh[vung]).mean() > 60
    assert np.abs(do[vung] - do2[vung]).mean() < 3  # đối chứng: cùng logo ⇒ cùng kết quả
    ngoai = np.ones(do.shape[:2], bool)
    ngoai[max(0, y - 20):y + h + 20, max(0, x - 20):x + w + 20] = False
    assert np.abs(do[ngoai] - xanh[ngoai]).mean() < 2  # ngoài vùng logo hai bản như nhau


def test_logo_khong_co_alpha_bao_loi_ro(ca, capsys):
    _, d, goc, boxes = ca
    p = d / "khong_alpha.png"
    cv2.imwrite(str(p), np.zeros((20, 40, 3), np.uint8))
    rc = cli.main(["chay", str(goc), "--boxes", str(boxes), "--out", str(d / "x.mp4"), "--logo", str(p), "--ffmpeg", FFMPEG])
    assert rc == cli.MA_LOI and "alpha" in capsys.readouterr().err
