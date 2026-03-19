"use client";

import { useEffect, useRef, useCallback, useState } from "react";
import type { DomainItem, Edge } from "@/lib/types";
import { DOMAIN_COLORS, DOMAIN_COLORS_RGB } from "@/lib/constants";

interface GraphNode {
  id: string;
  label: string;
  domain: string;
  score: number;
  active: boolean;
  x?: number;
  y?: number;
  vx?: number;
  vy?: number;
  // Animation state
  enterT?: number; // timestamp when node appeared (for entry animation)
  exitT?: number; // timestamp when node started disappearing
  targetScore?: number; // for score lerping
  displayScore?: number; // current interpolated score
  dying?: boolean; // node is fading out
}

interface GraphLink {
  source: string;
  target: string;
  relation: string;
  strength: number;
}

interface Props {
  items: DomainItem[];
  edges: Edge[];
}

function clamp(v: number, lo: number, hi: number) {
  return Math.max(lo, Math.min(hi, v));
}

function rgbaStr(rgb: [number, number, number], a: number): string {
  return `rgba(${rgb[0]},${rgb[1]},${rgb[2]},${a})`;
}

export default function GraphView({ items, edges }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const nodesRef = useRef<GraphNode[]>([]);
  const linksRef = useRef<GraphLink[]>([]);
  const animRef = useRef<number>(0);
  const prevNodeIdsRef = useRef<Set<string>>(new Set());
  const dragRef = useRef<{
    node: GraphNode | null;
    offsetX: number;
    offsetY: number;
  }>({ node: null, offsetX: 0, offsetY: 0 });
  const [hoveredNode, setHoveredNode] = useState<GraphNode | null>(null);

  // Build graph data from props — with entry/exit tracking
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const w = canvas.width;
    const h = canvas.height;
    const now = performance.now();

    const oldMap = new Map<string, GraphNode>(nodesRef.current.map((n: GraphNode) => [n.id, n]));
    const newIds = new Set(items.map((i: DomainItem) => i.id));
    const prevIds = prevNodeIdsRef.current;

    // Build new nodes
    const newNodes: GraphNode[] = items.map((item) => {
      const old = oldMap.get(item.id);
      const isNew = !prevIds.has(item.id);
      const score = item.raw_score ?? 0;
      return {
        id: item.id,
        label: item.title,
        domain: item.domain,
        score,
        active: item.above_floor !== false,
        x: old?.x ?? w / 2 + (Math.random() - 0.5) * 200,
        y: old?.y ?? h / 2 + (Math.random() - 0.5) * 200,
        vx: old?.vx ?? 0,
        vy: old?.vy ?? 0,
        enterT: isNew ? now : old?.enterT ?? 0,
        exitT: undefined,
        targetScore: score,
        displayScore: old?.displayScore ?? (isNew ? 0 : score),
        dying: false,
      };
    });

    // Keep dying nodes that just disappeared (for fade-out)
    for (const old of nodesRef.current) {
      if (!newIds.has(old.id) && !old.dying) {
        newNodes.push({
          ...old,
          dying: true,
          exitT: now,
          targetScore: 0,
        });
      }
    }

    nodesRef.current = newNodes;
    linksRef.current = edges.map((e) => ({
      source: e.source_id,
      target: e.target_id,
      relation: e.relation,
      strength: e.strength,
    }));

    prevNodeIdsRef.current = newIds;
  }, [items, edges]);

  // Resize canvas
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const resize = () => {
      canvas.width = window.innerWidth;
      canvas.height = window.innerHeight - 64;
    };
    resize();
    window.addEventListener("resize", resize);
    return () => window.removeEventListener("resize", resize);
  }, []);

  // Force simulation + render loop
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d")!;

    const tick = () => {
      const now = performance.now();
      let nodes = nodesRef.current;
      const links = linksRef.current;
      const nodeMap = new Map<string, GraphNode>(nodes.map((n: GraphNode) => [n.id, n]));
      const w = canvas.width;
      const h = canvas.height;
      const cx = w / 2;
      const cy = h / 2;

      // Remove dead nodes (finished fade-out)
      nodes = nodes.filter(
        (n: GraphNode) => !n.dying || now - (n.exitT ?? now) < 500
      );
      nodesRef.current = nodes;

      // Compute maxScore and maxStrength for normalization
      const maxScore = Math.max(
        0.01,
        ...nodes.filter((n: GraphNode) => !n.dying).map((n: GraphNode) => n.score)
      );
      const maxStrength = Math.max(0.01, ...links.map((l: GraphLink) => l.strength));

      // Lerp display scores toward target
      for (const n of nodes) {
        const target = n.targetScore ?? n.score;
        const current = n.displayScore ?? n.score;
        n.displayScore = current + (target - current) * 0.08;
      }

      const liveNodes = nodes.filter((n: GraphNode) => !n.dying);
      const nodeCount = liveNodes.length;
      const repulsionScale = clamp(nodeCount / 15, 0.5, 3);
      const gravityScale = clamp(nodeCount / 8, 0.5, 2);

      // Forces
      for (const n of liveNodes) {
        n.vx = (n.vx ?? 0) * 0.9;
        n.vy = (n.vy ?? 0) * 0.9;

        // Center gravity — adaptive
        n.vx! += (cx - n.x!) * (0.003 / gravityScale);
        n.vy! += (cy - n.y!) * (0.003 / gravityScale);
      }

      // Repulsion — adaptive
      for (let i = 0; i < liveNodes.length; i++) {
        for (let j = i + 1; j < liveNodes.length; j++) {
          const a = liveNodes[i];
          const b = liveNodes[j];
          const dx = a.x! - b.x!;
          const dy = a.y! - b.y!;
          const dist = Math.sqrt(dx * dx + dy * dy) || 1;
          const force = 600 / (dist * dist * repulsionScale);
          a.vx! += (dx / dist) * force;
          a.vy! += (dy / dist) * force;
          b.vx! -= (dx / dist) * force;
          b.vy! -= (dy / dist) * force;
        }
      }

      // Link attraction
      for (const link of links) {
        const a = nodeMap.get(link.source);
        const b = nodeMap.get(link.target);
        if (!a || !b || a.dying || b.dying) continue;
        const dx = b.x! - a.x!;
        const dy = b.y! - a.y!;
        const dist = Math.sqrt(dx * dx + dy * dy) || 1;
        const force =
          (dist - 120) * 0.005 * Math.min(link.strength, 3);
        a.vx! += (dx / dist) * force;
        a.vy! += (dy / dist) * force;
        b.vx! -= (dx / dist) * force;
        b.vy! -= (dy / dist) * force;
      }

      // Update positions
      for (const n of liveNodes) {
        if (dragRef.current.node?.id === n.id) continue;
        n.x = Math.max(40, Math.min(w - 40, n.x! + n.vx!));
        n.y = Math.max(40, Math.min(h - 40, n.y! + n.vy!));
      }

      // === DRAW ===
      ctx.clearRect(0, 0, w, h);

      // Edges — strength drives visibility
      for (const link of links) {
        const a = nodeMap.get(link.source);
        const b = nodeMap.get(link.target);
        if (!a || !b) continue;

        const normStr = link.strength / maxStrength;
        const edgeAlpha = 0.04 + normStr * 0.28;
        const edgeWidth = 0.5 + normStr * 3.5;

        // Tint edge toward source node's domain color
        const rgb = DOMAIN_COLORS_RGB[a.domain] || DOMAIN_COLORS_RGB.general;

        ctx.beginPath();
        ctx.moveTo(a.x!, a.y!);
        ctx.lineTo(b.x!, b.y!);
        ctx.strokeStyle = rgbaStr(rgb, edgeAlpha);
        ctx.lineWidth = edgeWidth;
        ctx.stroke();

        // Edge label — only for strong connections
        if (link.relation && link.strength >= 2) {
          const mx = (a.x! + b.x!) / 2;
          const my = (a.y! + b.y!) / 2;
          ctx.fillStyle = `rgba(255,255,255,${0.1 + normStr * 0.25})`;
          ctx.font = "9px 'SF Mono', 'Fira Code', monospace";
          ctx.textAlign = "center";
          ctx.fillText(link.relation, mx, my);
        }
      }

      // Nodes — score drives everything
      for (const n of nodes) {
        const dScore = n.displayScore ?? n.score;
        const normScore = clamp(dScore / maxScore, 0, 1);

        // Entry animation: scale up from 0 over 400ms
        let entryScale = 1;
        if (n.enterT && n.enterT > 0) {
          const elapsed = now - n.enterT;
          if (elapsed < 400) {
            entryScale = elapsed / 400;
            // Ease out cubic
            entryScale = 1 - Math.pow(1 - entryScale, 3);
          }
        }

        // Exit animation: fade over 500ms
        let exitAlpha = 1;
        if (n.dying && n.exitT) {
          const elapsed = now - n.exitT;
          exitAlpha = Math.max(0, 1 - elapsed / 500);
        }

        const r = (6 + normScore * 26) * entryScale;
        const rgb =
          DOMAIN_COLORS_RGB[n.domain] || DOMAIN_COLORS_RGB.general;
        const baseAlpha = (0.12 + normScore * 0.88) * exitAlpha;

        if (r < 0.5) continue; // too small to draw

        // Glow — radial gradient, proportional to score
        const glowIntensity = normScore * 0.45 * entryScale * exitAlpha;
        if (glowIntensity > 0.02) {
          const glowR = r + 8 + normScore * 16;
          const grad = ctx.createRadialGradient(
            n.x!,
            n.y!,
            r * 0.5,
            n.x!,
            n.y!,
            glowR
          );
          grad.addColorStop(0, rgbaStr(rgb, glowIntensity));
          grad.addColorStop(1, rgbaStr(rgb, 0));
          ctx.beginPath();
          ctx.arc(n.x!, n.y!, glowR, 0, Math.PI * 2);
          ctx.fillStyle = grad;
          ctx.globalAlpha = 1;
          ctx.fill();
        }

        // Node circle
        ctx.beginPath();
        ctx.arc(n.x!, n.y!, r, 0, Math.PI * 2);
        ctx.fillStyle = rgbaStr(rgb, baseAlpha);
        ctx.globalAlpha = 1;
        ctx.fill();

        // Subtle bright core for high-score nodes
        if (normScore > 0.4 && entryScale > 0.5) {
          ctx.beginPath();
          ctx.arc(n.x!, n.y!, r * 0.4, 0, Math.PI * 2);
          ctx.fillStyle = `rgba(255,255,255,${normScore * 0.3 * exitAlpha})`;
          ctx.fill();
        }

        // Label
        const fontSize = 9 + normScore * 3;
        const labelAlpha = (0.2 + normScore * 0.7) * exitAlpha * entryScale;
        ctx.font = `${fontSize}px 'SF Mono', 'Inter', system-ui`;
        ctx.textAlign = "center";
        ctx.fillStyle = `rgba(238,238,238,${labelAlpha})`;
        // Text shadow for readability
        ctx.shadowColor = "rgba(0,0,0,0.6)";
        ctx.shadowBlur = 3;
        ctx.fillText(n.label, n.x!, n.y! + r + 14);
        ctx.shadowColor = "transparent";
        ctx.shadowBlur = 0;
      }

      ctx.globalAlpha = 1;
      animRef.current = requestAnimationFrame(tick);
    };

    animRef.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(animRef.current);
  }, []);

  // Mouse interactions
  const getNodeAt = useCallback(
    (x: number, y: number): GraphNode | null => {
      for (const n of nodesRef.current) {
        if (n.dying) continue;
        const normScore = clamp(
          (n.displayScore ?? n.score) /
            Math.max(
              0.01,
              ...nodesRef.current
                .filter((nd: GraphNode) => !nd.dying)
                .map((nd: GraphNode) => nd.score)
            ),
          0,
          1
        );
        const r = 6 + normScore * 26;
        const dx = x - n.x!;
        const dy = y - n.y!;
        if (dx * dx + dy * dy < (r + 4) * (r + 4)) return n;
      }
      return null;
    },
    []
  );

  const onMouseDown = useCallback(
    (e: React.MouseEvent) => {
      const rect = canvasRef.current!.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const y = e.clientY - rect.top;
      const node = getNodeAt(x, y);
      if (node) {
        dragRef.current = {
          node,
          offsetX: x - node.x!,
          offsetY: y - node.y!,
        };
      }
    },
    [getNodeAt]
  );

  const onMouseMove = useCallback(
    (e: React.MouseEvent) => {
      const rect = canvasRef.current!.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const y = e.clientY - rect.top;

      if (dragRef.current.node) {
        dragRef.current.node.x = x - dragRef.current.offsetX;
        dragRef.current.node.y = y - dragRef.current.offsetY;
        dragRef.current.node.vx = 0;
        dragRef.current.node.vy = 0;
      } else {
        const node = getNodeAt(x, y);
        setHoveredNode(node);
        canvasRef.current!.style.cursor = node ? "grab" : "default";
      }
    },
    [getNodeAt]
  );

  const onMouseUp = useCallback(() => {
    dragRef.current = { node: null, offsetX: 0, offsetY: 0 };
  }, []);

  return (
    <div className="relative flex-1">
      <canvas
        ref={canvasRef}
        onMouseDown={onMouseDown}
        onMouseMove={onMouseMove}
        onMouseUp={onMouseUp}
        onMouseLeave={onMouseUp}
        className="block w-full h-full"
      />
      {hoveredNode && (
        <div
          className="absolute pointer-events-none px-3 py-2 rounded-lg text-xs backdrop-blur-sm"
          style={{
            left: (hoveredNode.x ?? 0) + 20,
            top: (hoveredNode.y ?? 0) - 14,
            background: "rgba(0,0,0,0.75)",
            border: `1px solid ${DOMAIN_COLORS[hoveredNode.domain] || "#555"}`,
            boxShadow: `0 0 12px ${DOMAIN_COLORS[hoveredNode.domain] || "#555"}33`,
          }}
        >
          <div
            className="font-medium"
            style={{ color: DOMAIN_COLORS[hoveredNode.domain] }}
          >
            {hoveredNode.label}
          </div>
          <div className="text-[#888] mt-0.5">
            {hoveredNode.domain} &middot; score{" "}
            {hoveredNode.score.toFixed(2)}
          </div>
        </div>
      )}
    </div>
  );
}
