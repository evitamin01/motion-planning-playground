// Benchmark tab: repeated trials across scenarios with summary statistics.

import { api } from "../api.js";
import { clear, downloadText, fmt, h, icon, toast } from "../dom.js";
import { barChart } from "./charts.js";

const CURRENT = "__current__";

function toCsv(rows) {
  if (!rows.length) return "";
  const keys = [];
  for (const r of rows) for (const k of Object.keys(r)) if (!keys.includes(k)) keys.push(k);
  const esc = (v) => {
    if (v === null || v === undefined) return "";
    const s = String(v);
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  return [keys.join(","), ...rows.map((r) => keys.map((k) => esc(r[k])).join(","))].join("\n") + "\n";
}

export class BenchmarkPanel {
  constructor(app) {
    this.app = app;
    this.el = document.getElementById("tab-benchmark");
    this.trials = 10;
    this.selected = new Set([CURRENT]);
    this.running = false;
    this.cancelled = false;
    this.data = null;
    app.on("runs", () => !this.running && this.render());
  }

  render() {
    const app = this.app;
    clear(this.el);
    const runs = app.runs.filter((r) => r.enabled);
    const trials = h("input", { type: "number", min: 1, max: 500, value: this.trials, id: "bench-trials" });
    trials.addEventListener("change", () => {
      this.trials = Math.max(1, Math.min(500, Math.round(Number(trials.value) || 1)));
      trials.value = this.trials;
    });
    const scenarioBox = (value, label) => {
      const cb = h("input", { type: "checkbox", checked: this.selected.has(value) });
      cb.addEventListener("change", () => (cb.checked ? this.selected.add(value) : this.selected.delete(value)));
      return h("label", { title: label }, cb, label);
    };
    const button = h(
      "button",
      { class: "btn primary", disabled: this.running || !runs.length, onclick: () => this.run() },
      icon("play"),
      "Run benchmark",
    );
    this.progress = h("div", { class: "progress", hidden: !this.running }, h("div"));
    this.status = h("div", { class: "note" });
    this.el.append(
      h(
        "div",
        { class: "bench-form" },
        h(
          "p",
          { class: "note", style: { marginTop: 0 } },
          "Runs every enabled planner several times without recording traces and reports mean ± standard deviation. Trial i uses seed (seed + i) for all planners.",
        ),
        h(
          "div",
          { class: "form-grid", style: { marginTop: 0 } },
          h("label", { for: "bench-trials" }, "Trials per planner"),
          trials,
        ),
        h("div", {}, h("div", { class: "section-title" }, "Environments"), h("div", { class: "bench-scenarios" }, scenarioBox(CURRENT, "Current environment"), app.catalog.scenarios.map((s) => scenarioBox(s.name, s.label)))),
        h(
          "div",
          {},
          h("div", { class: "section-title" }, `Planners (${runs.length} enabled)`),
          runs.length
            ? runs.map((r) => h("span", { class: "tag", style: { borderLeft: `3px solid ${app.colorOf(r)}` } }, app.runTitle(r)))
            : h("span", { class: "muted" }, "Enable at least one planner in the left panel."),
        ),
        h(
          "div",
          { style: { display: "flex", gap: "8px" } },
          button,
          this.running ? h("button", { class: "btn", onclick: () => (this.cancelled = true) }, "Cancel") : null,
        ),
        this.progress,
        this.status,
      ),
    );
    if (this.data) this.renderResults();
  }

  async run() {
    const app = this.app;
    const runs = app.runs.filter((r) => r.enabled);
    const envs = [];
    const names = new Set();
    for (const s of app.catalog.scenarios) {
      if (this.selected.has(s.name)) {
        envs.push(s.environment);
        names.add(s.environment.name);
      }
    }
    if (this.selected.has(CURRENT)) {
      const env = { ...app.env };
      if (names.has(env.name)) env.name = `${env.name} (current)`;
      envs.unshift(env);
    }
    if (!envs.length || !runs.length) {
      toast("Select at least one environment and enable at least one planner.", "error");
      return;
    }
    this.running = true;
    this.cancelled = false;
    this.data = { rows: [], summary: [], runs: runs.map((r) => ({ title: app.runTitle(r), color: app.colorOf(r) })) };
    this.render();
    const total = envs.length * runs.length;
    let done = 0;
    const t0 = performance.now();
    try {
      for (const env of envs) {
        for (const run of runs) {
          if (this.cancelled) throw new Error("cancelled");
          this.status.textContent = `${env.name} · ${app.runTitle(run)} (${done + 1}/${total})`;
          const res = await api.benchmark({
            environments: [env],
            runs: [{ planner: run.planner, params: run.params, label: app.runTitle(run), smoothing: run.smoothing }],
            trials: this.trials,
            seed: app.seed,
          });
          this.data.rows.push(...res.rows);
          this.data.summary.push(...res.summary);
          done++;
          this.progress.firstChild.style.width = `${(100 * done) / total}%`;
        }
      }
      this.status.textContent = `Finished ${done * this.trials} runs in ${((performance.now() - t0) / 1000).toFixed(1)} s.`;
    } catch (err) {
      if (err.message !== "cancelled") toast(`Benchmark failed: ${err.message}`, "error");
    } finally {
      this.running = false;
      const status = this.status.textContent;
      this.render();
      this.status.textContent = this.cancelled ? "Cancelled; showing partial results." : status;
    }
  }

  renderResults() {
    const { summary, rows, runs } = this.data;
    if (!summary.length) return;
    const colorOf = (title) => runs.find((r) => r.title === title)?.color || "#64748b";
    const scenarios = [...new Set(summary.map((s) => s.scenario))];
    const out = h("div", {});
    out.append(
      h(
        "div",
        { style: { display: "flex", gap: "8px", margin: "14px 0 4px" } },
        h("button", { class: "btn small", onclick: () => downloadText("benchmark-summary.csv", toCsv(summary), "text/csv") }, icon("download"), "Summary CSV"),
        h("button", { class: "btn small", onclick: () => downloadText("benchmark-trials.csv", toCsv(rows), "text/csv") }, icon("download"), "All trials CSV"),
      ),
    );
    const pm = (s, key) => (s[`${key}_mean`] === null || s[`${key}_mean`] === undefined ? "–" : `${fmt(s[`${key}_mean`])} ± ${fmt(s[`${key}_std`])}`);
    for (const name of scenarios) {
      const items = summary.filter((s) => s.scenario === name);
      const bestOf = (key) => {
        const vals = items.map((s) => s[`${key}_mean`]).filter((v) => typeof v === "number");
        return vals.length > 1 ? Math.min(...vals) : null;
      };
      const bestLen = bestOf("path_length");
      const bestTime = bestOf("planning_time_ms");
      const table = h(
        "table",
        { class: "data" },
        h("thead", {}, h("tr", {}, ["Planner", "Success", "Length", "Time (ms)", "Turning (°)"].map((t) => h("th", {}, t)))),
        h(
          "tbody",
          {},
          items.map((s) =>
            h(
              "tr",
              {},
              h("td", {}, h("span", { class: "col-head" }, h("span", { class: "swatch", style: { background: colorOf(s.run) } }), s.run)),
              h("td", { class: s.success_rate < 1 ? "fail" : "" }, `${Math.round(s.success_rate * 100)}%`),
              h("td", { class: s.path_length_mean === bestLen ? "best" : "" }, pm(s, "path_length")),
              h("td", { class: s.planning_time_ms_mean === bestTime ? "best" : "" }, pm(s, "planning_time_ms")),
              h("td", {}, pm(s, "turning_deg")),
            ),
          ),
        ),
      );
      const chart = (key, title, unit) =>
        barChart({
          title,
          unit,
          rows: items.map((s) => ({ label: s.run, color: colorOf(s.run), value: s[`${key}_mean`], error: s[`${key}_std`], note: "no success" })),
        });
      out.append(
        h("div", { class: "section-title" }, name),
        h("div", { class: "table-wrap" }, table),
        h("div", { style: { marginTop: "12px" } }, chart("path_length", "Mean path length", "± std"), chart("planning_time_ms", "Mean planning time", "ms ± std")),
      );
    }
    this.el.append(out);
  }
}
