// Màn khoanh: kéo chuột quanh logo cũ trên từng khung ⇒ box mồi (toạ độ PIXEL của video gốc) ⇒ Lưu / Lưu & chạy.
// Mỗi (khung, logo #) giữ tối đa MỘT box: khoanh lại trên cùng khung = thay box cũ. Box agy tìm sẵn hiện cùng, sửa/xoá được.
(() => {
  "use strict";
  const { $, el, goi, guiJson, tai, baoLoi } = window.TL;
  const CANH_TOI_THIEU = 4;  // px video — nhỏ hơn coi như bấm nhầm (máy chủ cũng chặn)
  const MAU = ["#2fd3c0", "#ff9b3d"];
  let S = null;  // { v, khung, boxes:[{khung,x,y,w,h,cum,nguon}], cum, keo, hen }

  const anh = $("khung-anh"), ve = $("khung-ve"), thanh = $("thanh-khung");

  function moKhoanh(v) {
    S = { v, khung: 0, cum: 0, keo: null, hen: null,
          boxes: (v.boxes || []).map((b) => ({ ...b, cum: b.cum == null ? 0 : b.cum, nguon: b.nguon || "tay" })) };
    $("khoanh-ten").textContent = `Khoanh logo cũ — ${v.ten}`;
    $("khoanh-loi").textContent = "";
    thanh.max = String(Math.max(0, v.so_khung - 1));
    const dau = S.boxes.length ? Math.min(...S.boxes.map((b) => b.khung)) : Math.floor(v.so_khung / 2);
    $("khoanh").hidden = false;
    toiKhung(dau);
    veBen();
  }
  const dongKhoanh = () => { $("khoanh").hidden = true; S = null; tai(); };

  function toiKhung(k) {
    if (!S) return;
    S.khung = Math.max(0, Math.min(S.v.so_khung - 1, Math.round(k)));
    thanh.value = String(S.khung);
    const t = S.v.fps ? (S.khung / S.v.fps).toFixed(2) : "?";
    $("vi-tri").textContent = `khung ${S.khung}/${S.v.so_khung - 1} · ${t}s`;
    clearTimeout(S.hen);  // kéo thanh nhanh ⇒ chỉ tải ảnh khi dừng tay
    S.hen = setTimeout(() => { anh.src = `/api/videos/${S.v.id}/khung/${S.khung}.jpg`; }, 80);
    veKhung();
    veBen();
  }
  anh.addEventListener("load", () => { ve.width = anh.naturalWidth; ve.height = anh.naturalHeight; veKhung(); });

  // toạ độ chuột ⇒ pixel video (canvas có cỡ đúng bằng khung gốc, CSS co giãn)
  function diem(e) {
    const r = ve.getBoundingClientRect();
    return [(e.clientX - r.left) * ve.width / r.width, (e.clientY - r.top) * ve.height / r.height];
  }
  ve.addEventListener("pointerdown", (e) => { if (!S) return; ve.setPointerCapture(e.pointerId); const [x, y] = diem(e); S.keo = { x0: x, y0: y, x1: x, y1: y }; });
  ve.addEventListener("pointermove", (e) => { if (!S || !S.keo) return; const [x, y] = diem(e); S.keo.x1 = x; S.keo.y1 = y; veKhung(); });
  ve.addEventListener("pointerup", () => {
    if (!S || !S.keo) return;
    const k = S.keo;
    S.keo = null;
    const W = ve.width, H = ve.height;
    const x0 = Math.max(0, Math.min(k.x0, k.x1)), y0 = Math.max(0, Math.min(k.y0, k.y1));
    const x1 = Math.min(W, Math.max(k.x0, k.x1)), y1 = Math.min(H, Math.max(k.y0, k.y1));
    const box = { khung: S.khung, x: Math.round(x0), y: Math.round(y0), w: Math.round(x1 - x0), h: Math.round(y1 - y0), cum: S.cum, nguon: "tay" };
    if (box.w >= CANH_TOI_THIEU && box.h >= CANH_TOI_THIEU) {
      S.boxes = S.boxes.filter((b) => !(b.khung === box.khung && b.cum === box.cum));
      S.boxes.push(box);
      S.boxes.sort((a, b) => a.khung - b.khung || a.cum - b.cum);
    }
    veKhung();
    veBen();
  });

  function veKhung() {
    if (!S || !ve.width) return;
    const c = ve.getContext("2d");
    c.clearRect(0, 0, ve.width, ve.height);
    const net = Math.max(2, Math.round(ve.width / 360));
    for (const b of S.boxes) {  // box ở khung KHÁC: viền mờ đứt nét — để thấy logo trôi tới đâu
      if (b.khung === S.khung) continue;
      c.setLineDash([net * 3, net * 3]); c.lineWidth = net / 1.5; c.strokeStyle = MAU[b.cum % 2] + "66";
      c.strokeRect(b.x, b.y, b.w, b.h);
    }
    c.setLineDash([]);
    for (const b of S.boxes.filter((z) => z.khung === S.khung)) {
      c.lineWidth = net; c.strokeStyle = MAU[b.cum % 2]; c.strokeRect(b.x, b.y, b.w, b.h);
      c.fillStyle = MAU[b.cum % 2]; c.font = `${12 * net}px sans-serif`;
      c.fillText(`#${b.cum + 1}${b.nguon === "agy" ? " agy" : ""}`, b.x, Math.max(12 * net, b.y - 4));
    }
    if (S.keo) {
      const k = S.keo;
      c.lineWidth = net; c.strokeStyle = "#fff"; c.setLineDash([net * 2, net * 2]);
      c.strokeRect(Math.min(k.x0, k.x1), Math.min(k.y0, k.y1), Math.abs(k.x1 - k.x0), Math.abs(k.y1 - k.y0));
    }
  }

  function veBen() {
    if (!S) return;
    const soCum = Math.max(2, ...S.boxes.map((b) => b.cum + 1));
    const cuaCum = S.boxes.filter((b) => b.cum === S.cum).length;
    $("cum-chon").replaceChildren(...Array.from({ length: soCum }, (_, i) => el("button", { type: "button", "aria-pressed": String(S.cum === i),
      style: `border-left: 4px solid ${MAU[i % 2]}`, text: `Logo cũ #${i + 1}`, onclick: () => { S.cum = i; veBen(); } })),
      // agy khoanh nhầm cả một vật thể (không phải logo) ⇒ bỏ cả nhóm đó một lần rồi chạy lại
      cuaCum ? el("button", { type: "button", class: "xoa-cum", text: `Xoá ${cuaCum} box của #${S.cum + 1}`,
        onclick: () => { S.boxes = S.boxes.filter((b) => b.cum !== S.cum); veKhung(); veBen(); } }) : null);
    $("dem-box").textContent = `· ${S.boxes.length} box`;
    $("ds-box").replaceChildren(...(S.boxes.length ? S.boxes.map((b) => el("div", { class: `dong-box${b.khung === S.khung ? " hien" : ""}` },
      el("span", { class: `mau${b.cum % 2 ? " c1" : ""}` }),
      el("span", { class: "mono", text: `#${b.cum + 1} · khung ${b.khung} · ${b.x},${b.y} ${b.w}×${b.h}${b.nguon === "agy" ? " · agy" : ""}` }),
      el("button", { type: "button", text: "Tới", onclick: () => toiKhung(b.khung) }),
      el("button", { type: "button", text: "Xoá", onclick: () => { S.boxes = S.boxes.filter((z) => z !== b); veKhung(); veBen(); } })))
      : [el("p", { class: "muted nho", text: "Chưa có box. Kéo chuột quanh logo cũ trên khung hình bên trái." })]));
    const n = Math.max(1, S.v.so_khung - 1);
    $("dai-box").replaceChildren(...S.boxes.map((b) => el("i", { class: b.cum % 2 ? "c1" : "", style: `left:${(100 * b.khung / n).toFixed(2)}%` })));
  }

  async function luu(chay) {
    $("khoanh-loi").textContent = "";
    if (chay && !S.boxes.length) { $("khoanh-loi").textContent = "Cần khoanh ít nhất một khung."; return; }
    try {
      await guiJson(`/api/videos/${S.v.id}/boxes`, "PUT", { boxes: S.boxes });
      if (chay) await goi(`/api/videos/${S.v.id}/chay`, { method: "POST" });
      dongKhoanh();
    } catch (e) { $("khoanh-loi").textContent = e.message; }
  }

  thanh.addEventListener("input", () => toiKhung(Number(thanh.value)));
  document.querySelectorAll("[data-buoc]").forEach((b) => b.addEventListener("click", () => toiKhung(S.khung + Number(b.dataset.buoc))));
  document.addEventListener("keydown", (e) => {
    if (!S) return;
    if (e.key === "Escape") dongKhoanh();
    else if (e.key === "ArrowLeft" || e.key === "ArrowRight") {
      e.preventDefault();
      toiKhung(S.khung + (e.key === "ArrowLeft" ? -1 : 1) * (e.shiftKey ? 10 : 1));
    }
  });
  $("khoanh-dong").addEventListener("click", dongKhoanh);
  $("khoanh-chay").addEventListener("click", () => luu(true));
  $("khoanh-luu").addEventListener("click", () => luu(false));

  Object.assign(window.TL, { moKhoanh, dangKhoanh: () => S !== null });
  void baoLoi;
})();
