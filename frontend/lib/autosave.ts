import { Job } from "@/lib/jobs";

// Minimal structural subset of the File System Access API we use. The project's
// TS lib config does not include these types, so we declare just what we call.
export interface WritableFileStream {
  write(data: Blob): Promise<void>;
  close(): Promise<void>;
}

export interface FileHandle {
  createWritable(): Promise<WritableFileStream>;
}

export interface DirectoryHandle {
  getFileHandle(name: string, options?: { create?: boolean }): Promise<FileHandle>;
}

declare global {
  interface Window {
    showDirectoryPicker?: (options?: { mode?: "read" | "readwrite" }) => Promise<DirectoryHandle>;
  }
}

// A batch of jobs created together, plus the folder chosen for auto-saving them
// (null when auto-save was off or unsupported).
export interface AutoSaveBatch {
  jobs: Job[];
  dirHandle: DirectoryHandle | null;
}

// True only where the File System Access API exists (Chrome/Edge).
export function isAutoSaveSupported(): boolean {
  return typeof window !== "undefined" && typeof window.showDirectoryPicker === "function";
}

// Opens the native folder chooser. Returns the granted handle, or null if the
// user dismissed the dialog (AbortError). Any other error propagates.
export async function pickDirectory(): Promise<DirectoryHandle | null> {
  if (!window.showDirectoryPicker) return null;
  try {
    return await window.showDirectoryPicker({ mode: "readwrite" });
  } catch (err) {
    if (err && (err as { name?: string }).name === "AbortError") return null;
    throw err;
  }
}

async function fileExists(dir: DirectoryHandle, name: string): Promise<boolean> {
  try {
    await dir.getFileHandle(name);
    return true;
  } catch (err) {
    if (err && (err as { name?: string }).name === "NotFoundError") return false;
    throw err;
  }
}

// Resolves a non-colliding "<base>.zip" name in dir: "<base>.zip", else
// "<base> (2).zip", "<base> (3).zip", ... Probes with getFileHandle (no create),
// treating NotFoundError as "free".
export async function resolveZipName(dir: DirectoryHandle, base: string): Promise<string> {
  for (let i = 1; ; i++) {
    const name = i === 1 ? `${base}.zip` : `${base} (${i}).zip`;
    if (!(await fileExists(dir, name))) return name;
  }
}

// Writes blob into dir under name. The caller passes a name already resolved to
// be collision-free (see resolveZipName).
export async function writeZipToDir(dir: DirectoryHandle, name: string, blob: Blob): Promise<void> {
  const handle = await dir.getFileHandle(name, { create: true });
  const writable = await handle.createWritable();
  await writable.write(blob);
  await writable.close();
}
