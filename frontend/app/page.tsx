"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import Nav from "@/components/Nav";
import JobForm from "@/components/JobForm";
import StatusBadge from "@/components/StatusBadge";
import { listJobs, Job } from "@/lib/jobs";
import { getToken } from "@/lib/api";

export default function HomePage() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [loading, setLoading] = useState(true);
  const router = useRouter();

  useEffect(() => {
    if (!getToken()) {
      router.push("/login");
      return;
    }
    listJobs()
      .then(setJobs)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [router]);

  return (
    <>
      <Nav />
      <main className="mx-auto w-full max-w-3xl px-4 py-10">
        <header className="mb-6">
          <h1 className="text-2xl font-semibold tracking-tight text-ink">
            Extract frames from a YouTube video
          </h1>
          <p className="mt-1 text-sm text-muted">
            Paste a link, choose an interval or exact timestamps, and download the frames.
          </p>
        </header>

        <section className="rounded-2xl border border-line bg-white p-6">
          <JobForm onCreated={(jobId) => router.push(`/jobs/${jobId}`)} />
        </section>

        <section className="mt-10">
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-muted">
            Your jobs
          </h2>

          {loading && (
            <div className="flex flex-col gap-2">
              <div className="h-14 animate-pulse rounded-xl bg-chip" />
              <div className="h-14 animate-pulse rounded-xl bg-chip" />
              <div className="h-14 animate-pulse rounded-xl bg-chip" />
            </div>
          )}

          {!loading && jobs.length === 0 && (
            <div className="rounded-xl border border-dashed border-line px-4 py-10 text-center">
              <p className="text-sm text-muted">
                No jobs yet — submit a YouTube URL above to get started.
              </p>
            </div>
          )}

          {!loading && jobs.length > 0 && (
            <ul className="flex flex-col gap-2">
              {jobs.map((job) => (
                <li key={job.id}>
                  <Link
                    href={`/jobs/${job.id}`}
                    className="flex items-center justify-between gap-3 rounded-xl border border-line bg-white px-4 py-3 transition-colors hover:bg-surface"
                  >
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium text-ink">{job.youtube_url}</p>
                      <p className="mt-0.5 text-xs text-muted">Job #{job.id}</p>
                    </div>
                    <StatusBadge status={job.status} />
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </section>
      </main>
    </>
  );
}
