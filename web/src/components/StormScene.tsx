// Three.js view of the ground and the 2D model's water: one or two scenes (existing | proposed) sharing a camera.
import { useEffect, useRef } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { Json } from "../lib/api";

export interface Grid { rows: number; cols: number; cell: number; ox: number; oy: number; z: Float32Array; zmin: number; zmax: number }
export interface Side { terrain: Grid; components?: Json; water?: { rows: number; cols: number; cell: number; ox: number; oy: number } }

const css = (name: string) => {
  const v = getComputedStyle(document.documentElement).getPropertyValue(`--color-${name}`).trim().split(/\s+/).map(Number);
  return new THREE.Color(v[0] / 255, v[1] / 255, v[2] / 255);
};

function inside(ring: number[][], x: number, y: number) {
  let r = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++)
    if ((ring[i][1] > y) !== (ring[j][1] > y) && x < ((ring[j][0] - ring[i][0]) * (y - ring[i][1])) / (ring[j][1] - ring[i][1]) + ring[i][0]) r = !r;
  return r;
}

function footprints(fc?: Json): number[][][] {
  if (!fc) return [];
  const out: number[][][] = [];
  for (const f of fc.features) {
    const g = f.geometry;
    if (g.type === "Polygon") out.push(g.coordinates[0]);
    else if (g.type === "LineString") {
      const w = (f.properties.top_width_m ?? 3) / 2;
      for (let i = 0; i < g.coordinates.length - 1; i++) {
        const [a, b] = [g.coordinates[i], g.coordinates[i + 1]];
        const d = Math.hypot(b[0] - a[0], b[1] - a[1]) || 1, nx = (-(b[1] - a[1]) / d) * w, ny = ((b[0] - a[0]) / d) * w;
        out.push([[a[0] + nx, a[1] + ny], [b[0] + nx, b[1] + ny], [b[0] - nx, b[1] - ny], [a[0] - nx, a[1] - ny]]);
      }
    } else if (g.type === "Point") {
      const r = (f.properties.well_diameter_m ?? 1.2) / 2;
      out.push(Array.from({ length: 16 }, (_, k) => [g.coordinates[0] + r * Math.cos((k * Math.PI) / 8), g.coordinates[1] + r * Math.sin((k * Math.PI) / 8)]));
    }
  }
  return out;
}

class SideScene {
  scene = new THREE.Scene();
  ground: (x: number, y: number) => number;
  water?: THREE.Mesh;
  waterGround?: Float32Array;
  constructor(side: Side, frame: { x0: number; y0: number; zref: number; ex: number }) {
    const t = side.terrain;
    this.scene.background = css("background");
    this.scene.add(new THREE.HemisphereLight(css("primary-foreground"), css("accent-foreground"), 0.9));
    const sun = new THREE.DirectionalLight(0xfff4e6, 1.3);
    sun.position.set(-60, 120, 80);
    this.scene.add(sun);
    this.ground = (x, y) => {
      const c = Math.floor((x - t.ox) / t.cell), r = Math.floor((t.oy - y) / t.cell);
      if (r < 0 || c < 0 || r >= t.rows || c >= t.cols) return NaN;
      return t.z[r * t.cols + c];
    };
    // terrain
    const polys = footprints(side.components);
    const low = css("primary"), high = css("accent"), nbs = css("water-deep");
    const pos: number[] = [], col: number[] = [], index = new Int32Array(t.rows * t.cols).fill(-1), tris: number[] = [];
    let n = 0;
    for (let r = 0; r < t.rows; r++) for (let c = 0; c < t.cols; c++) {
      const z = t.z[r * t.cols + c];
      if (!Number.isFinite(z)) continue;
      const x = t.ox + (c + 0.5) * t.cell, y = t.oy - (r + 0.5) * t.cell;
      pos.push(x - frame.x0, (z - frame.zref) * frame.ex, -(y - frame.y0));
      const k = (z - t.zmin) / Math.max(t.zmax - t.zmin, 1e-6);
      const cc = low.clone().lerp(high, 0.1 + 0.75 * k);
      if (polys.some((p) => inside(p, x, y))) cc.lerp(nbs, 0.35);
      col.push(cc.r, cc.g, cc.b);
      index[r * t.cols + c] = n++;
    }
    for (let r = 0; r < t.rows - 1; r++) for (let c = 0; c < t.cols - 1; c++) {
      const a = index[r * t.cols + c], b = index[r * t.cols + c + 1], d = index[(r + 1) * t.cols + c], e = index[(r + 1) * t.cols + c + 1];
      if (a < 0 || b < 0 || d < 0 || e < 0) continue;
      tris.push(a, d, b, b, d, e);
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
    g.setAttribute("color", new THREE.Float32BufferAttribute(col, 3));
    g.setIndex(tris);
    g.computeVertexNormals();
    this.scene.add(new THREE.Mesh(g, new THREE.MeshLambertMaterial({ vertexColors: true })));
    // water grid
    if (side.water) {
      const w = side.water;
      const wp = new Float32Array(w.rows * w.cols * 3), wc = new Float32Array(w.rows * w.cols * 4), wt: number[] = [];
      this.waterGround = new Float32Array(w.rows * w.cols);
      for (let r = 0; r < w.rows; r++) for (let c = 0; c < w.cols; c++) {
        const k = r * w.cols + c, x = w.ox + (c + 0.5) * w.cell, y = w.oy - (r + 0.5) * w.cell;
        this.waterGround[k] = this.ground(x, y);
        wp.set([x - frame.x0, 0, -(y - frame.y0)], 3 * k);
        if (r < w.rows - 1 && c < w.cols - 1) wt.push(k, k + w.cols, k + 1, k + 1, k + w.cols, k + w.cols + 1);
      }
      const wg = new THREE.BufferGeometry();
      wg.setAttribute("position", new THREE.BufferAttribute(wp, 3));
      wg.setAttribute("color", new THREE.BufferAttribute(wc, 4));
      wg.setIndex(wt);
      this.water = new THREE.Mesh(wg, new THREE.MeshLambertMaterial({ vertexColors: true, transparent: true, depthWrite: false }));
      this.scene.add(this.water);
    }
  }

  showDepth(depth: Float32Array, frame: { zref: number; ex: number }) {
    if (!this.water || !this.waterGround) return;
    const pos = this.water.geometry.getAttribute("position") as THREE.BufferAttribute;
    const col = this.water.geometry.getAttribute("color") as THREE.BufferAttribute;
    const shallow = css("water"), deep = css("water-deep");
    for (let k = 0; k < this.waterGround.length; k++) {
      const g = this.waterGround[k], d = depth[k] || 0;
      const show = Number.isFinite(g) && d >= 0.01;
      pos.setY(k, Number.isFinite(g) ? (g + (show ? d : 0) - frame.zref) * frame.ex + (show ? 0.03 : -0.05) : 0);
      const t = Math.min(d / 0.3, 1), c = shallow.clone().lerp(deep, t);
      col.setXYZW(k, c.r, c.g, c.b, show ? 0.45 + 0.45 * t : 0);
    }
    pos.needsUpdate = true;
    col.needsUpdate = true;
    this.water.geometry.computeVertexNormals();
  }
}

export interface SceneHandle { show: (left: Float32Array | null, right: Float32Array | null) => void; setTour: (on: boolean) => void }

export function StormScene({ left, right, exaggeration, onReady }: {
  left: Side; right?: Side; exaggeration: number; onReady: (h: SceneHandle) => void;
}) {
  const host = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = host.current!;
    const t = left.terrain;
    const frame = { x0: t.ox, y0: t.oy - t.rows * t.cell, zref: t.zmin, ex: exaggeration };
    const sides = [new SideScene(left, frame), ...(right ? [new SideScene(right, frame)] : [])];
    const renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    el.appendChild(renderer.domElement);
    const w = t.cols * t.cell, h = t.rows * t.cell;
    const camera = new THREE.PerspectiveCamera(40, 1, 0.5, 5000);
    // frame the whole site from the south-west, whatever the viewport shape
    const fit = () => {
      const aspect = Math.max(camera.aspect, 0.3);
      const span = Math.max(w / aspect, h) * 0.95;
      const dist = span / (2 * Math.tan(THREE.MathUtils.degToRad(camera.fov / 2)));
      const dir = new THREE.Vector3(-0.45, 0.75, 0.85).normalize();
      camera.position.set(w / 2, 0, -h / 2).addScaledVector(dir, dist);
    };
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.target.set(w / 2, 0, -h / 2);
    controls.enableDamping = true;
    controls.maxPolarAngle = Math.PI * 0.47;
    let tour = false;
    const resize = () => {
      const { clientWidth: cw, clientHeight: ch } = el;
      renderer.setSize(cw, ch);
      camera.aspect = (sides.length > 1 ? cw / 2 : cw) / ch;
      camera.updateProjectionMatrix();
    };
    const ro = new ResizeObserver(resize);
    ro.observe(el);
    resize();
    fit();
    let raf = 0;
    const tick = () => {
      raf = requestAnimationFrame(tick);
      if (tour) {
        const p = camera.position.clone().sub(controls.target);
        p.applyAxisAngle(new THREE.Vector3(0, 1, 0), 0.0025);
        camera.position.copy(controls.target).add(p);
      }
      controls.update();
      const { clientWidth: cw, clientHeight: ch } = el;
      renderer.setScissorTest(true);
      sides.forEach((s, i) => {
        const vw = sides.length > 1 ? cw / 2 : cw;
        renderer.setViewport(i * vw, 0, vw, ch);
        renderer.setScissor(i * vw, 0, vw, ch);
        renderer.render(s.scene, camera);
      });
    };
    tick();
    onReady({
      show: (a, b) => { if (a) sides[0].showDepth(a, frame); if (b && sides[1]) sides[1].showDepth(b, frame); },
      setTour: (on) => { tour = on; },
    });
    return () => { cancelAnimationFrame(raf); ro.disconnect(); controls.dispose(); renderer.dispose(); el.removeChild(renderer.domElement); };
  }, [left, right, exaggeration]); // eslint-disable-line react-hooks/exhaustive-deps
  return <div ref={host} className="absolute inset-0" />;
}
