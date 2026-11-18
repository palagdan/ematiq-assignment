import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowRightIcon, BombIcon, Grid3x3Icon, PlusIcon, UtensilsIcon } from "lucide-react";
import { type FormEvent, type ReactNode, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { api } from "@/api/client";
import { keys, useCurrentRoom, useMe } from "@/api/hooks";
import { CurrentGameCard } from "@/components/CurrentGameCard";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";

function Step({ icon, title, children }: { icon: ReactNode; title: string; children: ReactNode }) {
  return (
    <div className="flex gap-3">
      <span className="flex size-9 shrink-0 items-center justify-center rounded-md bg-white/15 text-white">
        {icon}
      </span>
      <div>
        <p className="font-semibold">{title}</p>
        <p className="text-sm text-white/75">{children}</p>
      </div>
    </div>
  );
}

// Decorative 4x4 board: a few safe cells opened and the bomb found.
const DEMO_CELLS = ["", "safe", "", "", "safe", "", "safe", "", "", "bomb", "", "safe", "", "", "", ""];

function DemoBoard() {
  return (
    <div aria-hidden="true" className="grid w-36 grid-cols-4 gap-1.5 rotate-6 opacity-90">
      {DEMO_CELLS.map((kind, i) => (
        <span
          key={i}
          className={
            kind === "bomb"
              ? "flex aspect-square items-center justify-center rounded-md bg-bomb text-bomb-foreground"
              : kind === "safe"
                ? "aspect-square rounded-md bg-safe"
                : "aspect-square rounded-md bg-white/15"
          }
        >
          {kind === "bomb" && <BombIcon className="size-4" />}
        </span>
      ))}
    </div>
  );
}

export function HomePage() {
  const navigate = useNavigate();
  const { data: me } = useMe();
  const { data: currentRoom } = useCurrentRoom();
  const queryClient = useQueryClient();
  const [code, setCode] = useState("");
  const busy = !!currentRoom;

  const create = useMutation({
    mutationFn: () => api<{ code: string }>("/api/rooms", { method: "POST" }),
    onSuccess: ({ code }) => {
      void queryClient.invalidateQueries({ queryKey: keys.currentRoom });
      navigate(`/r/${code}`);
    },
    onError: (error) => toast.error(error.message),
  });

  const join = (event: FormEvent) => {
    event.preventDefault();
    const normalized = code.trim().toUpperCase();
    if (normalized) navigate(`/r/${normalized}`);
  };

  return (
    <div className="space-y-6">
    {currentRoom && me && <CurrentGameCard room={currentRoom} me={me} />}
    <div className="grid gap-6 lg:grid-cols-[1.6fr_1fr]">
      <section className="relative overflow-hidden rounded-xl bg-primary p-8 text-primary-foreground sm:p-10">
        <div className="flex items-start justify-between gap-6">
          <div>
            <p className="text-sm font-medium text-white/75">Hi {me?.username} 👋</p>
            <h1 className="mt-2 max-w-sm text-4xl font-bold sm:text-5xl">Who's paying for lunch today?</h1>
          </div>
          <div className="hidden shrink-0 pt-2 pr-2 md:block">
            <DemoBoard />
          </div>
        </div>
        <div className="relative mt-8 grid gap-4 sm:grid-cols-3">
          <Step icon={<UtensilsIcon className="size-4" />} title="Order">
            Everyone enters what their meal costs.
          </Step>
          <Step icon={<Grid3x3Icon className="size-4" />} title="Take turns">
            Open cells on the grid, one at a time.
          </Step>
          <Step icon={<BombIcon className="size-4" />} title="Boom">
            Whoever opens the bomb pays for everyone.
          </Step>
        </div>
        <Button
          size="lg"
          className="relative mt-10 h-11 bg-white px-5 text-base text-primary hover:bg-white/90 disabled:opacity-60"
          onClick={() => create.mutate()}
          disabled={create.isPending || busy}
        >
          <PlusIcon className="size-5" />
          Create a room
        </Button>
        {busy && (
          <p className="relative mt-3 text-sm text-white/80">
            You can play one game at a time. Finish or leave {currentRoom.code} first.
          </p>
        )}
      </section>

      <Card className="self-start">
        <CardHeader>
          <CardTitle className="text-xl">Got a code?</CardTitle>
          <CardDescription>Join a room a colleague created.</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={join} className="space-y-3">
            <Input
              disabled={busy}
              className="h-14 text-center font-mono text-2xl tracking-[0.4em] uppercase placeholder:tracking-[0.2em] placeholder:text-base"
              placeholder="ROOM CODE"
              value={code}
              onChange={(e) => setCode(e.target.value.toUpperCase())}
              maxLength={6}
              aria-label="Room code"
            />
            <Button type="submit" variant="secondary" size="lg" className="h-10 w-full" disabled={busy || code.trim().length !== 6}>
              Join room
              <ArrowRightIcon />
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
    </div>
  );
}
