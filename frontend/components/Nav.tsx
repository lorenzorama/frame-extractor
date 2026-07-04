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
