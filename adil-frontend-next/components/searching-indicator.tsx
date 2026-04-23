export default function SearchingIndicator() {
  return (
    <div className="flex items-center gap-2 text-gray-500 text-sm py-2">
      <span className="inline-block w-2 h-2 rounded-full bg-brand-500 animate-pulse" />
      <span>Searching UK legislation and case law…</span>
    </div>
  );
}
