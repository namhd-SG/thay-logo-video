"""Tải MỘT file video từ link Google Drive công khai ("Bất kỳ ai có đường liên kết") bằng gdown — không cần đăng nhập.

Không hỗ trợ link thư mục và file riêng tư (gdown không có quyền đọc).
"""
from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

_MA = re.compile(r"^[A-Za-z0-9_-]{20,}$")


class LinkKhongHopLe(ValueError):
    pass


def ma_file_drive(link: str) -> str:
    """`…/file/d/<mã>/…`, `…?id=<mã>` (open, uc) hoặc mã trần ⇒ mã file. Link thư mục / link lạ ⇒ LinkKhongHopLe."""
    s = (link or "").strip()
    if _MA.match(s):
        return s
    u = urlsplit(s)
    if u.hostname not in ("drive.google.com", "docs.google.com"):
        raise LinkKhongHopLe("chỉ nhận link drive.google.com của MỘT file video")
    if "/folders/" in u.path:
        raise LinkKhongHopLe("đây là link THƯ MỤC — hãy mở thư mục và lấy link của từng video")
    m = re.search(r"/d/([A-Za-z0-9_-]{20,})", u.path)
    if m:
        return m.group(1)
    ma = parse_qs(u.query).get("id", [""])[0]
    if _MA.match(ma):
        return ma
    raise LinkKhongHopLe("không đọc được mã file trong link Drive này")


def tai_file_drive(ma: str, thu_muc: Path) -> tuple[Path, str]:
    """Tải về `thu_muc/goc<đuôi>`; trả (đường dẫn, tên gốc trên Drive). Lỗi quyền/không tồn tại ⇒ ném lỗi kèm lời dặn."""
    import gdown

    thu_muc.mkdir(parents=True, exist_ok=True)
    tam = thu_muc / "tai_ve"
    tam.mkdir(exist_ok=True)
    ra = gdown.download(id=ma, output=str(tam) + "/", quiet=True)
    if not ra or not Path(ra).is_file():
        raise RuntimeError("Drive không cho tải — kiểm tra link đã bật 'Bất kỳ ai có đường liên kết' chưa")
    p = Path(ra)
    dich = thu_muc / f"goc{p.suffix.lower() or '.mp4'}"
    p.replace(dich)
    tam.rmdir()
    return dich, p.name
