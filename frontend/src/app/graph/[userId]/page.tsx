"use client";

import { useState, useEffect, useRef, use } from "react";
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

  // Playback
  useEffect(() => {
    playRef.current = playing;
    if (!playing) return;
    const interval = setInterval(() => {
      if (!playRef.current) return;
      setIdx((i) => {
        if (i >= snapshots.length - 1) {
          setPlaying(false);
          return i;
        }
        return i + 1;
      });
    }, 1000);
    return () => clearInterval(interval);
  }, [playing, snapshots.length]);

  const current = snapshots[idx];
  const items: DomainItem[] = current?.snapshot_data?.items || [];
  const edges: Edge[] = current?.snapshot_data?.edges || [];
  const dateLabel = current?.snapshot_date || "—";

  return (
    <div className="h-screen flex flex-col">
      {/* Graph fills everything */}
      <div className="flex-1 relative">
        {loading ? (
          <div className="absolute inset-0 flex items-center justify-center text-[#444] text-sm">
            loading…
          </div>
        ) : items.length === 0 ? (
          <div className="absolute inset-0 flex items-center justify-center text-[#444] text-sm">
            No graph data
          </div>
        ) : (
          <GraphView items={items} edges={edges} />
        )}

        {/* Back button — top left, subtle */}
        <button
          onClick={() => router.push("/")}
          className="absolute top-3 left-3 text-xs text-[#555] hover:text-[#999] transition-colors"
        >
          ← back
        </button>

        {/* Legend — top right, tiny */}
        <div className="absolute top-3 right-3 flex gap-3">
          {Object.entries(DOMAIN_COLORS).map(([domain, color]) => (
            <div key={domain} className="flex items-center gap-1">
              <div
                className="w-2 h-2 rounded-full"
                style={{ background: color }}
              />
              <span className="text-[10px] text-[#555]">{domain}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Slider bar at bottom */}
      {snapshots.length > 1 && (
        <div className="flex items-center gap-3 px-4 h-[54px] shrink-0 border-t border-[#181818]">
          <button
            onClick={() => {
              if (playing) {
                setPlaying(false);
              } else {
                if (idx >= snapshots.length - 1) setIdx(0);
                setPlaying(true);
              }
            }}
            className="w-8 h-8 flex items-center justify-center rounded border border-[#333] text-[#999] hover:text-white hover:border-[#555] text-xs"
          >
            {playing ? "⏸" : "▶"}
          </button>
          <input
            type="range"
            min={0}
            max={snapshots.length - 1}
            value={idx}
            onChange={(e) => {
              setPlaying(false);
              setIdx(Number(e.target.value));
            }}
            className="flex-1 accent-[#4A90D9]"
          />
          <span className="text-sm text-[#999] min-w-[90px] text-right font-mono">
            {dateLabel}
          </span>
        </div>
      )}
    </div>
  );
}
