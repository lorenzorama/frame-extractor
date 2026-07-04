"use client";

import { useEffect, useState } from "react";
import { listFrames, Frame } from "@/lib/jobs";
import { getToken } from "@/lib/api";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function JobGallery({ jobId }: { jobId: number }) {
  const [frames, setFrames] = useState<Frame[]>([]);
  const [imageUrls, setImageUrls] = useState<Record<number, string>>({});

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

  return (
    <div>
      <button onClick={downloadZip} className="bg-black text-white rounded px-3 py-2 mb-4">
        Download all as ZIP
      </button>
      <div className="grid grid-cols-3 gap-3">
        {frames.map((frame) => (
          <div key={frame.id} className="flex flex-col items-center">
            {imageUrls[frame.id] ? (
              <img src={imageUrls[frame.id]} alt={`Frame at ${frame.timestamp_seconds}s`} className="rounded" />
            ) : (
              <div className="bg-gray-200 w-full aspect-video rounded animate-pulse" />
            )}
            <a href={imageUrls[frame.id]} download={`${frame.timestamp_seconds}.jpg`} className="text-sm underline mt-1">
              {frame.timestamp_seconds}s
            </a>
          </div>
        ))}
      </div>
    </div>
  );
}
