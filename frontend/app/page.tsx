"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
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
      <main className="max-w-2xl mx-auto mt-12 px-4">
        <h1 className="text-xl font-semibold mb-6 text-gray-900">New extraction job</h1>
        <JobForm onCreated={(jobId) => router.push(`/jobs/${jobId}`)} />

        <h2 className="text-lg font-semibold mt-10 mb-3 text-gray-900">Your jobs</h2>

        {loading && (
          <div className="flex flex-col gap-2">
            <div className="h-10 bg-gray-100 rounded animate-pulse" />
            <div className="h-10 bg-gray-100 rounded animate-pulse" />
            <div className="h-10 bg-gray-100 rounded animate-pulse" />
          </div>
        )}

        {!loading && jobs.length === 0 && (
          <p className="text-sm text-gray-500">
            No jobs yet — submit a YouTube URL above to get started.
          </p>
        )}

        {!loading && jobs.length > 0 && (
          <ul className="flex flex-col gap-2">
            {jobs.map((job) => (
              <li key={job.id}>
                <a
                  href={`/jobs/${job.id}`}
                  className="flex items-center justify-between border border-gray-200 rounded px-3 py-2 hover:bg-gray-50"
                >
                  <span className="text-sm text-gray-700">
                    #{job.id} — {job.youtube_url}
                  </span>
                  <StatusBadge status={job.status} />
                </a>
              </li>
            ))}
          </ul>
        )}
      </main>
    </>
  );
}
