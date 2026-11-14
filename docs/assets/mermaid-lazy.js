/* CampusRAG · Mermaid 12.3.0 按需加载：仅在展开模块 02 / 08 时 import ESM */
(() => {
  const ESM = "https://cdn.jsdelivr.net/npm/mermaid@12.3.0/dist/mermaid.esm.min.mjs";
  const TARGETS = new Set(["02", "08"]);
  let mermaidMod = null;
  let loading = null;
  let renderSeq = 0;

  function themeName() {
    return document.documentElement.getAttribute("data-theme") === "light" ? "default" : "dark";
  }

  function config() {
    const light = themeName() === "light";
    return {
      startOnLoad: false,
      theme: light ? "default" : "dark",
      securityLevel: "strict",
      fontFamily: "inherit",
      themeVariables: light ? undefined : {
        darkMode: true,
        background: "#10161d",
        primaryColor: "#2a3d4d",
        primaryTextColor: "#eef4fb",
        primaryBorderColor: "#7ad4b0",
        secondaryColor: "#243240",
        secondaryTextColor: "#eef4fb",
        secondaryBorderColor: "#6a8498",
        tertiaryColor: "#1a242e",
        tertiaryTextColor: "#eef4fb",
        lineColor: "#b7c8d6",
        textColor: "#eef4fb",
        mainBkg: "#2a3d4d",
        nodeBorder: "#7ad4b0",
        clusterBkg: "#151c24",
        clusterBorder: "#4d6273",
        titleColor: "#eef4fb",
        edgeLabelBackground: "#1c2732",
      },
    };
  }

  function loadMermaid() {
    if (!loading) {
      loading = import(ESM).then((mod) => {
        mermaidMod = mod.default || mod;
        mermaidMod.initialize(config());
        return mermaidMod;
      });
    }
    return loading;
  }


  function fitMermaidSvg(svg) {
    try {
      const box = svg.getBBox();
      if (!box.width || !box.height) return;
      const padX = 16, padY = 12;
      const x = box.x - padX;
      const y = box.y - padY;
      const w = box.width + padX * 2;
      const h = box.height + padY * 2;
      svg.setAttribute("viewBox", x + " " + y + " " + w + " " + h);
      svg.setAttribute("width", "100%");
      svg.style.maxWidth = Math.ceil(w) + "px";
      svg.removeAttribute("height");
    } catch (err) {}
  }

  async function renderBox(box) {
    const srcEl = box.querySelector(".mermaid-src");
    const mount = box.querySelector(".mmd-mount");
    if (!srcEl || !mount) return;
    const src = (srcEl.textContent || "").trim();
    if (!src) return;
    const mermaid = await loadMermaid();
    const id = "crag-mmd-" + (++renderSeq);
    try {
      const out = await mermaid.render(id, src);
      mount.innerHTML = out.svg || "";
      const svg = mount.querySelector("svg");
      if (svg) fitMermaidSvg(svg);
    } catch (err) {
      mount.innerHTML = "";
      const fail = document.createElement("p");
      fail.className = "mmd-fail";
      fail.textContent = "流程图暂时无法绘制。下面的文字列表同样完整。";
      mount.appendChild(fail);
      console.error("Mermaid render failed", err);
    }
  }

  async function ensureLi(li) {
    const box = li.querySelector(":scope .mmd-box");
    if (!box) return;
    box.classList.add("is-ready");
    await renderBox(box);
  }

  async function rerenderReady() {
    const boxes = document.querySelectorAll(".mmd-box.is-ready");
    if (!boxes.length) return;
    const mermaid = await loadMermaid();
    mermaid.initialize(config());
    for (const box of boxes) await renderBox(box);
  }

  function targetLis() {
    return [...document.querySelectorAll(".mind > ul.kids > li")].filter((li) => {
      const no = li.querySelector(":scope > .nd.lv1 .no");
      return no && TARGETS.has(no.textContent.trim());
    });
  }

  function boot() {
    targetLis().forEach((li) => {
      const maybe = () => {
        if (!li.classList.contains("collapsed")) ensureLi(li);
      };
      maybe();
      new MutationObserver(maybe).observe(li, { attributes: true, attributeFilter: ["class"] });
    });
    document.addEventListener("campusrag:themechange", () => { rerenderReady(); });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
