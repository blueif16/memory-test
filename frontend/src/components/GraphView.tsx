"use client";

import { useEffect, useRef, useCallback, useState } from "react";
import type { DomainItem, Edge } from "@/lib/types";
import { DOMAIN_COLORS } from "@/lib/constants";

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

// Simple force-directed graph on canvas — no library needed
export default function GraphView({ items, edges }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const nodesRef = useRef<GraphNode[]>([]);
  const linksRef = useRef<GraphLink[]>([]);
  const animRef = useRef<number>(0);
  const dragRef = useRef<{ node: GraphNode | null; offsetX: number; offsetY: number }>({
    node: null,
    offsetX: 0,
    offsetY: 0,
  });
  const [hoveredNode, setHoveredNode] = useState<GraphNode | null>(null);

  // Build graph data from props
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const w = canvas.width;
    const h = canvas.height;

    // Reuse positions for existing nodes
    const oldMap = new Map(nodesRef.current.map((n) => [n.id, n]));

    nodesRef.current = items.map((item) => {
      const old = oldMap.get(item.id);
      return {
        id: item.id,
        label: item.title,
        domain: item.domain,
        score: item.raw_score ?? 1,
        active: item.above_floor !== false,
        x: old?.x ?? w / 2 + (Math.random() - 0.5) * 300,
        y: old?.y ?? h / 2 + (Math.random() - 0.5) * 300,
        vx: old?.vx ?? 0,
        vy: old?.vy ?? 0,
      };
    });

    linksRef.current = edges.map((e) => ({
      source: e.source_id,
      target: e.target_id,
      relation: e.relation,
      strength: e.strength,
    }));
  }, [items, edges]);

  // Resize canvas
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const resize = () => {
      canvas.width = window.innerWidth;
      canvas.height = window.innerHeight - 64; // leave room for slider bar
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
      const nodes = nodesRef.current;
      const links = linksRef.current;
      const nodeMap = new Map(nodes.map((n) => [n.id, n]));
      const w = canvas.width;
      const h = canvas.height;
      const cx = w / 2;
      const cy = h / 2;

      // Forces
      for (const n of nodes) {
        n.vx = (n.vx ?? 0) * 0.9;
        n.vy = (n.vy ?? 0) * 0.9;

        // Center gravity
        n.vx! += (cx - n.x!) * 0.001;
        n.vy! += (cy - n.y!) * 0.001;
      }

      // Repulsion between nodes
      for (let i = 0; i < nodes.length; i++) {
        for (let j = i + 1; j < nodes.length; j++) {
          const a = nodes[i];
          const b = nodes[j];
          const dx = a.x! - b.x!;
          const dy = a.y! - b.y!;
          const dist = Math.sqrt(dx * dx + dy * dy) || 1;
          const force = 800 / (dist * dist);
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
        if (!a || !b) continue;
        const dx = b.x! - a.x!;
        const dy = b.y! - a.y!;
        const dist = Math.sqrt(dx * dx + dy * dy) || 1;
        const force = (dist - 120) * 0.005 * Math.min(link.strength, 3);
        a.vx! += (dx / dist) * force;
        a.vy! += (dy / dist) * force;
        b.vx! -= (dx / dist) * force;
        b.vy! -= (dy / dist) * force;
      }

      // Update positions
      for (const n of nodes) {
        if (dragRef.current.node?.id === n.id) continue;
        n.x = Math.max(30, Math.min(w - 30, n.x! + n.vx!));
        n.y = Math.max(30, Math.min(h - 30, n.y! + n.vy!));
      }

      // Draw
      ctx.clearRect(0, 0, w, h);

      // Edges
      for (const link of links) {
        const a = nodeMap.get(link.source);
        const b = nodeMap.get(link.target);
        if (!a || !b) continue;
        ctx.beginPath();
        ctx.moveTo(a.x!, a.y!);
        ctx.lineTo(b.x!, b.y!);
        ctx.strokeStyle = "rgba(255,255,255,0.12)";
        ctx.lineWidth = Math.max(0.5, Math.min(link.strength, 4));
        ctx.stroke();

        // Edge label
        if (link.relation) {
          const mx = (a.x! + b.x!) / 2;
          const my = (a.y! + b.y!) / 2;
          ctx.fillStyle = "rgba(255,255,255,0.2)";
          ctx.font = "9px system-ui";
          ctx.textAlign = "center";
          ctx.fillText(link.relation, mx, my);
        }
      }

      // Nodes
      for (const n of nodes) {
        const r = 8 + Math.min(n.score * 4, 24);
        const color = DOMAIN_COLORS[n.domain] || DOMAIN_COLORS.general;
        const alpha = n.active ? 1 : 0.25;

        ctx.beginPath();
        ctx.arc(n.x!, n.y!, r, 0, Math.PI * 2);
        ctx.fillStyle = color;
        ctx.globalAlpha = alpha;
        ctx.fill();

        // Glow for high-score active nodes
        if (n.active && n.score > 2) {
          ctx.beginPath();
          ctx.arc(n.x!, n.y!, r + 4, 0, Math.PI * 2);
          ctx.strokeStyle = color;
          ctx.lineWidth = 2;
          ctx.globalAlpha = 0.3;
          ctx.stroke();
        }

        ctx.globalAlpha = 1;

        // Label
        ctx.fillStyle = n.active ? "#eee" : "#666";
        ctx.font = `${Math.max(10, 11)}px system-ui`;
        ctx.textAlign = "center";
        ctx.fillText(n.label, n.x!, n.y! + r + 14);
      }

      animRef.current = requestAnimationFrame(tick);
    };

    animRef.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(animRef.current);
  }, []);

  // Mouse interactions
  const getNodeAt = useCallback(
    (x: number, y: number): GraphNode | null => {
      for (const n of nodesRef.current) {
        const r = 8 + Math.min(n.score * 4, 24);
        const dx = x - n.x!;
        const dy = y - n.y!;
        if (dx * dx + dy * dy < r * r) return n;
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
        dragRef.current = { node, offsetX: x - node.x!, offsetY: y - node.y! };
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
          className="absolute pointer-events-none px-3 py-1.5 rounded text-xs"
          style={{
            left: (hoveredNode.x ?? 0) + 20,
            top: (hoveredNode.y ?? 0) - 10,
            background: "rgba(0,0,0,0.85)",
            border: `1px solid ${DOMAIN_COLORS[hoveredNode.domain] || "#555"}`,
          }}
        >
          <span style={{ color: DOMAIN_COLORS[hoveredNode.domain] }}>
            {hoveredNode.domain}
          </span>{" "}
          &middot; score: {hoveredNode.score.toFixed(1)}
        </div>
      )}
    </div>
  );
}
