// Tekent alle grafieken uit window.G. Draait in de browser en in de prerender-stap.
(function () {
  const NS = "http://www.w3.org/2000/svg";
  const MAAND = ["jan", "feb", "mrt", "apr", "mei", "jun", "jul", "aug", "sep", "okt", "nov", "dec"];
  const nl = (v, d) => v == null ? "–" : v.toLocaleString("nl-NL", { minimumFractionDigits: d, maximumFractionDigits: d });
  const FMT = {
    pct: v => nl(v, v >= 10 ? 0 : 1) + "%", pctAs: v => nl(v, 0) + "%",
    dec: v => nl(v, v >= 100 ? 0 : 1), decAs: v => nl(v, 0),
    int: v => nl(v, 0), intAs: v => nl(v, 0),
  };
  const el = (tag, attrs, parent) => {
    const e = document.createElementNS(NS, tag);
    for (const k in attrs) e.setAttribute(k, attrs[k]);
    if (parent) parent.appendChild(e);
    return e;
  };
  const txt = (parent, x, y, s, attrs = {}) => { const t = el("text", { x, y, ...attrs }, parent); t.textContent = s; return t; };
  const datum = s => new Date(s + "T00:00:00Z");
  const weekVan = d => { const t = new Date(d); t.setUTCDate(t.getUTCDate() + 4 - (t.getUTCDay() || 7)); const y = t.getUTCFullYear(); return [Math.ceil(((t - Date.UTC(y, 0, 1)) / 864e5 + 1) / 7), y]; };
  const wkLabel = s => { const [w, y] = weekVan(datum(s)); return `week ${w} van ${y}`; };
  const dagLabel = s => { const d = datum(s); return `${d.getUTCDate()} ${MAAND[d.getUTCMonth()]} ${d.getUTCFullYear()}`; };
  function nice(max) {
    if (!max || max <= 0) return [1, [0, 1]];
    const ruw = max / 4, mag = Math.pow(10, Math.floor(Math.log10(ruw)));
    const stap = [1, 2, 2.5, 5, 10].map(m => m * mag).find(s => s >= ruw);
    const top = Math.ceil(max / stap) * stap, ticks = [];
    for (let v = 0; v <= top + 1e-9; v += stap) ticks.push(+v.toFixed(10));
    return [top, ticks];
  }
  function tip(box) {
    let t = box.querySelector(".tip");
    if (!t) { t = document.createElement("div"); t.className = "tip"; box.appendChild(t); }
    return t;
  }
  function plaatsTip(t, box, x) {
    t.style.display = "block";
    const w = t.offsetWidth, bw = box.clientWidth;
    t.style.left = Math.max(0, Math.min(x + 14 > bw - w ? x - w - 14 : x + 14, bw - w)) + "px";
    t.style.top = "0px";
  }
  function regels(t, kop, rijen) {
    t.replaceChildren();
    const b = document.createElement("b"); b.textContent = kop; t.appendChild(b);
    rijen.forEach(([naam, kleur, waarde]) => {
      const r = document.createElement("div"); r.className = "tr";
      const n = document.createElement("span"); n.innerHTML = `<i class="sw" style="background:${kleur}"></i>`; n.append(naam);
      const v = document.createElement("span"); v.textContent = waarde; r.append(n, v); t.appendChild(r);
    });
  }

  // assen + raster; geeft schalen terug
  function assen(svg, W, H, ml, mt, mb, top, ticks, fmt) {
    const y = v => mt + (H - mt - mb) * (1 - v / top);
    ticks.forEach(v => {
      el("line", { x1: ml, x2: W, y1: y(v), y2: y(v), class: "grid" }, svg);
      txt(svg, ml - 6, y(v) + 4, fmt(v), { "text-anchor": "end" });
    });
    return y;
  }
  function linkerMarge(svg, ticks, fmt) {
    let m = 0;
    ticks.forEach(v => { const t = txt(svg, 0, 0, fmt(v)); m = Math.max(m, t.getComputedTextLength() || fmt(v).length * 7); t.remove(); });
    return Math.ceil(m) + 10;
  }

  function lijn(box, g) {
    const mini = box.classList.contains("mini");
    const W = box.clientWidth || 640, H = box.classList.contains("hoog") ? 360 : mini ? 130 : 260, mt = 10, mb = 26;
    const fmt = FMT[g.fmt], fmtAs = FMT[g.fmt + "As"];
    const alle = g.s.flatMap(s => s.p);
    if (!alle.length) return;
    const [top, ticks] = nice(Math.max(...alle.map(p => p[1])));
    const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, width: W, height: H });
    box.replaceChildren(svg);
    const ml = linkerMarge(svg, ticks, fmtAs);
    const y = assen(svg, W, H, ml, mt, mb, top, ticks, fmtAs);
    const t0 = Math.min(...alle.map(p => datum(p[0]))), t1 = Math.max(...alle.map(p => datum(p[0])));
    const x = d => ml + (W - ml - 6) * ((datum(d) - t0) / ((t1 - t0) || 1));
    // x-as: jaren, of maanden bij een korte periode
    const jaren = (t1 - t0) / 3.15e10;
    const start = new Date(t0), labels = [];
    for (let d = new Date(Date.UTC(start.getUTCFullYear(), start.getUTCMonth() + 1, 1)); d <= t1; d.setUTCMonth(d.getUTCMonth() + 1)) {
      const m = d.getUTCMonth();
      if (jaren > 2.5 ? m === 0 : jaren > 1.2 ? m % 3 === 0 : true) labels.push(new Date(d));
    }
    const minAfstand = 46; let laatste = -1e9;
    labels.forEach(d => {
      const xx = ml + (W - ml - 6) * ((d - t0) / ((t1 - t0) || 1));
      if (xx - laatste < minAfstand) return; laatste = xx;
      el("line", { x1: xx, x2: xx, y1: H - mb, y2: H - mb + 4, class: "as" }, svg);
      txt(svg, xx, H - 8, d.getUTCMonth() === 0 ? String(d.getUTCFullYear()) : MAAND[d.getUTCMonth()], { "text-anchor": "middle" });
    });
    el("line", { x1: ml, x2: W, y1: H - mb, y2: H - mb, class: "as" }, svg);
    g.s.forEach(s => {
      let d = "", vorige = null;
      s.p.forEach(p => {
        const gat = vorige && (datum(p[0]) - datum(vorige)) > 15 * 864e5;
        d += (d && !gat ? "L" : "M") + x(p[0]).toFixed(1) + "," + y(p[1]).toFixed(1);
        vorige = p[0];
      });
      el("path", { d, fill: "none", stroke: s.kleur, "stroke-width": s.dun ? 1 : 2.25, opacity: s.dun ? 0.35 : 1, "stroke-linejoin": "round" }, svg);
      const l = s.p[s.p.length - 1];
      if (l && !s.dun) el("circle", { cx: x(l[0]), cy: y(l[1]), r: 3.5, fill: s.kleur }, svg);
    });
    // tooltip
    const t = tip(box), gids = el("line", { y1: mt, y2: H - mb, class: "gids" }, svg);
    const stippen = g.s.map(s => el("circle", { r: 4, fill: s.kleur, class: "stip" }, svg));
    const datums = [...new Set(alle.map(p => p[0]))].sort();
    const idx = g.s.map(s => Object.fromEntries(s.p));
    const zet = px => {
      const sx = px * W / svg.getBoundingClientRect().width;
      let best = datums[0], bd = 1e9;
      datums.forEach(d => { const a = Math.abs(x(d) - sx); if (a < bd) { bd = a; best = d; } });
      const cx = x(best);
      gids.setAttribute("x1", cx); gids.setAttribute("x2", cx); gids.style.opacity = 1;
      g.s.forEach((s, i) => { const v = idx[i][best]; stippen[i].style.opacity = v == null ? 0 : 1; if (v != null) { stippen[i].setAttribute("cx", cx); stippen[i].setAttribute("cy", y(v)); } });
      regels(t, g.dag ? dagLabel(best) : wkLabel(best), g.s.map((s, i) => [s.naam, s.kleur, idx[i][best] == null ? "geen cijfer" : fmt(idx[i][best])]));
      plaatsTip(t, box, cx * svg.getBoundingClientRect().width / W);
    };
    vang(svg, box, W, H, zet, () => { t.style.display = "none"; gids.style.opacity = 0; stippen.forEach(s => s.style.opacity = 0); });
  }

  function seizoen(box, g) {
    const W = box.clientWidth || 640, H = 260, mt = 10, mb = 26, fmt = FMT[g.fmt], fmtAs = FMT[g.fmt + "As"];
    const alle = g.s.flatMap(s => s.p);
    if (!alle.length) return;
    const [top, ticks] = nice(Math.max(...alle.map(p => p[1])));
    const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, width: W, height: H });
    box.replaceChildren(svg);
    const ml = linkerMarge(svg, ticks, fmtAs), mr = 56;
    const y = assen(svg, W - mr, H, ml, mt, mb, top, ticks, fmtAs);
    const x = i => ml + (W - mr - ml) * (i / 52);
    (W < 520 ? [[0, "okt"], [13, "jan"], [26, "apr"], [39, "jul"]] : [[0, "okt"], [9, "dec"], [13, "jan"], [22, "mrt"], [31, "mei"], [39, "jul"], [48, "sep"]]).forEach(([i, m]) => {
      el("line", { x1: x(i), x2: x(i), y1: H - mb, y2: H - mb + 4, class: "as" }, svg);
      txt(svg, x(i), H - 8, m, { "text-anchor": "middle" });
    });
    el("line", { x1: ml, x2: W - mr, y1: H - mb, y2: H - mb, class: "as" }, svg);
    const volgorde = [...g.s].sort((a, b) => a.nu - b.nu);
    volgorde.forEach((s, k) => {
      const d = s.p.map((p, i) => (i ? "L" : "M") + x(p[0]).toFixed(1) + "," + y(p[1]).toFixed(1)).join("");
      el("path", { d, fill: "none", stroke: s.kleur, "stroke-width": s.nu ? 2.75 : 1.5, opacity: s.nu ? 1 : 0.35 + 0.5 * k / g.s.length }, svg);
      const l = s.p[s.p.length - 1];
      if (s.nu && l) el("circle", { cx: x(l[0]), cy: y(l[1]), r: 4, fill: s.kleur }, svg);
    });
    // seizoensnamen aan het eind, uit elkaar geschoven
    const eind = g.s.map(s => ({ s, l: s.p[s.p.length - 1] })).filter(e => e.l).map(e => ({ ...e, yy: Math.min(y(e.l[1]) + 4, H - mb - 2) })).sort((a, b) => b.yy - a.yy);
    eind.forEach((e, i) => { if (i && eind[i - 1].yy - e.yy < 13) e.yy = eind[i - 1].yy - 13; });
    eind.forEach(e => txt(svg, (e.s.nu ? x(e.l[0]) : W - mr) + 6, e.yy, e.s.naam, { class: e.s.nu ? "nu" : "", style: e.s.nu ? `fill:${e.s.kleur};font-weight:500` : "" }));
    const t = tip(box), gids = el("line", { y1: mt, y2: H - mb, class: "gids" }, svg);
    const idx = g.s.map(s => Object.fromEntries(s.p.map(p => [p[0], p])));
    const zet = px => {
      const sx = px * W / svg.getBoundingClientRect().width;
      const i = Math.max(0, Math.min(52, Math.round((sx - ml) / (W - mr - ml) * 52)));
      gids.setAttribute("x1", x(i)); gids.setAttribute("x2", x(i)); gids.style.opacity = 1;
      const hier = g.s.map((s, k) => idx[k][i]).find(Boolean);
      regels(t, hier ? `week ${weekVan(datum(hier[2]))[0]}` : "", [...g.s].reverse().map((s, k2) => { const k = g.s.length - 1 - k2; const p = idx[k][i]; return [s.naam, s.kleur, p ? fmt(p[1]) : "–"]; }));
      plaatsTip(t, box, x(i) * svg.getBoundingClientRect().width / W);
    };
    vang(svg, box, W, H, zet, () => { t.style.display = "none"; gids.style.opacity = 0; });
  }

  function staaf(box, g) {
    const W = box.clientWidth || 640, rh = 34, H = g.s.length * rh + 4;
    const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, width: W, height: H });
    box.replaceChildren(svg);
    const smal = W < 480;
    let ml = 0;
    const namen = g.s.map((s, i) => { const t = txt(svg, 0, i * rh + rh / 2 + 4, s.naam); ml = Math.max(ml, t.getComputedTextLength() || s.naam.length * 7); return t; });
    ml = Math.min(ml + 12, W * (smal ? 0.42 : 0.32));
    namen.forEach(t => { let s = t.textContent; while ((t.getComputedTextLength() || 0) > ml - 12 && s.length > 4) { s = s.slice(0, -2); t.textContent = s + "…"; } });
    const maxB = Math.max(...g.s.map(s => s.b)), cap = maxB * 1.5;
    const mr = 92, x = v => ml + (W - ml - mr) * Math.min(v, cap) / Math.max(maxB, ...g.s.map(s => Math.min(s.a, cap)));
    g.s.forEach((s, i) => {
      const y0 = i * rh + 6, a = el("a", { href: s.href }, svg);
      el("rect", { x: ml, y: y0, width: Math.max(1, x(s.a) - ml), height: 9, rx: 2, fill: "var(--grijs)" }, a);
      el("rect", { x: ml, y: y0 + 11, width: Math.max(1, x(s.b) - ml), height: 12, rx: 2, fill: "var(--griep)" }, a);
      txt(a, x(s.b) + 6, y0 + 21, nl(s.b, 0), { class: "waarde" });
      if (s.a > cap) txt(a, x(cap) + 6, y0 + 8, `${g.la}: ${nl(s.a, 0)} ›`);
      el("rect", { x: 0, y: i * rh, width: W, height: rh, fill: "transparent" }, a).appendChild(Object.assign(document.createElementNS(NS, "title"), { textContent: `${s.naam}: ${nl(s.a, 0)} in ${g.la}, ${nl(s.b, 0)} in ${g.lb}` }));
    });
  }

  function jaren(box, g) {
    const W = box.clientWidth || 640, H = 240, mt = 18, mb = 26;
    const [top, ticks] = nice(Math.max(...g.s.map(p => p[1] || 0)));
    const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, width: W, height: H });
    box.replaceChildren(svg);
    const ml = linkerMarge(svg, ticks, FMT.intAs);
    const y = assen(svg, W, H, ml, mt, mb, top, ticks, FMT.intAs);
    const bw = (W - ml) / g.s.length;
    g.s.forEach(([j, v], i) => {
      const xx = ml + i * bw;
      if (v == null) {  // niet meldingsplichtig in dat jaar
        txt(svg, xx + bw / 2, H - 8, W < 480 ? "'" + j.slice(2) : j, { "text-anchor": "middle" });
        txt(svg, xx + bw / 2, H - mb - 6, "–", { "text-anchor": "middle" }).appendChild(Object.assign(document.createElementNS(NS, "title"), { textContent: "niet meldingsplichtig" }));
        return;
      }
      el("rect", { x: xx + bw * .15, y: y(v), width: bw * .7, height: Math.max(0, H - mb - y(v)), rx: 2, fill: i === g.s.length - 1 ? g.kleur : "var(--grijs)" }, svg);
      txt(svg, xx + bw / 2, H - 8, W < 480 ? "'" + j.slice(2) : j, { "text-anchor": "middle" });
      txt(svg, xx + bw / 2, y(v) - 4, nl(v, 0), { "text-anchor": "middle", class: "waarde" });
    });
    el("line", { x1: ml, x2: W, y1: H - mb, y2: H - mb, class: "as" }, svg);
  }

  function vang(svg, box, W, H, zet, weg) {
    const r = el("rect", { x: 0, y: 0, width: W, height: H, fill: "transparent" }, svg);
    r.addEventListener("pointermove", e => zet(e.clientX - svg.getBoundingClientRect().left));
    r.addEventListener("pointerdown", e => zet(e.clientX - svg.getBoundingClientRect().left));
    r.addEventListener("pointerleave", weg);
  }

  function sparks() {
    document.querySelectorAll(".spark[data-v]").forEach(s => {
      const v = JSON.parse(s.dataset.v), mx = Math.max(...v.map(a => a || 0)), w = 90, h = 20;
      const svg = el("svg", { width: w, height: h, viewBox: `0 0 ${w} ${h}`, "aria-hidden": "true" });
      if (mx > 0) {
        const x = i => 2 + (w - 6) * i / (v.length - 1), y = a => h - 2 - (h - 4) * a / mx;
        let d = "", open = false;
        v.forEach((a, i) => { if (a == null) { open = false; return; } d += (open ? "L" : "M") + x(i) + "," + y(a); open = true; });
        el("path", { d, fill: "none", stroke: "var(--griep)", "stroke-width": 1.5 }, svg);
        const li = v.map((a, i) => a == null ? -1 : i).filter(i => i >= 0).pop();
        if (li != null) el("circle", { cx: x(li), cy: y(v[li]), r: 2.5, fill: "var(--griep)" }, svg);
      } else el("line", { x1: 2, x2: w - 2, y1: h - 2, y2: h - 2, class: "grid" }, svg);
      s.replaceChildren(svg);
    });
  }

  const TEKEN = { lijn, seizoen, staaf, jaren };
  function alles() {
    document.querySelectorAll(".chart[data-g]").forEach(box => {
      const g = (window.G || {})[box.dataset.g];
      if (g && TEKEN[g.t]) TEKEN[g.t](box, g);
    });
    sparks();
  }
  alles();
  let breedte = window.innerWidth, wacht;
  window.addEventListener("resize", () => {
    if (window.innerWidth === breedte) return;
    breedte = window.innerWidth; clearTimeout(wacht); wacht = setTimeout(alles, 120);
  });
})();
document.querySelectorAll("nav.top .in > a:not(.logo)").forEach(a => { if (location.pathname.startsWith(a.getAttribute("href"))) a.setAttribute("aria-current", "page"); });
