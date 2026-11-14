/* CampusRAG · 液态玻璃
   折射规则来自观默 @guanmo_ai 开源令牌（guanmo-ai/design-style · 014-liquid-glass）：
   折射量 = 边缘坡度；位移 = 向内法线 × bevel × edge × t^2.4 − (p − 中心) × mag；
   光源锁定左上 −37°；色散 6%。网页实现为原创，未复制其源码。
   Chromium 用 backdrop-filter: url(#lens)；其他浏览器退回现有磨砂玻璃。 */
(function () {
  const SS = 2;
  const EDGE = 0.9;
  const CHROMA = 0.06;
  const LIGHT = { x: -0.6, y: -0.8 };
  const PRESETS = {
    thin:    { bevel: 12, mag: 0.03, frost: 0 },
    regular: { bevel: 26, mag: 0.04, frost: 0 },
    thick:   { bevel: 44, mag: 0.06, frost: 0 },
    label:   { bevel: 44, mag: 0.06, frost: 6 }
  };

  const reducedT = matchMedia("(prefers-reduced-transparency: reduce)").matches;
  const canLens = !reducedT && (window.CSS && CSS.supports("backdrop-filter", "url(#lg-x)"));
  if (!canLens) return;

  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("id", "lg-defs");
  svg.setAttribute("aria-hidden", "true");
  svg.setAttribute("width", "0");
  svg.setAttribute("height", "0");
  svg.style.cssText = "position:absolute;width:0;height:0;overflow:hidden";
  const defs = document.createElementNS("http://www.w3.org/2000/svg", "defs");
  svg.appendChild(defs);
  document.documentElement.appendChild(svg);

  let uid = 0;
  const cache = new Map();

  function sdfRoundRect(px, py, w, h, radius) {
    const cx = w / 2, cy = h / 2;
    const r = Math.max(0.5, Math.min(radius, Math.min(w, h) / 2));
    const qx = Math.abs(px - cx) - (w / 2 - r);
    const qy = Math.abs(py - cy) - (h / 2 - r);
    const out = Math.hypot(Math.max(qx, 0), Math.max(qy, 0)) + Math.min(Math.max(qx, qy), 0) - r;
    return -out;
  }

  function makeLens(w, h, radius, preset) {
    const key = [Math.round(w), Math.round(h), Math.round(radius * 10), preset.bevel, preset.mag, (w * h > 120000) ? 1 : 2].join(":");
    if (cache.has(key)) return cache.get(key);

    const ss = (w * h > 120000) ? 1 : SS;
    const nx = Math.max(2, Math.round(w * ss));
    const ny = Math.max(2, Math.round(h * ss));
    const d = new Float32Array(nx * ny);
    for (let y = 0; y < ny; y++) {
      const py = (y + 0.5) / ss;
      for (let x = 0; x < nx; x++) {
        d[y * nx + x] = sdfRoundRect((x + 0.5) / ss, py, w, h, radius);
      }
    }

    const inv = ss;
    const dxA = new Float32Array(nx * ny);
    const dyA = new Float32Array(nx * ny);
    let maxAbs = 1;
    const cx = w / 2, cy = h / 2;
    const bevel = preset.bevel;
    const mag = preset.mag;
    for (let y = 0; y < ny; y++) {
      for (let x = 0; x < nx; x++) {
        const i = y * nx + x;
        const xm = x > 0 ? x - 1 : x;
        const xp = x + 1 < nx ? x + 1 : x;
        const ym = y > 0 ? y - 1 : y;
        const yp = y + 1 < ny ? y + 1 : y;
        const gx = (d[y * nx + xp] - d[y * nx + xm]) * inv / (xp - xm);
        const gy = (d[yp * nx + x] - d[ym * nx + x]) * inv / (yp - ym);
        const gl = Math.hypot(gx, gy) + 1e-6;
        const inx = gx / gl, iny = gy / gl;
        const t = Math.min(1, Math.max(0, 1 - d[i] / bevel));
        const slope = Math.pow(t, 2.4);
        const px = (x + 0.5) / ss;
        const py = (y + 0.5) / ss;
        const dx = inx * slope * bevel * EDGE - (px - cx) * mag;
        const dy = iny * slope * bevel * EDGE - (py - cy) * mag;
        dxA[i] = dx;
        dyA[i] = dy;
        if (d[i] > 0) {
          const a = Math.max(Math.abs(dx), Math.abs(dy));
          if (a > maxAbs) maxAbs = a;
        }
      }
    }
    const scale = 2 * maxAbs + 2;

    const mapC = document.createElement("canvas");
    const overC = document.createElement("canvas");
    mapC.width = overC.width = nx;
    mapC.height = overC.height = ny;
    const mapCtx = mapC.getContext("2d");
    const overCtx = overC.getContext("2d");
    const mapImg = mapCtx.createImageData(nx, ny);
    const overImg = overCtx.createImageData(nx, ny);
    const md = mapImg.data, od = overImg.data;

    let lx = LIGHT.x, ly = LIGHT.y;
    const ll = Math.hypot(lx, ly);
    lx /= ll; ly /= ll;

    for (let y = 0; y < ny; y++) {
      for (let x = 0; x < nx; x++) {
        const i = y * nx + x;
        const di = d[i];
        const inside = Math.min(1, Math.max(0, di * ss + 0.5));
        const j = i * 4;
        md[j]     = Math.min(255, Math.max(0, (0.5 + dxA[i] / scale) * 255));
        md[j + 1] = Math.min(255, Math.max(0, (0.5 + dyA[i] / scale) * 255));
        md[j + 2] = 128;
        md[j + 3] = inside * 255;

        const xm = x > 0 ? x - 1 : x;
        const xp = x + 1 < nx ? x + 1 : x;
        const ym = y > 0 ? y - 1 : y;
        const yp = y + 1 < ny ? y + 1 : y;
        const gx = (d[y * nx + xp] - d[y * nx + xm]) * inv / (xp - xm);
        const gy = (d[yp * nx + x] - d[ym * nx + x]) * inv / (yp - ym);
        const gl = Math.hypot(gx, gy) + 1e-6;
        const inx = gx / gl, iny = gy / gl;
        const facing = -(inx * lx + iny * ly);
        const band = Math.exp(-Math.max(di, 0) / 2.2) * inside;
        const wide = Math.pow(Math.min(1, Math.max(0, 1 - di / (bevel * 0.9))), 3) * inside;
        const pos = Math.max(0, facing);
        const neg = Math.max(0, -facing);
        let hi = Math.pow(pos, 1.6) * (0.95 * band + 0.35 * wide) * 0.85;
        hi += Math.pow(neg, 2) * band * 0.45 * 0.85;
        const lo = neg * wide * 0.10;
        const aTint = 0.06 * inside;
        const A = Math.min(1, hi + lo + aTint);
        od[j]     = A > 1e-6 ? (255 * hi + 255 * aTint) / A : 0;
        od[j + 1] = A > 1e-6 ? (255 * hi + 255 * aTint) / A : 0;
        od[j + 2] = A > 1e-6 ? (255 * hi + 255 * aTint) / A : 0;
        od[j + 3] = A * 255;
      }
    }
    mapCtx.putImageData(mapImg, 0, 0);
    overCtx.putImageData(overImg, 0, 0);
    const out = { map: mapC.toDataURL("image/png"), overlay: overC.toDataURL("image/png"), scale };
    cache.set(key, out);
    return out;
  }

  function upsertFilter(id, lens) {
    const old = defs.querySelector("#" + id);
    if (old) old.remove();
    const s = lens.scale;
    const ns = "http://www.w3.org/2000/svg";
    const filter = document.createElementNS(ns, "filter");
    filter.setAttribute("id", id);
    filter.setAttribute("color-interpolation-filters", "sRGB");
    filter.setAttribute("filterUnits", "objectBoundingBox");
    filter.setAttribute("primitiveUnits", "userSpaceOnUse");
    filter.setAttribute("x", "0");
    filter.setAttribute("y", "0");
    filter.setAttribute("width", "1");
    filter.setAttribute("height", "1");
    const feImage = document.createElementNS(ns, "feImage");
    feImage.setAttribute("href", lens.map);
    feImage.setAttributeNS("http://www.w3.org/1999/xlink", "href", lens.map);
    feImage.setAttribute("x", "0");
    feImage.setAttribute("y", "0");
    feImage.setAttribute("width", "1");
    feImage.setAttribute("height", "1");
    feImage.setAttribute("preserveAspectRatio", "none");
    feImage.setAttribute("result", "map");
    filter.appendChild(feImage);
    function disp(scale, result) {
      const n = document.createElementNS(ns, "feDisplacementMap");
      n.setAttribute("in", "SourceGraphic");
      n.setAttribute("in2", "map");
      n.setAttribute("scale", scale.toFixed(2));
      n.setAttribute("xChannelSelector", "R");
      n.setAttribute("yChannelSelector", "G");
      n.setAttribute("result", result);
      filter.appendChild(n);
    }
    disp(s * (1 + CHROMA), "dr");
    disp(s, "dg");
    disp(s * (1 - CHROMA), "db");
    function mat(src, values, result) {
      const n = document.createElementNS(ns, "feColorMatrix");
      n.setAttribute("in", src);
      n.setAttribute("type", "matrix");
      n.setAttribute("values", values);
      n.setAttribute("result", result);
      filter.appendChild(n);
    }
    mat("dr", "1 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 1 0", "r");
    mat("dg", "0 0 0 0 0  0 1 0 0 0  0 0 0 0 0  0 0 0 1 0", "g");
    mat("db", "0 0 0 0 0  0 0 0 0 0  0 0 1 0 0  0 0 0 1 0", "b");
    function comp(a, b, result) {
      const n = document.createElementNS(ns, "feComposite");
      n.setAttribute("in", a);
      n.setAttribute("in2", b);
      n.setAttribute("operator", "arithmetic");
      n.setAttribute("k2", "1");
      n.setAttribute("k3", "1");
      n.setAttribute("result", result);
      filter.appendChild(n);
    }
    comp("r", "g", "rg");
    comp("rg", "b", "rgb0");
    mat("rgb0", "1 0 0 0 0  0 1 0 0 0  0 0 1 0 0  0 0 0 0 1", "rgb");
    const clip = document.createElementNS(ns, "feComposite");
    clip.setAttribute("in", "rgb");
    clip.setAttribute("in2", "map");
    clip.setAttribute("operator", "in");
    filter.appendChild(clip);
    defs.appendChild(filter);
  }

  function paint(el, kind) {
    if (!el) return;
    const w = el.offsetWidth, h = el.offsetHeight;
    if (w < 8 || h < 8) return;
    const cs = getComputedStyle(el);
    const radius = parseFloat(cs.borderTopLeftRadius) || 16;
    const preset = PRESETS[kind] || PRESETS.regular;
    const key = [w, h, Math.round(radius * 10), kind].join(":");
    if (el.getAttribute("data-lg-key") === key) return;
    el.setAttribute("data-lg-key", key);
    const lens = makeLens(w, h, radius, preset);
    let id = el.getAttribute("data-lg-id");
    if (!id) {
      id = "lg-" + (++uid);
      el.setAttribute("data-lg-id", id);
    }
    upsertFilter(id, lens);
    const frost = preset.frost ? ` blur(${preset.frost}px)` : "";
    el.style.setProperty("--lg-filter", `url(#${id})${frost} saturate(1.5)`);
    el.classList.add("lg-on");
    let sheen = el.querySelector(":scope > .lg-sheen");
    if (!sheen) {
      sheen = document.createElement("span");
      sheen.className = "lg-sheen";
      sheen.setAttribute("aria-hidden", "true");
      el.appendChild(sheen);
    }
    sheen.style.backgroundImage = `url("${lens.overlay}")`;
  }

  const targets = [
    [".mod-dock", "regular"],
    [".mod-hud", "thick"],
    [".mod-pal-card", "label"],
    [".tt-track", "regular"]
  ];

  function refresh() {
    targets.forEach(([sel, kind]) => {
      document.querySelectorAll(sel).forEach((el) => paint(el, kind));
    });
  }

  let tId = 0;
  function schedule() {
    clearTimeout(tId);
    tId = setTimeout(refresh, 140);
  }
  refresh();
  const ro = new ResizeObserver(schedule);
  function watch() {
    targets.forEach(([sel]) => {
      document.querySelectorAll(sel).forEach((el) => ro.observe(el));
    });
  }
  watch();
  const mo = new MutationObserver(() => { watch(); schedule(); });
  mo.observe(document.body, { childList: true, subtree: true });
})();
