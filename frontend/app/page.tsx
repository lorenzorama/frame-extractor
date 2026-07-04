"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import JobForm from "@/components/JobForm";
import { listJobs, Job } from "@/lib/jobs";
import { getToken } from "@/lib/api";

export default function HomePage() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const router = useRouter();

  useEffect(() => {
    if (!getToken()) {
      router.push("/login");
      return;
    }
    listJobs().then(setJobs).catch(() => {});
  }, [router]);

  return (
    <main className="max-w-2xl mx-auto mt-12 px-4">
      <h1 className="text-xl font-semibold mb-6">New extraction job</h1>
      <JobForm onCreated={(jobId) => router.push(`/jobs/${jobId}`)} />

      <h2 className="text-lg font-semibold mt-10 mb-3">Your jobs</h2>
      <ul className="flex flex-col gap-2">
        {jobs.map((job) => (
          <li key={job.id}>
            <a href={`/jobs/${job.id}`} className="underline">
              #{job.id} — {job.youtube_url} — {job.status}
            </a>
          </li>
        ))}
      </ul>
    </main>
  );
}
