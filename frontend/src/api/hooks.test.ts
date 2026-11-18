import { QueryClient } from "@tanstack/react-query";
import { beforeEach, describe, expect, it } from "vitest";
import { makeRoom } from "@/test/fixtures";
import { acceptRoom, keys } from "./hooks";
import type { Room } from "./types";

describe("acceptRoom", () => {
  let client: QueryClient;
  const cached = (code = "ABC234") => client.getQueryData<Room>(keys.room(code));

  beforeEach(() => {
    client = new QueryClient();
  });

  it("stores the first snapshot of a room", () => {
    acceptRoom(client, makeRoom({ version: 3 }));
    expect(cached()?.version).toBe(3);
  });

  it("keeps the newest snapshot when an older one arrives late", () => {
    acceptRoom(client, makeRoom({ version: 5, grid_size: 16 }));
    acceptRoom(client, makeRoom({ version: 4, grid_size: 9 }));
    expect(cached()).toMatchObject({ version: 5, grid_size: 16 });
  });

  it("replaces on equal version (a re-sent snapshot after reconnecting)", () => {
    acceptRoom(client, makeRoom({ version: 2, grid_size: 9 }));
    acceptRoom(client, makeRoom({ version: 2, grid_size: 12 }));
    expect(cached()?.grid_size).toBe(12);
  });

  it("keeps rooms apart", () => {
    acceptRoom(client, makeRoom({ code: "AAAAAA", version: 9 }));
    acceptRoom(client, makeRoom({ code: "BBBBBB", version: 1 }));
    expect(cached("AAAAAA")?.version).toBe(9);
    expect(cached("BBBBBB")?.version).toBe(1);
  });

  describe("current game", () => {
    it("follows updates of the room you're in", () => {
      client.setQueryData(keys.currentRoom, makeRoom({ version: 1 }));
      acceptRoom(client, makeRoom({ version: 2, status: "playing" }));
      expect(client.getQueryData<Room>(keys.currentRoom)?.status).toBe("playing");
    });

    it("is cleared once that game finishes", () => {
      client.setQueryData(keys.currentRoom, makeRoom({ version: 4, status: "playing" }));
      acceptRoom(client, makeRoom({ version: 5, status: "finished" }));
      expect(client.getQueryData(keys.currentRoom)).toBeNull();
    });

    it("ignores other rooms and stale snapshots", () => {
      const current = makeRoom({ version: 7, status: "playing" });
      client.setQueryData(keys.currentRoom, current);
      acceptRoom(client, makeRoom({ code: "ZZZZZZ", version: 99, status: "finished" }));
      acceptRoom(client, makeRoom({ version: 6, status: "finished" }));
      expect(client.getQueryData(keys.currentRoom)).toBe(current);
    });
  });
});
