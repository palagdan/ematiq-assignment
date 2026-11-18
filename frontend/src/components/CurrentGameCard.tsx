import { ArrowRightIcon, Gamepad2Icon } from "lucide-react";
import { Link } from "react-router-dom";
import type { Room, User } from "@/api/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { PlayerAvatar } from "./PlayerAvatar";

export function gameHeadline(room: Room, me: User): string {
  if (room.status === "lobby") {
    if (room.players.length < 2) return "Waiting for players to join";
    const missing = room.players.filter((p) => !p.meal_amount).length;
    if (missing > 0) return "Waiting for meal prices";
    return room.host_id === me.id ? "Ready. Start the game!" : "Waiting for the host to start";
  }
  return room.current_player_id === me.id ? "It's your turn!" : "Game in progress";
}

export function CurrentGameCard({ room, me }: { room: Room; me: User }) {
  const myTurn = room.status === "playing" && room.current_player_id === me.id;
  return (
    <Card
      className={cn(
        "border-2 transition-colors",
        myTurn ? "border-primary bg-primary/5" : "border-safe/60 bg-safe-soft/60",
      )}
    >
      <CardContent className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-4">
          <span
            className={cn(
              "flex size-12 items-center justify-center rounded-lg",
              myTurn ? "animate-pulse bg-primary text-primary-foreground" : "bg-safe text-safe-foreground",
            )}
          >
            <Gamepad2Icon className="size-6" />
          </span>
          <div>
            <p className="text-sm font-medium text-muted-foreground">
              Your game ·{" "}
              <span className="font-mono font-semibold tracking-widest text-foreground">{room.code}</span>
            </p>
            <p className="text-xl font-semibold">{gameHeadline(room, me)}</p>
          </div>
        </div>
        <div className="flex items-center gap-4">
          <div className="flex -space-x-2">
            {room.players.slice(0, 5).map((p) => (
              <PlayerAvatar key={p.user_id} name={p.username} className="ring-2 ring-card" />
            ))}
            {room.players.length > 5 && <Badge variant="secondary">+{room.players.length - 5}</Badge>}
          </div>
          <Button asChild size="lg" className="h-10">
            <Link to={`/r/${room.code}`}>
              Open game <ArrowRightIcon />
            </Link>
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
