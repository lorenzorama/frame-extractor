"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { login } from "@/lib/api";

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const router = useRouter();

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login(email, password);
      router.push("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-surface px-4">
      <div className="w-full max-w-sm rounded-2xl border border-line bg-white p-8">
        <div className="mb-6 flex items-center gap-2">
          <span className="flex h-6 w-9 items-center justify-center rounded-md bg-brand">
            <svg viewBox="0 0 24 24" className="h-3.5 w-3.5" aria-hidden="true">
              <path d="M8 5v14l11-7z" fill="#ffffff" />
            </svg>
          </span>
          <span className="text-lg font-semibold tracking-tight text-ink">youtoframe</span>
        </div>

        <h1 className="mb-1 text-xl font-semibold text-ink">Log in</h1>
        <p className="mb-6 text-sm text-muted">Welcome back — extract frames in seconds.</p>

        <form onSubmit={handleSubmit} className="flex flex-col gap-3">
          <input
            type="email"
            placeholder="Email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="rounded-lg border border-line px-3 py-2.5 text-sm text-ink outline-none transition-colors placeholder:text-muted focus:border-ink"
            required
          />
          <input
            type="password"
            placeholder="Password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="rounded-lg border border-line px-3 py-2.5 text-sm text-ink outline-none transition-colors placeholder:text-muted focus:border-ink"
            required
          />
          {error && <p className="text-sm text-brand">{error}</p>}
          <button
            type="submit"
            disabled={submitting}
            className="mt-1 rounded-full bg-brand px-4 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-brand-hover disabled:opacity-50"
          >
            {submitting ? "Logging in…" : "Log in"}
          </button>
        </form>

        <p className="mt-6 text-center text-sm text-muted">
          Don&apos;t have an account?{" "}
          <Link href="/signup" className="font-medium text-brand hover:underline">
            Sign up
          </Link>
        </p>
      </div>
    </main>
  );
}
