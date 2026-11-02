// Planner configuration cards ("runs"). Each run = planner + parameters + options.

import { clear, fmt, h, icon } from "../dom.js";
import { paramForm } from "./forms.js";

export class RunsPanel {
  constructor(app) {
    this.app = app;
    this.el = document.getElementById("runs");
    this.statusEls = new Map();
    document.getElementById("btn-add-run").addEventListener("click", () => app.addRun());
    app.on("runs", () => this.render());
    app.on("results", () => this.updateStatus());
  }

  plannerSelect(run) {
    const families = new Map();
    for (const p of this.app.catalog.planners) {
      if (!families.has(p.family)) families.set(p.family, []);
      families.get(p.family).push(p);
    }
    const select = h(
      "select",
      { "aria-label": "Planner", title: "Choose the algorithm" },
      [...families].map(([family, planners]) =>
        h(
          "optgroup",
          { label: family },
          planners.map((p) => h("option", { value: p.name, selected: p.name === run.planner }, p.label)),
        ),
      ),
    );
    select.addEventListener("change", () => this.app.updateRun(run.id, { planner: select.value, params: {} }));
    return select;
  }

  render() {
    const app = this.app;
    clear(this.el);
    this.statusEls.clear();
    if (!app.runs.length) {
      this.el.append(
        h("div", { class: "empty" }, h("strong", {}, "No planners yet"), "Add a planner to start comparing algorithms."),
      );
      return;
    }
    for (const run of app.runs) {
      const info = app.plannerInfo(run.planner);
      const enabled = h("input", {
        type: "checkbox",
        checked: run.enabled,
        title: "Include this planner when planning",
        "aria-label": "Enabled",
      });
      enabled.addEventListener("change", () => app.updateRun(run.id, { enabled: enabled.checked }));
      const smoothing = h("input", { type: "checkbox", id: `smooth-${run.id}`, checked: run.smoothing });
      smoothing.addEventListener("change", () => app.updateRun(run.id, { smoothing: smoothing.checked }, { rerender: false }));
      const status = h("div", { class: "run-status" });
      this.statusEls.set(run.id, status);
      const body = info
        ? h(
            "div",
            { class: "run-body" },
            paramForm(info.params, run.params, (name, value, opts) => app.setRunParam(run.id, name, value, opts)),
            h(
              "div",
              { class: "form-grid" },
              h("label", { for: `smooth-${run.id}`, title: "Greedy shortcutting: removes unnecessary waypoints" }, "Smooth path"),
              h("label", { class: "switch" }, smoothing, h("span", { class: "switch-track" })),
            ),
          )
        : h("div", { class: "run-body muted" }, `Unknown planner "${run.planner}"`);
      const card = h(
        "div",
        { class: `run${run.enabled ? "" : " disabled"}`, style: { "--run-color": app.colorOf(run) } },
        h(
          "div",
          { class: "run-head" },
          enabled,
          this.plannerSelect(run),
          h("button", { class: "btn icon ghost", title: "Duplicate", onclick: () => app.duplicateRun(run.id) }, icon("copy")),
          h("button", { class: "btn icon ghost danger", title: "Remove", onclick: () => app.removeRun(run.id) }, icon("close")),
        ),
        info ? h("div", { class: "run-summary" }, info.summary) : null,
        body,
        status,
      );
      this.el.append(card);
    }
    this.updateStatus();
  }

  updateStatus() {
    const app = this.app;
    for (const run of app.runs) {
      const el = this.statusEls.get(run.id);
      if (!el) continue;
      clear(el);
      el.className = "run-status";
      const result = app.results.get(run.id);
      if (app.pending.has(run.id)) {
        el.append(h("span", { class: "msg" }, "Planning…"));
      } else if (!result) {
        el.append(h("span", { class: "msg muted" }, run.enabled ? "Not planned yet" : "Disabled"));
      } else if (result.success) {
        el.classList.add("ok");
        const m = result.metrics;
        el.append(
          icon("check"),
          h("span", { class: "msg" }, `Length ${fmt(m.path_length)} · ${fmt(m.planning_time_ms)} ms`),
        );
      } else {
        el.classList.add("fail");
        el.append(icon("close"), h("span", { class: "msg", title: result.message }, result.message || "Failed"));
      }
    }
  }
}
