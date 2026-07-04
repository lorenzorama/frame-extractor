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

  if (!event) return <p>Connecting...</p>;

  if (event.status === "failed") {
    return <p className="text-red-600">Failed: {event.error}</p>;
  }

  return (
    <p>
      Status: {event.status} — {event.frames_done}/{event.frames_total} frames
    </p>
  );
}
