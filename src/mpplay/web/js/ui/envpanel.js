// Environment panel: editing tools, selected-shape properties and world settings.

import { clear, h, icon } from "../dom.js";
import { TOOLS } from "../editor.js";
import { centroid, round, translate } from "../geometry.js";
import { numberInput } from "./forms.js";

export class EnvPanel {
  constructor(app) {
    this.app = app;
    this.toolbox = document.getElementById("toolbox");
    this.hint = document.getElementById("tool-hint");
    this.props = document.getElementById("selection-props");
    this.form = document.getElementById("env-form");
    this.buttons = new Map();
    for (const tool of TOOLS) {
      const btn = h(
        "button",
        {
          class: "tool",
          title: `${tool.label} (${tool.key.toUpperCase()})`,
          "aria-label": tool.label,
          "aria-pressed": "false",
          onclick: () => app.setTool(tool.id),
        },
        icon(tool.icon),
      );
      if (tool.id === "start") btn.style.color = "var(--canvas-start)";
      if (tool.id === "goal") btn.style.color = "var(--canvas-goal)";
      this.buttons.set(tool.id, btn);
      this.toolbox.append(btn);
    }
    app.on("tool", () => this.renderTools());
    app.on("selection", () => this.renderSelection());
    app.on("env", (e) => {
      this.renderSelection();
      if (!e.detail.transient) this.renderWorld();
    });
  }

  render() {
    this.renderTools();
    this.renderSelection();
    this.renderWorld();
  }

  renderTools() {
    for (const [id, btn] of this.buttons) btn.setAttribute("aria-pressed", String(id === this.app.tool));
    this.hint.textContent = TOOLS.find((t) => t.id === this.app.tool)?.hint || "";
  }

  renderSelection() {
    const app = this.app;
    if (this.props.contains(document.activeElement) && document.activeElement.tagName === "INPUT") return;
    clear(this.props);
    const index = app.selection;
    const o = index !== null ? app.env.obstacles[index] : null;
    if (!o) return;
    const update = (shape) => app.updateObstacle(index, shape);
    const num = (value, fn, attrs) => numberInput(round(value, 3), fn, attrs);
    const grid = h("div", { class: "form-grid" });
    const center = o.type === "polygon" ? centroid(o) : o.center;
    const moveTo = (x, y) => update(translate(o, x - center[0], y - center[1]));
    grid.append(
      h("label", {}, "Center"),
      h(
        "div",
        { class: "pair" },
        num(center[0], (v) => moveTo(v, center[1]), { "aria-label": "Center x" }),
        num(center[1], (v) => moveTo(center[0], v), { "aria-label": "Center y" }),
      ),
    );
    if (o.type === "circle") {
      grid.append(h("label", {}, "Radius"), num(o.radius, (v) => v > 0 && update({ ...o, radius: v }), { min: 0.01 }));
    } else if (o.type === "rect") {
      grid.append(
        h("label", {}, "Size"),
        h(
          "div",
          { class: "pair" },
          num(o.size[0], (v) => v > 0 && update({ ...o, size: [v, o.size[1]] }), { min: 0.01, "aria-label": "Width" }),
          num(o.size[1], (v) => v > 0 && update({ ...o, size: [o.size[0], v] }), { min: 0.01, "aria-label": "Height" }),
        ),
        h("label", {}, "Angle (deg)"),
        num(o.angle || 0, (v) => update({ ...o, angle: v }), { step: 5 }),
      );
    } else {
      grid.append(h("label", {}, "Vertices"), h("span", { class: "muted" }, String(o.points.length)));
    }
    const names = { circle: "Circle", rect: "Rectangle", polygon: "Polygon" };
    this.props.append(
      h(
        "div",
        { class: "selection-card" },
        h(
          "div",
          { class: "row" },
          h("h3", {}, `${names[o.type]} #${index + 1}`),
          h(
            "div",
            {},
            h("button", { class: "btn icon ghost", title: "Duplicate (Ctrl+D)", onclick: () => app.duplicateSelection() }, icon("copy")),
            h("button", { class: "btn icon ghost danger", title: "Delete (Del)", onclick: () => app.deleteSelection() }, icon("trash")),
          ),
        ),
        grid,
      ),
    );
  }

  renderWorld() {
    const app = this.app;
    const env = app.env;
    if (this.form.contains(document.activeElement) && document.activeElement.tagName === "INPUT") return;
    clear(this.form);
    const [xmin, ymin, xmax, ymax] = env.bounds;
    const num = (value, fn, attrs) => numberInput(round(value, 3), fn, attrs);
    const name = h("input", { type: "text", value: env.name || "", "aria-label": "Name" });
    name.addEventListener("change", () => app.patchEnv({ name: name.value }));
    this.form.append(
      h("label", {}, "Name"),
      name,
      h("label", { title: "Width and height of the world" }, "Size"),
      h(
        "div",
        { class: "pair" },
        num(xmax - xmin, (v) => v > 0 && app.patchEnv({ bounds: [xmin, ymin, xmin + v, ymax] }), { min: 1, "aria-label": "Width" }),
        num(ymax - ymin, (v) => v > 0 && app.patchEnv({ bounds: [xmin, ymin, xmax, ymin + v] }), { min: 1, "aria-label": "Height" }),
      ),
      h("label", { title: "Cell size used by grid-based planners" }, "Grid cell size"),
      num(env.resolution, (v) => v > 0 && app.patchEnv({ resolution: v }), { min: 0.05, step: 0.1 }),
      h("label", { title: "The robot is a disc; 0 means a point robot" }, "Robot radius"),
      num(env.robot_radius, (v) => v >= 0 && app.patchEnv({ robot_radius: v }), { min: 0, step: 0.25 }),
      h("label", {}, "Start"),
      h(
        "div",
        { class: "pair" },
        num(env.start[0], (v) => app.patchEnv({ start: [v, env.start[1]] }), { "aria-label": "Start x" }),
        num(env.start[1], (v) => app.patchEnv({ start: [env.start[0], v] }), { "aria-label": "Start y" }),
      ),
      h("label", {}, "Goal"),
      h(
        "div",
        { class: "pair" },
        num(env.goal[0], (v) => app.patchEnv({ goal: [v, env.goal[1]] }), { "aria-label": "Goal x" }),
        num(env.goal[1], (v) => app.patchEnv({ goal: [env.goal[0], v] }), { "aria-label": "Goal y" }),
      ),
      h("label", {}, "Obstacles"),
      h(
        "div",
        { class: "pair", style: { alignItems: "center", justifyContent: "space-between" } },
        h("span", { class: "muted" }, String(env.obstacles.length)),
        h("button", { class: "btn small danger", disabled: !env.obstacles.length, onclick: () => app.clearObstacles() }, "Clear all"),
      ),
    );
  }
}
