// World <-> screen transforms shared by all views (y axis points up in the world).

export class Camera {
  constructor() {
    this.zoom = 1;
    this.center = null; // world point at the middle of each view; null = fit
  }

  fit() {
    this.zoom = 1;
    this.center = null;
  }

  /** Transform for a view of `width` x `height` CSS pixels showing `bounds`. */
  transform(bounds, width, height, pad = 18) {
    const [xmin, ymin, xmax, ymax] = bounds;
    const fit = Math.min((width - 2 * pad) / (xmax - xmin), (height - 2 * pad) / (ymax - ymin));
    const scale = Math.max(fit, 1e-6) * this.zoom;
    const [cx, cy] = this.center || [(xmin + xmax) / 2, (ymin + ymax) / 2];
    return new Transform(scale, width / 2 - cx * scale, height / 2 + cy * scale);
  }

  /** Zoom by `factor` keeping world point `anchor` fixed under the cursor. */
  zoomAt(bounds, view, factor, anchor) {
    const before = this.transform(bounds, view.width, view.height);
    const center = this.center || [(bounds[0] + bounds[2]) / 2, (bounds[1] + bounds[3]) / 2];
    const zoom = Math.min(Math.max(this.zoom * factor, 0.25), 60);
    const k = before.scale / (before.scale * (zoom / this.zoom));
    this.center = [anchor[0] + (center[0] - anchor[0]) * k, anchor[1] + (center[1] - anchor[1]) * k];
    this.zoom = zoom;
  }

  pan(bounds, dxPx, dyPx, scale) {
    const center = this.center || [(bounds[0] + bounds[2]) / 2, (bounds[1] + bounds[3]) / 2];
    this.center = [center[0] - dxPx / scale, center[1] + dyPx / scale];
  }
}

export class Transform {
  constructor(scale, ox, oy) {
    this.scale = scale;
    this.ox = ox;
    this.oy = oy;
  }

  x(wx) {
    return this.ox + wx * this.scale;
  }

  y(wy) {
    return this.oy - wy * this.scale;
  }

  toScreen([wx, wy]) {
    return [this.x(wx), this.y(wy)];
  }

  toWorld([sx, sy]) {
    return [(sx - this.ox) / this.scale, (this.oy - sy) / this.scale];
  }

  /** Length of `px` screen pixels in world units. */
  px(px) {
    return px / this.scale;
  }
}
