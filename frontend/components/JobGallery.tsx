"use client";

import { useEffect, useState } from "react";
import { listFrames, Frame } from "@/lib/jobs";
import { getToken } from "@/lib/api";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

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
      <button
        onClick={downloadZip}
        className="bg-indigo-600 text-white rounded px-3 py-2 mb-4 font-medium hover:bg-indigo-700"
      >
        Download all as ZIP
      </button>

      <div className="grid grid-cols-3 gap-3">
        {frames.map((frame, index) => (
          <button
            key={frame.id}
            onClick={() => setSelectedIndex(index)}
            className="flex flex-col items-center"
          >
            {imageUrls[frame.id] ? (
              <img
                src={imageUrls[frame.id]}
                alt={`Frame at ${frame.timestamp_seconds}s`}
                className="rounded"
              />
            ) : (
              <div className="bg-gray-200 w-full aspect-video rounded animate-pulse" />
            )}
            <span className="text-sm text-gray-600 mt-1">{frame.timestamp_seconds}s</span>
          </button>
        ))}
      </div>

      {selectedFrame && selectedIndex !== null && (
        <div
          className="fixed inset-0 bg-black/80 flex items-center justify-center z-50"
          onClick={() => setSelectedIndex(null)}
        >
          <button
            onClick={(e) => {
              e.stopPropagation();
              setSelectedIndex(null);
            }}
            className="absolute top-4 right-4 text-white text-2xl leading-none"
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
              className="absolute left-4 text-white text-3xl leading-none"
              aria-label="Previous frame"
            >
              &#8249;
            </button>
          )}

          <div
            className="flex flex-col items-center gap-4"
            onClick={(e) => e.stopPropagation()}
          >
            <img
              src={imageUrls[selectedFrame.id]}
              alt={`Frame at ${selectedFrame.timestamp_seconds}s`}
              className="max-h-[75vh] max-w-[85vw] rounded"
            />
            <button
              onClick={() => downloadFrame(selectedFrame)}
              className="bg-indigo-600 text-white rounded px-4 py-2 font-medium hover:bg-indigo-700"
            >
              Download
            </button>
          </div>

          {selectedIndex < frames.length - 1 && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                setSelectedIndex(selectedIndex + 1);
              }}
              className="absolute right-4 text-white text-3xl leading-none"
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
