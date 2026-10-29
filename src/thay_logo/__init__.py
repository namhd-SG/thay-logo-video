"""Thay logo trong video: tự bám watermark (đứng yên hoặc trôi), chặn mọi khung chưa chắc, rồi tô lấp + dán logo mới.

Luật an toàn cứng (đọc trước khi sửa bất kỳ cổng nào): khung không qua đủ mọi cổng ⇒ KHÔNG render, giữ nguyên watermark.
Thà để sót watermark còn hơn tô lấp + dán logo lên nội dung sạch.

Điểm vào cho người dùng: `thay_logo.cli` (lệnh `thay-logo`).
"""
import os

# Đè lại khung bị cổng nội dung chặn khi đã biết chỗ (cong.de_khi_biet_cho) — BẬT mặc định. Tắt: đặt biến môi trường
# THAY_LOGO_DE_KHI_BIET=off (hoặc 0 / false / no, không phân biệt hoa thường) ⇒ cổng chặt hơn, ít khung được thay hơn.
GIA_TRI_TAT = ("off", "0", "false", "no")


def de_khi_biet_bat(gia_tri: str | None) -> bool:
    return (gia_tri or "").strip().lower() not in GIA_TRI_TAT


DE_KHI_BIET = de_khi_biet_bat(os.environ.get("THAY_LOGO_DE_KHI_BIET"))
