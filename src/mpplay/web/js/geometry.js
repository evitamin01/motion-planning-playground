// Client-side geometry for editing: shape vertices, hit tests and transforms.
// Shapes use the same JSON format as the Python package (see docs/environment-format.md).

const DEG = Math.PI / 180;

export function rectVertices(o) {
  const [cx, cy] = o.center;
  const hw = o.size[0] / 2;
  const hh = o.size[1] / 2;
  const a = (o.angle || 0) * DEG;
  const c = Math.cos(a);
  const s = Math.sin(a);
  return [
    [-hw, -hh],
    [hw, -hh],
    [hw, hh],
    [-hw, hh],
  ].map(([x, y]) => [cx + x * c - y * s, cy + x * s + y * c]);
}

export function vertices(o) {
  if (o.type === "rect") return rectVertices(o);
  if (o.type === "polygon") return o.points;
  return null;
}

export function bbox(o) {
  if (o.type === "circle") {
    const [x, y] = o.center;
    return [x - o.radius, y - o.radius, x + o.radius, y + o.radius];
  }
  const v = vertices(o);
  const xs = v.map((p) => p[0]);
  const ys = v.map((p) => p[1]);
  return [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)];
}

export function centroid(o) {
  if (o.type !== "polygon") return o.center;
  const n = o.points.length;
  return [
    o.points.reduce((s, p) => s + p[0], 0) / n,
    o.points.reduce((s, p) => s + p[1], 0) / n,
  ];
}

export function pointInPolygon(p, poly) {
  let inside = false;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const [xi, yi] = poly[i];
    const [xj, yj] = poly[j];
    if (yi > p[1] !== yj > p[1] && p[0] < ((xj - xi) * (p[1] - yi)) / (yj - yi) + xi) {
      inside = !inside;
    }
  }
  return inside;
}

export function distToSegment(p, a, b) {
  const dx = b[0] - a[0];
  const dy = b[1] - a[1];
  const len2 = dx * dx + dy * dy;
  let t = len2 > 0 ? ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / len2 : 0;
  t = Math.max(0, Math.min(1, t));
  return Math.hypot(p[0] - (a[0] + t * dx), p[1] - (a[1] + t * dy));
}

/** Whether world point `p` hits shape `o` (with a tolerance in world units). */
export function hitShape(o, p, tol = 0) {
  if (o.type === "circle") return Math.hypot(p[0] - o.center[0], p[1] - o.center[1]) <= o.radius + tol;
  const v = vertices(o);
  if (pointInPolygon(p, v)) return true;
  if (tol <= 0) return false;
  for (let i = 0; i < v.length; i++) {
    if (distToSegment(p, v[i], v[(i + 1) % v.length]) <= tol) return true;
  }
  return false;
}

/** Index of the topmost obstacle under `p`, or -1. */
export function pickObstacle(obstacles, p, tol = 0) {
  for (let i = obstacles.length - 1; i >= 0; i--) {
    if (hitShape(obstacles[i], p, tol)) return i;
  }
  return -1;
}

export function translate(o, dx, dy) {
  if (o.type === "polygon") return { ...o, points: o.points.map(([x, y]) => [x + dx, y + dy]) };
  return { ...o, center: [o.center[0] + dx, o.center[1] + dy] };
}

export function round(v, digits = 3) {
  const f = 10 ** digits;
  return Math.round(v * f) / f;
}

export function roundShape(o) {
  const r = (p) => [round(p[0]), round(p[1])];
  if (o.type === "circle") return { type: "circle", center: r(o.center), radius: round(o.radius) };
  if (o.type === "rect") {
    return { type: "rect", center: r(o.center), size: r(o.size), angle: round(o.angle || 0, 2) };
  }
  return { type: "polygon", points: o.points.map(r) };
}

/** Rotate a vector by `deg` degrees. */
export function rotate([x, y], deg) {
  const a = deg * DEG;
  return [x * Math.cos(a) - y * Math.sin(a), x * Math.sin(a) + y * Math.cos(a)];
}

export function polygonArea(points) {
  let s = 0;
  for (let i = 0, j = points.length - 1; i < points.length; j = i++) {
    s += points[j][0] * points[i][1] - points[i][0] * points[j][1];
  }
  return s / 2;
}

export function clampPoint(p, bounds) {
  return [
    Math.min(Math.max(p[0], bounds[0]), bounds[2]),
    Math.min(Math.max(p[1], bounds[1]), bounds[3]),
  ];
}
