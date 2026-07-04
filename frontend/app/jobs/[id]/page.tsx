"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
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
      <main className="max-w-2xl mx-auto mt-12 px-4">
        <h1 className="text-xl font-semibold mb-6 text-gray-900">Job #{jobId}</h1>
        {!done && <JobProgress jobId={jobId} onDone={() => setDone(true)} />}
        {done && <JobGallery jobId={jobId} />}
      </main>
    </>
  );
}
