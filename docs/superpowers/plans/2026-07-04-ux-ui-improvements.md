# UX/UI Improvements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the existing youtoframe frontend a consistent clean/minimal visual layer (indigo accent) and close specific UX gaps: shared nav with logout, cross-linked auth pages, status badges + empty/loading states on the job list, a real progress bar, and a gallery lightbox.

**Architecture:** Frontend-only changes to the existing Next.js app (`frontend/`). No backend/API changes — all pages continue to consume the existing `lib/api.ts`/`lib/jobs.ts` functions and data shapes exactly as they are today. Each task is a small, independently buildable UI change.

**Tech Stack:** Next.js (App Router, TypeScript), React, Tailwind CSS (utility classes only — no new UI library).

## Global Constraints

- Accent color is indigo: `bg-indigo-600` / `hover:bg-indigo-700` / `text-indigo-600` / `focus:ring-indigo-500` (Tailwind's default indigo palette) — used for all primary buttons, links, and the progress bar fill.
- Status colors: `pending` = gray, `downloading`/`extracting` = indigo, `done` = green, `failed` = red.
- No backend/API changes. No new npm dependencies (icon libraries, UI kits, etc.) — plain Tailwind + hand-written components only.
- Every task must pass `npm run build` and `npm run lint` cleanly (matching the verification bar used in prior frontend tasks in this project).
- No automated component tests are required for this plan (consistent with how Tasks 9-12 of the original implementation were verified) — verification is `npm run build`/`npm run lint` plus a manual dev-server walkthrough per task.

---

## File Structure

```
frontend/
  lib/
    api.ts                  # MODIFY: add logout()
  components/
    Nav.tsx                 # CREATE: shared top nav (logo + logout)
    StatusBadge.tsx          # CREATE: colored status pill
    JobForm.tsx               # MODIFY: indigo accent styling only
    JobProgress.tsx             # MODIFY: progress bar + styled failure box
    JobGallery.tsx                # MODIFY: lightbox modal on thumbnail click
  app/
    login/page.tsx                # MODIFY: card styling + link to /signup
    signup/page.tsx                  # MODIFY: card styling + link to /login
    page.tsx                          # MODIFY: <Nav/>, status badges, empty/loading states
    jobs/[id]/page.tsx                  # MODIFY: <Nav/>
```

---

## Task 1: `logout()` helper + shared Nav component

**Files:**
- Modify: `frontend/lib/api.ts`
- Create: `frontend/components/Nav.tsx`
- Modify: `frontend/app/page.tsx`
- Modify: `frontend/app/jobs/[id]/page.tsx`

**Interfaces:**
- Produces: `logout(): void` (exported from `lib/api.ts`) and `<Nav />` (default export from `components/Nav.tsx`, no props). Both consumed by every later task that touches `app/page.tsx` or `app/jobs/[id]/page.tsx`.

- [ ] **Step 1: Add `logout()` to `frontend/lib/api.ts`**

Append this function at the end of the file:

```typescript
export function logout(): void {
  localStorage.removeItem("access_token");
}
```

- [ ] **Step 2: Create `frontend/components/Nav.tsx`**

```tsx
"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { logout } from "@/lib/api";

export default function Nav() {
  const router = useRouter();

  function handleLogout() {
    logout();
    router.push("/login");
  }

  return (
    <nav className="border-b border-gray-200 bg-white">
      <div className="max-w-2xl mx-auto px-4 py-3 flex items-center justify-between">
        <Link href="/" className="font-bold text-indigo-600">
          youtoframe
        </Link>
        <button
          onClick={handleLogout}
          className="text-sm text-gray-700 border border-gray-200 rounded px-3 py-1.5 hover:bg-gray-50"
        >
          Log out
        </button>
      </div>
    </nav>
  );
}
```

- [ ] **Step 3: Wire `<Nav />` into `frontend/app/page.tsx`**

Replace the file's return statement (the `HomePage` component's JSX) so the page renders `<Nav />` above the existing `<main>` block. The rest of the component (state, `useEffect`, `JobForm`, job list) stays exactly as-is for this task — only the import and the outer JSX wrapper change:

```tsx
"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Nav from "@/components/Nav";
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
    <>
      <Nav />
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
    </>
  );
}
```

(Status badges, empty/loading states, and further restyling of this page land in Task 3 — this task only adds the nav.)

- [ ] **Step 4: Wire `<Nav />` into `frontend/app/jobs/[id]/page.tsx`**

```tsx
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
        <h1 className="text-xl font-semibold mb-6">Job #{jobId}</h1>
        {!done && <JobProgress jobId={jobId} onDone={() => setDone(true)} />}
        {done && <JobGallery jobId={jobId} />}
      </main>
    </>
  );
}
```

- [ ] **Step 5: Verify build and lint**

Run: `cd frontend && npm run build`
Expected: builds successfully, no type errors.

Run: `npm run lint`
Expected: no errors.

- [ ] **Step 6: Manual verification**

Run `npm run dev` (with the backend also running). Log in, confirm the nav bar appears on `/` with the "youtoframe" logo and a "Log out" button. Click "Log out", confirm you're redirected to `/login` and that reloading `/` also redirects to `/login` (token cleared). Log back in, open a job's detail page, confirm the nav bar appears there too.

- [ ] **Step 7: Commit**

```bash
git add frontend/lib/api.ts frontend/components/Nav.tsx frontend/app/page.tsx frontend/app/jobs/\[id\]/page.tsx
git commit -m "feat: add shared nav bar with logout"
```

---

## Task 2: Auth page restyle + cross-links

**Files:**
- Modify: `frontend/app/login/page.tsx`
- Modify: `frontend/app/signup/page.tsx`

**Interfaces:**
- None — this task only restyles two existing pages and adds a `<Link>` between them. No new exports consumed elsewhere.

- [ ] **Step 1: Rewrite `frontend/app/login/page.tsx`**

```tsx
"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { login } from "@/lib/api";

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const router = useRouter();

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await login(email, password);
      router.push("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    }
  }

  return (
    <main className="min-h-screen flex items-center justify-center bg-gray-50 px-4">
      <div className="w-full max-w-sm bg-white border border-gray-200 rounded-lg shadow-sm p-8">
        <h1 className="text-xl font-semibold mb-6 text-gray-900">Log in</h1>
        <form onSubmit={handleSubmit} className="flex flex-col gap-3">
          <input
            type="email"
            placeholder="Email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="border border-gray-300 rounded px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-500"
            required
          />
          <input
            type="password"
            placeholder="Password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="border border-gray-300 rounded px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-500"
            required
          />
          {error && <p className="text-red-600 text-sm">{error}</p>}
          <button
            type="submit"
            className="bg-indigo-600 text-white rounded px-3 py-2 font-medium hover:bg-indigo-700"
          >
            Log in
          </button>
        </form>
        <p className="text-sm text-gray-600 mt-4 text-center">
          Don&apos;t have an account?{" "}
          <Link href="/signup" className="text-indigo-600 hover:underline">
            Sign up
          </Link>
        </p>
      </div>
    </main>
  );
}
```

- [ ] **Step 2: Rewrite `frontend/app/signup/page.tsx`**

```tsx
"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { signup } from "@/lib/api";

export default function SignupPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const router = useRouter();

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await signup(email, password);
      router.push("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Signup failed");
    }
  }

  return (
    <main className="min-h-screen flex items-center justify-center bg-gray-50 px-4">
      <div className="w-full max-w-sm bg-white border border-gray-200 rounded-lg shadow-sm p-8">
        <h1 className="text-xl font-semibold mb-6 text-gray-900">Sign up</h1>
        <form onSubmit={handleSubmit} className="flex flex-col gap-3">
          <input
            type="email"
            placeholder="Email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="border border-gray-300 rounded px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-500"
            required
          />
          <input
            type="password"
            placeholder="Password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="border border-gray-300 rounded px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-500"
            required
          />
          {error && <p className="text-red-600 text-sm">{error}</p>}
          <button
            type="submit"
            className="bg-indigo-600 text-white rounded px-3 py-2 font-medium hover:bg-indigo-700"
          >
            Sign up
          </button>
        </form>
        <p className="text-sm text-gray-600 mt-4 text-center">
          Already have an account?{" "}
          <Link href="/login" className="text-indigo-600 hover:underline">
            Log in
          </Link>
        </p>
      </div>
    </main>
  );
}
```

- [ ] **Step 3: Verify build and lint**

Run: `cd frontend && npm run build`
Expected: builds successfully, no type errors.

Run: `npm run lint`
Expected: no errors.

- [ ] **Step 4: Manual verification**

Run `npm run dev`. Open `/login`, confirm the card layout and the "Sign up" link at the bottom navigates to `/signup`. On `/signup`, confirm the "Log in" link navigates back to `/login`. Confirm both forms still submit correctly (sign up a new test account, then log in with it).

- [ ] **Step 5: Commit**

```bash
git add frontend/app/login/page.tsx frontend/app/signup/page.tsx
git commit -m "feat: restyle auth pages and add login/signup cross-links"
```

---

## Task 3: Status badges + empty/loading states + JobForm styling

**Files:**
- Create: `frontend/components/StatusBadge.tsx`
- Modify: `frontend/app/page.tsx`
- Modify: `frontend/components/JobForm.tsx`

**Interfaces:**
- Consumes: `Job` type from `lib/jobs.ts` (Task 1 already wired `<Nav/>` into this page — this task builds on that).
- Produces: `<StatusBadge status={string} />` (default export from `components/StatusBadge.tsx`), used only on the home page in this plan but reusable for any future job-status display.

- [ ] **Step 1: Create `frontend/components/StatusBadge.tsx`**

```tsx
const STATUS_STYLES: Record<string, string> = {
  pending: "bg-gray-100 text-gray-600",
  downloading: "bg-indigo-100 text-indigo-700",
  extracting: "bg-indigo-100 text-indigo-700",
  done: "bg-green-100 text-green-700",
  failed: "bg-red-100 text-red-700",
};

export default function StatusBadge({ status }: { status: string }) {
  const style = STATUS_STYLES[status] || "bg-gray-100 text-gray-600";
  return (
    <span className={`inline-block rounded-full px-3 py-1 text-xs font-semibold ${style}`}>
      {status}
    </span>
  );
}
```

- [ ] **Step 2: Rewrite `frontend/app/page.tsx`**

```tsx
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
```

- [ ] **Step 3: Restyle `frontend/components/JobForm.tsx`**

Update only the `className` values on the inputs and the submit button (logic/state/handlers unchanged):

```tsx
"use client";

import { useState } from "react";
import { createJob } from "@/lib/jobs";

export default function JobForm({ onCreated }: { onCreated: (jobId: number) => void }) {
  const [url, setUrl] = useState("");
  const [interval, setInterval_] = useState("5");
  const [timestamps, setTimestamps] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const manual = timestamps
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean)
        .map(Number)
        .filter((n) => !Number.isNaN(n));
      const job = await createJob({
        youtube_url: url,
        interval_seconds: interval ? Number(interval) : undefined,
        manual_timestamps: manual.length ? manual : undefined,
      });
      onCreated(job.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create job");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-3 max-w-md">
      <input
        placeholder="YouTube URL"
        value={url}
        onChange={(e) => setUrl(e.target.value)}
        className="border border-gray-300 rounded px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-500"
        required
      />
      <input
        placeholder="Interval seconds (e.g. 5)"
        value={interval}
        onChange={(e) => setInterval_(e.target.value)}
        className="border border-gray-300 rounded px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-500"
      />
      <input
        placeholder="Manual timestamps, comma-separated (e.g. 12.5, 30)"
        value={timestamps}
        onChange={(e) => setTimestamps(e.target.value)}
        className="border border-gray-300 rounded px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-500"
      />
      {error && <p className="text-red-600 text-sm">{error}</p>}
      <button
        type="submit"
        disabled={submitting}
        className="bg-indigo-600 text-white rounded px-3 py-2 font-medium hover:bg-indigo-700 disabled:opacity-50"
      >
        {submitting ? "Submitting..." : "Extract frames"}
      </button>
    </form>
  );
}
```

- [ ] **Step 4: Verify build and lint**

Run: `cd frontend && npm run build`
Expected: builds successfully, no type errors.

Run: `npm run lint`
Expected: no errors.

- [ ] **Step 5: Manual verification**

Run `npm run dev`. On `/`, confirm the loading skeleton briefly appears while jobs load, then either the empty-state message (if you have no jobs) or a list with color-coded status badges (gray/indigo/green/red matching each job's actual status). Submit a new job and confirm it appears in the list with a `pending` (gray) badge.

- [ ] **Step 6: Commit**

```bash
git add frontend/components/StatusBadge.tsx frontend/app/page.tsx frontend/components/JobForm.tsx
git commit -m "feat: add status badges and empty/loading states to job list"
```

---

## Task 4: Progress bar on job detail page

**Files:**
- Modify: `frontend/components/JobProgress.tsx`

**Interfaces:**
- No change to the component's props (`{ jobId: number; onDone: () => void }`) — `app/jobs/[id]/page.tsx` (already wired in Task 1) needs no changes for this task.

- [ ] **Step 1: Rewrite `frontend/components/JobProgress.tsx`**

```tsx
"use client";

import { useEffect, useState } from "react";
import { getToken } from "@/lib/api";

interface StreamEvent {
  status: string;
  frames_done: number;
  frames_total: number;
  error: string | null;
}

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function JobProgress({ jobId, onDone }: { jobId: number; onDone: () => void }) {
  const [event, setEvent] = useState<StreamEvent | null>(null);

  useEffect(() => {
    const token = getToken();
    const source = new EventSource(`${API_URL}/jobs/${jobId}/stream?token=${token}`);

    source.onmessage = (e) => {
      const data: StreamEvent = JSON.parse(e.data);
      setEvent(data);
      if (data.status === "done") {
        source.close();
        onDone();
      } else if (data.status === "failed") {
        source.close();
      }
    };

    return () => source.close();
  }, [jobId, onDone]);

  if (!event) {
    return <p className="text-sm text-gray-500">Connecting...</p>;
  }

  if (event.status === "failed") {
    return (
      <div className="bg-red-50 border border-red-200 text-red-700 rounded px-4 py-3 text-sm">
        <p className="font-semibold mb-1">Failed</p>
        <p>{event.error}</p>
      </div>
    );
  }

  const percent =
    event.frames_total > 0
      ? Math.min(100, Math.round((event.frames_done / event.frames_total) * 100))
      : 0;

  return (
    <div>
      <div className="flex justify-between items-center mb-2 text-sm text-gray-700">
        <span className="capitalize">{event.status}&hellip;</span>
        <span className="text-gray-500">
          {event.frames_done} / {event.frames_total}
        </span>
      </div>
      <div className="bg-gray-100 rounded-full h-2 overflow-hidden">
        <div
          className="bg-indigo-600 h-full rounded-full transition-all"
          style={{ width: `${percent}%` }}
        />
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Verify build and lint**

Run: `cd frontend && npm run build`
Expected: builds successfully, no type errors.

Run: `npm run lint`
Expected: no errors.

- [ ] **Step 3: Manual verification**

Run `npm run dev` with the backend running. Submit a job and open its detail page. Confirm the progress bar fills as `frames_done` increases (watch the SSE-driven updates) and reaches 100% width right as the page transitions to the gallery. Submit a job that will fail (e.g. an invalid/unreachable URL) and confirm the red failure box shows the real error message instead of a bar.

- [ ] **Step 4: Commit**

```bash
git add frontend/components/JobProgress.tsx
git commit -m "feat: add progress bar to job detail page"
```

---

## Task 5: Gallery lightbox

**Files:**
- Modify: `frontend/components/JobGallery.tsx`

**Interfaces:**
- No change to the component's props (`{ jobId: number }`) — `app/jobs/[id]/page.tsx` needs no changes for this task.

- [ ] **Step 1: Rewrite `frontend/components/JobGallery.tsx`**

```tsx
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
```

- [ ] **Step 2: Verify build and lint**

Run: `cd frontend && npm run build`
Expected: builds successfully, no type errors.

Run: `npm run lint`
Expected: no errors (the existing `@next/next/no-img-element` warning on the `<img>` tags is expected/accepted, same as in the original implementation, since the images are runtime blob URLs).

- [ ] **Step 3: Manual verification**

Run `npm run dev` with the backend running, open a completed job's gallery. Click a thumbnail — confirm a full-size lightbox opens over a dark overlay. Click the prev/next arrows and confirm navigation between frames without closing the modal (arrows disappear at the first/last frame). Click "Download" inside the modal and confirm the single frame downloads. Click the `×` (or click outside the image) and confirm the modal closes. Confirm "Download all as ZIP" still works from the grid view.

- [ ] **Step 4: Commit**

```bash
git add frontend/components/JobGallery.tsx
git commit -m "feat: add lightbox modal to frame gallery"
```

---

## Task 6: Full manual walkthrough

**Files:**
- None — this task is verification-only, tying together Tasks 1-5.

- [ ] **Step 1: Run the full stack**

Ensure the backend is up (`docker compose up --build` from the repo root, plus `docker compose exec api alembic upgrade head` if not already applied), then `cd frontend && npm run dev`.

- [ ] **Step 2: Walk through the full flow end-to-end**

1. Visit `/login` with no account — click through to `/signup`, create an account, confirm redirect to `/` with the nav bar visible.
2. On `/`, confirm the empty-state message, submit a job, confirm it appears in the list with a `pending` badge.
3. Open the job — confirm the progress bar animates as it processes.
4. On completion, confirm the gallery renders, the lightbox opens/closes/navigates correctly, and both single-frame and zip downloads work.
5. Click "Log out" in the nav — confirm redirect to `/login` and that `/` now redirects back to `/login` when visited directly.
6. Log back in with the same account — confirm the previously created job still appears in the list with its final (`done` or `failed`) badge.

- [ ] **Step 3: Final build/lint check**

Run: `cd frontend && npm run build && npm run lint`
Expected: both succeed cleanly with no errors.

- [ ] **Step 4: Commit (if any final tweaks were needed)**

```bash
git add -A
git commit -m "chore: final UX/UI walkthrough fixes" --allow-empty
```

(Use `--allow-empty` only if the walkthrough needed no code changes — otherwise omit it and let the commit carry the actual diff.)
