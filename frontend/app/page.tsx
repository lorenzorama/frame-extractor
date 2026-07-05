"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import Nav from "@/components/Nav";
import JobForm from "@/components/JobForm";
import StatusBadge from "@/components/StatusBadge";
import { listJobs, cancelJob, fetchJobZip, Job } from "@/lib/jobs";
import { resolveZipName, writeZipToDir, DirectoryHandle, AutoSaveBatch } from "@/lib/autosave";
import { getToken } from "@/lib/api";

export default function HomePage() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [loading, setLoading] = useState(true);
  const [autoSaveError, setAutoSaveError] = useState<string | null>(null);
  const router = useRouter();

  // jobId -> where/which name to save when it finishes. In a ref because handles
  // are not serializable and this must survive re-renders without triggering them.
  const pendingSaves = useRef<Map<number, { position: number; dir: DirectoryHandle }>>(new Map());
  // Jobs whose write is in flight, so overlapping polls don't start it twice.
  const savingIds = useRef<Set<number>>(new Set());

  const processAutoSaves = useCallback(async (current: Job[]) => {
    for (const job of current) {
      const entry = pendingSaves.current.get(job.id);
      if (!entry) continue;
      if (job.status === "failed") {
        pendingSaves.current.delete(job.id); // no file; its number is skipped
        continue;
      }
      if (job.status !== "done") continue;
      if (savingIds.current.has(job.id)) continue;
      savingIds.current.add(job.id);
      try {
        const blob = await fetchJobZip(job.id);
        const name = await resolveZipName(entry.dir, `video_${entry.position}`);
        await writeZipToDir(entry.dir, name, blob);
        pendingSaves.current.delete(job.id);
      } catch (err) {
        // Give up on this one, keep saving the rest of the batch.
        pendingSaves.current.delete(job.id);
        setAutoSaveError(
          `Couldn't save video_${entry.position}.zip — ${err instanceof Error ? err.message : "write failed"}`
        );
      } finally {
        savingIds.current.delete(job.id);
      }
    }
  }, []);

  const reload = useCallback(() => {
    listJobs()
      .then((current) => {
        setJobs(current);
        void processAutoSaves(current);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [processAutoSaves]);

  useEffect(() => {
    if (!getToken()) {
      router.push("/login");
      return;
    }
    reload();
    const timer = setInterval(reload, 3000);
    return () => clearInterval(timer);
  }, [router, reload]);

  function handleCreated(batch: AutoSaveBatch) {
    const dir = batch.dirHandle;
    if (dir) {
      batch.jobs.forEach((job, i) => {
        pendingSaves.current.set(job.id, { position: i + 1, dir });
      });
    }
    reload();
  }

  async function handleCancel(jobId: number) {
    try {
      await cancelJob(jobId);
      setJobs((prev) => prev.filter((j) => j.id !== jobId));
      pendingSaves.current.delete(jobId);
    } catch {
      // ignore; next poll will reconcile
    }
  }

  return (
    <>
      <Nav />
      <main className="mx-auto w-full max-w-3xl px-4 py-10">
        <header className="mb-6">
          <h1 className="text-2xl font-semibold tracking-tight text-ink">
            Extract frames from YouTube videos
          </h1>
          <p className="mt-1 text-sm text-muted">
            Paste one or more links (one per line). They&apos;re queued and processed one at a time.
          </p>
        </header>

        <section className="rounded-2xl border border-line bg-white p-6">
          <JobForm onCreated={handleCreated} />
        </section>

        {autoSaveError && (
          <p className="mt-4 text-sm text-red-600">{autoSaveError}</p>
        )}

        <section className="mt-10">
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-muted">Your jobs</h2>

          {loading && (
            <div className="flex flex-col gap-2">
              <div className="h-14 animate-pulse rounded-xl bg-chip" />
              <div className="h-14 animate-pulse rounded-xl bg-chip" />
              <div className="h-14 animate-pulse rounded-xl bg-chip" />
            </div>
          )}

          {!loading && jobs.length === 0 && (
            <div className="rounded-xl border border-dashed border-line px-4 py-10 text-center">
              <p className="text-sm text-muted">No jobs yet — paste a YouTube URL above to get started.</p>
            </div>
          )}

          {!loading && jobs.length > 0 && (
            <ul className="flex flex-col gap-2">
              {jobs.map((job) => (
                <li
                  key={job.id}
                  className="flex items-center justify-between gap-3 rounded-xl border border-line bg-white px-4 py-3"
                >
                  <Link href={`/jobs/${job.id}`} className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium text-ink">{job.youtube_url}</p>
                    <p className="mt-0.5 text-xs text-muted">Job #{job.id}</p>
                  </Link>
                  <div className="flex shrink-0 items-center gap-2">
                    <StatusBadge status={job.status} />
                    {job.status === "waiting" && (
                      <button
                        onClick={() => handleCancel(job.id)}
                        className="rounded-full border border-line px-3 py-1 text-xs font-medium text-muted transition-colors hover:bg-chip"
                      >
                        Cancel
                      </button>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>
      </main>
    </>
  );
}
