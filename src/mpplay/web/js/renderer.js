// Canvas rendering of environments, planner traces and results.

import { rectVertices } from "./geometry.js";
import { CELL } from "./trace.js";

const TAU = Math.PI * 2;

// ------------------------------------------------------------------ colors

let themeCache = null;

/** Canvas colors from the CSS design tokens (re-read after theme changes). */
export function themeColors(refresh = false) {
  if (themeCache && !refresh) return themeCache;
  const css = getComputedStyle(document.documentElement);
  const v = (name) => css.getPropertyValue(name).trim();
  themeCache = {
    bg: v("--canvas-bg"),
    world: v("--canvas-world"),
    grid: v("--canvas-grid"),
    obstacle: v("--canvas-obstacle"),
    obstacleEdge: v("--canvas-obstacle-edge"),
    cspace: v("--canvas-cspace"),
    occupied: v("--canvas-occupied"),
    roadmap: v("--canvas-roadmap"),
    start: v("--canvas-start"),
    goal: v("--canvas-goal"),
    select: v("--canvas-select"),
    halo: v("--canvas-halo"),
    text: v("--canvas-text"),
    accent: v("--accent"),
  };
  return themeCache;
}

export function hexToRgb(hex) {
  const m = /^#?([0-9a-f]{6})$/i.exec(hex.trim());
  if (!m) return [100, 116, 139];
  const n = parseInt(m[1], 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

export function rgba(hex, alpha) {
  const [r, g, b] = hexToRgb(hex);
  return `rgba(${r},${g},${b},${alpha})`;
}

function parseCssColor(color) {
  // Accepts rgba()/rgb()/#hex as produced by our tokens.
  const m = /rgba?\(([^)]+)\)/.exec(color);
  if (m) {
    const parts = m[1].split(",").map((s) => parseFloat(s));
    return [parts[0], parts[1], parts[2], Math.round((parts[3] ?? 1) * 255)];
  }
  return [...hexToRgb(color), 255];
}

// Viridis-like ramp for heatmaps (dark = low).
const RAMP = [
  [68, 1, 84],
  [59, 82, 139],
  [33, 145, 140],
  [94, 201, 98],
  [253, 231, 37],
];

function ramp(t) {
  const x = Math.min(Math.max(t, 0), 1) * (RAMP.length - 1);
  const i = Math.min(Math.floor(x), RAMP.length - 2);
  const f = x - i;
  return RAMP[i].map((c, k) => Math.round(c + (RAMP[i + 1][k] - c) * f));
}

// ------------------------------------------------------------------ offscreen caches

const cellCache = new WeakMap(); // TraceState -> {canvas, ctx, image, key}
const gridCache = new WeakMap(); // decoded grid -> {canvas, key}
const scratch = document.createElement("canvas");

function cellCanvas(state, color) {
  const { nx, ny } = state.grid;
  const front = hexToRgb(color);
  const key = color;
  let entry = cellCache.get(state);
  const full = !entry || entry.key !== key || state.cellsReset;
  if (!entry) {
    const canvas = document.createElement("canvas");
    canvas.width = nx;
    canvas.height = ny;
    const ctx = canvas.getContext("2d");
    entry = { canvas, ctx, image: ctx.createImageData(nx, ny), key };
    cellCache.set(state, entry);
  }
  const px = entry.image.data;
  const write = (c) => {
    const i = c % nx;
    const j = (c - i) / nx;
    const o = ((ny - 1 - j) * nx + i) * 4;
    const v = state.cells[c];
    px[o] = front[0];
    px[o + 1] = front[1];
    px[o + 2] = front[2];
    px[o + 3] = v === CELL.EXPANDED ? 70 : v === CELL.FRONTIER ? 170 : 0;
  };
  if (full) {
    for (let c = 0; c < state.cells.length; c++) write(c);
    entry.key = key;
    state.cellsReset = false;
    state.changedCells = [];
    entry.ctx.putImageData(entry.image, 0, 0);
  } else if (state.changedCells.length) {
    for (const c of state.changedCells) write(c);
    state.changedCells = [];
    entry.ctx.putImageData(entry.image, 0, 0);
  }
  return entry.canvas;
}

function gridCanvas(grid, colorFn, key) {
  let entry = gridCache.get(grid);
  if (entry && entry.key === key) return entry.canvas;
  const { nx, ny, data } = grid;
  const canvas = document.createElement("canvas");
  canvas.width = nx;
  canvas.height = ny;
  const ctx = canvas.getContext("2d");
  const image = ctx.createImageData(nx, ny);
  for (let j = 0; j < ny; j++) {
    for (let i = 0; i < nx; i++) {
      const rgbaVal = colorFn(data[j * nx + i]);
      const o = ((ny - 1 - j) * nx + i) * 4;
      image.data[o] = rgbaVal[0];
      image.data[o + 1] = rgbaVal[1];
      image.data[o + 2] = rgbaVal[2];
      image.data[o + 3] = rgbaVal[3];
    }
  }
  ctx.putImageData(image, 0, 0);
  entry = { canvas, key };
  gridCache.set(grid, entry);
  return canvas;
}

function drawGridImage(ctx, T, grid, canvas, smooth) {
  ctx.imageSmoothingEnabled = smooth;
  const x = T.x(grid.ox);
  const y = T.y(grid.oy + grid.ny * grid.res);
  ctx.drawImage(canvas, x, y, grid.nx * grid.res * T.scale, grid.ny * grid.res * T.scale);
  ctx.imageSmoothingEnabled = true;
}

// ------------------------------------------------------------------ shapes

function shapePath(ctx, T, o, grow = 0) {
  if (o.type === "circle") {
    ctx.moveTo(T.x(o.center[0]) + (o.radius + grow) * T.scale, T.y(o.center[1]));
    ctx.arc(T.x(o.center[0]), T.y(o.center[1]), Math.max((o.radius + grow) * T.scale, 0), 0, TAU);
    return;
  }
  const v = o.type === "rect" ? rectVertices(o) : o.points;
  ctx.moveTo(T.x(v[0][0]), T.y(v[0][1]));
  for (let i = 1; i < v.length; i++) ctx.lineTo(T.x(v[i][0]), T.y(v[i][1]));
  ctx.closePath();
}

function drawObstacles(ctx, T, env, colors) {
  ctx.beginPath();
  for (const o of env.obstacles) shapePath(ctx, T, o);
  ctx.fillStyle = colors.obstacle;
  ctx.fill("nonzero");
  ctx.lineWidth = 1;
  ctx.strokeStyle = colors.obstacleEdge;
  ctx.stroke();
}

function drawCspace(ctx, T, env, colors, width, height) {
  const r = env.robot_radius * T.scale;
  if (r < 0.5 || !env.obstacles.length) return;
  const dpr = ctx.getTransform().a;
  scratch.width = Math.ceil(width * dpr);
  scratch.height = Math.ceil(height * dpr);
  const s = scratch.getContext("2d");
  s.setTransform(dpr, 0, 0, dpr, 0, 0);
  s.clearRect(0, 0, width, height);
  s.fillStyle = colors.cspace;
  s.strokeStyle = colors.cspace;
  s.lineJoin = "round";
  s.lineWidth = 2 * r;
  for (const o of env.obstacles) {
    s.beginPath();
    if (o.type === "circle") {
      shapePath(s, T, o, env.robot_radius);
      s.fill();
    } else {
      shapePath(s, T, o);
      s.fill();
      s.stroke();
    }
  }
  // The world border is a wall as well.
  const [xmin, ymin, xmax, ymax] = env.bounds;
  s.lineWidth = 2 * r;
  s.strokeRect(T.x(xmin), T.y(ymax), (xmax - xmin) * T.scale, (ymax - ymin) * T.scale);
  ctx.save();
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.globalAlpha = 0.18;
  ctx.drawImage(scratch, 0, 0);
  ctx.restore();
}

function drawGridLines(ctx, T, env, colors) {
  const res = env.resolution;
  if (res * T.scale < 7) return;
  const [xmin, ymin, xmax, ymax] = env.bounds;
  ctx.beginPath();
  for (let x = xmin; x <= xmax + 1e-9; x += res) {
    ctx.moveTo(Math.round(T.x(x)) + 0.5, T.y(ymin));
    ctx.lineTo(Math.round(T.x(x)) + 0.5, T.y(ymax));
  }
  for (let y = ymin; y <= ymax + 1e-9; y += res) {
    ctx.moveTo(T.x(xmin), Math.round(T.y(y)) + 0.5);
    ctx.lineTo(T.x(xmax), Math.round(T.y(y)) + 0.5);
  }
  ctx.strokeStyle = colors.grid;
  ctx.lineWidth = 1;
  ctx.stroke();
}

// ------------------------------------------------------------------ traces

function edgeStyle(layer, color, color2, colors) {
  switch (layer) {
    case "tree2":
      return { stroke: rgba(color2, 0.75), width: 1 };
    case "roadmap":
      return { stroke: colors.roadmap, width: 0.8 };
    case "trajectory":
      return { stroke: color, width: 2.2 };
    default:
      return { stroke: rgba(color, 0.7), width: 1 };
  }
}

function drawExploration(ctx, T, state, color, color2, colors) {
  // Edges grouped by layer, one stroke per layer.
  if (state.edges.size) {
    const paths = new Map();
    for (const e of state.edges.values()) {
      const layer = e[6];
      let p = paths.get(layer);
      if (!p) paths.set(layer, (p = new Path2D()));
      p.moveTo(T.x(e[2]), T.y(e[3]));
      p.lineTo(T.x(e[4]), T.y(e[5]));
    }
    ctx.lineCap = "round";
    for (const [layer, p] of paths) {
      const style = edgeStyle(layer, color, color2, colors);
      ctx.strokeStyle = style.stroke;
      ctx.lineWidth = style.width;
      ctx.stroke(p);
    }
  }
  if (state.nodes.length) {
    const roadmap = new Path2D();
    const visited = new Path2D();
    for (const n of state.nodes) {
      const x = T.x(n[1]);
      const y = T.y(n[2]);
      if (n[3] === "visited") visited.rect(x - 2.5, y - 2.5, 5, 5);
      else roadmap.rect(x - 1.5, y - 1.5, 3, 3);
    }
    ctx.fillStyle = colors.roadmap;
    ctx.fill(roadmap);
    ctx.fillStyle = color;
    ctx.fill(visited);
  }
  for (const geom of state.overlays.values()) {
    if (geom.type === "ellipse") {
      ctx.beginPath();
      ctx.ellipse(
        T.x(geom.center[0]),
        T.y(geom.center[1]),
        Math.max(geom.rx * T.scale, 0.1),
        Math.max(geom.ry * T.scale, 0.1),
        -geom.angle,
        0,
        TAU,
      );
      ctx.fillStyle = rgba(color, 0.06);
      ctx.fill();
      ctx.setLineDash([6, 5]);
      ctx.strokeStyle = rgba(color, 0.9);
      ctx.lineWidth = 1.5;
      ctx.stroke();
      ctx.setLineDash([]);
    }
  }
}

function drawSample(ctx, T, p, color) {
  const x = T.x(p[0]);
  const y = T.y(p[1]);
  ctx.beginPath();
  ctx.arc(x, y, 6, 0, TAU);
  ctx.strokeStyle = color;
  ctx.lineWidth = 1.5;
  ctx.stroke();
  ctx.beginPath();
  ctx.moveTo(x - 3, y);
  ctx.lineTo(x + 3, y);
  ctx.moveTo(x, y - 3);
  ctx.lineTo(x, y + 3);
  ctx.stroke();
}

function polyline(ctx, T, pts) {
  ctx.beginPath();
  ctx.moveTo(T.x(pts[0][0]), T.y(pts[0][1]));
  for (let i = 1; i < pts.length; i++) ctx.lineTo(T.x(pts[i][0]), T.y(pts[i][1]));
}

export function drawPath(ctx, T, pts, color, colors, { width = 3, dashed = false, halo = true } = {}) {
  if (!pts || pts.length < 2) return;
  ctx.lineCap = "round";
  ctx.lineJoin = "round";
  if (halo) {
    polyline(ctx, T, pts);
    ctx.strokeStyle = colors.halo;
    ctx.lineWidth = width + 3.5;
    ctx.stroke();
  }
  polyline(ctx, T, pts);
  ctx.strokeStyle = color;
  ctx.lineWidth = width;
  if (dashed) ctx.setLineDash([7, 6]);
  ctx.stroke();
  ctx.setLineDash([]);
  if (!dashed && pts.length <= 80) {
    ctx.fillStyle = color;
    for (const p of pts.slice(1, -1)) {
      ctx.beginPath();
      ctx.arc(T.x(p[0]), T.y(p[1]), width * 0.85, 0, TAU);
      ctx.fill();
    }
  }
}

function drawMarker(ctx, T, p, radius, color, colors, kind) {
  const x = T.x(p[0]);
  const y = T.y(p[1]);
  const rr = radius * T.scale;
  if (rr > 4) {
    ctx.beginPath();
    ctx.arc(x, y, rr, 0, TAU);
    ctx.fillStyle = rgba(color, 0.18);
    ctx.fill();
    ctx.strokeStyle = color;
    ctx.lineWidth = 1.5;
    ctx.stroke();
  }
  const r = 7;
  ctx.beginPath();
  ctx.arc(x, y, r + 2, 0, TAU);
  ctx.fillStyle = colors.halo;
  ctx.fill();
  ctx.beginPath();
  ctx.arc(x, y, r, 0, TAU);
  ctx.fillStyle = color;
  ctx.fill();
  ctx.fillStyle = colors.halo;
  ctx.font = "bold 9px system-ui, sans-serif";
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText(kind === "start" ? "S" : "G", x, y + 0.5);
}

// ------------------------------------------------------------------ editing overlays

function drawSelection(ctx, T, o, handles, colors) {
  ctx.beginPath();
  shapePath(ctx, T, o);
  ctx.setLineDash([5, 4]);
  ctx.strokeStyle = colors.select;
  ctx.lineWidth = 2;
  ctx.stroke();
  ctx.setLineDash([]);
  for (const hd of handles) {
    const [x, y] = T.toScreen(hd.p);
    if (hd.kind === "rotate") {
      const [cx, cy] = T.toScreen(hd.anchor);
      ctx.beginPath();
      ctx.moveTo(cx, cy);
      ctx.lineTo(x, y);
      ctx.strokeStyle = colors.select;
      ctx.lineWidth = 1;
      ctx.stroke();
      ctx.beginPath();
      ctx.arc(x, y, 5, 0, TAU);
    } else {
      ctx.beginPath();
      ctx.rect(x - 4.5, y - 4.5, 9, 9);
    }
    ctx.fillStyle = colors.halo;
    ctx.fill();
    ctx.strokeStyle = colors.select;
    ctx.lineWidth = 1.5;
    ctx.stroke();
  }
}

function drawDraft(ctx, T, draft, colors) {
  ctx.save();
  ctx.setLineDash([5, 4]);
  ctx.strokeStyle = colors.accent;
  ctx.fillStyle = rgba(colors.accent.startsWith("#") ? colors.accent : "#2563eb", 0.12);
  ctx.lineWidth = 1.5;
  if (draft.type === "polyline") {
    const pts = draft.cursor ? [...draft.points, draft.cursor] : draft.points;
    if (pts.length) {
      polyline(ctx, T, pts);
      ctx.stroke();
      ctx.setLineDash([]);
      for (const [i, p] of draft.points.entries()) {
        ctx.beginPath();
        ctx.arc(T.x(p[0]), T.y(p[1]), i === 0 ? 6 : 3.5, 0, TAU);
        ctx.fillStyle = colors.halo;
        ctx.fill();
        ctx.stroke();
      }
    }
  } else if (draft.type === "eraser") {
    ctx.setLineDash([]);
    ctx.beginPath();
    ctx.arc(T.x(draft.p[0]), T.y(draft.p[1]), draft.r, 0, TAU);
    ctx.strokeStyle = colors.goal;
    ctx.stroke();
  } else {
    ctx.beginPath();
    shapePath(ctx, T, draft);
    ctx.fill();
    ctx.stroke();
  }
  ctx.restore();
}

// ------------------------------------------------------------------ scene

/**
 * Draw a full view.
 *
 * @param {CanvasRenderingContext2D} ctx - context already scaled for device pixels
 * @param {object} scene - {width, height, T, env, layers, items, selection, draft, hover}
 *   items: [{color, color2, state (TraceState|null), result, exploration: bool, path: bool}]
 */
export function drawScene(ctx, scene) {
  const { width, height, T, env, layers } = scene;
  const colors = themeColors();
  ctx.fillStyle = colors.bg;
  ctx.fillRect(0, 0, width, height);
  if (!env) return;

  const [xmin, ymin, xmax, ymax] = env.bounds;
  ctx.fillStyle = colors.world;
  ctx.fillRect(T.x(xmin), T.y(ymax), (xmax - xmin) * T.scale, (ymax - ymin) * T.scale);

  const items = scene.items || [];
  const explored = items.filter((it) => it.exploration && it.state);

  // Everything inside the world (layers, obstacles, search) is clipped to its bounds;
  // the border, paths, markers and editing handles are drawn unclipped afterwards.
  ctx.save();
  ctx.beginPath();
  ctx.rect(T.x(xmin), T.y(ymax), (xmax - xmin) * T.scale, (ymax - ymin) * T.scale);
  ctx.clip();

  // Background layers: heatmaps, discretization, explored cells.
  if (layers.heatmap) {
    for (const it of explored) {
      for (const hm of it.state.heatmaps) {
        const canvas = gridCanvas(hm, (v) => [...ramp(v / 255), 120], "heatmap");
        drawGridImage(ctx, T, hm, canvas, true);
      }
    }
  }
  if (layers.gridLines) drawGridLines(ctx, T, env, colors);
  if (layers.occupancy) {
    for (const it of explored) {
      if (!it.state.grid) continue;
      const occ = parseCssColor(colors.occupied);
      const canvas = gridCanvas(it.state.grid, (v) => (v ? occ : [0, 0, 0, 0]), colors.occupied);
      drawGridImage(ctx, T, it.state.grid, canvas, false);
    }
  }
  // Finished searches are dimmed so that the final path stands out.
  const dim = (it) => (it.state.complete && it.result?.path ? 0.5 : 1);
  if (layers.exploration) {
    for (const it of explored) {
      if (it.state.grid && it.state.cells) {
        ctx.globalAlpha = dim(it);
        drawGridImage(ctx, T, it.state.grid, cellCanvas(it.state, it.color), false);
        ctx.globalAlpha = 1;
      }
    }
  }

  if (layers.cspace && env.robot_radius > 0) drawCspace(ctx, T, env, colors, width, height);
  drawObstacles(ctx, T, env, colors);

  if (layers.exploration) {
    for (const it of explored) {
      ctx.globalAlpha = dim(it);
      drawExploration(ctx, T, it.state, it.color, it.color2, colors);
      ctx.globalAlpha = 1;
      const sample = it.state.currentSample();
      if (sample) drawSample(ctx, T, sample, it.color);
      if (!it.state.complete && it.state.path) {
        drawPath(ctx, T, it.state.path, it.color, colors, { width: 2, dashed: true, halo: false });
      }
    }
  }
  ctx.restore();

  // World border.
  ctx.strokeStyle = colors.obstacleEdge;
  ctx.lineWidth = 1.5;
  ctx.strokeRect(T.x(xmin), T.y(ymax), (xmax - xmin) * T.scale, (ymax - ymin) * T.scale);

  // Paths: final results once the animation for that run has finished.
  for (const it of items) {
    if (!it.path || !it.result) continue;
    const done = !it.state || it.state.complete;
    if (!done) continue;
    if (layers.rawPath && it.result.raw_path) {
      drawPath(ctx, T, it.result.raw_path, rgba(it.color, 0.7), colors, {
        width: 1.5,
        dashed: true,
        halo: false,
      });
    }
    if (it.result.path) drawPath(ctx, T, it.result.path, it.color, colors);
  }

  if (scene.hover !== undefined && scene.hover !== null && typeof scene.hover === "number") {
    const o = env.obstacles[scene.hover];
    if (o) {
      ctx.beginPath();
      shapePath(ctx, T, o);
      ctx.strokeStyle = colors.select;
      ctx.lineWidth = 1.5;
      ctx.stroke();
    }
  }
  if (scene.selection && scene.selection.shape) {
    drawSelection(ctx, T, scene.selection.shape, scene.selection.handles || [], colors);
  }
  if (scene.draft) drawDraft(ctx, T, scene.draft, colors);

  drawMarker(ctx, T, env.start, env.robot_radius, colors.start, colors, "start");
  drawMarker(ctx, T, env.goal, env.robot_radius, colors.goal, colors, "goal");
}

