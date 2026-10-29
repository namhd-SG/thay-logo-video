// Trang chính: đưa video vào, theo dõi hàng đợi, thẻ duyệt trước/sau, Đạt/Hỏng, tải về. Màn khoanh ở khoanh.js (window.TL.moKhoanh).
// Chữ dữ liệu (tên file, lý do lỗi) luôn vào bằng textContent — không innerHTML với dữ liệu.
(() => {
  "use strict";
  const $ = (id) => document.getElementById(id);
  function el(tag, attrs = {}, ...con) {
    const e = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (v == null || v === false) continue;
      if (k === "class") e.className = v;
      else if (k === "text") e.textContent = v;
      else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
      else e.setAttribute(k, v === true ? "" : v);
    }
    for (const c of con.flat()) if (c != null && c !== false) e.append(c);
    return e;
  }
  async function goi(path, opts = {}) {
    const r = await fetch(path, opts);
    if (!r.ok) {
      let msg = `${r.status}`;
      try { const j = await r.json(); msg = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail); } catch (_) { /* không phải JSON */ }
      throw new Error(msg);
    }
    return r.status === 204 || r.status === 202 ? null : r.json().catch(() => null);
  }
  const guiJson = (path, method, body) => goi(path, { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  const baoLoi = (e) => { const p = $("loi-chung"); p.textContent = `Lỗi: ${e.message || e}`; p.hidden = false; setTimeout(() => { p.hidden = true; }, 8000); };

  // ---- giao diện sáng/tối (nhớ lựa chọn trong trình duyệt) ----
  const THEME_KEY = "thay-logo-theme";
  const apTheme = (t) => (t === "light" || t === "dark") ? document.documentElement.setAttribute("data-theme", t)
                                                        : document.documentElement.removeAttribute("data-theme");
  try { apTheme(localStorage.getItem(THEME_KEY)); } catch (_) { /* không có storage */ }
  $("theme-toggle").addEventListener("click", () => {
    const cur = document.documentElement.getAttribute("data-theme") || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
    const moi = cur === "dark" ? "light" : "dark";
    apTheme(moi);
    try { localStorage.setItem(THEME_KEY, moi); } catch (_) { /* bỏ qua */ }
  });

  // ---- trạng thái ----
  const NHAN = {
    dang_tai: ["Đang tải về", "chip-xu-ly"], cho_tim: ["Chờ agy tìm", "chip-xu-ly"], dang_tim: ["agy đang tìm", "chip-xu-ly"],
    cho_khoanh: ["Cần bạn khoanh", "chip-warn"], cho_chay: ["Chờ thay", "chip-xu-ly"], dang_chay: ["Đang thay", "chip-xu-ly"],
    xong: ["Chờ duyệt", "chip-ok"], khong_chac: ["Không chắc", "chip-warn"], loi: ["Lỗi", "chip-loi"],
  };
  const LOC = [
    ["tat_ca", "Tất cả", () => true],
    ["cho_duyet", "Chờ duyệt", (v) => v.trang_thai === "xong" && !v.danh_gia],
    ["can_ban", "Cần bạn xử lý", (v) => ["cho_khoanh", "khong_chac", "loi"].includes(v.trang_thai) || v.danh_gia === "hong"],
    ["dang_lam", "Đang làm", (v) => ["dang_tai", "cho_tim", "dang_tim", "cho_chay", "dang_chay"].includes(v.trang_thai)],
    ["da_dat", "Đã Đạt", (v) => v.danh_gia === "dat"],
  ];
  const S = { videos: [], loc: "tat_ca", agy: false, dauVet: "" };
  const DANG_LAM = new Set(["dang_tai", "cho_tim", "dang_tim", "cho_chay", "dang_chay"]);

  function giay(v) { return v.so_khung && v.fps ? `${(v.so_khung / v.fps).toFixed(1)} giây` : ""; }

  function nutDanhGia(v) {
    const dat = el("button", { type: "button", class: `btn dat${v.danh_gia === "dat" ? " on" : ""}`, text: "✓ Đạt",
      onclick: () => guiJson(`/api/videos/${v.id}/danh-gia`, "POST", { gia_tri: v.danh_gia === "dat" ? "" : "dat" }).then(tai).catch(baoLoi) });
    const hong = el("button", { type: "button", class: `btn hong${v.danh_gia === "hong" ? " on" : ""}`, text: "✕ Hỏng",
      onclick: () => guiJson(`/api/videos/${v.id}/danh-gia`, "POST", { gia_tri: v.danh_gia === "hong" ? "" : "hong" }).then(tai).catch(baoLoi) });
    return [dat, hong];
  }
  const nutKhoanh = (v, chu) => el("button", { type: "button", class: "btn", text: chu, onclick: () => window.TL.moKhoanh(v) });
  const nutTim = (v) => S.agy ? el("button", { type: "button", class: "btn ghost", text: "Nhờ agy tìm lại",
    onclick: () => goi(`/api/videos/${v.id}/tim`, { method: "POST" }).then(tai).catch(baoLoi) }) : null;
  const anh = (src, nhan, cls) => el("figure", { class: cls }, el("img", { src, alt: nhan, loading: "lazy", onclick: () => xemAnh(src) }),
    el("figcaption", { text: nhan }));
  const giuaVideo = (v) => `/api/videos/${v.id}/khung/${Math.floor((v.so_khung || 1) / 2)}.jpg`;

  function thanThe(v) {
    const kq = v.ket_qua || {};
    const l = `?l=${v.luot}`;
    switch (v.trang_thai) {
      case "dang_tai": return [el("div", { class: "dang-lam" }, el("span", { class: "quay" }), "Đang tải video về máy…")];
      case "cho_tim": case "dang_tim":
        return [el("div", { class: "dang-lam" }, el("span", { class: "quay" }),
          v.trang_thai === "dang_tim" ? "agy đang tìm logo cũ trên video (thường 30 giây – vài phút)…" : "Đang chờ tới lượt agy tìm…")];
      case "cho_chay": case "dang_chay":
        return [el("div", { class: "cap-anh" }, anh(giuaVideo(v), "Gốc", "mot")),
          el("div", { class: "dang-lam" }, el("span", { class: "quay" }),
            v.trang_thai === "dang_chay" ? `Đang thay logo (lượt ${v.luot})…` : `Đang chờ tới lượt thay · ${v.boxes.length} box mồi`)];
      case "cho_khoanh":
        return [
          v.loi ? el("p", { class: "ghi-chu warn", text: v.loi }) : el("p", { class: "ghi-chu", text: "Khoanh logo cũ ở vài khung để máy biết cần thay chỗ nào." }),
          el("div", { class: "cap-anh" }, anh(giuaVideo(v), "Gốc", "mot")),
          el("div", { class: "nut-hang" }, el("button", { type: "button", class: "btn primary", text: "Khoanh logo cũ", onclick: () => window.TL.moKhoanh(v) }), nutTim(v)),
        ];
      case "xong":
        return [
          el("div", { class: "cap-anh" }, anh(`/api/videos/${v.id}/anh/truoc${l}`, "Trước"), anh(`/api/videos/${v.id}/anh/sau${l}`, "Sau")),
          v.danh_gia === "hong" ? el("p", { class: "ghi-chu warn", text: "Bạn chấm Hỏng: khoanh thêm chỗ logo cũ còn lộ (hoặc chỗ máy đè sai) rồi chạy lại." }) : null,
          el("div", { class: "nut-hang" }, ...nutDanhGia(v), el("span", { class: "grow" }),
            el("a", { class: `btn${v.danh_gia === "dat" ? " primary" : ""}`, href: `/api/videos/${v.id}/ra.mp4?tai=1`, text: "⬇ Tải về" })),
          el("div", { class: "nut-hang" },
            el("button", { type: "button", class: "btn ghost", text: "▶ Xem video", onclick: (ev) => xemVideo(ev.target, v) }),
            kq.anh_soi ? el("button", { type: "button", class: "btn ghost", text: "Ảnh soi", onclick: () => xemAnh(`/api/videos/${v.id}/anh/soi${l}`) }) : null,
            nutKhoanh(v, "Khoanh thêm")),
        ];
      case "khong_chac":
        return [
          el("p", { class: "ghi-chu warn", text: `Máy chưa đủ chắc nên CHƯA thay (giữ nguyên gốc). ${v.loi || ""}` }),
          el("div", { class: "cap-anh" }, anh(kq.anh_truoc ? `/api/videos/${v.id}/anh/truoc${l}` : giuaVideo(v), "Gốc", "mot")),
          el("div", { class: "nut-hang" }, el("button", { type: "button", class: "btn primary", text: "Khoanh thêm", onclick: () => window.TL.moKhoanh(v) }), nutTim(v)),
        ];
      default:
        return [
          el("p", { class: "ghi-chu loi", text: v.loi || "Lỗi không rõ." }),
          el("div", { class: "nut-hang" }, v.so_khung ? nutKhoanh(v, "Khoanh lại") : null,
            v.boxes.length ? el("button", { type: "button", class: "btn", text: "Chạy lại", onclick: () => goi(`/api/videos/${v.id}/chay`, { method: "POST" }).then(tai).catch(baoLoi) }) : null),
        ];
    }
  }

  function the(v) {
    const [nhan, cls] = NHAN[v.trang_thai] || [v.trang_thai, ""];
    const canBan = ["cho_khoanh", "khong_chac"].includes(v.trang_thai) || (v.trang_thai === "xong" && !v.danh_gia);
    const meta = [v.rong && `${v.rong}×${v.cao}`, giay(v), v.luot ? `lượt ${v.luot}` : ""].filter(Boolean).join(" · ");
    return el("article", { class: `panel the${canBan ? " can-ban" : ""}`, "data-id": v.id },
      el("div", { class: "the-dau" },
        el("div", {}, el("div", { class: "ten", title: v.ten, text: v.ten }), el("div", { class: "meta", text: meta })),
        el("span", { class: `chip ${v.danh_gia === "hong" ? "chip-loi" : cls}`,
          text: v.danh_gia === "dat" ? "Đã Đạt" : v.danh_gia === "hong" ? "Hỏng" : nhan })),
      el("div", { class: "the-than" }, ...thanThe(v)),
      el("div", { class: "the-chan" }, el("span", { text: `#${v.id}` }),
        DANG_LAM.has(v.trang_thai) && v.trang_thai !== "cho_tim" ? null : el("button", { type: "button", class: "btn ghost danger", text: "Xoá",
          onclick: () => { if (confirm(`Xoá "${v.ten}" và mọi kết quả của nó?`)) goi(`/api/videos/${v.id}`, { method: "DELETE" }).then(tai).catch(baoLoi); } })));
  }

  function xemVideo(nut, v) {
    const cap = nut.closest(".the").querySelector(".cap-anh");
    cap.replaceChildren(el("figure", { class: "mot" }, el("video", { src: `/api/videos/${v.id}/ra.mp4?l=${v.luot}`, controls: true, autoplay: true }),
      el("figcaption", { text: "Sau" })));
    nut.remove();
  }
  function xemAnh(src) { $("xem-anh-img").src = src; $("xem-anh").hidden = false; }
  $("xem-anh").addEventListener("click", () => { $("xem-anh").hidden = true; });

  function veLoc() {
    $("loc").replaceChildren(...LOC.map(([k, chu, f]) => el("button", { type: "button", "aria-pressed": String(S.loc === k),
      onclick: () => { S.loc = k; veLoc(); veDs(); } }, chu, el("span", { class: "so", text: String(S.videos.filter(f).length) }))));
  }
  function veDs() {
    const f = LOC.find(([k]) => k === S.loc)[2];
    const ds = S.videos.filter(f);
    $("ds-video").replaceChildren(...ds.map(the));
    $("trong").hidden = S.videos.length > 0;
    const dem = (p) => S.videos.filter(p).length;
    $("tom-tat").textContent = S.videos.length
      ? `${S.videos.length} video · ${dem((v) => DANG_LAM.has(v.trang_thai))} đang làm · ${dem((v) => v.trang_thai === "xong" && !v.danh_gia)} chờ duyệt · ${dem((v) => v.danh_gia === "dat")} đã Đạt`
      : "Thay logo cũ (watermark) trong video bằng logo của bạn — chạy hoàn toàn trên máy này.";
  }

  async function tai() {
    try {
      const d = await goi("/api/trang-thai");
      S.agy = d.agy_bat;
      const chip = $("agy-chip");
      chip.textContent = d.agy_bat ? "agy: tự tìm BẬT" : "agy: TẮT — khoanh tay";
      chip.className = `chip ${d.agy_bat ? "chip-ok" : "chip-warn"}`;
      $("logo-mau").hidden = !d.logo_tuy_chinh;
      $("logo-nhan").textContent = d.logo_tuy_chinh ? "Logo mới của bạn" : "Logo mẫu (đổi thành logo của bạn)";
      const vet = JSON.stringify(d.videos);
      if (vet !== S.dauVet && !window.TL.dangKhoanh()) {
        S.dauVet = vet;
        S.videos = d.videos;
        veLoc();
        veDs();
      }
    } catch (e) {
      $("tom-tat").textContent = `Mất kết nối tới máy chủ (${e.message}). Cửa sổ Terminal chạy "thay-logo web" còn mở không?`;
    }
  }

  // ---- tabs đưa video vào ----
  document.querySelectorAll(".tab").forEach((t) => t.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((x) => x.setAttribute("aria-selected", String(x === t)));
    $("tab-may").hidden = t.dataset.tab !== "may";
    $("tab-link").hidden = t.dataset.tab !== "link";
  }));

  function taiLenMot(file) {
    const prog = el("progress", { max: "100", value: "0" });
    const pct = el("span", { class: "mono", text: "0%" });
    const dong = el("div", { class: "tien-do-dong" }, el("span", { class: "ten", title: file.name, text: file.name }), prog, pct);
    $("tien-do").append(dong);
    return new Promise((xong) => {
      const fd = new FormData();
      fd.append("file", file);
      const x = new XMLHttpRequest();
      x.open("POST", "/api/videos");
      x.upload.onprogress = (e) => { if (e.lengthComputable) { const p = Math.round(100 * e.loaded / e.total); prog.value = p; pct.textContent = `${p}%`; } };
      x.onload = () => {
        if (x.status < 300) { pct.textContent = "✓"; setTimeout(() => dong.remove(), 2500); }
        else { let m = x.status; try { m = JSON.parse(x.responseText).detail; } catch (_) { /* giữ mã */ } pct.textContent = "✕"; dong.title = String(m); baoLoi(new Error(m)); }
        tai();
        xong();
      };
      x.onerror = () => { pct.textContent = "✕"; baoLoi(new Error("mất kết nối khi tải lên")); xong(); };
      x.send(fd);
    });
  }
  async function taiLenNhieu(files) { for (const f of files) await taiLenMot(f); }  // lần lượt: đĩa + máy chủ không bị dồn
  $("file-video").addEventListener("change", (e) => { taiLenNhieu([...e.target.files]); e.target.value = ""; });
  const tha = $("tha-vao");
  ["dragenter", "dragover"].forEach((t) => tha.addEventListener(t, (e) => { e.preventDefault(); tha.classList.add("keo"); }));
  ["dragleave", "drop"].forEach((t) => tha.addEventListener(t, (e) => { e.preventDefault(); tha.classList.remove("keo"); }));
  tha.addEventListener("drop", (e) => taiLenNhieu([...e.dataTransfer.files]));

  $("form-link").addEventListener("submit", async (e) => {
    e.preventDefault();
    $("loi-link").textContent = "";
    try { await guiJson("/api/videos/drive", "POST", { link: $("o-link").value }); $("o-link").value = ""; tai(); }
    catch (err) { $("loi-link").textContent = err.message; }
  });

  // ---- logo ----
  const lamMoiLogo = () => { $("logo-anh").src = `/api/logo.png?t=${Date.now()}`; tai(); };
  $("logo-file").addEventListener("change", async (e) => {
    const f = e.target.files[0];
    e.target.value = "";
    if (!f) return;
    const fd = new FormData();
    fd.append("file", f);
    try { await goi("/api/logo", { method: "POST", body: fd }); lamMoiLogo(); } catch (err) { baoLoi(err); }
  });
  $("logo-mau").addEventListener("click", () => goi("/api/logo", { method: "DELETE" }).then(lamMoiLogo).catch(baoLoi));

  window.TL = Object.assign(window.TL || {}, { $, el, goi, guiJson, tai, baoLoi, dangKhoanh: () => false });
  tai();
  setInterval(tai, 2000);
})();
