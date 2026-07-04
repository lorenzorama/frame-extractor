import { apiFetch } from "@/lib/api";

export interface Job {
  id: number;
  youtube_url: string;
  status: "pending" | "downloading" | "extracting" | "done" | "failed";
  error_message: string | null;
  frames_total: number;
  frames_done: number;
  created_at: string;
}

export interface CreateJobInput {
  youtube_url: string;
  interval_seconds?: number;
  manual_timestamps?: number[];
}

export async function createJob(input: CreateJobInput): Promise<Job> {
  const res = await apiFetch("/jobs", { method: "POST", body: JSON.stringify(input) });
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: "Failed to create job" }));
    throw new Error(body.detail || "Failed to create job");
  }
  return res.json();
}

export async function listJobs(): Promise<Job[]> {
  const res = await apiFetch("/jobs");
  if (!res.ok) throw new Error("Failed to list jobs");
  return res.json();
}

export interface Frame {
  id: number;
  timestamp_seconds: number;
}

export async function listFrames(jobId: number): Promise<Frame[]> {
  const res = await apiFetch(`/jobs/${jobId}/frames`);
  if (!res.ok) throw new Error("Failed to list frames");
  return res.json();
}
