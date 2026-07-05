import { apiFetch } from "@/lib/api";

export interface Job {
  id: number;
  youtube_url: string;
  status: "waiting" | "pending" | "downloading" | "extracting" | "transcribing" | "done" | "failed";
  error_message: string | null;
  frames_total: number;
  frames_done: number;
  created_at: string;
}

export interface CreateJobsInput {
  youtube_urls: string[];
  interval_seconds?: number;
  manual_timestamps?: number[];
}

export async function createJobs(input: CreateJobsInput): Promise<Job[]> {
  const res = await apiFetch("/jobs", { method: "POST", body: JSON.stringify(input) });
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: "Failed to create jobs" }));
    throw new Error(body.detail || "Failed to create jobs");
  }
  return res.json();
}

export async function cancelJob(jobId: number): Promise<void> {
  const res = await apiFetch(`/jobs/${jobId}`, { method: "DELETE" });
  if (!res.ok) throw new Error("Failed to cancel job");
}

export async function listJobs(): Promise<Job[]> {
  const res = await apiFetch("/jobs");
  if (!res.ok) throw new Error("Failed to list jobs");
  return res.json();
}

export async function fetchJobZip(jobId: number): Promise<Blob> {
  const res = await apiFetch(`/jobs/${jobId}/zip`);
  if (!res.ok) throw new Error("Failed to fetch zip");
  return res.blob();
}

export interface Frame {
  id: number;
  timestamp_seconds: number;
  caption: string | null;
}

export interface TranscriptCue {
  start_seconds: number;
  end_seconds: number;
  text: string;
}

export interface Transcript {
  language: string | null;
  source: string | null;
  cues: TranscriptCue[];
}

export async function listFrames(jobId: number): Promise<Frame[]> {
  const res = await apiFetch(`/jobs/${jobId}/frames`);
  if (!res.ok) throw new Error("Failed to list frames");
  return res.json();
}

export async function getTranscript(jobId: number): Promise<Transcript> {
  const res = await apiFetch(`/jobs/${jobId}/transcript`);
  if (!res.ok) throw new Error("Failed to load transcript");
  return res.json();
}
