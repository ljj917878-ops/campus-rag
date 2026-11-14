/* CampusRAG · 仪表盘动效：星尘背景、鼠标光晕、错落入场、页面切换 */
(() => {
  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;

  function boot() {
    markPage();
    initLenis();
    if (!reduce) {
      makeBackdrop();
      spotlight();
      staggerIn();
      countUp();
      setTimeout(revealFx, 1500);
    }
    glowCards();
    pageTransitions();
    enhanceCodeTabs();
    shotRainbow();
    themeToggle();
    sectionNav();
    codeToc();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }

  function markPage() {
    const parts = [
      document.querySelector(".wrap"),
      document.querySelector("nav.subtabs"),
      document.querySelector("main"),
      document.querySelector("footer.site-foot"),
    ].filter(Boolean);
    if (!parts.length) document.body.classList.add("fx-page");
    parts.forEach((el) => el.classList.add("fx-page"));
  }

  function makeBackdrop() {
    const canvas = document.createElement("canvas");
    canvas.id = "fx-stars";
    canvas.setAttribute("aria-hidden", "true");
    const ray = document.createElement("div");
    ray.id = "fx-ray";
    ray.setAttribute("aria-hidden", "true");
    const spot = document.createElement("div");
    spot.id = "fx-spot";
    spot.setAttribute("aria-hidden", "true");
    document.body.prepend(spot);
    document.body.prepend(ray);
    document.body.prepend(canvas);

    const ctx = canvas.getContext("2d", { alpha: true });
    let w = 0, h = 0, dpr = 1, dots = [], raf = 0;

    function resize() {
      dpr = 1;
      w = innerWidth;
      h = innerHeight;
      canvas.width = Math.floor(w * dpr);
      canvas.height = Math.floor(h * dpr);
      canvas.style.width = w + "px";
      canvas.style.height = h + "px";
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      const n = Math.max(36, Math.min(70, Math.floor((w * h) / 22000)));
      dots = Array.from({ length: n }, () => ({
        x: Math.random() * w,
        y: Math.random() * h,
        r: Math.random() * 1.35 + 0.25,
        a: Math.random() * 0.42 + 0.08,
        vx: (Math.random() - 0.5) * 0.18,
        vy: -0.07 - Math.random() * 0.16,
      }));
    }

    let last = 0;
    function tick(now = 0) {
      raf = requestAnimationFrame(tick);
      if (now - last < 33) return; // 约 30 帧，够顺滑又省电
      last = now;
      ctx.clearRect(0, 0, w, h);
      for (const d of dots) {
        d.x += d.vx;
        d.y += d.vy;
        if (d.y < -6) {
          d.y = h + 4;
          d.x = Math.random() * w;
        }
        if (d.x < -6) d.x = w + 4;
        if (d.x > w + 6) d.x = -4;
        ctx.beginPath();
        ctx.arc(d.x, d.y, d.r, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(226,240,255,${d.a})`;
        ctx.fill();
      }
    }

    resize();
    tick();
    addEventListener("resize", resize, { passive: true });
    document.addEventListener("visibilitychange", () => {
      cancelAnimationFrame(raf);
      if (!document.hidden) tick();
    });
  }

  function spotlight() {
    const spot = document.getElementById("fx-spot");
    if (!spot) return;
    let tx = -9999, ty = -9999, cx = -9999, cy = -9999, running = false;
    const step = () => {
      cx += (tx - cx) * 0.14; // 缓动跟随，光斑柔和地追鼠标
      cy += (ty - cy) * 0.14;
      spot.style.transform = `translate3d(${cx}px, ${cy}px, 0)`;
      if (Math.abs(tx - cx) > 0.5 || Math.abs(ty - cy) > 0.5) {
        requestAnimationFrame(step);
      } else {
        running = false;
      }
    };
    addEventListener("mousemove", (e) => {
      tx = e.clientX; ty = e.clientY;
      if (cx < -9000) { cx = tx; cy = ty; }
      spot.style.opacity = ".9";
      if (!running) { running = true; requestAnimationFrame(step); }
    }, { passive: true });
    document.addEventListener("mouseleave", () => { spot.style.opacity = "0"; }, { passive: true });
  }

  const GLOW_SEL = [
    ".card", ".note", ".warn", ".fn", ".detail", ".mroot",
    ".cside", "details.qa", ".dict>div", ".flowbar",
    ".node", ".legend",
  ].join(",");

  function glowCards() {
    const els = [...document.querySelectorAll(GLOW_SEL)];
    const visible = new Set();
    const io = "IntersectionObserver" in window
      ? new IntersectionObserver((entries) => {
          entries.forEach((en) => {
            if (en.isIntersecting) visible.add(en.target);
            else { visible.delete(en.target); en.target.classList.remove("is-lit"); }
          });
        }, { rootMargin: "120px" })
      : null;
    els.forEach((el) => {
      if (getComputedStyle(el).borderRadius === "0px") el.style.borderRadius = "14px";
      el.classList.add("fx-glow");
      if (io) io.observe(el); else visible.add(el);
    });
    if (reduce) return;

    let mx = 0, my = 0, pending = false;
    addEventListener("mousemove", (e) => {
      mx = e.clientX; my = e.clientY;
      if (pending) return;
      pending = true;
      requestAnimationFrame(() => {
        pending = false;
        for (const el of visible) {
          const r = el.getBoundingClientRect();
          const pad = 60;
          const inside = mx >= r.left - pad && mx <= r.right + pad &&
                         my >= r.top - pad && my <= r.bottom + pad;
          if (el.classList.contains("is-lit") !== inside) el.classList.toggle("is-lit", inside);
          if (inside) {
            el.style.setProperty("--lx", (mx - r.left) + "px");
            el.style.setProperty("--ly", (my - r.top) + "px");
          }
        }
      });
    }, { passive: true });
  }


  function revealFx() {
    if (document.body.classList.contains("fx-leaving")) return;
    document.querySelectorAll(".fx-page, .fx-stagger").forEach((el) => {
      el.style.animation = "none";
      el.style.opacity = "1";
      el.style.transform = "none";
    });
  }

  function staggerIn() {
    const sel = [
      "h1", ".sub", ".note", ".legend", ".mind-top", ".mroot",
      ".fn", "details.qa", ".flowbar", ".card", ".warn",
    ].join(",");
    const seen = new Set();
    let i = 0;
    document.querySelectorAll(sel).forEach((el) => {
      if (seen.has(el) || el.closest(".site-head")) return;
      seen.add(el);
      el.classList.add("fx-stagger");
      el.style.animationDelay = Math.min(i * 70, 560) + "ms";
      i += 1;
    });
  }

  function countUp() {
    const targets = [...document.querySelectorAll(".mroot em")];
    targets.forEach((el) => {
      const raw = el.textContent.trim();
      const m = raw.match(/^(\d+)(.*)$/);
      if (!m) return;
      const end = parseInt(m[1], 10);
      const suffix = m[2];
      const start = performance.now();
      const dur = 1400;
      const tick = (now) => {
        const t = Math.min(1, (now - start) / dur);
        const eased = 1 - Math.pow(1 - t, 3);
        el.textContent = Math.round(end * eased) + suffix;
        if (t < 1) requestAnimationFrame(tick);
      };
      requestAnimationFrame(tick);
    });
  }

  function pageTransitions() {
    const go = (href) => {
      if (reduce) {
        location.href = href;
        return;
      }
      document.body.classList.add("fx-leaving");
      setTimeout(() => { location.href = href; }, 380);
    };
    document.querySelectorAll("a[href]").forEach((a) => {
      const href = a.getAttribute("href") || "";
      if (!/^(index|code)\.html/.test(href)) return;
      a.addEventListener("click", (e) => {
        if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || a.target === "_blank") return;
        const dest = new URL(a.href, location.href);
        if (dest.pathname === location.pathname && dest.hash === location.hash) return;
        e.preventDefault();
        go(a.href);
      });
    });
  }

  function enhanceCodeTabs() {
    const buttons = [...document.querySelectorAll("nav.subtabs button[data-t]")];
    const panels = [...document.querySelectorAll(".panel")];
    if (!buttons.length || reduce) return;
    buttons.forEach((btn) => {
      btn.addEventListener("click", (e) => {
        // 在原有onclick之后补一段切换动画意义不大（它会立刻切 class）。
        // 这里不阻断原逻辑，只给即将出现的面板加进入动画。
        const id = btn.dataset.t;
        const next = panels.find((p) => p.id === id);
        if (next) {
          next.classList.remove("fx-swap-in");
          void next.offsetWidth;
          next.classList.add("fx-swap-in");
        }
      }, true);
    });
  }


  function shotRainbow() {
    if (location.hash !== "#shot-rainbow") return;
    document.querySelectorAll(".fx-page, .fx-stagger").forEach((el) => {
      el.style.animation = "none";
      el.style.opacity = "1";
      el.style.transform = "none";
    });
    const el =
      document.querySelector(".fn") ||
      document.querySelector(".card") ||
      document.querySelector(".nd");
    if (el) {
      el.classList.add("fx-glow", "is-lit", "fx-demo-hover");
      el.style.setProperty("--lx", "72%");
      el.style.setProperty("--ly", "22%");
    }
  }


  const THEME_KEY = "campusrag-theme";

  function currentTheme() {
    const t = document.documentElement.getAttribute("data-theme");
    return t === "light" ? "light" : "dark";
  }

  function syncPrismTheme(theme) {
    const light = theme === "light";
    const darkSheet = document.getElementById("prism-theme-dark");
    const lightSheet = document.getElementById("prism-theme-light");
    if (!darkSheet || !lightSheet) return;
    darkSheet.disabled = light;
    lightSheet.disabled = !light;
  }

  function applyTheme(theme, persist = true) {
    const t = theme === "light" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", t);
    document.documentElement.style.colorScheme = t;
    if (persist) {
      try { localStorage.setItem(THEME_KEY, t); } catch {}
    }
    const btn = document.querySelector(".theme-toggle");
    if (btn) {
      const light = t === "light";
      btn.setAttribute("aria-checked", String(light));
      btn.setAttribute("aria-label", light ? "切换到深色模式" : "切换到浅色模式");
      btn.title = light ? "切换到深色模式" : "切换到浅色模式";
    }
    syncPrismTheme(t);
    document.dispatchEvent(new CustomEvent("campusrag:themechange", { detail: { theme: t } }));
  }

  function buildToggle() {
    const btn = document.createElement("button");
    btn.className = "theme-toggle";
    btn.type = "button";
    btn.setAttribute("role", "switch");
    btn.setAttribute("aria-checked", "false");
    btn.setAttribute("aria-label", "切换到浅色模式");
    btn.title = "切换到浅色模式";
    btn.innerHTML = `
      <span class="tt-bloom" aria-hidden="true"></span>
      <span class="tt-track" aria-hidden="true">
        <span class="tt-ambient"></span>
        <span class="tt-glow"></span>
        <span class="tt-thumb">
          <svg class="tt-moon" viewBox="0 0 24 24" width="16" height="16" fill="currentColor"><path d="M20.4 14.2A8.4 8.4 0 0 1 9.8 3.6a8.5 8.5 0 1 0 10.6 10.6Z"/></svg>
          <svg class="tt-sun" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><circle cx="12" cy="12" r="4" fill="currentColor" stroke="none"/><path d="M12 3v2.2M12 18.8V21M4.9 4.9l1.6 1.6M17.5 17.5l1.6 1.6M3 12h2.2M18.8 12H21M4.9 19.1l1.6-1.6M17.5 6.5l1.6-1.6"/></svg>
        </span>
      </span>`;
    return btn;
  }

  function themeToggle() {
    let saved = null;
    try { saved = localStorage.getItem(THEME_KEY); } catch {}
    try {
      const q = new URLSearchParams(location.search).get("theme");
      const hash = location.hash;
      if (hash === "#light" || hash === "#shot-light" || q === "light") saved = "light";
      else if (hash === "#dark" || q === "dark") saved = "dark";
    } catch {}
    applyTheme(saved === "light" ? "light" : "dark", false);

    let btn = document.querySelector(".theme-toggle");
    if (!btn) {
      const bar = document.querySelector(".site-head .bar");
      if (bar) {
        btn = buildToggle();
        bar.appendChild(btn);
      }
    }
    if (!btn) return;
    applyTheme(currentTheme(), false);
    btn.addEventListener("click", () => {
      document.documentElement.classList.add("theme-switching");
      applyTheme(currentTheme() === "light" ? "dark" : "light");
      setTimeout(() => document.documentElement.classList.remove("theme-switching"), 500);
    });
  }




  function initLenis() {
    if (reduce || typeof Lenis !== "function") {
      document.documentElement.classList.remove("has-lenis");
      window.__campusragLenis = null;
      return;
    }
    document.documentElement.classList.add("has-lenis");
    const lenis = new Lenis({ autoRaf: true, autoToggle: true });
    window.__campusragLenis = lenis;
  }

  function scrollPageTo(top, opts) {
    const immediate = !!(opts && opts.immediate);
    const duration = (opts && opts.duration != null) ? opts.duration : 0.35;
    const lenis = window.__campusragLenis;
    if (lenis && !reduce && !immediate) {
      // 默认 lerp 0.1 会漂很久；锚点跳转改成短时长，按钮会立刻跟上
      lenis.scrollTo(top, {
        duration,
        easing: (t) => 1 - Math.pow(1 - t, 3),
      });
      return;
    }
    window.scrollTo({ top: top, behavior: (reduce || immediate) ? "auto" : "smooth" });
  }
  window.__campusragScrollTo = scrollPageTo;

  function stickyOffset() {
    const head = document.querySelector(".site-head");
    const bar = document.querySelector(".fnbar");
    const hh = head ? head.getBoundingClientRect().height : 0;
    const bh = bar ? bar.getBoundingClientRect().height : 0;
    document.documentElement.style.setProperty("--crag-head-h", hh + "px");
    document.documentElement.style.setProperty("--crag-fnbar-h", bh + "px");
    return hh + bh + 8;
  }

  function syncFnbar() {
    const toc = document.getElementById("fn-toc");
    const bar = document.querySelector(".fnbar");
    if (!toc || !bar) return;
    const active = toc.querySelector(".is-active-link");
    const href = active ? active.getAttribute("href") : "";
    bar.querySelectorAll("a[href^='#']").forEach((a) => {
      const on = !!(href && a.getAttribute("href") === href);
      a.classList.toggle("is-active-link", on);
      if (on) a.setAttribute("aria-current", "location");
      else a.removeAttribute("aria-current");
    });
  }

  function bindFnbarClicks() {
    const bar = document.querySelector(".fnbar");
    if (!bar || bar.dataset.cragBound === "1") return;
    bar.dataset.cragBound = "1";
    bar.addEventListener("click", (e) => {
      const a = e.target.closest("a[href^='#']");
      if (!a) return;
      const id = (a.getAttribute("href") || "").slice(1);
      const el = id ? document.getElementById(id) : null;
      if (!el) return;
      e.preventDefault();
      bar.querySelectorAll("a[href^='#']").forEach((link) => {
        const on = link === a;
        link.classList.toggle("is-active-link", on);
        if (on) link.setAttribute("aria-current", "location");
        else link.removeAttribute("aria-current");
      });
      const top = Math.max(0, el.getBoundingClientRect().top + window.scrollY - stickyOffset());
      scrollPageTo(top, { immediate: reduce, duration: 0.32 });
      try { history.replaceState(null, "", "#" + id); } catch {}
    });
  }

  function codeToc() {
    const bar = document.querySelector(".fnbar");
    const tocEl = document.getElementById("fn-toc");
    if (!bar || !tocEl || typeof tocbot === "undefined") {
      stickyOffset();
      return;
    }
    bindFnbarClicks();
    const start = () => {
      const offset = stickyOffset();
      if (tocbot.destroy) tocbot.destroy();
      tocbot.init({
        tocSelector: "#fn-toc",
        contentSelector: "#code",
        headingSelector: "section.fn > h3",
        ignoreSelector: ".js-toc-ignore",
        hasInnerContainers: true,
        scrollSmooth: false,
        headingsOffset: offset,
        headingObjectCallback: function (obj, heading) {
          const id = heading && heading.id;
          if (id) obj.id = id;
          return obj;
        },
        scrollEndCallback: function () { syncFnbar(); }
      });
      syncFnbar();
    };
    start();
    let resizeT;
    window.addEventListener("resize", () => {
      clearTimeout(resizeT);
      resizeT = setTimeout(start, 200);
    });
    const mo = new MutationObserver(() => syncFnbar());
    mo.observe(tocEl, { subtree: true, attributes: true, attributeFilter: ["class"] });
  }


  function sectionNav() {
    const reduceMotion = matchMedia("(prefers-reduced-motion: reduce)").matches;
    const EASE = "cubic-bezier(.22,1.12,.36,1)";

    function isShown(el) {
      if (!el) return false;
      const st = getComputedStyle(el);
      if (st.display === "none" || st.visibility === "hidden") return false;
      const r = el.getBoundingClientRect();
      return r.width > 0 && r.height > 0;
    }

    function modules() {
      const seen = new Set();
      const out = [];
      document.querySelectorAll([
        ".wrap > h1",
        ".nd.lv1",
        "section.fn",
        ".panel.on > h2",
        "footer",
        "footer.site-foot",
      ].join(",")).forEach((el) => {
        if (seen.has(el) || !isShown(el)) return;
        seen.add(el);
        out.push(el);
      });
      out.sort((a, b) => a.getBoundingClientRect().top - b.getBoundingClientRect().top);
      return out;
    }

    function headerOffset() {
      const h = document.querySelector(".site-head");
      return (h ? h.getBoundingClientRect().height : 0) + 10;
    }

    function infoOf(el) {
      if (!el) return { no: "", title: "", full: "" };
      if (el.matches("footer, .site-foot")) return { no: "↓", title: "页脚", full: "页脚" };
      const no = (el.querySelector && el.querySelector(":scope > .no")) ? el.querySelector(":scope > .no").textContent.trim() : "";
      const b = (el.querySelector && el.querySelector(":scope > b")) ? el.querySelector(":scope > b").textContent.trim() : "";
      if (no && b) return { no, title: b, full: no + "  " + b };
      const h = el.matches("h1, h2, h3") ? el : (el.querySelector && el.querySelector("h3, h2, h1"));
      const node = h || el;
      let title = "";
      node.childNodes.forEach((n) => {
        if (n.nodeType === 3) title += n.textContent;
        else if (n.nodeType === 1 && !n.classList.contains("loc") && n.tagName !== "SPAN") title += n.textContent;
      });
      title = title.replace(/\s+/g, " ").trim() || (el.textContent || "").replace(/\s+/g, " ").trim();
      title = title.slice(0, 28);
      if (el.matches("h1")) {
        const t = (el.textContent || "").replace(/\s+/g, " ").trim().slice(0, 28);
        return { no: "顶", title: t, full: t };
      }
      return { no: "", title, full: title };
    }

    function currentIndex(list) {
      const off = headerOffset();
      const y = window.scrollY + off + 2;
      const tops = list.map((el) => el.getBoundingClientRect().top + window.scrollY);
      let i = 0;
      for (let k = 0; k < tops.length; k++) if (tops[k] <= y + 2) i = k;
      return { i, y, tops, off };
    }

    function openIfCollapsed(el) {
      const li = el.closest && el.closest("li.collapsed");
      if (li) {
        const nd = li.querySelector(".nd.lv1.has-kids");
        if (nd) nd.click();
      }
    }

    /* —— 旅途抬头显示 —— */
    const hud = document.createElement("div");
    hud.className = "mod-hud";
    hud.setAttribute("aria-hidden", "true");
    hud.innerHTML = `
      <div class="mod-hud-dir"></div>
      <div class="mod-hud-no"></div>
      <div class="mod-hud-title"></div>
      <div class="mod-hud-rail" role="presentation"></div>`;
    document.body.appendChild(hud);
    const hudDir = hud.querySelector(".mod-hud-dir");
    const hudNo = hud.querySelector(".mod-hud-no");
    const hudTitle = hud.querySelector(".mod-hud-title");
    const hudRail = hud.querySelector(".mod-hud-rail");

    function paintRail(list, active) {
      hudRail.innerHTML = list.map((el, i) => {
        const info = infoOf(el);
        const cls = i === active ? "on" : (i < active ? "past" : "");
        return `<i class="${cls}" data-i="${i}" title="${info.full}"></i>`;
      }).join("");
    }

    let hudTimer = 0;
    function showHud(dir, list, index) {
      const info = infoOf(list[index]);
      hudDir.textContent = dir < 0 ? "上一模块" : "下一模块";
      hud.classList.toggle("up", dir < 0);
      hud.classList.toggle("down", dir > 0);
      hudNo.textContent = info.no || "•";
      hudTitle.textContent = info.title;
      paintRail(list, index);
      hud.classList.remove("on", "from-up", "from-down");
      void hud.offsetWidth;
      hud.classList.add("on", dir < 0 ? "from-up" : "from-down");
      clearTimeout(hudTimer);
      hudTimer = setTimeout(() => hud.classList.remove("on", "from-up", "from-down"), 1600);
    }

    /* —— 落点光框 —— */
    const frame = document.createElement("div");
    frame.className = "mod-frame";
    frame.setAttribute("aria-hidden", "true");
    document.body.appendChild(frame);

    function placeFrame(el) {
      const r = el.getBoundingClientRect();
      const pad = 6;
      frame.style.top = Math.round(r.top - pad) + "px";
      frame.style.left = Math.round(r.left - pad) + "px";
      frame.style.width = Math.round(r.width + pad * 2) + "px";
      frame.style.height = Math.round(r.height + pad * 2) + "px";
      frame.classList.remove("on");
      void frame.offsetWidth;
      frame.classList.add("on");
      clearTimeout(placeFrame._t);
      placeFrame._t = setTimeout(() => frame.classList.remove("on"), 900);
    }

    /* —— 右侧旅途坞 —— */
    const dock = document.createElement("div");
    dock.className = "mod-dock";
    dock.innerHTML = `
      <button type="button" class="mod-dock-btn" data-dir="-1" aria-label="上一模块，快捷键 K" title="上一模块（K / Alt+↑）">
        <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true"><path d="M3 10.5 8 5l5 5.5" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/></svg>
      </button>
      <div class="mod-dock-rail" role="navigation" aria-label="模块位置"></div>
      <button type="button" class="mod-dock-btn" data-dir="1" aria-label="下一模块，快捷键 J" title="下一模块（J / Alt+↓）">
        <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true"><path d="M3 5.5 8 11l5-5.5" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/></svg>
      </button>
      <button type="button" class="mod-dock-open" aria-label="打开模块目录，快捷键 / 或 M" title="模块目录（/ 或 M）">目录 <kbd>/</kbd></button>`;
    document.body.appendChild(dock);
    const dockRail = dock.querySelector(".mod-dock-rail");

    function paintDock(list, active) {
      dockRail.innerHTML = list.map((el, i) => {
        const info = infoOf(el);
        return `<button type="button" class="mod-dot${i === active ? " on" : ""}" data-i="${i}" aria-label="${info.full}" aria-current="${i === active ? "true" : "false"}" title="${info.full}"></button>`;
      }).join("");
    }

    function syncDock() {
      const list = modules();
      if (!list.length) return;
      const { i } = currentIndex(list);
      paintDock(list, i);
      const max = document.documentElement.scrollHeight - innerHeight;
      dock.classList.toggle("on", window.scrollY > 140 && max > 240);
    }

    /* —— 模块目录 —— */
    const pal = document.createElement("div");
    pal.className = "mod-pal";
    pal.hidden = true;
    pal.innerHTML = `
      <div class="mod-pal-bg" data-close="1"></div>
      <div class="mod-pal-card" role="dialog" aria-modal="true" aria-label="跳转到模块">
        <div class="mod-pal-head">
          <input class="mod-pal-input" type="text" placeholder="跳转到哪一个模块…" aria-label="筛选模块" autocomplete="off" spellcheck="false">
          <div class="mod-pal-keys"><kbd>↑↓</kbd> 选择 <kbd>Enter</kbd> 前往 <kbd>Esc</kbd> 关闭</div>
        </div>
        <div class="mod-pal-list" role="listbox"></div>
      </div>`;
    document.body.appendChild(pal);
    const palInput = pal.querySelector(".mod-pal-input");
    const palList = pal.querySelector(".mod-pal-list");
    let palItems = [];
    let palSel = 0;
    let palOpen = false;

    function filteredPalette() {
      const list = modules();
      const q = palInput.value.trim().toLowerCase();
      return list.map((el, i) => ({ el, i, info: infoOf(el) }))
        .filter((x) => !q || x.info.full.toLowerCase().includes(q) || String(x.i + 1).includes(q));
    }

    function paintPalette() {
      palItems = filteredPalette();
      if (palSel >= palItems.length) palSel = Math.max(0, palItems.length - 1);
      const cur = currentIndex(modules()).i;
      palList.innerHTML = palItems.length ? palItems.map((x, n) => `
        <button type="button" class="mod-pal-item${n === palSel ? " on" : ""}" role="option" data-n="${n}" aria-selected="${n === palSel}">
          <span class="mod-pal-no">${x.info.no || String(x.i + 1).padStart(2, "0")}</span>
          <span class="mod-pal-name">${x.info.title}</span>
          ${x.i === cur ? '<span class="mod-pal-now">当前</span>' : ""}
        </button>`).join("") : `<div class="mod-pal-empty">没有匹配的模块</div>`;
      const on = palList.querySelector(".mod-pal-item.on");
      if (on) on.scrollIntoView({ block: "nearest" });
    }

    function openPal() {
      pal.hidden = false;
      palOpen = true;
      palSel = 0;
      const list = modules();
      const { i } = currentIndex(list);
      palSel = Math.max(0, filteredPalette().findIndex((x) => x.i === i));
      palInput.value = "";
      paintPalette();
      requestAnimationFrame(() => {
        pal.classList.add("on");
        palInput.focus();
      });
    }

    function closePal() {
      pal.classList.remove("on");
      palOpen = false;
      setTimeout(() => { if (!palOpen) pal.hidden = true; }, reduceMotion ? 0 : 220);
    }

    function jumpTo(index, dir) {
      const list = modules();
      if (!list.length) return;
      const el = list[Math.max(0, Math.min(list.length - 1, index))];
      const next = list.indexOf(el);
      const { i: prev } = currentIndex(list);
      const travel = dir || (next >= prev ? 1 : -1);
      openIfCollapsed(el);
      const off = headerOffset();
      const top = Math.max(0, el.getBoundingClientRect().top + window.scrollY - off);
      scrollPageTo(top, { immediate: reduceMotion });
      showHud(travel, list, next);
      paintDock(list, next);
      clearTimeout(jumpTo._t);
      jumpTo._t = setTimeout(() => placeFrame(el), reduceMotion ? 30 : 420);
    }

    function go(dir) {
      const list = modules();
      if (!list.length) return;
      const { i, y, tops } = currentIndex(list);
      let next = i;
      if (dir < 0) next = (y - tops[i] > 56) ? i : Math.max(0, i - 1);
      else next = Math.min(list.length - 1, i + 1);
      jumpTo(next, dir);
    }

    dock.addEventListener("click", (e) => {
      const openBtn = e.target.closest(".mod-dock-open");
      if (openBtn) { openPal(); return; }
      const dot = e.target.closest(".mod-dot");
      if (dot) { jumpTo(Number(dot.getAttribute("data-i"))); return; }
      const btn = e.target.closest("[data-dir]");
      if (btn) go(Number(btn.getAttribute("data-dir")));
    });

    pal.addEventListener("click", (e) => {
      if (e.target.closest("[data-close]")) { closePal(); return; }
      const item = e.target.closest(".mod-pal-item");
      if (item) {
        const x = palItems[Number(item.getAttribute("data-n"))];
        if (x) { closePal(); jumpTo(x.i); }
      }
    });
    palInput.addEventListener("input", () => { palSel = 0; paintPalette(); });

    syncDock();
    document.addEventListener("scroll", syncDock, { passive: true });
    window.addEventListener("resize", syncDock);

    document.addEventListener("keydown", (e) => {
      const tag = (e.target && e.target.tagName) || "";
      const typing = /^(INPUT|TEXTAREA|SELECT)$/.test(tag) || e.target.isContentEditable;

      if (palOpen) {
        if (e.key === "Escape") { e.preventDefault(); closePal(); return; }
        if (e.key === "ArrowDown") { e.preventDefault(); palSel = Math.min(palItems.length - 1, palSel + 1); paintPalette(); return; }
        if (e.key === "ArrowUp") { e.preventDefault(); palSel = Math.max(0, palSel - 1); paintPalette(); return; }
        if (e.key === "Enter") {
          e.preventDefault();
          const x = palItems[palSel];
          if (x) { closePal(); jumpTo(x.i); }
          return;
        }
        return;
      }

      if (typing || e.ctrlKey || e.metaKey) return;
      if (!e.altKey && !e.shiftKey && (e.key === "/" || e.key === "m" || e.key === "M")) {
        e.preventDefault();
        openPal();
        return;
      }
      let dir = 0;
      if (!e.altKey && !e.shiftKey && (e.key === "k" || e.key === "K")) dir = -1;
      else if (!e.altKey && !e.shiftKey && (e.key === "j" || e.key === "J")) dir = 1;
      else if (e.altKey && (e.key === "ArrowUp" || e.key === "Up")) dir = -1;
      else if (e.altKey && (e.key === "ArrowDown" || e.key === "Down")) dir = 1;
      if (!dir) return;
      e.preventDefault();
      go(dir);
    });
  }

})();
