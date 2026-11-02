// Modal dialogs: environment generator and help.

import { api } from "../api.js";
import { clear, h, toast } from "../dom.js";
import { paramForm } from "./forms.js";

export class GenerateDialog {
  constructor(app) {
    this.app = app;
    this.dialog = document.getElementById("dlg-generate");
    this.fields = document.getElementById("generate-fields");
    this.generator = null;
    this.params = {};
    this.seed = Math.floor(Math.random() * 10000);
    this.dialog.addEventListener("close", () => {
      if (this.dialog.returnValue === "ok") this.generate();
    });
  }

  open() {
    if (!this.generator) this.generator = this.app.catalog.generators[0]?.name;
    this.render();
    this.dialog.returnValue = "";
    this.dialog.showModal();
  }

  render() {
    clear(this.fields);
    const gens = this.app.catalog.generators;
    const select = h(
      "select",
      { id: "gen-kind" },
      gens.map((g) => h("option", { value: g.name, selected: g.name === this.generator }, g.label)),
    );
    select.addEventListener("change", () => {
      this.generator = select.value;
      this.params = {};
      this.render();
    });
    const info = gens.find((g) => g.name === this.generator);
    const seed = h("input", { type: "number", id: "gen-seed", value: this.seed, min: 0, step: 1 });
    seed.addEventListener("change", () => (this.seed = Math.max(0, Math.round(Number(seed.value) || 0))));
    const reseed = h("button", { type: "button", class: "btn small", onclick: () => { this.seed = Math.floor(Math.random() * 10000); seed.value = this.seed; } }, "Random");
    this.fields.append(
      h("label", { for: "gen-kind" }, "Type"),
      select,
      h("p", { class: "note full", style: { margin: 0 } }, info?.description || ""),
      h("label", { for: "gen-seed" }, "Seed"),
      h("div", { class: "pair" }, seed, reseed),
      h(
        "div",
        { class: "full" },
        info ? paramForm(info.params, this.params, (name, value) => (this.params[name] = value)) : null,
      ),
    );
  }

  async generate() {
    try {
      const env = await api.generate({ generator: this.generator, params: this.params, seed: this.seed });
      this.app.setEnv(env, { scenario: null });
      this.seed += 1;
      toast(`Generated: ${env.description}`);
    } catch (err) {
      toast(`Could not generate: ${err.message}`, "error");
    }
  }
}

const SHORTCUTS = [
  ["Enter", "Plan with all enabled planners"],
  ["Space", "Play / pause"],
  ["← / →", "Step backward / forward"],
  ["Home / End", "Restart / jump to the end"],
  ["V R C P E S G", "Tools: select, rectangle, circle, polygon, erase, start, goal"],
  ["Del", "Delete the selected obstacle"],
  ["Ctrl+D", "Duplicate the selected obstacle"],
  ["Ctrl+Z / Ctrl+Shift+Z", "Undo / redo"],
  ["F", "Fit the map to the view"],
  ["Esc", "Cancel drawing / clear selection"],
  ["Scroll / drag", "Zoom / pan (right- or middle-drag pans with any tool)"],
  ["?", "Show this help"],
];

export class HelpDialog {
  constructor(app) {
    this.app = app;
    this.dialog = document.getElementById("dlg-help");
    const body = document.getElementById("help-body");
    body.append(
      h("h2", {}, "Motion Planning Playground"),
      h(
        "p",
        { class: "muted" },
        "Build a 2D world, pick a few motion planners and watch how they search, step by step. Then compare their paths and effort, or benchmark them across many random seeds.",
      ),
      h("h3", {}, "Getting started"),
      h(
        "ol",
        {},
        h("li", {}, "Choose a scenario at the top, or draw your own obstacles with the tools on the left. Drag the S and G markers to move the start and goal."),
        h("li", {}, "Add planners in the Planners panel and tune their parameters. Duplicate a planner to compare parameter settings."),
        h("li", {}, "Press Plan. Each planner gets its own panel (Split) or all paths share one map (Overlay). Use the playback bar to replay the search."),
        h("li", {}, "Read the Metrics and Charts tabs, run a statistical Benchmark, and use the Learn tab to understand each algorithm."),
        h("li", {}, "Turn on Live to re-plan instantly while you drag obstacles, the start or the goal."),
      ),
      h("h3", {}, "Keyboard shortcuts"),
      h(
        "div",
        { class: "kbd-grid" },
        SHORTCUTS.map(([k, v]) => [h("span", {}, k.split(" / ").map((x, i) => [i ? " / " : "", h("kbd", {}, x)])), h("span", {}, v)]),
      ),
      h("h3", {}, "Command line & Python"),
      h(
        "p",
        { class: "muted" },
        "Everything in the UI is also available from Python (import mpplay) and the command line: mpplay plan, mpplay benchmark, mpplay export. New planners register themselves with a decorator and show up here automatically - see docs/adding-a-planner.md.",
      ),
      h(
        "div",
        { class: "dialog-actions" },
        h("button", { class: "btn primary", onclick: () => this.dialog.close() }, "Got it"),
      ),
    );
    this.dialog.addEventListener("click", (e) => {
      if (e.target === this.dialog) this.dialog.close();
    });
  }

  open() {
    this.dialog.showModal();
  }
}
