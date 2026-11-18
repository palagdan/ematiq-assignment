import { CopyIcon, EyeIcon, HomeIcon } from "lucide-react";
import { Link, useParams } from "react-router-dom";
import { ApiError, api } from "@/api/client";
import { useCurrentRoom, useMe, useRoom, useRoomAction } from "@/api/hooks";
import type { Room } from "@/api/types";
import { useRoomSocket } from "@/api/useRoomSocket";
import { Board } from "@/components/Board";
import { Lobby } from "@/components/Lobby";
import { PageSpinner } from "@/components/PageSpinner";
import { Result } from "@/components/Result";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { copyCode } from "@/lib/invite";
import { cn } from "@/lib/utils";

const STATUS_LABEL = { lobby: "Lobby", playing: "In game", finished: "Finished" } as const;

export function RoomPage() {
  const code = (useParams().code ?? "").toUpperCase();
  const { data: me } = useMe();
  const { data: room, error, isPending } = useRoom(code);
  const finished = room?.status === "finished";
  const connected = useRoomSocket(code, !!room && !finished);
  const { data: currentRoom } = useCurrentRoom();
  const join = useRoomAction(() => api<Room>(`/api/rooms/${code}/join`, { method: "POST" }));

  if (isPending) return <PageSpinner label="Loading room…" />;
  if (error) {
    const notFound = error instanceof ApiError && error.status === 404;
    return (
      <Card className="mx-auto max-w-md text-center">
        <CardContent className="space-y-4 py-10">
          <p className="text-5xl">🍽️</p>
          <h2 className="text-xl font-bold">
            {notFound ? `Room ${code} doesn't exist` : "Could not load the room"}
          </h2>
          <Button asChild variant="secondary">
            <Link to="/">
              <HomeIcon />
              Back home
            </Link>
          </Button>
        </CardContent>
      </Card>
    );
  }
  if (!me) return null;

  const isMember = room.players.some((p) => p.user_id === me.id);
  const busyElsewhere = currentRoom && currentRoom.code !== room.code ? currentRoom.code : null;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <h1 className="text-2xl font-bold">Room</h1>
          <button
            type="button"
            onClick={() => copyCode(room.code)}
            className="group inline-flex items-center gap-2 rounded-md border border-dashed border-primary/50 bg-card px-3 py-1 font-mono text-xl font-semibold tracking-[0.25em] transition-colors hover:border-primary"
            aria-label="Copy room code"
          >
            {room.code}
            <CopyIcon className="size-4 text-muted-foreground group-hover:text-primary" />
          </button>
          <Badge variant="secondary">{STATUS_LABEL[room.status]}</Badge>
        </div>
        {!finished && (
        <span className="inline-flex items-center gap-2 text-sm text-muted-foreground">
          <span className="relative flex size-2.5">
            {connected && (
              <span className="absolute inline-flex size-full animate-ping rounded-full bg-safe opacity-75" />
            )}
            <span className={cn("relative inline-flex size-2.5 rounded-full", connected ? "bg-safe" : "bg-muted-foreground/40")} />
          </span>
          {connected ? "Live" : "Reconnecting…"}
        </span>
        )}
      </div>

      {!isMember && !finished && (
        <Alert>
          <EyeIcon />
          <AlertTitle>You're watching this room</AlertTitle>
          <AlertDescription className="flex flex-wrap items-center justify-between gap-3">
            {room.status !== "lobby" ? (
              "This game started without you."
            ) : busyElsewhere ? (
              <span>
                You're already in{" "}
                <Link to={`/r/${busyElsewhere}`} className="font-mono font-semibold text-primary underline">
                  {busyElsewhere}
                </Link>
                . Finish or leave it to join this one.
              </span>
            ) : (
              "Join to play along."
            )}
            {room.status === "lobby" && !busyElsewhere && (
              <Button size="sm" onClick={() => join.mutate()} disabled={join.isPending}>
                Join the game
              </Button>
            )}
          </AlertDescription>
        </Alert>
      )}

      {room.status === "lobby" && <Lobby room={room} me={me} isMember={isMember} />}
      {room.status === "playing" && <Board room={room} me={me} />}
      {room.status === "finished" && (
        <>
          <Result room={room} />
          <Board room={room} me={me} />
        </>
      )}
    </div>
  );
}
