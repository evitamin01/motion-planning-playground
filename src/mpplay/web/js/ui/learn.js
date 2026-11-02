// "Learn" tab: how each algorithm works, its properties and references.

import { clear, h } from "../dom.js";

function card(info, color) {
  return h(
    "article",
    { class: "algo", style: color ? { borderLeft: `4px solid ${color}` } : {} },
    h("div", { class: "family" }, info.family),
    h("h3", {}, info.label),
    info.description.split(/\n\s*\n/).map((p) => h("p", {}, p.replace(/\s*\n\s*/g, " "))),
    Object.keys(info.properties).length
      ? h("dl", {}, Object.entries(info.properties).map(([k, v]) => [h("dt", {}, k), h("dd", {}, v)]))
      : null,
    info.references.length ? h("ul", { class: "refs" }, info.references.map((r) => h("li", {}, r))) : null,
  );
}

const LEGEND = [
  ["Explored cells", "Cells already expanded by a grid search (lighter) and its open frontier (darker)."],
  ["Tree / roadmap edges", "Edges added by sampling-based planners. RRT-Connect's goal tree uses a second color; PRM's roadmap is grey."],
  ["Ring marker", "The random sample drawn in the current step."],
  ["Dashed path", "The best solution found so far (anytime planners) or the path before smoothing."],
  ["Thick path", "The final path, shown once the planner's animation has finished."],
  ["Shaded border", "Configuration space: obstacles grown by the robot radius."],
];

export class LearnPanel {
  constructor(app) {
    this.app = app;
    this.el = document.getElementById("tab-learn");
    app.on("runs", () => this.render());
  }

  render() {
    const app = this.app;
    clear(this.el);
    const used = [];
    for (const run of app.runs) {
      if (!used.find((u) => u.name === run.planner)) {
        const info = app.plannerInfo(run.planner);
        if (info) used.push({ ...info, color: app.colorOf(run) });
      }
    }
    if (used.length) {
      this.el.append(h("div", { class: "section-title" }, "Planners in your comparison"));
      for (const info of used) this.el.append(card(info, info.color));
    }
    const others = app.catalog.planners.filter((p) => !used.find((u) => u.name === p.name));
    if (others.length) {
      const list = h("details", { class: "subsection" }, h("summary", {}, `All other algorithms (${others.length})`));
      for (const info of others) list.append(card(info));
      this.el.append(list);
    }
    this.el.append(
      h("div", { class: "section-title" }, "Reading the visualization"),
      h("dl", { class: "algo" }, LEGEND.map(([k, v]) => [h("dt", {}, h("strong", {}, k)), h("dd", { style: { margin: "0 0 8px" } }, v)])),
    );
  }
}
