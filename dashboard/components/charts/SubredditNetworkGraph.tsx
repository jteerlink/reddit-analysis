"use client";

import { useEffect, useMemo, useRef, useState } from "react";
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
import { cn, parentColor, PARENT_PALETTE } from "@/lib/utils";
import type { SubredditGraphEdge, SubredditGraphNode } from "@/lib/types";

type GraphNode = SubredditGraphNode & SimulationNodeDatum & { radius: number };
type LinkEndpoint = string | GraphNode;
type GraphLink = Omit<SubredditGraphEdge, "source" | "target"> &
  SimulationLinkDatum<GraphNode> & {
    source: LinkEndpoint;
    target: LinkEndpoint;
  };

interface Props {
  nodes: SubredditGraphNode[];
  edges: SubredditGraphEdge[];
  selectedParent: string | null;
  onSelectParent: (parentId: string | null) => void;
}

const WIDTH = 920;
const HEIGHT = 520;

function endpointId(value: LinkEndpoint): string {
  return typeof value === "string" ? value : value.subreddit;
}

function linkIds(link: GraphLink) {
  return [endpointId(link.source), endpointId(link.target)] as const;
}

export function SubredditNetworkGraph({ nodes, edges, selectedParent, onSelectParent }: Props) {
  const svgRef = useRef<SVGSVGElement | null>(null);
  const simulationRef = useRef<Simulation<GraphNode, GraphLink> | null>(null);
  const [graphNodes, setGraphNodes] = useState<GraphNode[]>([]);
  const [graphLinks, setGraphLinks] = useState<GraphLink[]>([]);
  const [hovered, setHovered] = useState<SubredditGraphNode | null>(null);
  const [hoveredEdge, setHoveredEdge] = useState<GraphLink | null>(null);
  const [topicFocus, setTopicFocus] = useState<number | null>(null);

  const maxVolume = useMemo(
    () => Math.max(...nodes.map((node) => node.total_volume), 1),
    [nodes],
  );

  const presentParents = useMemo(() => {
    const seen = new Map<string, { id: string; display_name: string; count: number }>();
    for (const node of nodes) {
      const existing = seen.get(node.parent_id);
      if (existing) existing.count += 1;
      else seen.set(node.parent_id, { id: node.parent_id, display_name: node.display_name, count: 1 });
    }
    return Array.from(seen.values()).sort((a, b) => b.count - a.count);
  }, [nodes]);

  const presentTopics = useMemo(() => {
    const seen = new Map<number, { topic_id: number; label: string; count: number }>();
    for (const node of nodes) {
      for (const topic of node.top_topics) {
        const current = seen.get(topic.topic_id) ?? {
          topic_id: topic.topic_id,
          label: topic.label || `Topic ${topic.topic_id}`,
          count: 0,
        };
        current.count += 1;
        seen.set(topic.topic_id, current);
      }
    }
    return Array.from(seen.values()).sort((a, b) => b.count - a.count).slice(0, 5);
  }, [nodes]);

  useEffect(() => {
    const graph: GraphNode[] = nodes.map((node, index) => {
      const angle = (index / Math.max(nodes.length, 1)) * Math.PI * 2;
      return {
        ...node,
        x: WIDTH / 2 + Math.cos(angle) * 200,
        y: HEIGHT / 2 + Math.sin(angle) * 160,
        radius: 8 + Math.sqrt(node.total_volume / maxVolume) * 28,
      };
    });
    const links: GraphLink[] = edges.map((edge) => ({ ...edge }));
    setGraphNodes(graph);
    setGraphLinks(links);

    simulationRef.current?.stop();
    const simulation = forceSimulation<GraphNode, GraphLink>(graph)
      .force(
        "link",
        forceLink<GraphNode, GraphLink>(links)
          .id((node) => node.subreddit)
          .distance((link) => 200 - link.score * 110)
          .strength((link) => 0.12 + link.score * 0.38),
      )
      .force("charge", forceManyBody().strength(-260))
      .force("collide", forceCollide<GraphNode>().radius((node) => node.radius + 12).iterations(2))
      .force("x", forceX(WIDTH / 2).strength(0.03))
      .force("y", forceY(HEIGHT / 2).strength(0.04))
      .force("center", forceCenter(WIDTH / 2, HEIGHT / 2))
      .alpha(0.95)
      .alphaDecay(0.04);

    simulation.on("tick", () => {
      setGraphNodes([...graph]);
      setGraphLinks([...links]);
    });
    simulationRef.current = simulation;
    return () => {
      simulation.stop();
    };
  }, [nodes, edges, maxVolume]);

  function isMuted(parentId: string) {
    return selectedParent != null && parentId !== selectedParent;
  }

  function nodeHasTopic(node: SubredditGraphNode, topicId: number | null) {
    return topicId == null || node.top_topics.some((topic) => topic.topic_id === topicId);
  }

  return (
    <div className="relative">
      <svg
        ref={svgRef}
        className={cn("h-full w-full select-none rounded-lg border border-white/8 bg-black/18 signal-grid", "min-h-[520px]")}
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        role="img"
        aria-label="Subreddit similarity network"
      >
        <g>
          {graphLinks.map((edge) => {
            const source = edge.source as GraphNode;
            const target = edge.target as GraphNode;
            const [sId, tId] = linkIds(edge);
            const sourceNode = graphNodes.find((n) => n.subreddit === sId);
            const targetNode = graphNodes.find((n) => n.subreddit === tId);
            const dim = selectedParent != null
              && sourceNode?.parent_id !== selectedParent
              && targetNode?.parent_id !== selectedParent;
            const topicDim = topicFocus != null
              && !(sourceNode && targetNode && nodeHasTopic(sourceNode, topicFocus) && nodeHasTopic(targetNode, topicFocus));
            return (
              <line
                key={`${sId}-${tId}`}
                x1={source.x}
                y1={source.y}
                x2={target.x}
                y2={target.y}
                stroke="#9aa3a8"
                strokeOpacity={dim || topicDim ? 0.08 : 0.25 + edge.score * 0.55}
                strokeWidth={1 + edge.score * 6}
                onMouseEnter={() => setHoveredEdge(edge)}
                onMouseLeave={() => setHoveredEdge(null)}
                style={{ cursor: "pointer" }}
              />
            );
          })}
          {graphNodes.map((node) => {
            const color = parentColor(node.parent_id);
            const muted = isMuted(node.parent_id) || !nodeHasTopic(node, topicFocus);
            return (
              <g
                key={node.subreddit}
                role="button"
                tabIndex={0}
                aria-label={`${node.subreddit} in ${node.display_name}`}
                transform={`translate(${node.x ?? WIDTH / 2} ${node.y ?? HEIGHT / 2})`}
                onMouseEnter={() => setHovered(node)}
                onMouseLeave={() => setHovered(null)}
                onClick={() => onSelectParent(selectedParent === node.parent_id ? null : node.parent_id)}
                className="cursor-pointer outline-none"
              >
                <circle r={node.radius} fill={color} opacity={muted ? 0.2 : 0.9} />
                <circle r={node.radius + 2} fill="none" stroke={color} strokeOpacity={muted ? 0.25 : 0.85} strokeWidth={1.5} />
                <text
                  y={node.radius + 14}
                  textAnchor="middle"
                  className="pointer-events-none fill-foreground font-mono text-[10px]"
                  opacity={muted ? 0.35 : 0.95}
                >
                  {node.subreddit}
                </text>
              </g>
            );
          })}
        </g>
      </svg>

      {!nodes.length && (
        <div className="pointer-events-none absolute inset-0 grid place-items-center rounded-lg text-xs text-muted-foreground">
          Waiting for graph signals
        </div>
      )}

      <div className="absolute right-3 top-3 flex flex-col gap-1 rounded-md border border-border bg-card/90 px-2 py-2 text-[11px] shadow-2xl">
        <p className="px-1 font-mono text-[10px] uppercase tracking-wide text-muted-foreground">Parents</p>
        {presentParents.map((parent) => {
          const active = selectedParent === parent.id;
          return (
            <button
              key={parent.id}
              type="button"
              onClick={() => onSelectParent(active ? null : parent.id)}
              className={cn(
                "flex items-center gap-2 rounded px-2 py-1 text-left transition-colors",
                active ? "bg-muted text-foreground" : "text-muted-foreground hover:bg-muted/60 hover:text-foreground",
              )}
            >
              <span
                className="size-2.5 rounded-full"
                style={{ background: PARENT_PALETTE[parent.id] ?? PARENT_PALETTE.OTHER }}
              />
              <span className="truncate">{parent.display_name}</span>
              <span className="ml-auto font-mono tabular-nums text-[10px] text-muted-foreground">{parent.count}</span>
            </button>
          );
        })}
        {selectedParent && (
          <button
            type="button"
            onClick={() => onSelectParent(null)}
            className="mt-1 rounded px-2 py-1 text-left text-[10px] text-signal-copper hover:text-foreground"
          >
            Clear isolation
          </button>
        )}
      </div>

      {!!presentTopics.length && (
        <div className="absolute left-3 top-3 max-w-80 rounded-md border border-border bg-card/90 px-2 py-2 text-[11px] shadow-2xl">
          <p className="px-1 font-mono text-[10px] uppercase tracking-wide text-muted-foreground">Topic lens</p>
          <div className="mt-1 flex flex-wrap gap-1">
            {presentTopics.map((topic) => {
              const active = topicFocus === topic.topic_id;
              return (
                <button
                  key={topic.topic_id}
                  type="button"
                  onClick={() => setTopicFocus(active ? null : topic.topic_id)}
                  className={cn(
                    "max-w-36 truncate rounded border px-2 py-1 text-left transition-colors",
                    active ? "border-signal-green/45 bg-signal-green/10 text-foreground" : "border-border text-muted-foreground hover:bg-muted/60 hover:text-foreground",
                  )}
                  title={`Topic ${topic.topic_id}`}
                >
                  {topic.label}
                </button>
              );
            })}
          </div>
        </div>
      )}

      {hovered && (
        <div className="pointer-events-none absolute bottom-4 left-4 z-20 max-w-72 rounded-lg border border-signal-copper/35 bg-[#081816]/95 px-3 py-2 text-[11px] shadow-2xl">
          <p className="font-mono text-signal-copper">{hovered.display_name}</p>
          <p className="mt-1 text-sm font-medium text-foreground">{hovered.subreddit}</p>
          <p className="mt-1 font-mono text-muted-foreground">
            {hovered.total_volume.toLocaleString()} comments / sentiment{" "}
            {hovered.mean_sentiment == null ? "n/a" : hovered.mean_sentiment.toFixed(2)}
          </p>
          {!!hovered.top_topics.length && (
            <p className="mt-1 truncate font-mono text-signal-green">
              {hovered.top_topics
                .slice(0, 3)
                .map((t) => t.label ?? `Topic ${t.topic_id}`)
                .join(", ")}
            </p>
          )}
        </div>
      )}

      {hoveredEdge && (
        <div className="pointer-events-none absolute right-3 bottom-3 z-20 max-w-72 rounded-lg border border-signal-copper/35 bg-[#081816]/95 px-3 py-2 text-[11px] shadow-2xl">
          <p className="font-mono text-signal-copper">
            {endpointId(hoveredEdge.source as LinkEndpoint)}
            {" ↔ "}
            {endpointId(hoveredEdge.target as LinkEndpoint)}
          </p>
          <p className="mt-1 font-mono text-muted-foreground">
            score {hoveredEdge.score.toFixed(2)} / authors {hoveredEdge.author_overlap.toFixed(2)} / topics {hoveredEdge.topic_overlap.toFixed(2)}
          </p>
          {!!hoveredEdge.shared_topic_ids.length && (
            <p className="mt-1 truncate font-mono text-signal-green">
              shared topics: {
                (hoveredEdge.shared_topics?.length ? hoveredEdge.shared_topics : hoveredEdge.shared_topic_ids.map((id) => ({ topic_id: id, label: `Topic ${id}` })))
                  .slice(0, 5)
                  .map((topic) => topic.label || `Topic ${topic.topic_id}`)
                  .join(", ")
              }
            </p>
          )}
        </div>
      )}
    </div>
  );
}
