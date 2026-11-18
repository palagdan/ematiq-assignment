import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { cn } from "@/lib/utils";

const TONES = [
  "bg-primary text-primary-foreground",
  "bg-safe text-safe-foreground",
  "bg-sky text-[#0b3550]",
  "bg-steel text-white",
];

function tone(name: string): string {
  let hash = 0;
  for (const char of name) hash = (hash * 31 + char.charCodeAt(0)) >>> 0;
  return TONES[hash % TONES.length]!;
}

export function PlayerAvatar({ name, className }: { name: string; className?: string }) {
  return (
    <Avatar className={cn("size-8", className)}>
      <AvatarFallback className={cn("text-xs font-semibold uppercase", tone(name))}>
        {name.slice(0, 2)}
      </AvatarFallback>
    </Avatar>
  );
}
