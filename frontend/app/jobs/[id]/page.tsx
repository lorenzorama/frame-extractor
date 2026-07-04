"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import Nav from "@/components/Nav";
import JobProgress from "@/components/JobProgress";
import JobGallery from "@/components/JobGallery";

export default function JobPage() {
  const params = useParams();
  const jobId = Number(params.id);
  const [done, setDone] = useState(false);

  return (
    <>
      <Nav />
      <main className="mx-auto w-full max-w-3xl px-4 py-10">
        <Link
          href="/"
          className="mb-6 inline-flex items-center gap-1 text-sm text-muted transition-colors hover:text-ink"
        >
          <span aria-hidden="true">&#8249;</span> All jobs
        </Link>

        <h1 className="mb-6 text-2xl font-semibold tracking-tight text-ink">Job #{jobId}</h1>

        {!done && <JobProgress jobId={jobId} onDone={() => setDone(true)} />}
        {done && <JobGallery jobId={jobId} />}
      </main>
    </>
  );
}
