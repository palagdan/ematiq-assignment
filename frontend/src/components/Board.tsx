import { BombIcon, FingerprintIcon, FlagIcon, SaladIcon } from "lucide-react";
import { api } from "@/api/client";
import { useRoomAction } from "@/api/hooks";
import type { Room, User } from "@/api/types";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import { PlayerAvatar } from "./PlayerAvatar";
import { TurnProgress, TurnTimer } from "./TurnTimer";

export function Board({ room, me }: { room: Room; me: User }) {
  const open = useRoomAction((cell: number) =>
    api<Room>(`/api/rooms/${room.code}/moves`, { method: "POST", body: { cell } }),
  );
  const giveUp = useRoomAction(() =>
    api<Room>(`/api/rooms/${room.code}/give-up`, { method: "POST" }),
  );
  const isMember = room.players.some((p) => p.user_id === me.id);
  const names = new Map(room.players.map((p) => [p.user_id, p.username]));
  const opened = new Map(room.moves.map((m) => [m.cell, m]));
  const playing = room.status === "playing";
  const myTurn = playing && room.current_player_id === me.id;
  const columns = Math.ceil(Math.sqrt(room.grid_size));
  const onTurn = names.get(room.current_player_id ?? -1);
  const safeLeft = room.grid_size - room.moves.length - 1;

  return (
    <div className="grid gap-6 md:grid-cols-[1.6fr_1fr]">
      <Card className="overflow-hidden">
        {playing && (
          <div
            className={cn(
              "flex items-center justify-between gap-3 px-6 py-4 transition-colors",
              myTurn ? "bg-primary text-primary-foreground" : "bg-muted",
            )}
          >
            <div>
              <p className="text-lg font-semibold">
                {myTurn ? "Your turn. Pick a cell!" : `${onTurn}'s turn…`}
              </p>
              <span className={cn("text-sm", myTurn ? "opacity-90" : "text-muted-foreground")}>
                {safeLeft} safe cell{safeLeft === 1 ? "" : "s"} left
              </span>
            </div>
            <TurnTimer room={room} onPrimary={myTurn} />
          </div>
        )}
        {playing && <TurnProgress room={room} />}
        <CardContent className="pt-6">
          <div
            className="mx-auto grid max-w-lg gap-2 sm:gap-3"
            style={{ gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))` }}
          >
            {Array.from({ length: room.grid_size }, (_, cell) => {
              const move = opened.get(cell);
              const isBomb = room.bomb_index === cell;
              const clickable = myTurn && !move && !open.isPending;
              const button = (
                <button
                  key={cell}
                  type="button"
                  disabled={!clickable}
                  onClick={() => open.mutate(cell)}
                  aria-label={move ? `Cell ${cell + 1}, opened by ${names.get(move.user_id)}` : `Cell ${cell + 1}`}
                  className={cn(
                    "relative flex aspect-square flex-col items-center justify-center gap-1 rounded-lg border-2 text-xs font-medium transition-all duration-150",
                    !move && !isBomb && "border-border bg-card shadow-[0_3px_0_var(--border)]",
                    clickable && "cursor-pointer hover:-translate-y-0.5 hover:border-primary hover:bg-sky-soft hover:shadow-[0_5px_0_var(--primary)] active:translate-y-0.5 active:shadow-none",
                    !clickable && !move && playing && "opacity-80",
                    move && !isBomb && "border-safe/50 bg-safe-soft text-safe-strong animate-pop-in",
                    isBomb && "border-bomb bg-bomb text-bomb-foreground shadow-lg shadow-bomb/40",
                  )}
                >
                  {isBomb ? (
                    <BombIcon className="size-1/3 animate-shake" />
                  ) : move ? (
                    <SaladIcon className="size-1/3" />
                  ) : null}
                  {move && (
                    <span className="max-w-full truncate px-1 text-[0.65rem] sm:text-xs">
                      {names.get(move.user_id)}
                    </span>
                  )}
                </button>
              );
              return button;
            })}
          </div>
        </CardContent>
      </Card>

      <Card className="self-start">
        <CardHeader>
          <CardTitle className="text-lg font-semibold">Turn order</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <ol className="space-y-1.5">
            {room.players.map((p, index) => {
              const current = p.user_id === room.current_player_id;
              const paid = p.user_id === room.loser_id;
              return (
                <li
                  key={p.user_id}
                  className={cn(
                    "flex items-center gap-3 rounded-lg px-2 py-2 transition-colors",
                    current && "bg-sky-soft ring-2 ring-sky",
                  )}
                >
                  <span className="w-4 text-right font-mono text-xs text-muted-foreground">{index + 1}</span>
                  <PlayerAvatar name={p.username} />
                  <span className="flex-1 font-medium">{p.username}</span>
                  {p.user_id === me.id && <Badge variant="outline">you</Badge>}
                  {paid && <Badge className="bg-bomb text-bomb-foreground">pays</Badge>}
                  {room.status === "finished" && !paid && (
                    <Badge className="bg-safe text-safe-foreground">free lunch</Badge>
                  )}
                </li>
              );
            })}
          </ol>
          {room.bomb_commitment && (
            <Tooltip>
              <TooltipTrigger asChild>
                <p className="flex cursor-help items-center gap-2 rounded-lg bg-muted px-3 py-2 text-xs text-muted-foreground">
                  <FingerprintIcon className="size-4 shrink-0" />
                  <span className="truncate font-mono">{room.bomb_commitment}</span>
                </p>
              </TooltipTrigger>
              <TooltipContent className="max-w-64">
                sha256 of the bomb's position, published before the first move. It's revealed at the end so
                anyone can check the bomb was never moved.
              </TooltipContent>
            </Tooltip>
          )}
          {playing && isMember && (
            <AlertDialog>
              <AlertDialogTrigger asChild>
                <Button variant="ghost" size="sm" className="w-full text-muted-foreground">
                  <FlagIcon /> Give up
                </Button>
              </AlertDialogTrigger>
              <AlertDialogContent>
                <AlertDialogHeader>
                  <AlertDialogTitle>Give up and pay for lunch?</AlertDialogTitle>
                  <AlertDialogDescription>
                    The game ends right away and you pay for everyone's meals. This can't be undone.
                  </AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                  <AlertDialogCancel>Keep playing</AlertDialogCancel>
                  <AlertDialogAction onClick={() => giveUp.mutate()}>Give up, I'll pay</AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
