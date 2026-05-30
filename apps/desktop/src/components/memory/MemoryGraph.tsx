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
import type {
  MemoryGraphEdge,
  MemoryItemKind,
  MemoryItemSummary,
  MemoryParentRole,
} from "../../api/memoryItems";

export interface GraphPayload {
  nodes: MemoryItemSummary[];
  edges: MemoryGraphEdge[];
}

// Curated, harmonized kind palette (Flexoki mid-tones; read well on warm light + dark).
export const KIND_COLOR: Record<MemoryItemKind, string> = {
  episode: "#4385be",
  observation: "#3aa99f",
  claim: "#da702c",
  skill: "#879a39",
  proposal: "#8b7ec8",
  artifact_ref: "#ce5d97",
  entity: "#d0a215",
  directory: "#a892d7",
};

const KIND_RADIUS: Record<MemoryItemKind, number> = {
  episode: 7,
  observation: 8,
  claim: 10,
  skill: 11,
  proposal: 9,
  artifact_ref: 7,
  entity: 10,
  directory: 13,
};

const ROLE_DASH: Record<MemoryParentRole, string | undefined> = {
  evidence: undefined,
  supersedes: undefined,
  contradicts: "5 4",
  step: undefined,
  similar_to: "1 5",
  member_of: undefined,
};

interface SimNode {
  id: string;
  item: MemoryItemSummary;
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
  role: MemoryParentRole;
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
  onSelect: (item: MemoryItemSummary) => void;
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
      .force("collide", forceCollide<SimNode>((d) => KIND_RADIUS[d.item.kind] + 14))
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

  const onPointerDownBg = useCallback((e: React.PointerEvent) => {
    if (e.button !== 0) return;
    panState.current = { x: e.clientX, y: e.clientY, tx: transform.x, ty: transform.y };
  }, [transform]);

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
    const minX = Math.min(...xs), maxX = Math.max(...xs);
    const minY = Math.min(...ys), maxY = Math.max(...ys);
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

  // Recenter on the requested node (drawer navigation), easing the slide so the
  // hop reads as spatial. Direct pans keep `easePan` false and stay instant.
  useEffect(() => {
    if (!centerRequest) return;
    const node = nodesRef.current.get(centerRequest.id);
    if (!node) return;
    setEasePan(true);
    setTransform((t) => ({ ...t, x: size.w / 2 - node.x * t.k, y: size.h / 2 - node.y * t.k }));
    const timer = setTimeout(() => setEasePan(false), 380);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [centerRequest?.nonce]);

  const nodes = [...nodesRef.current.values()];
  const links = linksRef.current;
  const labelsVisible = transform.k > 0.7;

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
          style={easePan ? { transition: "transform 360ms var(--ease-emphasized)" } : undefined}
        >
          {links.map((l, i) => {
            const lit = isLit(l.source.id) && isLit(l.target.id);
            const stroke = l.role === "contradicts" || l.role === "supersedes" ? "var(--color-bad)" : "var(--color-line-strong)";
            return (
              <line
                key={i}
                x1={l.source.x}
                y1={l.source.y}
                x2={l.target.x}
                y2={l.target.y}
                stroke={stroke}
                strokeWidth={l.role === "evidence" ? 1.4 : 1.1}
                strokeDasharray={ROLE_DASH[l.role]}
                opacity={lit ? (focusId ? 0.85 : 0.4) : 0.06}
              />
            );
          })}
          {focusId &&
            links
              .filter((l) => (l.source.id === focusId || l.target.id === focusId))
              .map((l, i) => {
                const mx = (l.source.x + l.target.x) / 2;
                const my = (l.source.y + l.target.y) / 2;
                return (
                  <text key={`rl-${i}`} x={mx} y={my} dy={-3} textAnchor="middle" className="pointer-events-none" fontSize={8} fill="var(--color-faint)">
                    {l.role}
                  </text>
                );
              })}
          {nodes.map((n) => {
            const r = KIND_RADIUS[n.item.kind];
            const lit = isLit(n.id);
            const isRoot = n.id === rootId;
            const isSelected = n.id === selectedId;
            const color = KIND_COLOR[n.item.kind];
            const dim = n.item.status !== "active";
            return (
              <g
                key={n.id}
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
                <circle
                  r={r}
                  fill={dim ? "var(--color-surface)" : color}
                  stroke={color}
                  strokeWidth={dim ? 1.5 : 0}
                  strokeDasharray={n.item.status === "superseded" ? "3 2" : undefined}
                />
                {labelsVisible && lit && (
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
                    {truncate(n.item.title ?? n.item.content, 28)}
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
          className="pointer-events-auto rounded-md border border-line-soft bg-surface/80 px-2.5 py-1 text-xs text-ink-soft backdrop-blur-sm transition-colors hover:bg-surface-soft hover:text-ink"
        >
          Fit
        </button>
      </div>
    </div>
  );
}

function Legend() {
  const kinds = Object.keys(KIND_COLOR) as MemoryItemKind[];
  return (
    <div className="pointer-events-none flex flex-wrap gap-x-3 gap-y-1 rounded-lg border border-line-soft bg-surface/80 px-3 py-2 backdrop-blur-sm">
      {kinds.map((kind) => (
        <span key={kind} className="flex items-center gap-1.5 text-2xs text-muted">
          <span className="size-2 rounded-full" style={{ backgroundColor: KIND_COLOR[kind] }} />
          {kind}
        </span>
      ))}
    </div>
  );
}

function truncate(text: string, max: number): string {
  const t = text.replace(/\s+/g, " ").trim();
  return t.length > max ? `${t.slice(0, max)}…` : t;
}
