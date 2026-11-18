import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { acceptRoom, keys } from "./hooks";
import type { RoomStateMessage } from "./types";

const FATAL_CLOSE_CODES = new Set([4401, 4404]);
const HEARTBEAT_INTERVAL_MS = 15_000;
const HEARTBEAT_TIMEOUT_MS = 5_000;

type ServerMessage = RoomStateMessage | { type: "pong" } | { type: "room.closed" };

/**
 * Subscribes to live room snapshots. The server sends the current state on connect
 * and after every change, so reconnecting is all it takes to catch up.
 * Pass `enabled: false` for finished games, which never change again.
 */
export function useRoomSocket(code: string, enabled = true): boolean {
  const queryClient = useQueryClient();
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    if (!enabled) {
      setConnected(false);
      return;
    }
    let socket: WebSocket | null = null;
    let retryTimer: number | undefined;
    let heartbeatTimer: number | undefined;
    let deadlineTimer: number | undefined;
    let attempt = 0;
    let disposed = false;

    const stopHeartbeat = () => {
      window.clearInterval(heartbeatTimer);
      window.clearTimeout(deadlineTimer);
      deadlineTimer = undefined;
    };

    const scheduleReconnect = () => {
      setConnected(false);
      stopHeartbeat();
      if (disposed) return;
      const delay = Math.min(500 * 2 ** attempt, 10_000);
      attempt += 1;
      retryTimer = window.setTimeout(connect, delay);
    };

    // Give up on a socket that stopped answering. Closing a dead connection can take the
    // browser a long time, so detach it and reconnect right away instead of waiting for onclose.
    const abandon = (dead: WebSocket) => {
      dead.onopen = dead.onmessage = dead.onclose = null;
      dead.close();
      scheduleReconnect();
    };

    const connect = () => {
      const protocol = window.location.protocol === "https:" ? "wss" : "ws";
      const current = new WebSocket(`${protocol}://${window.location.host}/ws/rooms/${code}`);
      socket = current;
      current.onopen = () => {
        attempt = 0;
        setConnected(true);
        heartbeatTimer = window.setInterval(() => {
          if (deadlineTimer !== undefined || current.readyState !== WebSocket.OPEN) return;
          current.send("ping");
          deadlineTimer = window.setTimeout(() => abandon(current), HEARTBEAT_TIMEOUT_MS);
        }, HEARTBEAT_INTERVAL_MS);
      };
      current.onmessage = (event: MessageEvent<string>) => {
        // Any message proves the connection is alive.
        window.clearTimeout(deadlineTimer);
        deadlineTimer = undefined;
        const message = JSON.parse(event.data) as ServerMessage;
        if (message.type === "room.state") acceptRoom(queryClient, message.room);
        if (message.type === "room.closed") {
          toast.info("This lobby was closed after 30 minutes without activity.");
          void queryClient.invalidateQueries({ queryKey: keys.room(code) });
          void queryClient.invalidateQueries({ queryKey: keys.currentRoom });
        }
      };
      current.onclose = (event) => {
        if (FATAL_CLOSE_CODES.has(event.code)) {
          setConnected(false);
          stopHeartbeat();
          return;
        }
        scheduleReconnect();
      };
    };

    connect();
    return () => {
      disposed = true;
      window.clearTimeout(retryTimer);
      stopHeartbeat();
      if (socket) {
        socket.onclose = null;
        socket.close();
      }
    };
  }, [code, enabled, queryClient]);

  return connected;
}
