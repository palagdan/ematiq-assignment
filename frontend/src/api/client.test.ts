import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, api } from "./client";

function respond(status: number, body?: unknown) {
  const fetchMock = vi.fn().mockResolvedValue(
    new Response(body === undefined ? null : JSON.stringify(body), {
      status,
      headers: { "Content-Type": "application/json" },
    }),
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => vi.unstubAllGlobals());

describe("api", () => {
  it("sends JSON bodies with the session cookie and parses the reply", async () => {
    const fetchMock = respond(200, { code: "ABC234" });
    await expect(api("/api/rooms", { method: "POST", body: { a: 1 } })).resolves.toEqual({ code: "ABC234" });
    expect(fetchMock).toHaveBeenCalledWith("/api/rooms", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: '{"a":1}',
    });
  });

  it("returns nothing for 204 responses", async () => {
    respond(204);
    await expect(api("/api/auth/logout", { method: "POST" })).resolves.toBeUndefined();
  });

  it("turns a domain error into an ApiError with the server's message", async () => {
    respond(409, { detail: "It is not your turn" });
    const error = await api("/api/rooms/X/moves").catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ status: 409, message: "It is not your turn" });
  });

  it("joins FastAPI validation errors into one readable message", async () => {
    respond(422, {
      detail: [
        { loc: ["body", "username"], msg: "String should have at least 3 characters" },
        { loc: ["body", "password"], msg: "String should have at least 8 characters" },
      ],
    });
    await expect(api("/api/auth/register")).rejects.toThrow(
      "String should have at least 3 characters; String should have at least 8 characters",
    );
  });

  it("falls back to a generic message for unexpected bodies", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("<html>Bad gateway</html>", { status: 502 })));
    await expect(api("/api/health")).rejects.toMatchObject({ status: 502, message: "Something went wrong" });
  });
});
