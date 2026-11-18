import { TimerIcon } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import type { Room } from "@/api/types";
import { cn } from "@/lib/utils";

const URGENT_SECONDS = 10;

function secondsLeft(deadline: number | null, skewMs: number): number | null {
  return deadline === null ? null : Math.max(0, (deadline - (Date.now() + skewMs)) / 1000);
}

/** Seconds left in the current turn, ticking locally, corrected for client clock skew. */
function useSecondsLeft(room: Room): number | null {
  const deadline = room.turn_deadline ? Date.parse(room.turn_deadline) : null;
  const serverTime = Date.parse(room.server_time);
  // How far the server clock is ahead of ours, measured when this snapshot arrived.
  const skewMs = useMemo(() => serverTime - Date.now(), [serverTime]);
  const [left, setLeft] = useState(() => secondsLeft(deadline, skewMs));

  useEffect(() => {
    setLeft(secondsLeft(deadline, skewMs));
    if (deadline === null) return;
    const timer = window.setInterval(() => setLeft(secondsLeft(deadline, skewMs)), 250);
    return () => window.clearInterval(timer);
  }, [deadline, skewMs]);

  return left;
}

export function TurnTimer({ room, onPrimary }: { room: Room; onPrimary: boolean }) {
  const left = useSecondsLeft(room);
  if (left === null) return null;
  const urgent = left <= URGENT_SECONDS;
  const shown = Math.ceil(left);
  const label = shown >= 60 ? `${Math.floor(shown / 60)}:${String(shown % 60).padStart(2, "0")}` : `${shown}s`;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-md px-2 py-1 font-mono text-sm font-semibold tabular-nums",
        urgent
          ? "animate-pulse bg-bomb text-bomb-foreground"
          : onPrimary
            ? "bg-white/15"
            : "bg-card text-foreground",
      )}
      title="If time runs out, the player on turn pays"
    >
      <TimerIcon className="size-4" />
      {label}
    </span>
  );
}

/** Thin bar under the turn banner that drains as the turn runs out. */
export function TurnProgress({ room }: { room: Room }) {
  const left = useSecondsLeft(room);
  if (left === null) return null;
  const fraction = Math.min(1, left / room.turn_seconds);
  return (
    <div className="h-1 w-full bg-black/10">
      <div
        className={cn("h-full transition-[width] duration-300 ease-linear", left <= URGENT_SECONDS ? "bg-bomb" : "bg-sky")}
        style={{ width: `${fraction * 100}%` }}
      />
    </div>
  );
}
