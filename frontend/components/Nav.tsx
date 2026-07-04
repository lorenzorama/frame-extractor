"use client";

import { useEffect } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { getToken, logout } from "@/lib/api";

export default function Nav() {
  const router = useRouter();

  useEffect(() => {
    if (!getToken()) {
      router.push("/login");
    }
  }, [router]);

  function handleLogout() {
    logout();
    router.push("/login");
  }

  return (
    <nav className="sticky top-0 z-30 border-b border-line bg-white/95 backdrop-blur">
      <div className="mx-auto flex max-w-3xl items-center justify-between px-4 py-3">
        <Link href="/" className="flex items-center gap-2" aria-label="youtoframe home">
          <span className="flex h-6 w-9 items-center justify-center rounded-md bg-brand">
            <svg viewBox="0 0 24 24" className="h-3.5 w-3.5" aria-hidden="true">
              <path d="M8 5v14l11-7z" fill="#ffffff" />
            </svg>
          </span>
          <span className="text-lg font-semibold tracking-tight text-ink">youtoframe</span>
        </Link>
        <button
          onClick={handleLogout}
          className="rounded-full border border-line px-4 py-1.5 text-sm font-medium text-ink transition-colors hover:bg-chip"
        >
          Log out
        </button>
      </div>
    </nav>
  );
}
