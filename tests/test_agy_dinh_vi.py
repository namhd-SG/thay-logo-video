"""Tự tìm bằng agy: đọc đúng đầu ra, KHÔNG tin mã thoát. Dùng một lệnh `agy` GIẢ (script Python) — không gọi agy thật."""
import json
import os
import stat
import sys

import pytest

cv2 = pytest.importorskip("cv2")

from thay_logo_tong_hop import tao_clip  # noqa: E402

from thay_logo import agy_dinh_vi as ad  # noqa: E402

KICH_BAN = {
    # mỗi ảnh: một watermark nhãn "wmark" ở box_2d cố định; ảnh cuối (màn kết) đánh endcard=true
    "dung": "items=[{'file': f, 'endcard': i == len(fs) - 1, 'watermarks': [{'label': 'WMARK', 'box_2d': [656, 166, 700, 333]}]} for i, f in enumerate(fs)]\n"
            "print(json.dumps({'status': 'SUCCESS', 'structured_output': {'items': items}}))",
    "rac_rc0": "print('xin chao, day khong phai json')",
    "sai_model": "print('Error: model gemini-x is not recognized', file=sys.stderr)",
    "khong_xong": "print(json.dumps({'status': 'ERROR'}))",
    "sot_anh": "items=[{'file': f, 'endcard': False, 'watermarks': []} for f in fs[:-2]]\n"
               "print(json.dumps({'status': 'SUCCESS', 'structured_output': {'items': items}}))",
    "khong_logo": "items=[{'file': f, 'endcard': False, 'watermarks': []} for f in fs]\n"
                  "print(json.dumps({'status': 'SUCCESS', 'structured_output': {'items': items}}))",
    "logo_nha": "items=[{'file': f, 'endcard': False, 'watermarks': [{'label': 'My Brand', 'box_2d': [10, 10, 60, 200]},"
                " {'label': 'wmark', 'box_2d': [656, 166, 700, 333]}]} for f in fs]\n"
                "print(json.dumps({'status': 'SUCCESS', 'structured_output': {'items': items}}))",
}


def _agy_gia(tmp_path, kich_ban: str, vet: list | None = None):
    p = tmp_path / f"agy_{kich_ban}"
    p.write_text(f"#!{sys.executable}\n"
                 "import json, os, sys\n"
                 "a = sys.argv\n"
                 "d = a[a.index('--add-dir') + 1]\n"
                 f"open({str(tmp_path / 'argv.json')!r}, 'w').write(json.dumps(a))\n"
                 "fs = sorted(os.path.join(d, x) for x in os.listdir(d))\n"
                 + KICH_BAN[kich_ban] + "\n")
    p.chmod(p.stat().st_mode | stat.S_IEXEC)
    return str(p)


@pytest.fixture(scope="module")
def clip():
    return tao_clip(n=40)


def test_doc_dung_box_va_bo_khung_man_ket(tmp_path, clip):
    boxes, man_ket = ad.tim_box(clip.nguon, lenh=_agy_gia(tmp_path, "dung"), model="m-test")
    assert man_ket is None or isinstance(man_ket, bool)
    assert 1 <= len(boxes) <= 6 and all(b.nguon == "agy" and b.cum == 0 for b in boxes)
    b = boxes[0]  # [ymin 656, xmin 166, ymax 700, xmax 333] trên khung 360x640 ⇒ x≈59, y≈419, w≈60, h≈28
    assert (abs(b.x - 59) <= 1, abs(b.y - 419) <= 1, abs(b.w - 60) <= 1, abs(b.h - 28) <= 1) == (True,) * 4
    argv = json.loads((tmp_path / "argv.json").read_text())
    assert "--dangerously-skip-permissions" not in argv and argv[argv.index("--model") + 1] == "m-test"


@pytest.mark.parametrize("kich_ban, ma", [("rac_rc0", "khong_phai_json"), ("sai_model", "model_khong_nhan"),
                                          ("khong_xong", "trang_thai_khac"), ("sot_anh", "thieu_anh"),
                                          ("khong_logo", "khong_thay_logo")])
def test_moi_duong_truot_deu_ra_ma_ro(tmp_path, clip, kich_ban, ma):
    with pytest.raises(ad.LoiAgy) as e:
        ad.tim_box(clip.nguon, lenh=_agy_gia(tmp_path, kich_ban), model="m")
    assert e.value.ma == ma and e.value.ly_do


def test_khong_co_agy(monkeypatch, clip):
    monkeypatch.setenv("THAY_LOGO_AGY", "/khong/co/agy-nay")
    assert ad.tim_lenh_agy() is None
    with pytest.raises(ad.LoiAgy) as e:
        ad.tim_box(clip.nguon)
    assert e.value.ma == "khong_co_agy"


def test_bo_qua_nhan_logo_cua_minh(tmp_path, clip, monkeypatch):
    monkeypatch.setenv("THAY_LOGO_BO_QUA_NHAN", "mybrand")
    boxes, _ = ad.tim_box(clip.nguon, lenh=_agy_gia(tmp_path, "logo_nha"), model="m")
    assert boxes and all(b.y > 300 for b in boxes)  # chỉ còn watermark thật ở dưới; logo "My Brand" ở trên bị bỏ


def test_model_mac_dinh_va_env(monkeypatch):
    monkeypatch.delenv("THAY_LOGO_AGY_MODEL", raising=False)
    assert ad.model_agy() == ad.MODEL_MAC_DINH
    monkeypatch.setenv("THAY_LOGO_AGY_MODEL", "gemini-4-argon-low")
    assert ad.model_agy() == "gemini-4-argon-low" and ad.model_agy("x") == "x"
    assert os.environ["THAY_LOGO_AGY_MODEL"]
