"use client";

import { useState } from "react";
import { createJob } from "@/lib/jobs";

const fieldClass =
  "w-full rounded-lg border border-line px-3 py-2.5 text-sm text-ink outline-none transition-colors placeholder:text-muted focus:border-ink";

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
    <form onSubmit={handleSubmit} className="flex flex-col gap-4">
      <div className="flex flex-col gap-1.5">
        <label className="text-xs font-medium text-muted">YouTube URL</label>
        <input
          placeholder="https://youtube.com/watch?v=…"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          className={fieldClass}
          required
        />
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div className="flex flex-col gap-1.5">
          <label className="text-xs font-medium text-muted">Interval (seconds)</label>
          <input
            placeholder="5"
            value={interval}
            onChange={(e) => setInterval_(e.target.value)}
            className={fieldClass}
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <label className="text-xs font-medium text-muted">Manual timestamps</label>
          <input
            placeholder="e.g. 12.5, 30, 90"
            value={timestamps}
            onChange={(e) => setTimestamps(e.target.value)}
            className={fieldClass}
          />
        </div>
      </div>

      {error && <p className="text-sm text-brand">{error}</p>}

      <button
        type="submit"
        disabled={submitting}
        className="self-start rounded-full bg-brand px-5 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-brand-hover disabled:opacity-50"
      >
        {submitting ? "Submitting…" : "Extract frames"}
      </button>
    </form>
  );
}
