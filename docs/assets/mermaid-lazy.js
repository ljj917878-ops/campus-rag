/* CampusRAG · Mermaid 12.3.0 按需加载：仅在展开模块 02 / 08 时 import ESM */
(() => {
  const ESM = "https://cdn.jsdelivr.net/npm/mermaid@12.3.0/dist/mermaid.esm.min.mjs";
  const TARGETS = new Set(["02", "08"]);
  let mermaidMod = null;
  let loading = null;
  let renderSeq = 0;

  function isLight() {
    return document.documentElement.getAttribute("data-theme") === "light";
  }

  function config() {
    const light = isLight();
    const darkVars = {
      darkMode: true,
      background: "#10161d",
      primaryColor: "#1a242e",
      primaryTextColor: "#eef4fb",
      primaryBorderColor: "#5c6e7c",
      secondaryColor: "#1e2832",
      secondaryTextColor: "#eef4fb",
      secondaryBorderColor: "#5c6e7c",
      tertiaryColor: "#151c24",
      tertiaryTextColor: "#eef4fb",
      lineColor: "#8aa0b2",
      textColor: "#eef4fb",
      mainBkg: "#1a242e",
      nodeBorder: "#5c6e7c",
      clusterBkg: "#151c24",
      clusterBorder: "#4d6273",
      titleColor: "#eef4fb",
      edgeLabelBackground: "#1c2732",
    };
    const lightVars = {
      background: "#f4f1ea",
      primaryColor: "#f7f4ee",
      primaryTextColor: "#1c2430",
      primaryBorderColor: "#b9b2a4",
      secondaryColor: "#efeae0",
      secondaryTextColor: "#1c2430",
      secondaryBorderColor: "#b9b2a4",
      tertiaryColor: "#ece8df",
      tertiaryTextColor: "#1c2430",
      lineColor: "#6b7380",
      textColor: "#1c2430",
      mainBkg: "#f7f4ee",
      nodeBorder: "#b9b2a4",
      clusterBkg: "#efeae0",
      clusterBorder: "#c5beb0",
      titleColor: "#1c2430",
      edgeLabelBackground: "#f4f1ea",
    };
    return {
      startOnLoad: false,
      theme: light ? "default" : "dark",
      securityLevel: "strict",
      fontFamily: "inherit",
      themeVariables: light ? lightVars : darkVars,
      flowchart: {
        htmlLabels: true,
        wrappingWidth: 280,
        padding: 12,
        nodeSpacing: 36,
        rankSpacing: 44,
        useMaxWidth: true,
        curve: "basis",
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
      // 圆角细边，跟树卡片一致；只改 Mermaid SVG，不动页面里的 .rail .node
      svg.querySelectorAll(".node rect, .cluster rect").forEach((r) => {
        r.setAttribute("rx", "12");
        r.setAttribute("ry", "12");
        r.setAttribute("stroke-width", "1");
      });
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
