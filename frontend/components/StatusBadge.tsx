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
