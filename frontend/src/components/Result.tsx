import { ShieldAlertIcon, ShieldCheckIcon } from "lucide-react";
import { useEffect, useState } from "react";
import { CURRENCIES, type FinishReason, type Room } from "@/api/types";
import { Card, CardContent } from "@/components/ui/card";
import { formatDateTime, formatMoney, sha256Hex } from "../money";
import { PlayerAvatar } from "./PlayerAvatar";

type Verification = "checking" | "ok" | "mismatch";

const REASON_LABEL: Record<FinishReason, string> = { bomb: "Boom", gave_up: "Gave up", timeout: "Time's up" };
const REASON_HEADLINE: Record<FinishReason, string> = {
  bomb: "pays for lunch",
  gave_up: "gave up and pays",
  timeout: "ran out of time and pays",
};

export function Result({ room }: { room: Room }) {
  const loser = room.players.find((p) => p.user_id === room.loser_id);
  const [verification, setVerification] = useState<Verification>("checking");

  useEffect(() => {
    if (room.bomb_index === null || !room.bomb_salt || !room.bomb_commitment) return;
    void sha256Hex(`${room.bomb_index}:${room.bomb_salt}`).then((hash) =>
      setVerification(hash === room.bomb_commitment ? "ok" : "mismatch"),
    );
  }, [room.bomb_index, room.bomb_salt, room.bomb_commitment]);

  return (
    <Card className="relative overflow-hidden border-0 bg-primary text-primary-foreground animate-pop-in">
      <CardContent className="grid gap-6 py-2 md:grid-cols-[1fr_auto] md:items-center">
        <div className="flex items-center gap-4">
          {loser && <PlayerAvatar name={loser.username} className="size-16 ring-4 ring-white/30 [&_*]:text-xl" />}
          <div>
            <span className="inline-flex items-center rounded-md bg-bomb px-2 py-0.5 text-xs font-semibold tracking-wider text-bomb-foreground uppercase">
              {REASON_LABEL[room.finish_reason ?? "bomb"]}
            </span>
            <h2 className="mt-1 text-3xl font-bold">
              {loser?.username} {REASON_HEADLINE[room.finish_reason ?? "bomb"]}
            </h2>
            {room.finished_at && <p className="text-sm opacity-80">{formatDateTime(room.finished_at)}</p>}
          </div>
        </div>
        {room.totals && (
          <div className="grid grid-cols-3 gap-2 rounded-xl bg-black/15 p-2">
            {CURRENCIES.map((c) => (
              <div key={c} className="rounded-lg bg-white/10 px-3 py-2 text-center">
                <p className="text-[0.65rem] font-semibold tracking-wider uppercase opacity-80">{c}</p>
                <p className="font-mono text-sm font-bold whitespace-nowrap sm:text-base">
                  {formatMoney(room.totals![c], c)}
                </p>
              </div>
            ))}
          </div>
        )}
        <p className="flex items-center gap-2 text-sm opacity-90 md:col-span-2">
          {verification === "ok" && (
            <>
              <ShieldCheckIcon className="size-4" /> Fair game: the bomb's position matches the fingerprint
              published at the start.
            </>
          )}
          {verification === "mismatch" && (
            <>
              <ShieldAlertIcon className="size-4" /> Warning: the bomb's position does NOT match the published
              fingerprint!
            </>
          )}
        </p>
      </CardContent>
    </Card>
  );
}
