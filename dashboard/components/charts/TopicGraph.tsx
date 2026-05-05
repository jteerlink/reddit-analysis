"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type { PointerEvent, WheelEvent } from "react";
import {
  forceCenter,
  forceCollide,
  forceLink,
  forceManyBody,
  forceSimulation,
  forceX,
  forceY,
  type Simulation,
  type SimulationLinkDatum,
  type SimulationNodeDatum,
} from "d3-force";
import { CHART_COLORS } from "@/components/charts/chartTooltip";
import { cn } from "@/lib/utils";
import type { TopicGraphEdge, TopicGraphNode } from "@/lib/types";

type GraphNode = TopicGraphNode & SimulationNodeDatum & { radius: number };
type GraphLink = Omit<TopicGraphEdge, "source" | "target"> &
  SimulationLinkDatum<GraphNode> & {
    source: number | GraphNode;
    target: number | GraphNode;
  };

interface Props {
  nodes?: TopicGraphNode[];
  edges?: TopicGraphEdge[];
  selectedTopicId: number | null;
  onSelectTopic: (topicId: number) => void;
  compact?: boolean;
}

const WIDTH = 920;
const HEIGHT = 520;
const EMPTY_NODES: TopicGraphNode[] = [];
const EMPTY_EDGES: TopicGraphEdge[] = [];

function topicName(keywords: string) {
  return keywords.replace(/[[\]"]/g, "").split(",")[0].trim() || keywords.slice(0, 22);
}

function nodeColor(node: TopicGraphNode, selectedTopicId: number | null) {
  if (node.topic_id === selectedTopicId) return CHART_COLORS.yellow;
  if (node.emerging) return CHART_COLORS.violet;
  if ((node.coherence_score ?? 0) >= 0.5) return CHART_COLORS.green;
  if ((node.coherence_score ?? 0) < 0) return CHART_COLORS.red;
  return CHART_COLORS.copper;
}

function linkIds(link: GraphLink) {
  const source = typeof link.source === "object" ? link.source.topic_id : Number(link.source);
  const target = typeof link.target === "object" ? link.target.topic_id : Number(link.target);
  return [source, target] as const;
}

function clamp(value: number, min: number, max: number) {
  return Math.max(min, Math.min(max, value));
}

export function TopicGraph({ nodes, edges, selectedTopicId, onSelectTopic, compact = false }: Props) {
  const safeNodes = useMemo(() => (Array.isArray(nodes) ? nodes : EMPTY_NODES), [nodes]);
  const safeEdges = useMemo(() => (Array.isArray(edges) ? edges : EMPTY_EDGES), [edges]);
  const svgRef = useRef<SVGSVGElement | null>(null);
  const simulationRef = useRef<Simulation<GraphNode, GraphLink> | null>(null);
  const dragIdRef = useRef<number | null>(null);
  const panRef = useRef<{ x: number; y: number; tx: number; ty: number } | null>(null);
  const [graphNodes, setGraphNodes] = useState<GraphNode[]>([]);
  const [graphLinks, setGraphLinks] = useState<GraphLink[]>([]);
  const [hoveredTopicId, setHoveredTopicId] = useState<number | null>(null);
  const [view, setView] = useState({ x: 0, y: 0, k: 1 });

  const maxDocs = useMemo(() => Math.max(...safeNodes.map((node) => node.doc_count), 1), [safeNodes]);
  const selectedNeighbors = useMemo(() => {
    if (selectedTopicId == null) return new Set<number>();
    const neighbors = new Set<number>();
    for (const edge of graphLinks) {
      const [source, target] = linkIds(edge);
      if (source === selectedTopicId) neighbors.add(target);
      if (target === selectedTopicId) neighbors.add(source);
    }
    return neighbors;
  }, [graphLinks, selectedTopicId]);

  const hoveredNode = graphNodes.find((node) => node.topic_id === hoveredTopicId) ?? null;

  useEffect(() => {
    const graph = safeNodes.map((node, index) => {
      const angle = (index / Math.max(safeNodes.length, 1)) * Math.PI * 2;
      return {
        ...node,
        x: WIDTH / 2 + Math.cos(angle) * 180,
        y: HEIGHT / 2 + Math.sin(angle) * 130,
        radius: 7 + Math.sqrt(node.doc_count / maxDocs) * (compact ? 12 : 22),
      };
    });
    const links = safeEdges.map((edge) => ({ ...edge }));
    setGraphNodes(graph);
    setGraphLinks(links);

    simulationRef.current?.stop();
    const simulation = forceSimulation<GraphNode, GraphLink>(graph)
      .force("link", forceLink<GraphNode, GraphLink>(links).id((node) => node.topic_id).distance((link) => 180 - link.similarity * 96).strength((link) => 0.18 + link.similarity * 0.32))
      .force("charge", forceManyBody().strength(compact ? -180 : -260))
      .force("collide", forceCollide<GraphNode>().radius((node) => node.radius + 10).iterations(2))
      .force("x", forceX(WIDTH / 2).strength(0.035))
      .force("y", forceY(HEIGHT / 2).strength(0.045))
      .force("center", forceCenter(WIDTH / 2, HEIGHT / 2))
      .alpha(0.9)
      .alphaDecay(0.045);

    simulation.on("tick", () => {
      setGraphNodes([...graph]);
      setGraphLinks([...links]);
    });
    simulationRef.current = simulation;

    return () => {
      simulation.stop();
    };
  }, [safeNodes, safeEdges, maxDocs, compact]);

  function svgPoint(event: PointerEvent<SVGSVGElement> | PointerEvent<SVGGElement> | WheelEvent<SVGSVGElement>) {
    const rect = svgRef.current?.getBoundingClientRect();
    if (!rect) return { x: 0, y: 0 };
    return {
      x: ((event.clientX - rect.left) / rect.width) * WIDTH,
      y: ((event.clientY - rect.top) / rect.height) * HEIGHT,
    };
  }

  function graphPoint(event: PointerEvent<SVGSVGElement> | PointerEvent<SVGGElement>) {
    const point = svgPoint(event);
    return {
      x: (point.x - view.x) / view.k,
      y: (point.y - view.y) / view.k,
    };
  }

  function handleWheel(event: WheelEvent<SVGSVGElement>) {
    event.preventDefault();
    const point = svgPoint(event);
    const nextK = clamp(view.k * (event.deltaY > 0 ? 0.9 : 1.1), 0.65, 2.6);
    const ratio = nextK / view.k;
    setView({
      k: nextK,
      x: point.x - (point.x - view.x) * ratio,
      y: point.y - (point.y - view.y) * ratio,
    });
  }

  function beginPan(event: PointerEvent<SVGSVGElement>) {
    panRef.current = { x: event.clientX, y: event.clientY, tx: view.x, ty: view.y };
    event.currentTarget.setPointerCapture(event.pointerId);
  }

  function beginDrag(topicId: number, event: PointerEvent<SVGGElement>) {
    event.stopPropagation();
    dragIdRef.current = topicId;
    const point = graphPoint(event);
    const node = graphNodes.find((item) => item.topic_id === topicId);
    if (node) {
      node.fx = point.x;
      node.fy = point.y;
    }
    simulationRef.current?.alphaTarget(0.25).restart();
    svgRef.current?.setPointerCapture(event.pointerId);
  }

  function handlePointerMove(event: PointerEvent<SVGSVGElement>) {
    if (dragIdRef.current != null) {
      const point = graphPoint(event);
      const node = graphNodes.find((item) => item.topic_id === dragIdRef.current);
      if (node) {
        node.fx = point.x;
        node.fy = point.y;
        setGraphNodes([...graphNodes]);
      }
      return;
    }
    if (panRef.current) {
      const rect = svgRef.current?.getBoundingClientRect();
      if (!rect) return;
      setView({
        ...view,
        x: panRef.current.tx + ((event.clientX - panRef.current.x) / rect.width) * WIDTH,
        y: panRef.current.ty + ((event.clientY - panRef.current.y) / rect.height) * HEIGHT,
      });
    }
  }

  function endPointer() {
    if (dragIdRef.current != null) {
      const node = graphNodes.find((item) => item.topic_id === dragIdRef.current);
      if (node) {
        node.fx = undefined;
        node.fy = undefined;
      }
    }
    dragIdRef.current = null;
    panRef.current = null;
    simulationRef.current?.alphaTarget(0);
  }

  return (
    <div className="relative">
      <svg
        ref={svgRef}
        className={cn(
          "h-full w-full touch-none select-none rounded-lg border border-white/8 bg-black/18 signal-grid",
          compact ? "min-h-[260px]" : "min-h-[520px]"
        )}
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        role="img"
        aria-label="Interactive topic similarity graph"
        onWheel={handleWheel}
        onPointerDown={beginPan}
        onPointerMove={handlePointerMove}
        onPointerUp={endPointer}
        onPointerCancel={endPointer}
      >
        <defs>
          <filter id="topicGraphGlow">
            <feGaussianBlur stdDeviation="3" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
          <radialGradient id="topicGraphHalo">
            <stop offset="0%" stopColor="#31d38f" stopOpacity="0.18" />
            <stop offset="100%" stopColor="#31d38f" stopOpacity="0" />
          </radialGradient>
        </defs>
        <rect width={WIDTH} height={HEIGHT} fill="url(#topicGraphHalo)" opacity="0.85" />
        <g transform={`translate(${view.x} ${view.y}) scale(${view.k})`}>
          {graphLinks.map((edge) => {
            const source = edge.source as GraphNode;
            const target = edge.target as GraphNode;
            const [sourceId, targetId] = linkIds(edge);
            const active = selectedTopicId == null || sourceId === selectedTopicId || targetId === selectedTopicId || sourceId === hoveredTopicId || targetId === hoveredTopicId;
            return (
              <line
                key={`${sourceId}-${targetId}`}
                x1={source.x}
                y1={source.y}
                x2={target.x}
                y2={target.y}
                stroke={active ? CHART_COLORS.green : "rgba(255,255,255,0.16)"}
                strokeOpacity={active ? 0.56 : 0.18}
                strokeWidth={1 + edge.similarity * 5}
              />
            );
          })}
          {graphNodes.map((node) => {
            const selected = node.topic_id === selectedTopicId;
            const neighbor = selectedNeighbors.has(node.topic_id);
            const muted = selectedTopicId != null && !selected && !neighbor;
            const color = nodeColor(node, selectedTopicId);
            return (
              <g
                key={node.topic_id}
                role="button"
                tabIndex={0}
                aria-label={`Topic ${node.topic_id}: ${topicName(node.keywords)}`}
                className="cursor-grab outline-none"
                transform={`translate(${node.x ?? WIDTH / 2} ${node.y ?? HEIGHT / 2})`}
                onPointerDown={(event) => beginDrag(node.topic_id, event)}
                onClick={() => onSelectTopic(node.topic_id)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") onSelectTopic(node.topic_id);
                }}
                onMouseEnter={() => setHoveredTopicId(node.topic_id)}
                onMouseLeave={() => setHoveredTopicId(null)}
              >
                {(selected || neighbor) && <circle r={node.radius + 13} fill={color} opacity={selected ? 0.17 : 0.08} />}
                <circle r={node.radius} fill={color} opacity={muted ? 0.32 : 0.94} filter={selected ? "url(#topicGraphGlow)" : undefined} />
                <circle r={node.radius + 3} fill="none" stroke={color} strokeOpacity={selected ? 0.85 : 0.24} strokeWidth={selected ? 2 : 1} />
                {(!compact || selected || hoveredTopicId === node.topic_id) && (
                  <text
                    y={node.radius + 17}
                    textAnchor="middle"
                    className="pointer-events-none fill-foreground font-mono text-[11px]"
                    opacity={muted ? 0.42 : 0.9}
                  >
                    {topicName(node.keywords)}
                  </text>
                )}
              </g>
            );
          })}
        </g>
      </svg>

      {!safeNodes.length && (
        <div className="pointer-events-none absolute inset-0 grid place-items-center rounded-lg text-xs text-muted-foreground">
          Waiting for graph signals
        </div>
      )}

      <div className="pointer-events-none absolute left-4 top-4 rounded-md border border-signal-copper/25 bg-[#081816]/88 px-3 py-2 font-mono text-[10px] text-muted-foreground shadow-2xl">
        wheel zoom / drag pan / drag nodes
      </div>

      {hoveredNode && (
        <div className="pointer-events-none absolute bottom-4 left-4 z-20 max-w-72 rounded-lg border border-signal-copper/35 bg-[#081816]/95 px-3 py-2 text-[11px] shadow-2xl">
          <p className="font-mono text-signal-copper">topic #{hoveredNode.topic_id}</p>
          <p className="mt-1 text-sm font-medium text-foreground">{topicName(hoveredNode.keywords)}</p>
          <p className="mt-1 font-mono text-muted-foreground">
            {hoveredNode.doc_count.toLocaleString()} docs / coherence {(hoveredNode.coherence_score ?? 0).toFixed(2)}
          </p>
          {!!hoveredNode.keyword_terms.length && (
            <p className="mt-1 truncate font-mono text-signal-green">{hoveredNode.keyword_terms.slice(0, 6).join(", ")}</p>
          )}
        </div>
      )}
    </div>
  );
}
