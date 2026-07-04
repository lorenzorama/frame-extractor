"use client";

import { useState } from "react";
import { createJobs } from "@/lib/jobs";

const fieldClass =
  "w-full rounded-lg border border-line px-3 py-2.5 text-sm text-ink outline-none transition-colors placeholder:text-muted focus:border-ink";

export default function JobForm({ onCreated }: { onCreated: () => void }) {
  const [urls, setUrls] = useState("");
  const [interval, setInterval_] = useState("5");
  const [timestamps, setTimestamps] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const urlList = urls
        .split("\n")
        .map((s) => s.trim())
        .filter(Boolean);
      const manual = timestamps
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean)
        .map(Number)
        .filter((n) => !Number.isNaN(n));
      await createJobs({
        youtube_urls: urlList,
        interval_seconds: interval ? Number(interval) : undefined,
        manual_timestamps: manual.length ? manual : undefined,
      });
      setUrls("");
      onCreated();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create jobs");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-4">
      <div className="flex flex-col gap-1.5">
        <label className="text-xs font-medium text-muted">YouTube URLs (one per line)</label>
        <textarea
          placeholder={"https://youtube.com/watch?v=…\nhttps://youtube.com/watch?v=…"}
          value={urls}
          onChange={(e) => setUrls(e.target.value)}
          rows={4}
          className={`${fieldClass} resize-y`}
          required
        />
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div className="flex flex-col gap-1.5">
          <label className="text-xs font-medium text-muted">Interval (seconds)</label>
          <input placeholder="5" value={interval} onChange={(e) => setInterval_(e.target.value)} className={fieldClass} />
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

      <label className="flex items-start gap-2.5 text-xs leading-relaxed text-muted">
        <input type="checkbox" required className="mt-0.5 h-4 w-4 shrink-0 accent-ink" />
        <span>
          I confirm I own these videos or am otherwise authorized to extract frames from them, and
          that doing so complies with the source platform&apos;s Terms of Service and applicable
          copyright law.
        </span>
      </label>

      {error && <p className="text-sm text-red-600">{error}</p>}

      <button
        type="submit"
        disabled={submitting}
        className="self-start rounded-full bg-brand px-5 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-brand-hover disabled:opacity-50"
      >
        {submitting ? "Queuing…" : "Queue extraction"}
      </button>
    </form>
  );
}
