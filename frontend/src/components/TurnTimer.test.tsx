import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Room } from "@/api/types";
import { makeRoom } from "@/test/fixtures";
import { TurnProgress, TurnTimer } from "./TurnTimer";

const NOW = new Date("2026-11-18T12:00:00Z").getTime();

function playing(secondsLeft: number, overrides: Partial<Room> = {}): Room {
  const serverNow = overrides.server_time ? Date.parse(overrides.server_time) : NOW;
  return makeRoom({
    status: "playing",
    turn_seconds: 60,
    server_time: new Date(serverNow).toISOString(),
    turn_deadline: new Date(serverNow + secondsLeft * 1000).toISOString(),
    ...overrides,
  });
}

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(NOW);
});

afterEach(() => vi.useRealTimers());

describe("TurnTimer", () => {
  it("shows seconds left and counts down", () => {
    render(<TurnTimer room={playing(42)} onPrimary={false} />);
    expect(screen.getByText("42s")).toBeTruthy();
    act(() => vi.advanceTimersByTime(5_000));
    expect(screen.getByText("37s")).toBeTruthy();
  });

  it("uses minutes for long turns", () => {
    render(<TurnTimer room={playing(90)} onPrimary={false} />);
    expect(screen.getByText("1:30")).toBeTruthy();
  });

  it("corrects for a client clock that is off", () => {
    // The phone's clock is an hour behind the server: the turn still has 30 s, not 1 h 30 s.
    const serverAhead = new Date(NOW + 3_600_000).toISOString();
    render(<TurnTimer room={playing(30, { server_time: serverAhead })} onPrimary={false} />);
    expect(screen.getByText("30s")).toBeTruthy();
  });

  it("turns urgent in the last ten seconds and stops at zero", () => {
    render(<TurnTimer room={playing(12)} onPrimary={false} />);
    expect(screen.getByText("12s").className).not.toContain("bg-bomb");
    act(() => vi.advanceTimersByTime(3_000));
    expect(screen.getByText("9s").className).toContain("bg-bomb");
    act(() => vi.advanceTimersByTime(20_000));
    expect(screen.getByText("0s")).toBeTruthy();
  });

  it("renders nothing without a running turn", () => {
    const { container } = render(<TurnTimer room={makeRoom({ status: "lobby" })} onPrimary={false} />);
    expect(container.innerHTML).toBe("");
  });
});

describe("TurnProgress", () => {
  it("drains with the time left", () => {
    const { container } = render(<TurnProgress room={playing(45)} />);
    const bar = container.querySelector<HTMLDivElement>("[style]")!;
    expect(bar.style.width).toBe("75%");
    act(() => vi.advanceTimersByTime(40_000));
    expect(parseFloat(bar.style.width)).toBeCloseTo((5 / 60) * 100, 3);
    expect(bar.className).toContain("bg-bomb");
  });
});
