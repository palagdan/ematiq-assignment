import { CrownIcon, LinkIcon, LogOutIcon, PlayIcon, UserMinusIcon, UtensilsIcon } from "lucide-react";
import { type FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "@/api/client";
import { keys, useRates, useRoomAction } from "@/api/hooks";
import { useQueryClient } from "@tanstack/react-query";
import { CURRENCIES, type Currency, type Room, TURN_SECONDS_OPTIONS, type User } from "@/api/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { copyInvite } from "@/lib/invite";
import { estimateTotal, formatMoney } from "../money";
import { PlayerAvatar } from "./PlayerAvatar";

const GRID_SIZES = [4, 6, 9, 12, 16, 20, 25, 36, 49, 64];
const CURRENCY_LABEL: Record<Currency, string> = { CZK: "Kč · CZK", EUR: "€ · EUR", BTC: "₿ · BTC" };

export function Lobby({ room, me, isMember }: { room: Room; me: User; isMember: boolean }) {
  const navigate = useNavigate();
  const isHost = room.host_id === me.id;
  const mine = room.players.find((p) => p.user_id === me.id);
  const meals = room.players.flatMap((p) =>
    p.meal_amount && p.meal_currency ? [{ amount: p.meal_amount, currency: p.meal_currency }] : [],
  );
  const { data: rates } = useRates(meals.length > 0);

  const [amount, setAmount] = useState(mine?.meal_amount ? String(Number(mine.meal_amount)) : "");
  const [currency, setCurrency] = useState<Currency>(mine?.meal_currency ?? "CZK");

  const base = `/api/rooms/${room.code}`;
  const saveMeal = useRoomAction(() =>
    api<Room>(`${base}/meal`, { method: "PUT", body: { amount, currency } }),
  );
  const saveSettings = useRoomAction((settings: { grid_size?: number; turn_seconds?: number }) =>
    api<Room>(base, { method: "PATCH", body: settings }),
  );
  const removePlayer = useRoomAction((userId: number) =>
    api<Room>(`${base}/players/${userId}`, { method: "DELETE" }),
  );
  const start = useRoomAction(() => api<Room>(`${base}/start`, { method: "POST" }));

  const queryClient = useQueryClient();
  const leave = async () => {
    await api(`${base}/leave`, { method: "POST" });
    queryClient.setQueryData(keys.currentRoom, null);
    navigate("/");
  };

  const onSaveMeal = (event: FormEvent) => {
    event.preventDefault();
    saveMeal.mutate();
  };

  const missingMeals = room.players.filter((p) => !p.meal_amount).length;
  const startBlocker =
    room.players.length < 2
      ? "Waiting for at least one more player. Share the code!"
      : missingMeals > 0
        ? `Waiting for ${missingMeals} player${missingMeals > 1 ? "s" : ""} to enter a meal price`
        : room.grid_size < room.players.length + 1
          ? "The grid is too small for this many players"
          : null;

  return (
    <div className="grid gap-6 md:grid-cols-[1.3fr_1fr]">
      <Card className="self-start">
        <CardHeader>
          <CardTitle className="text-lg font-semibold">Players · {room.players.length}</CardTitle>
          <CardDescription>Everyone needs to enter a meal price before the game starts.</CardDescription>
        </CardHeader>
        <CardContent>
          <ul className="divide-y">
            {room.players.map((p) => (
              <li key={p.user_id} className="flex items-center justify-between gap-3 py-3 animate-pop-in">
                <span className="flex items-center gap-3">
                  <PlayerAvatar name={p.username} />
                  <span className="font-medium">{p.username}</span>
                  {p.user_id === room.host_id && (
                    <Badge variant="secondary" className="gap-1">
                      <CrownIcon className="size-3" /> host
                    </Badge>
                  )}
                  {p.user_id === me.id && <Badge variant="outline">you</Badge>}
                </span>
                <span className="flex items-center gap-1">
                  {p.meal_amount && p.meal_currency ? (
                    <span className="font-mono text-sm font-semibold">
                      {formatMoney(p.meal_amount, p.meal_currency)}
                    </span>
                  ) : (
                    <span className="text-sm text-muted-foreground italic">choosing…</span>
                  )}
                  {isHost && p.user_id !== me.id && (
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      className="text-muted-foreground hover:text-destructive"
                      aria-label={`Remove ${p.username}`}
                      title={`Remove ${p.username} from the lobby`}
                      disabled={removePlayer.isPending}
                      onClick={() => removePlayer.mutate(p.user_id)}
                    >
                      <UserMinusIcon />
                    </Button>
                  )}
                </span>
              </li>
            ))}
          </ul>
        </CardContent>
        <CardFooter className="justify-between border-t">
          <span className="text-sm text-muted-foreground">Bill so far</span>
          <span className="text-xl font-semibold">
            {rates && meals.length > 0 ? `≈ ${formatMoney(estimateTotal(meals, rates, "CZK"), "CZK")}` : "-"}
          </span>
        </CardFooter>
      </Card>

      <div className="space-y-6">
        {isMember && (
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-lg font-semibold">
                <UtensilsIcon className="size-5 text-primary" /> Your meal
              </CardTitle>
            </CardHeader>
            <CardContent>
              <form className="space-y-3" onSubmit={onSaveMeal}>
                <div className="flex gap-2">
                  <Input
                    type="number"
                    inputMode="decimal"
                    min="0"
                    step="any"
                    placeholder="Price"
                    value={amount}
                    onChange={(e) => setAmount(e.target.value)}
                    required
                    aria-label="Meal price"
                    className="h-10 font-mono"
                  />
                  <Select value={currency} onValueChange={(v) => setCurrency(v as Currency)}>
                    <SelectTrigger className="!h-10 w-32" aria-label="Currency">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {CURRENCIES.map((c) => (
                        <SelectItem key={c} value={c}>
                          {CURRENCY_LABEL[c]}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <Button type="submit" variant="secondary" className="h-9 w-full" disabled={saveMeal.isPending || !amount}>
                  {mine?.meal_amount ? "Update price" : "Save price"}
                </Button>
              </form>
            </CardContent>
          </Card>
        )}

        {isMember && (
          <Card>
            <CardHeader>
              <CardTitle className="text-lg font-semibold">Game setup</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex items-center justify-between gap-3">
                <Label>Grid size</Label>
                <Select
                  value={String(room.grid_size)}
                  disabled={!isHost || saveSettings.isPending}
                  onValueChange={(v) => saveSettings.mutate({ grid_size: Number(v) })}
                >
                  <SelectTrigger className="w-36" aria-label="Grid size">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {GRID_SIZES.map((size) => (
                      <SelectItem key={size} value={String(size)} disabled={size < room.players.length + 1}>
                        {size} cells
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="flex items-center justify-between gap-3">
                <Label>Turn time</Label>
                <Select
                  value={String(room.turn_seconds)}
                  disabled={!isHost || saveSettings.isPending}
                  onValueChange={(v) => saveSettings.mutate({ turn_seconds: Number(v) })}
                >
                  <SelectTrigger className="w-36" aria-label="Turn time">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {TURN_SECONDS_OPTIONS.map((seconds) => (
                      <SelectItem key={seconds} value={String(seconds)}>
                        {seconds < 60 ? `${seconds} seconds` : `${seconds / 60} min`}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <p className="text-xs text-muted-foreground">
                If a player's time runs out, they lose and pay.
              </p>
              {isHost ? (
                <>
                  <Button
                    size="lg"
                    className="h-12 w-full text-base shadow-lg shadow-primary/25"
                    disabled={startBlocker !== null || start.isPending}
                    onClick={() => start.mutate()}
                  >
                    <PlayIcon className="size-5" /> Start the game
                  </Button>
                  {startBlocker && <p className="text-center text-sm text-muted-foreground">{startBlocker}</p>}
                </>
              ) : (
                <p className="rounded-lg bg-muted p-3 text-center text-sm text-muted-foreground">
                  Waiting for the host to start the game…
                </p>
              )}
            </CardContent>
            <CardFooter className="justify-between border-t">
              <Button variant="ghost" size="sm" onClick={() => copyInvite(room.code)}>
                <LinkIcon /> Copy invite
              </Button>
              <Button variant="ghost" size="sm" className="text-muted-foreground" onClick={leave}>
                <LogOutIcon /> Leave
              </Button>
            </CardFooter>
          </Card>
        )}
      </div>
    </div>
  );
}
