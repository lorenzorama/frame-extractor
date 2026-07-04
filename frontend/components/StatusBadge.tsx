// Minimal status chips. "Active" states (downloading/extracting) share a
// soft blue; done = green; failed = brand red; pending = neutral chip.
const STATUS_STYLES: Record<string, string> = {
  pending: "bg-chip text-muted",
  downloading: "bg-blue-50 text-blue-700",
  extracting: "bg-blue-50 text-blue-700",
  done: "bg-green-50 text-green-700",
  failed: "bg-red-50 text-brand",
};

export default function StatusBadge({ status }: { status: string }) {
  const style = STATUS_STYLES[status] || "bg-chip text-muted";
  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-1 text-xs font-medium ${style}`}>
      {status}
    </span>
  );
}
