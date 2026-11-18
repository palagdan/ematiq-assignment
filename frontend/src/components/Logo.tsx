import { BombIcon } from "lucide-react";
import { cn } from "@/lib/utils";

export function LogoMark({ className }: { className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex size-9 items-center justify-center rounded-lg bg-primary text-primary-foreground",
        className,
      )}
    >
      <BombIcon className="size-5" />
    </span>
  );
}

export function Logo() {
  return (
    <span className="flex items-center gap-2.5">
      <LogoMark />
      <span className="hidden text-base font-semibold tracking-tight whitespace-nowrap sm:inline">
        Lunch Roulette
      </span>
    </span>
  );
}
