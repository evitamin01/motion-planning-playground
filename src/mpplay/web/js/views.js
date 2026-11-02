// Canvas panels: one per planner in split mode, a single shared panel in overlay mode.

import { clear, fmt, h } from "./dom.js";
import { handlesFor } from "./editor.js";
import { drawScene } from "./renderer.js";

class View {
  constructor(app, key) {
    this.app = app;
    this.key = key;
    this.canvas = h("canvas");
    this.ctx = this.canvas.getContext("2d");
    this.label = h("div", { class: "view-label" });
    this.legend = h("div", { class: "view-legend" });
    this.coords = h("div", { class: "view-coords" });
    this.el = h(
      "div",
      { class: "view" },
      this.canvas,
      this.label,
      this.legend,
      this.coords,
      h("div", { class: "view-loading" }, h("span")),
    );
    this.runIds = [];
    this.width = 0;
    this.height = 0;
    this.coords.hidden = true;
  }

  size() {
    return { width: this.width, height: this.height };
  }

  transform() {
    return this.app.camera.transform(this.app.env.bounds, this.width, this.height);
  }

  setCoords(p) {
    if (!p) {
      this.coords.hidden = true;
      return;
    }
    this.coords.hidden = false;
    this.coords.textContent = `x ${p[0].toFixed(2)}  y ${p[1].toFixed(2)}`;
  }

  resize() {
    const rect = this.el.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    this.width = rect.width;
    this.height = rect.height;
    const w = Math.max(1, Math.round(rect.width * dpr));
    const hgt = Math.max(1, Math.round(rect.height * dpr));
    if (this.canvas.width !== w || this.canvas.height !== hgt) {
      this.canvas.width = w;
      this.canvas.height = hgt;
    }
    this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }
}

export class Views {
  constructor(app, container) {
    this.app = app;
    this.container = container;
    this.views = [];
    this.observer = new ResizeObserver(() => {
      this.arrange();
      app.requestRender();
    });
    this.observer.observe(container);
  }

  /** Rebuild the set of panels for the current mode and runs. */
  layout() {
    const app = this.app;
    const runs = app.runs.filter((r) => r.enabled);
    let specs;
    if (app.viewMode === "overlay" || runs.length <= 1) {
      specs = [{ key: "overlay", runIds: runs.map((r) => r.id), overlay: app.viewMode === "overlay" }];
    } else {
      specs = runs.map((r) => ({ key: `run-${r.id}`, runIds: [r.id], overlay: false }));
    }
    const existing = new Map(this.views.map((v) => [v.key, v]));
    const next = specs.map((spec) => {
      let view = existing.get(spec.key);
      if (!view) {
        view = new View(app, spec.key);
        app.editor.attach(view);
      }
      view.runIds = spec.runIds;
      view.overlay = spec.overlay;
      return view;
    });
    clear(this.container);
    for (const v of next) this.container.append(v.el);
    this.views = next;
    this.arrange();
    this.updateLabels();
    app.requestRender();
  }

  /** Choose rows x columns maximizing the drawn map size. */
  arrange() {
    const n = Math.max(this.views.length, 1);
    const rect = this.container.getBoundingClientRect();
    const env = this.app.env;
    const aspect = env ? (env.bounds[2] - env.bounds[0]) / (env.bounds[3] - env.bounds[1]) : 1.6;
    let best = { cols: 1, score: -1 };
    for (let cols = 1; cols <= n; cols++) {
      const rows = Math.ceil(n / cols);
      const w = rect.width / cols;
      const hgt = rect.height / rows;
      const score = Math.min(w, hgt * aspect);
      if (score > best.score + 1e-6) best = { cols, score };
    }
    const rows = Math.ceil(n / best.cols);
    this.container.style.gridTemplateColumns = `repeat(${best.cols}, minmax(0, 1fr))`;
    this.container.style.gridTemplateRows = `repeat(${rows}, minmax(0, 1fr))`;
    for (const v of this.views) v.resize();
  }

  updateLabels() {
    const app = this.app;
    for (const v of this.views) {
      clear(v.label);
      clear(v.legend);
      const runs = v.runIds.map((id) => app.runById(id)).filter(Boolean);
      v.el.classList.toggle("loading", runs.some((r) => app.pending.has(r.id)));
      if (!runs.length) {
        v.label.hidden = true;
        continue;
      }
      if (v.overlay && runs.length > 1) {
        v.label.hidden = true;
        const focus = app.focusRunId();
        for (const run of runs) {
          const result = app.results.get(run.id);
          const chip = h(
            "button",
            {
              class: "legend-chip",
              "aria-pressed": String(run.id === focus),
              title: "Show this planner's exploration",
              onclick: () => app.setFocus(run.id),
            },
            h("span", { class: "swatch", style: { background: app.colorOf(run) } }),
            app.runTitle(run),
            result && result.success ? h("span", { class: "muted" }, fmt(result.metrics.path_length)) : null,
          );
          v.legend.append(chip);
        }
        continue;
      }
      v.label.hidden = false;
      const run = runs[0];
      const result = app.results.get(run.id);
      let sub = null;
      if (app.pending.has(run.id)) sub = h("span", { class: "sub" }, "planning…");
      else if (result && result.success) {
        sub = h("span", { class: "sub" }, `${fmt(result.metrics.path_length)} · ${fmt(result.metrics.planning_time_ms)} ms`);
      } else if (result) {
        sub = h("span", { class: "sub fail", title: result.message }, result.message || "failed");
      }
      v.label.append(h("span", { class: "swatch", style: { background: app.colorOf(run) } }), app.runTitle(run));
      if (sub) v.label.append(sub);
    }
  }

  render() {
    const app = this.app;
    if (!app.env) return;
    const focus = app.focusRunId();
    const shape = app.selection !== null ? app.env.obstacles[app.selection] : null;
    for (const v of this.views) {
      if (!v.width || !v.height) v.resize();
      const T = v.transform();
      const items = v.runIds
        .map((id) => app.runById(id))
        .filter(Boolean)
        .map((run) => ({
          color: app.colorOf(run),
          color2: app.colorOf(run, 1),
          result: app.results.get(run.id) || null,
          state: app.states.get(run.id) || null,
          exploration: !v.overlay || run.id === focus,
          path: true,
        }));
      drawScene(v.ctx, {
        width: v.width,
        height: v.height,
        T,
        env: app.env,
        layers: app.layers,
        items,
        selection: shape ? { shape, handles: app.tool === "select" ? handlesFor(shape, T) : [] } : null,
        draft: app.editor.draft,
        hover: app.editor.hover,
      });
    }
  }

  /** Composite all panels into one PNG. */
  async snapshot() {
    const rect = this.container.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    const out = document.createElement("canvas");
    out.width = Math.round(rect.width * dpr);
    out.height = Math.round(rect.height * dpr);
    const ctx = out.getContext("2d");
    ctx.fillStyle = getComputedStyle(this.container).backgroundColor;
    ctx.fillRect(0, 0, out.width, out.height);
    for (const v of this.views) {
      const r = v.el.getBoundingClientRect();
      ctx.drawImage(v.canvas, Math.round((r.left - rect.left) * dpr), Math.round((r.top - rect.top) * dpr));
      const label = v.label.hidden ? null : v.label.textContent;
      if (label) {
        ctx.font = `${12 * dpr}px system-ui, sans-serif`;
        ctx.fillStyle = getComputedStyle(document.body).color;
        ctx.fillText(label, (r.left - rect.left + 12) * dpr, (r.top - rect.top + 20) * dpr);
      }
    }
    return new Promise((resolve) => out.toBlob(resolve, "image/png"));
  }
}
