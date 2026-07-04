"use client";

import { useEffect, useState } from "react";
import { getToken } from "@/lib/api";

interface StreamEvent {
  status: string;
  frames_done: number;
  frames_total: number;
  error: string | null;
}

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function JobProgress({ jobId, onDone }: { jobId: number; onDone: () => void }) {
  const [event, setEvent] = useState<StreamEvent | null>(null);

  useEffect(() => {
    const token = getToken();
    const source = new EventSource(`${API_URL}/jobs/${jobId}/stream?token=${token}`);

    source.onmessage = (e) => {
      const data: StreamEvent = JSON.parse(e.data);
      setEvent(data);
      if (data.status === "done") {
        source.close();
        onDone();
      } else if (data.status === "failed") {
        source.close();
      }
    };

    return () => source.close();
  }, [jobId, onDone]);

  if (!event) {
    return (
      <div className="flex items-center gap-3 rounded-2xl border border-line bg-white px-5 py-4 text-sm text-muted">
        <span className="h-2 w-2 animate-pulse rounded-full bg-brand" />
        Connecting…
      </div>
    );
  }

  if (event.status === "failed") {
    return (
      <div className="rounded-2xl border border-red-200 bg-red-50 p-5">
        <p className="mb-2 text-sm font-semibold text-brand">Extraction failed</p>
        <pre className="max-h-64 overflow-auto whitespace-pre-wrap break-words rounded-lg bg-white/70 p-3 font-mono text-xs text-ink">
          {event.error}
        </pre>
      </div>
    );
  }

  const percent =
    event.frames_total > 0
      ? Math.min(100, Math.round((event.frames_done / event.frames_total) * 100))
      : 0;

  return (
    <div className="rounded-2xl border border-line bg-white p-5">
      <div className="mb-3 flex items-center justify-between text-sm">
        <span className="font-medium capitalize text-ink">{event.status}…</span>
        <span className="text-muted">
          {event.frames_done} / {event.frames_total} frames
        </span>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-chip">
        <div
          className="h-full rounded-full bg-brand transition-all duration-500"
          style={{ width: `${percent}%` }}
        />
      </div>
    </div>
  );
}
