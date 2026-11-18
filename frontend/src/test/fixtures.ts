import type { Room } from "@/api/types";

export function makeRoom(overrides: Partial<Room> = {}): Room {
  return {
    code: "ABC234",
    status: "lobby",
    version: 1,
    host_id: 1,
    grid_size: 9,
    players: [
      { user_id: 1, username: "anna", seat: null, meal_amount: "210.00000000", meal_currency: "CZK" },
      { user_id: 2, username: "ben", seat: null, meal_amount: null, meal_currency: null },
    ],
    moves: [],
    current_player_id: null,
    bomb_commitment: null,
    bomb_index: null,
    bomb_salt: null,
    loser_id: null,
    finish_reason: null,
    turn_seconds: 60,
    turn_deadline: null,
    server_time: new Date().toISOString(),
    rates: null,
    totals: null,
    created_at: "2026-11-18T12:00:00Z",
    started_at: null,
    finished_at: null,
    ...overrides,
  };
}
