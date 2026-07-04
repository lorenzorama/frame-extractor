const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("access_token");
}

export async function apiFetch(path: string, options: RequestInit = {}): Promise<Response> {
  const token = getToken();
  const headers = new Headers(options.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (options.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  return fetch(`${API_URL}${path}`, { ...options, headers });
}

async function authRequest(path: string, email: string, password: string): Promise<void> {
  const res = await apiFetch(path, {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: "Request failed" }));
    throw new Error(body.detail || "Request failed");
  }
  const data = await res.json();
  localStorage.setItem("access_token", data.access_token);
}

export function login(email: string, password: string): Promise<void> {
  return authRequest("/auth/login", email, password);
}

export function signup(email: string, password: string): Promise<void> {
  return authRequest("/auth/signup", email, password);
}
