import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook } from "@testing-library/react";
import type { ReactNode } from "react";
import { toast } from "sonner";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { makeRoom } from "@/test/fixtures";
import { keys } from "./hooks";
import type { Room } from "./types";
import { useRoomSocket } from "./useRoomSocket";

class FakeSocket {
  static instances: FakeSocket[] = [];
  static readonly OPEN = 1;
  readyState = 0;
  sent: string[] = [];
  closed = false;
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onclose: ((event: { code: number }) => void) | null = null;

  constructor(readonly url: string) {
    FakeSocket.instances.push(this);
  }
  send(data: string) {
    this.sent.push(data);
  }
  close() {
    this.closed = true;
  }
  // Server-side helpers
  open() {
    this.readyState = FakeSocket.OPEN;
    this.onopen?.();
  }
  receive(message: object) {
    this.onmessage?.({ data: JSON.stringify(message) });
  }
  drop(code = 1006) {
    this.readyState = 3;
    this.onclose?.({ code });
  }
}

const latest = () => FakeSocket.instances.at(-1)!;

function setup(code = "ABC234", enabled = true) {
  const client = new QueryClient();
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  const hook = renderHook(({ on }) => useRoomSocket(code, on), { wrapper, initialProps: { on: enabled } });
  return { client, hook };
}

beforeEach(() => {
  FakeSocket.instances = [];
  vi.useFakeTimers();
  vi.stubGlobal("WebSocket", FakeSocket);
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("useRoomSocket", () => {
  it("connects to the room's socket and reports when it's live", () => {
    const { hook } = setup();
    expect(latest().url).toBe(`ws://${window.location.host}/ws/rooms/ABC234`);
    expect(hook.result.current).toBe(false);
    act(() => latest().open());
    expect(hook.result.current).toBe(true);
  });

  it("puts snapshots into the query cache, newest version wins", () => {
    const { client } = setup();
    act(() => {
      latest().open();
      latest().receive({ type: "room.state", room: makeRoom({ version: 2, grid_size: 16 }) });
      latest().receive({ type: "room.state", room: makeRoom({ version: 1, grid_size: 9 }) });
    });
    expect(client.getQueryData<Room>(keys.room("ABC234"))).toMatchObject({ version: 2, grid_size: 16 });
  });

  it("reconnects with growing backoff after the connection drops", () => {
    const { hook } = setup();
    act(() => latest().open());
    act(() => latest().drop());
    expect(hook.result.current).toBe(false);
    expect(FakeSocket.instances).toHaveLength(1);

    act(() => vi.advanceTimersByTime(500));
    expect(FakeSocket.instances).toHaveLength(2);
    act(() => latest().drop()); // fails again before opening
    act(() => vi.advanceTimersByTime(999));
    expect(FakeSocket.instances).toHaveLength(2);
    act(() => vi.advanceTimersByTime(1));
    expect(FakeSocket.instances).toHaveLength(3);

    act(() => latest().open());
    expect(hook.result.current).toBe(true);
  });

  it.each([4401, 4404])("gives up after close code %i (not logged in / no such room)", (code) => {
    setup();
    act(() => latest().open());
    act(() => latest().drop(code));
    act(() => vi.advanceTimersByTime(60_000));
    expect(FakeSocket.instances).toHaveLength(1);
  });

  it("pings every 15 s and stays connected while pongs come back", () => {
    const { hook } = setup();
    act(() => latest().open());
    act(() => vi.advanceTimersByTime(15_000));
    expect(latest().sent).toEqual(["ping"]);
    act(() => latest().receive({ type: "pong" }));
    act(() => vi.advanceTimersByTime(15_000));
    expect(latest().sent).toEqual(["ping", "ping"]);
    act(() => latest().receive({ type: "pong" }));
    act(() => vi.advanceTimersByTime(5_000));
    expect(hook.result.current).toBe(true);
    expect(FakeSocket.instances).toHaveLength(1);
  });

  it("abandons a silent connection and reconnects without waiting for the browser", () => {
    const { hook } = setup();
    act(() => latest().open());
    const silent = latest();
    act(() => vi.advanceTimersByTime(15_000 + 5_000)); // ping sent, no pong within 5 s
    expect(silent.closed).toBe(true);
    expect(hook.result.current).toBe(false);
    act(() => vi.advanceTimersByTime(500));
    expect(FakeSocket.instances).toHaveLength(2);
    act(() => silent.drop()); // a late close from the dead socket must not start another reconnect
    act(() => vi.advanceTimersByTime(10_000));
    expect(FakeSocket.instances).toHaveLength(2);
  });

  it("refetches and notifies when the room is closed", () => {
    const info = vi.spyOn(toast, "info").mockImplementation(() => "id");
    const { client } = setup();
    const invalidate = vi.spyOn(client, "invalidateQueries");
    act(() => {
      latest().open();
      latest().receive({ type: "room.closed" });
    });
    expect(info).toHaveBeenCalledOnce();
    expect(invalidate).toHaveBeenCalledWith({ queryKey: keys.room("ABC234") });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: keys.currentRoom });
  });

  it("does not connect for finished games, and disconnects when a game finishes", () => {
    setup("ABC234", false);
    expect(FakeSocket.instances).toHaveLength(0);

    const { hook } = setup();
    act(() => latest().open());
    hook.rerender({ on: false });
    expect(latest().closed).toBe(true);
    expect(hook.result.current).toBe(false);
    act(() => vi.advanceTimersByTime(60_000));
    expect(FakeSocket.instances).toHaveLength(1);
  });

  it("closes the socket and stops timers on unmount", () => {
    const { hook } = setup();
    act(() => latest().open());
    hook.unmount();
    expect(latest().closed).toBe(true);
    act(() => vi.advanceTimersByTime(60_000));
    expect(latest().sent).toEqual([]);
    expect(FakeSocket.instances).toHaveLength(1);
  });
});
