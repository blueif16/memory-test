"use client";

import { useState, useEffect, useRef, use, useMemo } from "react";
import dynamic from "next/dynamic";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import type { Snapshot, DomainItem, Edge } from "@/lib/types";
import { DOMAIN_COLORS } from "@/lib/constants";

const GraphView = dynamic(() => import("@/components/GraphView"), {
  ssr: false,
});

export default function GraphPage({
  params,
}: {
  params: Promise<{ userId: string }>;
}) {
  const { userId } = use(params);
  const decodedUserId = decodeURIComponent(userId);
  const router = useRouter();

  const [snapshots, setSnapshots] = useState<Snapshot[]>([]);
  const [idx, setIdx] = useState(0);
  const [loading, setLoading] = useState(true);
  const [playing, setPlaying] = useState(false);
  const playRef = useRef(false);

  useEffect(() => {
    api
      .getSnapshots(decodedUserId)
      .then((r) => {
        setSnapshots(r.snapshots);
        setIdx(r.snapshots.length > 0 ? r.snapshots.length - 1 : 0);
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [decodedUserId]);

  // Playback — 1.5s per snapshot
  useEffect(() => {
    playRef.current = playing;
    if (!playing) return;
    const interval = setInterval(() => {
      if (!playRef.current) return;
      setIdx((i: number) => {
        if (i >= snapshots.length - 1) {
          setPlaying(false);
          return i;
        }
        return i + 1;
      });
    }, 1500);
    return () => clearInterval(interval);
  }, [playing, snapshots.length]);

  const current = snapshots[idx];
  const prev = idx > 0 ? snapshots[idx - 1] : null;
  const items: DomainItem[] = current?.snapshot_data?.items || [];
  const edges: Edge[] = current?.snapshot_data?.edges || [];
  const dateLabel = current?.snapshot_date || "—";

  // Stats for current snapshot
  const stats = useMemo(() => {
    const prevItems = prev?.snapshot_data?.items || [];
    const prevIds = new Set(prevItems.map((i: DomainItem) => i.id));
    const newCount = items.filter((i: DomainItem) => !prevIds.has(i.id)).length;
    const domainCounts: Record<string, number> = {};
    for (const item of items) {
      domainCounts[item.domain] = (domainCounts[item.domain] || 0) + 1;
    }
    const maxScore = Math.max(0, ...items.map((i) => i.raw_score ?? 0));
    const avgScore =
      items.length > 0
        ? items.reduce((s: number, i: DomainItem) => s + (i.raw_score ?? 0), 0) / items.length
        : 0;
    return { newCount, domainCounts, maxScore, avgScore };
  }, [items, prev]);

  return (
    <div className="h-screen flex flex-col bg-black">
      {/* Graph fills everything */}
      <div className="flex-1 relative">
        {loading ? (
          <div className="absolute inset-0 flex items-center justify-center text-[#333] text-sm font-mono">
            loading...
          </div>
        ) : items.length === 0 ? (
          <div className="absolute inset-0 flex items-center justify-center text-[#222] text-sm font-mono">
            {snapshots.length === 0 ? "no entries yet" : "empty snapshot"}
          </div>
        ) : (
          <GraphView items={items} edges={edges} />
        )}

        {/* Back — top left */}
        <button
          onClick={() => router.push("/")}
          className="absolute top-3 left-3 text-xs text-[#444] hover:text-[#888] transition-colors font-mono"
        >
          &larr; back
        </button>

        {/* Stats overlay — top right */}
        <div className="absolute top-3 right-3 text-right font-mono text-[10px] leading-relaxed">
          <div className="text-[#666]">{dateLabel}</div>
          <div className="text-[#444]">
            {items.length} nodes &middot; {edges.length} edges
          </div>
          {stats.newCount > 0 && prev && (
            <div className="text-[#50C878]">+{stats.newCount} new</div>
          )}
          {items.length > 0 && (
            <div className="text-[#333]">
              avg {stats.avgScore.toFixed(2)} &middot; max{" "}
              {stats.maxScore.toFixed(2)}
            </div>
          )}
          {/* Domain breakdown */}
          <div className="mt-2 space-y-0.5">
            {(Object.entries(stats.domainCounts) as [string, number][])
              .sort((a, b) => b[1] - a[1])
              .map(([domain, count]) => (
                <div key={domain} className="flex items-center justify-end gap-1.5">
                  <span className="text-[#444]">
                    {domain} {count}
                  </span>
                  <div
                    className="w-1.5 h-1.5 rounded-full"
                    style={{
                      background: DOMAIN_COLORS[domain] || DOMAIN_COLORS.general,
                    }}
                  />
                </div>
              ))}
          </div>
        </div>
      </div>

      {/* Timeline bar — bottom */}
      {snapshots.length > 1 && (
        <div className="shrink-0 px-4 py-2 border-t border-[#111]">
          <div className="flex items-center gap-3">
            <button
              onClick={() => {
                if (playing) {
                  setPlaying(false);
                } else {
                  if (idx >= snapshots.length - 1) setIdx(0);
                  setPlaying(true);
                }
              }}
              className="w-7 h-7 flex items-center justify-center rounded border border-[#222] text-[#666] hover:text-white hover:border-[#444] text-[10px] font-mono transition-colors"
            >
              {playing ? "||" : ">"}
            </button>

            {/* Custom track */}
            <div
              className="flex-1 relative h-6 flex items-center cursor-pointer"
              onClick={(e: React.MouseEvent<HTMLDivElement>) => {
                const rect = e.currentTarget.getBoundingClientRect();
                const pct = (e.clientX - rect.left) / rect.width;
                const newIdx = Math.round(pct * (snapshots.length - 1));
                setPlaying(false);
                setIdx(clampIdx(newIdx, snapshots.length));
              }}
            >
              {/* Track line */}
              <div className="absolute left-0 right-0 h-px bg-[#222]" />
              {/* Progress fill */}
              <div
                className="absolute left-0 h-px bg-[#333]"
                style={{
                  width: `${(idx / Math.max(1, snapshots.length - 1)) * 100}%`,
                }}
              />
              {/* Snapshot dots */}
              {snapshots.map((snap: Snapshot, i: number) => {
                const pct = (i / Math.max(1, snapshots.length - 1)) * 100;
                const nodeCount = snap.snapshot_data?.items?.length || 0;
                const intensity = Math.min(
                  1,
                  nodeCount / Math.max(1, ...snapshots.map((s: Snapshot) => s.snapshot_data?.items?.length || 1))
                );
                const isActive = i === idx;
                return (
                  <div
                    key={i}
                    className="absolute -translate-x-1/2"
                    style={{
                      left: `${pct}%`,
                    }}
                  >
                    <div
                      className="rounded-full transition-all duration-200"
                      style={{
                        width: isActive ? 8 : 3,
                        height: isActive ? 8 : 3,
                        background: isActive
                          ? "#4A90D9"
                          : `rgba(255,255,255,${0.08 + intensity * 0.25})`,
                        boxShadow: isActive
                          ? "0 0 8px rgba(74,144,217,0.5)"
                          : "none",
                      }}
                    />
                  </div>
                );
              })}
            </div>

            <span className="text-[10px] text-[#444] min-w-[60px] text-right font-mono">
              {idx + 1}/{snapshots.length}
            </span>
          </div>
        </div>
      )}
    </div>
  );
}

function clampIdx(i: number, len: number): number {
  return Math.max(0, Math.min(len - 1, i));
}
