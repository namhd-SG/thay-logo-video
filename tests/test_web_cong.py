"""Kiểm cổng trước khi mở web: tắt tool rồi mở lại ngay không được báo nhầm cổng bận; cổng có máy chủ khác thì vẫn báo bận."""
import socket

import pytest

from thay_logo.web_app import cong_dang_ban


def _may_chu_vua_tat() -> int:
    """Mở một máy chủ, phục vụ một kết nối rồi tắt — để lại cổng ở TIME_WAIT như lúc vừa tắt tool."""
    may_chu = socket.socket()
    may_chu.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)  # như uvicorn
    may_chu.bind(("127.0.0.1", 0))
    may_chu.listen()
    cong = may_chu.getsockname()[1]
    khach = socket.create_connection(("127.0.0.1", cong))
    ket_noi, _ = may_chu.accept()
    ket_noi.close()  # máy chủ đóng trước ⇒ phía máy chủ giữ TIME_WAIT trên cổng này
    khach.close()
    may_chu.close()
    return cong


def test_mo_lai_ngay_sau_khi_tat_khong_bao_ban():
    cong = _may_chu_vua_tat()
    with socket.socket() as tran:  # đối chứng: bind không SO_REUSEADDR (cách kiểm cũ) vẫn bị từ chối lúc này
        try:
            tran.bind(("127.0.0.1", cong))
            cach_cu_bao_ban = False
        except OSError:
            cach_cu_bao_ban = True
    assert cach_cu_bao_ban, "không dựng được cổng TIME_WAIT — phép thử mất sức phân định"
    assert not cong_dang_ban(cong)


@pytest.mark.parametrize("dia_chi", ["127.0.0.1", "0.0.0.0"])
def test_cong_dang_co_may_chu_lang_nghe_van_bao_ban(dia_chi):
    with socket.socket() as khac:
        khac.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        khac.bind((dia_chi, 0))
        khac.listen()
        assert cong_dang_ban(khac.getsockname()[1])
