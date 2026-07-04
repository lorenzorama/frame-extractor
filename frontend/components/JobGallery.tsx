"use client";

import { useEffect, useState } from "react";
import { listFrames, Frame } from "@/lib/jobs";
import { getToken } from "@/lib/api";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

function formatTime(seconds: number): string {
  const total = Math.floor(seconds);
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${m}:${s.toString().padStart(2, "0")}`;
}

export default function JobGallery({ jobId }: { jobId: number }) {
  const [frames, setFrames] = useState<Frame[]>([]);
  const [imageUrls, setImageUrls] = useState<Record<number, string>>({});
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null);

  useEffect(() => {
    listFrames(jobId).then(setFrames).catch(() => {});
  }, [jobId]);

  useEffect(() => {
    const token = getToken();
    let cancelled = false;
    const urls: Record<number, string> = {};

    Promise.all(
      frames.map(async (frame) => {
        const res = await fetch(`${API_URL}/frames/${frame.id}/image`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        const blob = await res.blob();
        urls[frame.id] = URL.createObjectURL(blob);
      })
    ).then(() => {
      if (!cancelled) setImageUrls(urls);
    });

    return () => {
      cancelled = true;
      Object.values(urls).forEach(URL.revokeObjectURL);
    };
  }, [frames]);

  // Keyboard controls for the lightbox: Escape to close, arrows to navigate.
  useEffect(() => {
    if (selectedIndex === null) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setSelectedIndex(null);
      else if (e.key === "ArrowLeft") setSelectedIndex((i) => (i !== null && i > 0 ? i - 1 : i));
      else if (e.key === "ArrowRight")
        setSelectedIndex((i) => (i !== null && i < frames.length - 1 ? i + 1 : i));
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [selectedIndex, frames.length]);

  async function downloadZip() {
    const token = getToken();
    const res = await fetch(`${API_URL}/jobs/${jobId}/zip`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `job_${jobId}_frames.zip`;
    a.click();
    URL.revokeObjectURL(url);
  }

  function downloadFrame(frame: Frame) {
    const url = imageUrls[frame.id];
    if (!url) return;
    const a = document.createElement("a");
    a.href = url;
    a.download = `${frame.timestamp_seconds}.jpg`;
    a.click();
  }

  const selectedFrame = selectedIndex !== null ? frames[selectedIndex] : null;

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <p className="text-sm text-muted">
          {frames.length} frame{frames.length === 1 ? "" : "s"}
        </p>
        <button
          onClick={downloadZip}
          className="rounded-full bg-brand px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-brand-hover"
        >
          Download all as ZIP
        </button>
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        {frames.map((frame, index) => (
          <button
            key={frame.id}
            onClick={() => setSelectedIndex(index)}
            className="group relative overflow-hidden rounded-xl border border-line bg-chip"
          >
            {imageUrls[frame.id] ? (
              <img
                src={imageUrls[frame.id]}
                alt={`Frame at ${frame.timestamp_seconds}s`}
                className="aspect-video w-full object-cover transition-transform duration-200 group-hover:scale-[1.03]"
              />
            ) : (
              <div className="aspect-video w-full animate-pulse bg-chip" />
            )}
            <span className="absolute bottom-1.5 right-1.5 rounded bg-black/80 px-1.5 py-0.5 text-[11px] font-medium text-white">
              {formatTime(frame.timestamp_seconds)}
            </span>
          </button>
        ))}
      </div>

      {selectedFrame && selectedIndex !== null && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/90 p-4"
          onClick={() => setSelectedIndex(null)}
        >
          <button
            onClick={(e) => {
              e.stopPropagation();
              setSelectedIndex(null);
            }}
            className="absolute right-4 top-4 flex h-10 w-10 items-center justify-center rounded-full bg-white/10 text-2xl leading-none text-white transition-colors hover:bg-white/20"
            aria-label="Close"
          >
            &times;
          </button>

          {selectedIndex > 0 && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                setSelectedIndex(selectedIndex - 1);
              }}
              className="absolute left-4 flex h-11 w-11 items-center justify-center rounded-full bg-white/10 text-3xl leading-none text-white transition-colors hover:bg-white/20"
              aria-label="Previous frame"
            >
              &#8249;
            </button>
          )}

          <div className="flex flex-col items-center gap-4" onClick={(e) => e.stopPropagation()}>
            <img
              src={imageUrls[selectedFrame.id]}
              alt={`Frame at ${selectedFrame.timestamp_seconds}s`}
              className="max-h-[75vh] max-w-[85vw] rounded-lg"
            />
            <div className="flex items-center gap-4">
              <span className="text-sm text-white/70">
                {formatTime(selectedFrame.timestamp_seconds)} · {selectedFrame.timestamp_seconds}s
              </span>
              <button
                onClick={() => downloadFrame(selectedFrame)}
                className="rounded-full bg-brand px-5 py-2 text-sm font-semibold text-white transition-colors hover:bg-brand-hover"
              >
                Download
              </button>
            </div>
          </div>

          {selectedIndex < frames.length - 1 && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                setSelectedIndex(selectedIndex + 1);
              }}
              className="absolute right-4 flex h-11 w-11 items-center justify-center rounded-full bg-white/10 text-3xl leading-none text-white transition-colors hover:bg-white/20"
              aria-label="Next frame"
            >
              &#8250;
            </button>
          )}
        </div>
      )}
    </div>
  );
}
