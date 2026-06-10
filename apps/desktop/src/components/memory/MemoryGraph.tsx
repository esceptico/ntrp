import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import {
  forceCenter,
  forceCollide,
  forceLink,
  forceManyBody,
  forceSimulation,
  forceX,
  forceY,
  type Simulation,
} from "d3-force";
import type { MemoryEdge, MemoryEdgeRole, MemoryItem } from "../../api/memoryItems";
import { MOTION } from "../../lib/tokens/motion";
import { nodeColor, provenanceLabel, truncate } from "./lens";

export interface GraphPayload {
  nodes: MemoryItem[];
  edges: MemoryEdge[];
}

// Every node is a claim → every node is a circle (locked model §5: no squares,
// differentiate by color/size only). Size grows mildly with corroboration so a
// well-supported claim reads larger; it never encodes a different shape.
const BASE_RADIUS = 9;
function nodeRadius(item: MemoryItem): number {
  return BASE_RADIUS + Math.min(5, item.corroboration);
}

// Dashed for the "tension" roles so they read as caveats, not structure.
const ROLE_DASH: Record<MemoryEdgeRole, string | undefined> = {
  evidence: undefined,
  supersedes: "5 4",
  contradicts: "2 4",
};

const ROLE_LABEL: Record<MemoryEdgeRole, string> = {
  evidence: "evidence",
  supersedes: "supersedes",
  contradicts: "contradicts",
};

interface SimNode {
  id: string;
  item: MemoryItem;
  x: number;
  y: number;
  vx?: number;
  vy?: number;
  fx?: number | null;
  fy?: number | null;
}

interface SimLink {
  source: SimNode;
  target: SimNode;
  role: MemoryEdgeRole;
}

interface Transform {
  x: number;
  y: number;
  k: number;
}

export interface CenterRequest {
  id: string;
  nonce: number;
}

function nodeLabel(item: MemoryItem): string {
  return item.content;
}

function roleStroke(role: MemoryEdgeRole): string {
  return role === "contradicts" || role === "supersedes"
    ? "var(--color-bad)"
    : "var(--color-line-strong)";
}

export function MemoryGraph({
  graph,
  rootId,
  selectedId,
  onSelect,
  centerRequest,
}: {
  graph: GraphPayload;
  rootId: string | null;
  selectedId: string | null;
  onSelect: (item: MemoryItem) => void;
  centerRequest?: CenterRequest | null;
}) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const simRef = useRef<Simulation<SimNode, SimLink> | null>(null);
  const nodesRef = useRef<Map<string, SimNode>>(new Map());
  const linksRef = useRef<SimLink[]>([]);
  const [, bump] = useState(0);
  const tick = useCallback(() => bump((v) => (v + 1) % 1_000_000), []);

  const [size, setSize] = useState({ w: 800, h: 600 });
  const [transform, setTransform] = useState<Transform>({ x: 0, y: 0, k: 1 });
  const [hoverId, setHoverId] = useState<string | null>(null);
  const [easePan, setEasePan] = useState(false);

  useLayoutEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const ro = new ResizeObserver(([entry]) => {
      const { width, height } = entry.contentRect;
      if (width > 0 && height > 0) setSize({ w: width, h: height });
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // Build / rebuild the simulation when the graph payload changes.
  useEffect(() => {
    const prev = nodesRef.current;
    const next = new Map<string, SimNode>();
    for (const item of graph.nodes) {
      const old = prev.get(item.id);
      next.set(item.id, {
        id: item.id,
        item,
        x: old?.x ?? size.w / 2 + (Math.random() - 0.5) * 60,
        y: old?.y ?? size.h / 2 + (Math.random() - 0.5) * 60,
        vx: old?.vx,
        vy: old?.vy,
      });
    }
    const links: SimLink[] = [];
    for (const edge of graph.edges) {
      const source = next.get(edge.child_id);
      const target = next.get(edge.parent_id);
      if (source && target) links.push({ source, target, role: edge.role });
    }
    nodesRef.current = next;
    linksRef.current = links;

    simRef.current?.stop();
    const nodes = [...next.values()];
    const sim = forceSimulation<SimNode>(nodes)
      .force("charge", forceManyBody().strength(-340).distanceMax(420))
      .force("link", forceLink<SimNode, SimLink>(links).id((d) => d.id).distance(96).strength(0.55))
      .force("center", forceCenter(size.w / 2, size.h / 2).strength(0.06))
      .force("collide", forceCollide<SimNode>((d) => nodeRadius(d.item) + 14))
      .force("x", forceX(size.w / 2).strength(0.03))
      .force("y", forceY(size.h / 2).strength(0.03))
      .alpha(0.9)
      .alphaDecay(0.035);
    sim.on("tick", tick);
    simRef.current = sim;
    tick();
    return () => {
      sim.stop();
    };
    // size intentionally excluded: resizing shouldn't reheat the whole layout.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [graph, tick]);

  const adjacency = useMemo(() => {
    const map = new Map<string, Set<string>>();
    const link = (a: string, b: string) => {
      let set = map.get(a);
      if (!set) map.set(a, (set = new Set()));
      set.add(b);
    };
    for (const edge of graph.edges) {
      link(edge.child_id, edge.parent_id);
      link(edge.parent_id, edge.child_id);
    }
    return map;
  }, [graph]);

  const focusId = hoverId ?? selectedId;
  const isLit = useCallback(
    (id: string) => {
      if (!focusId) return true;
      if (id === focusId) return true;
      return adjacency.get(focusId)?.has(id) ?? false;
    },
    [focusId, adjacency],
  );

  // Hubs: the highest-degree nodes carry a standing label even with no focus, so
  // the whole-graph view is legible without every node shouting. Degree threshold
  // scales with graph size; cap the set so labels never pile up at scale.
  const hubIds = useMemo(() => {
    const degree = (id: string) => adjacency.get(id)?.size ?? 0;
    const ranked = [...nodesRef.current.keys()]
      .map((id) => ({ id, d: degree(id) }))
      .filter((n) => n.d >= 2)
      .sort((a, b) => b.d - a.d);
    return new Set(ranked.slice(0, 8).map((n) => n.id));
    // graph identity drives adjacency; recompute when it changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [adjacency, graph]);

  // ── Pan & zoom ───────────────────────────────────────────────────────
  const panState = useRef<{ x: number; y: number; tx: number; ty: number } | null>(null);
  const dragState = useRef<{ node: SimNode; startX: number; startY: number; moved: boolean } | null>(null);

  const toGraph = useCallback(
    (clientX: number, clientY: number) => {
      const rect = wrapRef.current?.getBoundingClientRect();
      const sx = clientX - (rect?.left ?? 0);
      const sy = clientY - (rect?.top ?? 0);
      return { x: (sx - transform.x) / transform.k, y: (sy - transform.y) / transform.k };
    },
    [transform],
  );

  const onWheel = useCallback((e: React.WheelEvent) => {
    const rect = wrapRef.current?.getBoundingClientRect();
    const sx = e.clientX - (rect?.left ?? 0);
    const sy = e.clientY - (rect?.top ?? 0);
    setTransform((t) => {
      const k = Math.min(3, Math.max(0.25, t.k * (e.deltaY < 0 ? 1.12 : 1 / 1.12)));
      const ratio = k / t.k;
      return { k, x: sx - (sx - t.x) * ratio, y: sy - (sy - t.y) * ratio };
    });
  }, []);

  const onPointerDownBg = useCallback(
    (e: React.PointerEvent) => {
      if (e.button !== 0) return;
      panState.current = { x: e.clientX, y: e.clientY, tx: transform.x, ty: transform.y };
    },
    [transform],
  );

  const onPointerMove = useCallback(
    (e: React.PointerEvent) => {
      const drag = dragState.current;
      if (drag) {
        if (Math.abs(e.clientX - drag.startX) > 3 || Math.abs(e.clientY - drag.startY) > 3) drag.moved = true;
        const p = toGraph(e.clientX, e.clientY);
        drag.node.fx = p.x;
        drag.node.fy = p.y;
        simRef.current?.alphaTarget(0.18).restart();
        return;
      }
      if (panState.current) {
        const { x: startX, y: startY, tx, ty } = panState.current;
        const dx = e.clientX - startX;
        const dy = e.clientY - startY;
        setTransform((t) => ({ ...t, x: tx + dx, y: ty + dy }));
      }
    },
    [toGraph],
  );

  const endInteraction = useCallback(() => {
    if (dragState.current) {
      dragState.current.node.fx = null;
      dragState.current.node.fy = null;
      simRef.current?.alphaTarget(0);
      dragState.current = null;
    }
    panState.current = null;
  }, []);

  const onPointerDownNode = useCallback((e: React.PointerEvent, node: SimNode) => {
    e.stopPropagation();
    dragState.current = { node, startX: e.clientX, startY: e.clientY, moved: false };
    node.fx = node.x;
    node.fy = node.y;
  }, []);

  const fit = useCallback(() => {
    const nodes = [...nodesRef.current.values()];
    if (nodes.length === 0) return;
    const xs = nodes.map((n) => n.x);
    const ys = nodes.map((n) => n.y);
    const minX = Math.min(...xs),
      maxX = Math.max(...xs);
    const minY = Math.min(...ys),
      maxY = Math.max(...ys);
    const pad = 60;
    const w = maxX - minX + pad * 2;
    const h = maxY - minY + pad * 2;
    const k = Math.min(2, Math.max(0.3, Math.min(size.w / w, size.h / h)));
    setTransform({
      k,
      x: size.w / 2 - ((minX + maxX) / 2) * k,
      y: size.h / 2 - ((minY + maxY) / 2) * k,
    });
  }, [size]);

  // Recenter on the requested node (peel navigation), easing the slide so the
  // hop reads as spatial. Direct pans keep `easePan` false and stay instant.
  useEffect(() => {
    if (!centerRequest) return;
    const node = nodesRef.current.get(centerRequest.id);
    if (!node) return;
    setEasePan(true);
    setTransform((t) => ({ ...t, x: size.w / 2 - node.x * t.k, y: size.h / 2 - node.y * t.k }));
    // Reset just after the CSS transition (--duration-route) settles.
    const timer = setTimeout(() => setEasePan(false), MOTION.route * 1000 + 20);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [centerRequest?.nonce]);

  const nodes = [...nodesRef.current.values()];
  const links = linksRef.current;

  // Which nodes show a label this frame, collision-avoided in screen space.
  // Priority: the focus node + its lit neighbours (on hover/selection), then
  // hubs (standing labels). A label is dropped if its screen box overlaps one
  // already placed, so labels never pile up at whole-graph scale.
  const labelledIds = (() => {
    const candidates: { id: string; pri: number; n: SimNode }[] = [];
    for (const n of nodes) {
      const lit = isLit(n.id);
      if (focusId != null && lit) candidates.push({ id: n.id, pri: n.id === focusId ? 0 : 1, n });
      else if (focusId == null && hubIds.has(n.id)) candidates.push({ id: n.id, pri: 2, n });
    }
    candidates.sort((a, b) => a.pri - b.pri);
    const placed: { x: number; y: number; w: number; h: number }[] = [];
    const accepted = new Set<string>();
    const charW = 6.2; // ~10px label glyph advance in screen px
    for (const c of candidates) {
      const r = nodeRadius(c.n.item);
      const text = truncate(nodeLabel(c.n.item), 28);
      const sx = transform.x + (c.n.x + r + 5) * transform.k;
      const sy = transform.y + c.n.y * transform.k;
      const box = { x: sx, y: sy - 7, w: text.length * charW + 6, h: 14 };
      const hit = placed.some(
        (p) => box.x < p.x + p.w && box.x + box.w > p.x && box.y < p.y + p.h && box.y + box.h > p.y,
      );
      if (hit) continue;
      placed.push(box);
      accepted.add(c.id);
    }
    return accepted;
  })();

  return (
    <div ref={wrapRef} className="relative h-full w-full overflow-hidden">
      <svg
        width={size.w}
        height={size.h}
        className="block touch-none select-none"
        style={{ cursor: panState.current ? "grabbing" : "grab" }}
        onWheel={onWheel}
        onPointerDown={onPointerDownBg}
        onPointerMove={onPointerMove}
        onPointerUp={endInteraction}
        onPointerLeave={endInteraction}
      >
        <g
          transform={`translate(${transform.x},${transform.y}) scale(${transform.k})`}
          style={easePan ? { transition: "transform var(--duration-route) var(--ease-emphasized)" } : undefined}
        >
          {links.map((l, i) => {
            const lit = isLit(l.source.id) && isLit(l.target.id);
            return (
              <line
                key={i}
                className="transition-opacity duration-row ease-out"
                x1={l.source.x}
                y1={l.source.y}
                x2={l.target.x}
                y2={l.target.y}
                stroke={roleStroke(l.role)}
                strokeWidth={l.role === "evidence" ? 1.4 : 1.1}
                strokeDasharray={ROLE_DASH[l.role]}
                opacity={lit ? (focusId ? 0.85 : 0.4) : 0.06}
              />
            );
          })}
          {focusId &&
            links
              .filter((l) => l.source.id === focusId || l.target.id === focusId)
              .map((l, i) => {
                const mx = (l.source.x + l.target.x) / 2;
                const my = (l.source.y + l.target.y) / 2;
                return (
                  <text
                    key={`rl-${i}`}
                    x={mx}
                    y={my}
                    dy={-3}
                    textAnchor="middle"
                    className="pointer-events-none"
                    fontSize={8}
                    fill="var(--color-faint)"
                  >
                    {ROLE_LABEL[l.role]}
                  </text>
                );
              })}
          {nodes.map((n) => {
            const r = nodeRadius(n.item);
            const lit = isLit(n.id);
            const isRoot = n.id === rootId;
            const isSelected = n.id === selectedId;
            const color = nodeColor(n.item);
            const dim = n.item.status !== "active";
            // De-clutter: label the focused/hovered node + lit neighbours, plus
            // standing hub labels — all collision-avoided (locked model §4).
            const labelled = labelledIds.has(n.id);
            return (
              <g
                key={n.id}
                className="transition-opacity duration-row ease-out"
                transform={`translate(${n.x},${n.y})`}
                opacity={lit ? 1 : 0.18}
                style={{ cursor: "pointer" }}
                onPointerDown={(e) => onPointerDownNode(e, n)}
                onPointerUp={(e) => {
                  e.stopPropagation();
                  if (!dragState.current?.moved) onSelect(n.item);
                  endInteraction();
                }}
                onPointerEnter={() => setHoverId(n.id)}
                onPointerLeave={() => setHoverId((h) => (h === n.id ? null : h))}
              >
                {(isSelected || isRoot) && (
                  <circle r={r + 5} fill="none" stroke={color} strokeWidth={1.5} opacity={0.5} />
                )}
                {/* All nodes are claims → all circles. Color = provenance, size =
                    corroboration; shape never varies (locked model §5). */}
                <circle
                  r={r}
                  fill={dim ? "var(--color-surface)" : color}
                  stroke={color}
                  strokeWidth={dim ? 1.5 : 0}
                  strokeDasharray={n.item.status === "superseded" ? "3 2" : undefined}
                />
                {labelled && (
                  <text
                    x={r + 5}
                    y={3}
                    fontSize={10}
                    className="pointer-events-none"
                    fill="var(--color-ink-soft)"
                    paintOrder="stroke"
                    stroke="var(--color-surface)"
                    strokeWidth={3}
                  >
                    {truncate(nodeLabel(n.item), 28)}
                  </text>
                )}
              </g>
            );
          })}
        </g>
      </svg>

      <div className="pointer-events-none absolute inset-x-0 bottom-0 flex items-end justify-between gap-3 p-3">
        <Legend />
        <button
          type="button"
          onClick={fit}
          className="pointer-events-auto rounded-md border border-line-soft bg-surface/80 px-2.5 py-1 text-xs text-ink-soft backdrop-blur-sm transition-[background-color,color,scale] duration-check ease-out active:scale-[0.97] hover:bg-surface-soft hover:text-ink"
        >
          Fit
        </button>
      </div>
    </div>
  );
}

const LEGEND_ROLES: MemoryEdgeRole[] = ["evidence", "supersedes", "contradicts"];
const LEGEND_PROVENANCE: MemoryItem["provenance"][] = [
  "user_authored",
  "recorded",
  "inferred",
  "external",
];

function Legend() {
  return (
    <div className="pointer-events-none flex flex-wrap items-center gap-x-3 gap-y-1 rounded-lg border border-line-soft bg-surface/80 px-3 py-2 backdrop-blur-sm">
      {LEGEND_PROVENANCE.map((p) => (
        <span key={p} className="flex items-center gap-1.5 text-2xs text-muted">
          <span
            className="size-2 rounded-full"
            style={{ backgroundColor: nodeColor({ provenance: p } as MemoryItem) }}
          />
          {provenanceLabel(p)}
        </span>
      ))}
      {LEGEND_ROLES.map((role) => (
        <span key={role} className="flex items-center gap-1.5 text-2xs text-muted">
          <span
            className="h-px w-4"
            style={
              ROLE_DASH[role]
                ? {
                    backgroundImage: `repeating-linear-gradient(to right, ${roleStroke(role)} 0 3px, transparent 3px 6px)`,
                  }
                : { backgroundColor: roleStroke(role) }
            }
          />
          {ROLE_LABEL[role]}
        </span>
      ))}
    </div>
  );
}
