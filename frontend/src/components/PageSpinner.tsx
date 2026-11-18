import { Loader2Icon } from "lucide-react";

export function PageSpinner({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="flex items-center justify-center gap-2 py-24 text-muted-foreground">
      <Loader2Icon className="size-5 animate-spin" />
      {label}
    </div>
  );
}
