// Metrics table and charts comparing the latest results of all runs.

import { clear, fmt, h } from "../dom.js";
import { barChart, lineChart } from "./charts.js";

const STAT_LABELS = {
  expansions: "Expansions",
  generated: "Nodes generated",
  path_cells: "Path cells",
  iterations: "Iterations",
  tree_size: "Tree size",
  start_tree_size: "Start-tree size",
  goal_tree_size: "Goal-tree size",
  rewires: "Rewires",
  first_solution_iteration: "First solution (iter.)",
  first_solution_cost: "First solution cost",
  samples: "Samples",
  roadmap_edges: "Roadmap edges",
  sampling_attempts: "Sampling attempts",
  line_of_sight_checks: "Line-of-sight checks",
  escapes: "Random-walk escapes",
  stalls: "Stalls",
};

export function statLabel(key) {
  return STAT_LABELS[key] || key.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());
}

function emptyState(text) {
  return h("div", { class: "empty" }, h("strong", {}, "No results yet"), text);
}

function resultRuns(app) {
  return app.runs.filter((r) => app.results.has(r.id));
}

export class MetricsPanel {
  constructor(app) {
    this.app = app;
    this.el = document.getElementById("tab-metrics");
    app.on("results", () => this.render());
    app.on("runs", () => this.render());
  }

  render() {
    const app = this.app;
    clear(this.el);
    const runs = resultRuns(app);
    if (!runs.length) {
      this.el.append(emptyState("Press Plan (or Enter) to run the enabled planners and compare them here."));
      return;
    }
    const results = runs.map((r) => app.results.get(r.id));
    const head = h(
      "tr",
      {},
      h("th", {}, "Metric"),
      runs.map((r) =>
        h("th", {}, h("span", { class: "col-head" }, h("span", { class: "swatch", style: { background: app.colorOf(r) } }), app.runTitle(r))),
      ),
    );
    const rows = [
      h(
        "tr",
        {},
        h("td", {}, "Result"),
        results.map((res) =>
          res.success
            ? h("td", { class: "best" }, "success")
            : h("td", { class: "fail", title: res.message }, "failed"),
        ),
      ),
    ];
    const metricRow = (key, label, unit, lowerIsBetter, highlight = true) => {
      const values = results.map((res) => (res.success || key.endsWith("_ms") || key === "collision_checks" ? res.metrics?.[key] : undefined));
      const valid = values.filter((v) => typeof v === "number");
      if (!valid.length) return null;
      const best = lowerIsBetter ? Math.min(...valid) : Math.max(...valid);
      return h(
        "tr",
        {},
        h("td", { title: unit ? `${label} [${unit}]` : label }, unit ? `${label} (${unit})` : label),
        values.map((v) =>
          h("td", { class: highlight && valid.length > 1 && v === best ? "best" : "" }, typeof v === "number" ? fmt(v) : "–"),
        ),
      );
    };
    for (const m of app.catalog.metrics) {
      const row = metricRow(m.key, m.label, m.unit, m.lower_is_better);
      if (row) rows.push(row);
    }
    const setup = metricRow("setup_time_ms", "Setup time", "ms", true, false);
    if (setup) rows.push(setup);

    const statKeys = [];
    for (const res of results) for (const k of Object.keys(res.stats || {})) if (!statKeys.includes(k)) statKeys.push(k);
    if (statKeys.length) {
      rows.push(h("tr", {}, h("td", { colspan: runs.length + 1, class: "muted" }, "Planner statistics")));
      for (const k of statKeys) {
        rows.push(
          h(
            "tr",
            {},
            h("td", {}, statLabel(k)),
            results.map((res) => h("td", {}, res.stats && k in res.stats ? fmt(res.stats[k]) : "–")),
          ),
        );
      }
    }
    this.el.append(
      h("div", { class: "table-wrap" }, h("table", { class: "data" }, h("thead", {}, head), h("tbody", {}, rows))),
      h("p", { class: "note" }, "Best values are highlighted. Lengths and clearances are in world units; planning time excludes setup such as grid rasterization."),
    );
    const failures = runs.filter((r) => !app.results.get(r.id).success);
    for (const r of failures) {
      this.el.append(h("p", { class: "note" }, h("strong", {}, `${app.runTitle(r)}: `), app.results.get(r.id).message));
    }
  }
}

export class ChartsPanel {
  constructor(app) {
    this.app = app;
    this.el = document.getElementById("tab-charts");
    app.on("results", () => this.render());
    app.on("runs", () => this.render());
  }

  render() {
    const app = this.app;
    clear(this.el);
    const runs = resultRuns(app);
    if (!runs.length) {
      this.el.append(emptyState("Charts compare path quality and effort once planners have run."));
      return;
    }
    const metric = (key, title, unit, lower = true, onlySuccess = true) => {
      const rows = runs.map((r) => {
        const res = app.results.get(r.id);
        const v = res.metrics?.[key];
        return {
          label: app.runTitle(r),
          color: app.colorOf(r),
          value: (!onlySuccess || res.success) && typeof v === "number" ? v : null,
        };
      });
      if (rows.every((r) => r.value === null)) return null;
      return barChart({ title, unit, rows, lowerIsBetter: lower });
    };
    this.el.append(
      metric("path_length", "Path length", "world units"),
      metric("planning_time_ms", "Planning time", "ms", true, false),
      metric("turning_deg", "Total turning", "degrees"),
      metric("min_clearance", "Minimum clearance", "world units", false),
      metric("collision_checks", "Collision checks", "count", true, false),
    );

    // Effort: expansions for graph search, iterations for sampling planners.
    const effort = runs
      .map((r) => {
        const st = app.results.get(r.id).stats || {};
        const v = st.expansions ?? st.iterations ?? null;
        return { label: app.runTitle(r), color: app.colorOf(r), value: v, note: "n/a" };
      })
      .filter((r) => r.value !== null);
    if (effort.length) {
      this.el.append(barChart({ title: "Search effort", unit: "expansions / iterations", rows: effort }));
    }

    const series = runs
      .filter((r) => app.results.get(r.id).series?.best_cost?.length)
      .map((r) => ({ label: app.runTitle(r), color: app.colorOf(r), points: app.results.get(r.id).series.best_cost }));
    if (series.length) {
      // Reference lines for the other planners; equal lengths share one labelled line.
      const refs = [];
      for (const r of runs) {
        const res = app.results.get(r.id);
        if (res.series?.best_cost || !res.success) continue;
        const value = res.metrics.path_length;
        const same = refs.find((x) => Math.abs(x.value - value) < 1e-6);
        if (same) same.label += `, ${app.runTitle(r)}`;
        else refs.push({ label: app.runTitle(r), color: app.colorOf(r), value });
      }
      this.el.append(
        lineChart({
          title: "Convergence of anytime planners (best path cost)",
          series,
          refs,
          xLabel: "iteration",
          yLabel: "cost",
        }),
        h("p", { class: "note" }, "Dashed lines mark the path lengths of the other planners."),
      );
    }
  }
}
