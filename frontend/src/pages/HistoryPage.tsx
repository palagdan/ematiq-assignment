import { CalendarIcon, ChevronRightIcon, ReceiptIcon } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { useHistory, useMe } from "@/api/hooks";
import type { HistoryEntry } from "@/api/types";
import { PlayerAvatar } from "@/components/PlayerAvatar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardFooter, CardHeader } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { cn } from "@/lib/utils";
import { formatDateTime, formatMoney } from "../money";

function GameCard({ entry, meId }: { entry: HistoryEntry; meId: number | undefined }) {
  return (
    <Link
      to={`/r/${entry.code}`}
      aria-label={`Open game ${entry.code}`}
      className="group block rounded-xl outline-none focus-visible:ring-2 focus-visible:ring-ring"
    >
    <Card className="transition-all group-hover:-translate-y-0.5 group-hover:border-primary/50 group-hover:shadow-md">
      <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-2">
        <span className="flex items-center gap-2 font-medium">
          <CalendarIcon className="size-4 text-muted-foreground" />
          {formatDateTime(entry.finished_at)}
        </span>
        <span className="flex items-center gap-2">
          {entry.finish_reason !== "bomb" && (
            <Badge variant="outline">{entry.finish_reason === "timeout" ? "⏱ time ran out" : "🏳️ gave up"}</Badge>
          )}
          <Badge className="bg-bomb text-bomb-foreground">💸 {entry.loser_username} paid</Badge>
          <span className="inline-flex items-center gap-0.5 rounded-md border px-2 py-0.5 font-mono text-xs tracking-widest text-muted-foreground group-hover:border-primary/50 group-hover:text-primary">
            {entry.code}
            <ChevronRightIcon className="size-3.5" />
          </span>
        </span>
      </CardHeader>
      <CardContent>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Player</TableHead>
              <TableHead className="text-right">Meal</TableHead>
              <TableHead className="hidden sm:table-cell">Currency</TableHead>
              <TableHead className="text-right">Result</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {entry.players.map((p) => (
              <TableRow key={p.user_id} className={cn(p.paid && "bg-bomb-soft/60")}>
                <TableCell>
                  <span className="flex items-center gap-2">
                    <PlayerAvatar name={p.username} className="size-7" />
                    <span className="font-medium">{p.username}</span>
                    {p.user_id === meId && <Badge variant="outline">you</Badge>}
                  </span>
                </TableCell>
                <TableCell className="text-right font-mono">{formatMoney(p.meal_amount, p.meal_currency)}</TableCell>
                <TableCell className="hidden text-muted-foreground sm:table-cell">{p.meal_currency}</TableCell>
                <TableCell className="text-right">
                  {p.paid ? (
                    <Badge className="bg-bomb text-bomb-foreground">paid</Badge>
                  ) : (
                    <Badge className="bg-safe text-safe-foreground">won</Badge>
                  )}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
      <CardFooter className="flex-wrap justify-between gap-2 border-t text-sm">
        <span className="flex items-center gap-2 text-muted-foreground">
          <ReceiptIcon className="size-4" /> Total bill
        </span>
        <span className="font-mono font-semibold">
          {formatMoney(entry.totals.CZK, "CZK")}
          <span className="text-muted-foreground">
            {" · "}
            {formatMoney(entry.totals.EUR, "EUR")} · {formatMoney(entry.totals.BTC, "BTC")}
          </span>
        </span>
      </CardFooter>
    </Card>
    </Link>
  );
}

export function HistoryPage() {
  const [mine, setMine] = useState(false);
  const { data: me } = useMe();
  const history = useHistory(mine);
  const entries = history.data?.pages.flatMap((page) => page.items) ?? [];

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold">Game history</h1>
          <p className="text-muted-foreground">Every lunch that was played for, and who paid.</p>
        </div>
        <div className="flex items-center gap-2">
          <Switch id="mine" checked={mine} onCheckedChange={setMine} />
          <Label htmlFor="mine">Only my games</Label>
        </div>
      </div>

      {history.isPending &&
        Array.from({ length: 2 }, (_, i) => <Skeleton key={i} className="h-64 w-full rounded-xl" />)}
      {history.error && <p className="text-destructive">{history.error.message}</p>}
      {!history.isPending && entries.length === 0 && (
        <Card>
          <CardContent className="space-y-3 py-12 text-center">
            <p className="text-5xl">🥪</p>
            <p className="font-medium">No games yet</p>
            <Button asChild>
              <Link to="/">Play the first one</Link>
            </Button>
          </CardContent>
        </Card>
      )}

      {entries.map((entry) => (
        <GameCard key={entry.code} entry={entry} meId={me?.id} />
      ))}

      {history.hasNextPage && (
        <div className="text-center">
          <Button variant="outline" onClick={() => history.fetchNextPage()} disabled={history.isFetchingNextPage}>
            Load more
          </Button>
        </div>
      )}
    </div>
  );
}
