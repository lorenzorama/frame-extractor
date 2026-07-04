"use client";

import { useState } from "react";
import { createJob } from "@/lib/jobs";

export default function JobForm({ onCreated }: { onCreated: (jobId: number) => void }) {
  const [url, setUrl] = useState("");
  const [interval, setInterval_] = useState("5");
  const [timestamps, setTimestamps] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const manual = timestamps
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean)
        .map(Number)
        .filter((n) => !Number.isNaN(n));
      const job = await createJob({
        youtube_url: url,
        interval_seconds: interval ? Number(interval) : undefined,
        manual_timestamps: manual.length ? manual : undefined,
      });
      onCreated(job.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create job");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-3 max-w-md">
      <input
        placeholder="YouTube URL"
        value={url}
        onChange={(e) => setUrl(e.target.value)}
        className="border rounded px-3 py-2"
        required
      />
      <input
        placeholder="Interval seconds (e.g. 5)"
        value={interval}
        onChange={(e) => setInterval_(e.target.value)}
        className="border rounded px-3 py-2"
      />
      <input
        placeholder="Manual timestamps, comma-separated (e.g. 12.5, 30)"
        value={timestamps}
        onChange={(e) => setTimestamps(e.target.value)}
        className="border rounded px-3 py-2"
      />
      {error && <p className="text-red-600 text-sm">{error}</p>}
      <button type="submit" disabled={submitting} className="bg-black text-white rounded px-3 py-2 disabled:opacity-50">
        {submitting ? "Submitting..." : "Extract frames"}
      </button>
    </form>
  );
}
