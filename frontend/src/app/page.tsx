"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";

export default function Home() {
  const [users, setUsers] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const router = useRouter();

  useEffect(() => {
    api
      .getUsers()
      .then((r) => setUsers(r.users))
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="h-screen flex items-center justify-center">
      <div className="w-full max-w-md px-6">
        <h1 className="text-lg font-medium text-[#eee] mb-6">Journal Graph</h1>
        {loading ? (
          <p className="text-sm text-[#666]">loading users…</p>
        ) : users.length === 0 ? (
          <p className="text-sm text-[#666]">No users found</p>
        ) : (
          <div className="flex flex-col gap-2">
            {users.map((u) => (
              <button
                key={u}
                onClick={() => router.push(`/graph/${encodeURIComponent(u)}`)}
                className="text-left px-4 py-3 rounded border border-[#222] hover:border-[#4A90D9] hover:bg-[#111] text-sm text-[#ccc] transition-colors font-mono"
              >
                {u}
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
