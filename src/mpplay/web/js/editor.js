// Pointer interaction on the canvas views: editing tools, selection handles, pan & zoom.

import {
  clampPoint,
  pickObstacle,
  polygonArea,
  rectVertices,
  rotate,
  roundShape,
  translate,
} from "./geometry.js";

export const TOOLS = [
  { id: "select", icon: "cursor", label: "Select & move", key: "v", hint: "Drag shapes, handles, start or goal. Drag empty space to pan; scroll to zoom." },
  { id: "rect", icon: "rect", label: "Rectangle", key: "r", hint: "Drag to draw a rectangle (Shift: square)." },
  { id: "circle", icon: "circle", label: "Circle", key: "c", hint: "Drag from the center outwards to draw a circle." },
  { id: "polygon", icon: "polygon", label: "Polygon", key: "p", hint: "Click to add vertices; click the first vertex, double-click or press Enter to close. Esc cancels." },
  { id: "erase", icon: "eraser", label: "Erase", key: "e", hint: "Click or drag over obstacles to delete them." },
  { id: "start", icon: "start", label: "Place start", key: "s", hint: "Click to place the start position." },
  { id: "goal", icon: "goal", label: "Place goal", key: "g", hint: "Click to place the goal position." },
];

const MARKER_PX = 11;
const HANDLE_PX = 8;
const MIN_SIZE = 0.2;

/** Interactive handles of a selected shape (world coordinates). */
export function handlesFor(o, T) {
  if (!o) return [];
  if (o.type === "circle") {
    return [{ kind: "radius", p: [o.center[0] + o.radius, o.center[1]] }];
  }
  if (o.type === "polygon") return o.points.map((p, index) => ({ kind: "vertex", index, p }));
  const corners = rectVertices(o).map((p, index) => ({ kind: "corner", index, p }));
  const top = rotate([0, o.size[1] / 2], o.angle || 0);
  const knob = rotate([0, o.size[1] / 2 + T.px(26)], o.angle || 0);
  return [
    ...corners,
    {
      kind: "rotate",
      p: [o.center[0] + knob[0], o.center[1] + knob[1]],
      anchor: [o.center[0] + top[0], o.center[1] + top[1]],
    },
  ];
}

export class Editor {
  constructor(app) {
    this.app = app;
    this.drag = null;
    this.draft = null;
    this.hover = null;
    this.polygon = null; // vertices of the polygon being drawn
    this.spaceDown = false;
  }

  /** Wire pointer events of a view canvas. `view.transform()` returns its current Transform. */
  attach(view) {
    const c = view.canvas;
    c.addEventListener("pointerdown", (e) => this.onDown(e, view));
    c.addEventListener("pointermove", (e) => this.onMove(e, view));
    c.addEventListener("pointerup", (e) => this.onUp(e, view));
    c.addEventListener("pointercancel", (e) => this.onUp(e, view));
    c.addEventListener("pointerleave", () => {
      if (!this.drag) {
        this.hover = null;
        view.setCoords(null);
        if (this.draft && this.draft.type === "polyline") this.draft.cursor = null;
        this.app.requestRender();
      }
    });
    c.addEventListener("wheel", (e) => this.onWheel(e, view), { passive: false });
    c.addEventListener("dblclick", (e) => {
      if (this.app.tool === "polygon") this.finishPolygon();
      e.preventDefault();
    });
    c.addEventListener("contextmenu", (e) => e.preventDefault());
  }

  // ------------------------------------------------------------------ helpers

  world(e, view) {
    const rect = view.canvas.getBoundingClientRect();
    const T = view.transform();
    return { T, s: [e.clientX - rect.left, e.clientY - rect.top], p: T.toWorld([e.clientX - rect.left, e.clientY - rect.top]) };
  }

  selectedShape() {
    const sel = this.app.selection;
    return sel !== null ? this.app.env.obstacles[sel] : null;
  }

  hitTest(p, T) {
    const env = this.app.env;
    const near = (q, px) => Math.hypot(q[0] - p[0], q[1] - p[1]) <= T.px(px);
    const shape = this.selectedShape();
    if (shape && this.app.tool === "select") {
      for (const hd of handlesFor(shape, T)) if (near(hd.p, HANDLE_PX)) return { kind: "handle", handle: hd };
    }
    const r = Math.max(env.robot_radius, T.px(MARKER_PX));
    if (Math.hypot(env.goal[0] - p[0], env.goal[1] - p[1]) <= r) return { kind: "goal" };
    if (Math.hypot(env.start[0] - p[0], env.start[1] - p[1]) <= r) return { kind: "start" };
    const idx = pickObstacle(env.obstacles, p, T.px(3));
    if (idx >= 0) return { kind: "obstacle", index: idx };
    return null;
  }

  cursorFor(hit) {
    if (!hit) return this.app.tool === "select" ? "grab" : "crosshair";
    if (hit.kind === "handle") return hit.handle.kind === "rotate" ? "alias" : "pointer";
    if (hit.kind === "start" || hit.kind === "goal") return "grab";
    return this.app.tool === "erase" ? "not-allowed" : "move";
  }

  setEnvField(field, value) {
    this.app.previewEnv({ ...this.app.env, [field]: value });
  }

  replaceObstacle(index, shape) {
    const obstacles = this.app.env.obstacles.slice();
    obstacles[index] = shape;
    this.app.previewEnv({ ...this.app.env, obstacles });
  }

  // ------------------------------------------------------------------ events

  onDown(e, view) {
    const { T, s, p } = this.world(e, view);
    view.canvas.setPointerCapture(e.pointerId);
    const app = this.app;
    const pan = e.button === 1 || e.button === 2 || this.spaceDown;
    if (pan) {
      this.drag = { kind: "pan", last: s };
      view.canvas.style.cursor = "grabbing";
      return;
    }
    if (e.button !== 0) return;
    const tool = app.tool;
    const env = app.env;
    const inside = clampPoint(p, env.bounds);

    if (tool === "start" || tool === "goal") {
      app.beginEdit();
      this.setEnvField(tool, inside);
      this.drag = { kind: tool };
      return;
    }
    if (tool === "polygon") {
      this.addPolygonPoint(inside, T);
      return;
    }
    if (tool === "rect" || tool === "circle") {
      this.drag = { kind: "draw", anchor: inside, shift: e.shiftKey };
      this.updateDraw(inside, e.shiftKey);
      return;
    }
    if (tool === "erase") {
      app.beginEdit();
      this.drag = { kind: "erase", erased: 0 };
      this.eraseAt(p, T);
      return;
    }

    // select tool
    const hit = this.hitTest(p, T);
    if (!hit) {
      app.select(null);
      this.drag = { kind: "pan", last: s };
      view.canvas.style.cursor = "grabbing";
      return;
    }
    app.beginEdit();
    if (hit.kind === "start" || hit.kind === "goal") {
      this.drag = { kind: hit.kind, offset: [env[hit.kind][0] - p[0], env[hit.kind][1] - p[1]] };
    } else if (hit.kind === "obstacle") {
      app.select(hit.index);
      this.drag = { kind: "move", index: hit.index, origin: p, shape: env.obstacles[hit.index] };
    } else {
      const index = app.selection;
      this.drag = { kind: "handle", handle: hit.handle, index, shape: env.obstacles[index] };
    }
  }

  onMove(e, view) {
    const { T, s, p } = this.world(e, view);
    const app = this.app;
    view.setCoords(p);
    const d = this.drag;
    if (!d) {
      if (app.tool === "polygon" && this.draft) {
        this.draft.cursor = clampPoint(p, app.env.bounds);
        app.requestRender();
      } else if (app.tool === "erase") {
        this.draft = { type: "eraser", p, r: 6 };
        app.requestRender();
      }
      const hit = app.tool === "select" || app.tool === "erase" ? this.hitTest(p, T) : null;
      const hover = hit && hit.kind === "obstacle" ? hit.index : null;
      if (hover !== this.hover) {
        this.hover = hover;
        app.requestRender();
      }
      view.canvas.style.cursor = this.spaceDown ? "grab" : this.cursorFor(hit);
      return;
    }
    const env = app.env;
    const inside = clampPoint(p, env.bounds);
    switch (d.kind) {
      case "pan":
        app.camera.pan(env.bounds, s[0] - d.last[0], s[1] - d.last[1], T.scale);
        d.last = s;
        app.requestRender();
        break;
      case "start":
      case "goal": {
        const off = d.offset || [0, 0];
        this.setEnvField(d.kind, clampPoint([p[0] + off[0], p[1] + off[1]], env.bounds));
        break;
      }
      case "move":
        this.replaceObstacle(d.index, translate(d.shape, p[0] - d.origin[0], p[1] - d.origin[1]));
        break;
      case "handle":
        this.replaceObstacle(d.index, this.applyHandle(d.shape, d.handle, inside, e.shiftKey));
        break;
      case "draw":
        this.updateDraw(inside, e.shiftKey);
        break;
      case "erase":
        this.draft = { type: "eraser", p, r: 6 };
        this.eraseAt(p, T);
        break;
      default:
        break;
    }
  }

  onUp(e, view) {
    const d = this.drag;
    this.drag = null;
    if (view.canvas.hasPointerCapture(e.pointerId)) view.canvas.releasePointerCapture(e.pointerId);
    if (!d) return;
    const app = this.app;
    view.canvas.style.cursor = "";
    if (d.kind === "draw") {
      const shape = this.draft;
      this.draft = null;
      if (shape && this.validShape(shape)) {
        app.beginEdit();
        const obstacles = [...app.env.obstacles, roundShape(shape)];
        app.previewEnv({ ...app.env, obstacles });
        app.commitEdit();
        app.select(obstacles.length - 1);
      } else {
        app.requestRender();
      }
      return;
    }
    if (d.kind === "erase") {
      if (d.erased) app.commitEdit();
      else app.cancelEdit();
      return;
    }
    if (d.kind === "pan") return;
    if (d.kind === "move" || d.kind === "handle") {
      const shape = app.env.obstacles[d.index];
      if (shape) {
        const obstacles = app.env.obstacles.slice();
        obstacles[d.index] = roundShape(shape);
        app.previewEnv({ ...app.env, obstacles });
      }
    }
    app.commitEdit();
  }

  onWheel(e, view) {
    e.preventDefault();
    const { p } = this.world(e, view);
    const factor = Math.exp(-e.deltaY * (e.ctrlKey ? 0.01 : 0.0015));
    this.app.camera.zoomAt(this.app.env.bounds, view.size(), factor, p);
    this.app.requestRender();
  }

  // ------------------------------------------------------------------ tool logic

  updateDraw(p, shift) {
    const a = this.drag.anchor;
    if (this.app.tool === "circle") {
      this.draft = { type: "circle", center: a, radius: Math.hypot(p[0] - a[0], p[1] - a[1]) };
    } else {
      let w = p[0] - a[0];
      let hgt = p[1] - a[1];
      if (shift) {
        const m = Math.max(Math.abs(w), Math.abs(hgt));
        w = Math.sign(w || 1) * m;
        hgt = Math.sign(hgt || 1) * m;
      }
      this.draft = {
        type: "rect",
        center: [a[0] + w / 2, a[1] + hgt / 2],
        size: [Math.abs(w), Math.abs(hgt)],
        angle: 0,
      };
    }
    this.app.requestRender();
  }

  validShape(o) {
    if (o.type === "circle") return o.radius >= MIN_SIZE;
    if (o.type === "rect") return o.size[0] >= MIN_SIZE && o.size[1] >= MIN_SIZE;
    return o.points.length >= 3 && Math.abs(polygonArea(o.points)) > 1e-3;
  }

  applyHandle(shape, handle, p, shift) {
    if (handle.kind === "radius") {
      return { ...shape, radius: Math.max(Math.hypot(p[0] - shape.center[0], p[1] - shape.center[1]), MIN_SIZE) };
    }
    if (handle.kind === "vertex") {
      const points = shape.points.slice();
      points[handle.index] = p;
      return { ...shape, points };
    }
    const [cx, cy] = shape.center;
    const angle = shape.angle || 0;
    if (handle.kind === "rotate") {
      let deg = (Math.atan2(p[1] - cy, p[0] - cx) * 180) / Math.PI - 90;
      if (shift) deg = Math.round(deg / 15) * 15;
      deg = ((((deg + 180) % 360) + 360) % 360) - 180;
      return { ...shape, angle: deg };
    }
    // Corner: keep the opposite corner fixed (in the rectangle's own frame).
    const signs = [
      [-1, -1],
      [1, -1],
      [1, 1],
      [-1, 1],
    ][handle.index];
    const opp = [-signs[0] * shape.size[0] / 2, -signs[1] * shape.size[1] / 2];
    const local = rotate([p[0] - cx, p[1] - cy], -angle);
    const size = [Math.max(Math.abs(local[0] - opp[0]), MIN_SIZE), Math.max(Math.abs(local[1] - opp[1]), MIN_SIZE)];
    const mid = rotate([(local[0] + opp[0]) / 2, (local[1] + opp[1]) / 2], angle);
    return { ...shape, center: [cx + mid[0], cy + mid[1]], size };
  }

  eraseAt(p, T) {
    const env = this.app.env;
    const idx = pickObstacle(env.obstacles, p, T.px(6));
    if (idx >= 0) {
      const obstacles = env.obstacles.filter((_, i) => i !== idx);
      this.drag.erased++;
      this.app.select(null);
      this.app.previewEnv({ ...env, obstacles });
    } else {
      this.app.requestRender();
    }
  }

  addPolygonPoint(p, T) {
    if (!this.draft || this.draft.type !== "polyline") this.draft = { type: "polyline", points: [], cursor: p };
    const pts = this.draft.points;
    const close = (q, px) => Math.hypot(q[0] - p[0], q[1] - p[1]) <= T.px(px);
    if (pts.length >= 3 && close(pts[0], 9)) {
      this.finishPolygon();
      return;
    }
    if (pts.length && close(pts[pts.length - 1], 4)) {
      if (pts.length >= 3) this.finishPolygon();
      return;
    }
    pts.push(p);
    this.app.requestRender();
  }

  finishPolygon() {
    const d = this.draft;
    if (!d || d.type !== "polyline") return;
    this.draft = null;
    const shape = { type: "polygon", points: d.points };
    if (this.validShape(shape)) {
      this.app.beginEdit();
      const obstacles = [...this.app.env.obstacles, roundShape(shape)];
      this.app.previewEnv({ ...this.app.env, obstacles });
      this.app.commitEdit();
      this.app.select(obstacles.length - 1);
    }
    this.app.requestRender();
  }

  /** Keyboard handling for drafts; returns true if the key was consumed. */
  onKey(e) {
    if (this.draft && this.draft.type === "polyline") {
      if (e.key === "Escape") {
        this.draft = null;
        this.app.requestRender();
        return true;
      }
      if (e.key === "Enter") {
        this.finishPolygon();
        return true;
      }
      if (e.key === "Backspace") {
        this.draft.points.pop();
        if (!this.draft.points.length) this.draft = null;
        this.app.requestRender();
        return true;
      }
    }
    return false;
  }

  cancel() {
    this.draft = null;
    this.drag = null;
  }
}
