export type Currency = "CZK" | "EUR" | "BTC";
export const CURRENCIES: Currency[] = ["CZK", "EUR", "BTC"];

export type RoomStatus = "lobby" | "playing" | "finished";
export type FinishReason = "bomb" | "gave_up" | "timeout";

export const TURN_SECONDS_OPTIONS = [15, 30, 60, 120, 300] as const;

/** Decimal values are serialized as strings to keep precision. */
export type DecimalString = string;

export interface User {
  id: number;
  username: string;
}

export interface Account {
  id: number;
  username: string;
  email: string | null;
  has_password: boolean;
  google_email: string | null;
  google_linked: boolean;
}

export interface Providers {
  password: boolean;
  google: boolean;
}

export interface Player {
  user_id: number;
  username: string;
  seat: number | null;
  meal_amount: DecimalString | null;
  meal_currency: Currency | null;
}

export interface Move {
  user_id: number;
  cell: number;
  at: string;
}

export interface Room {
  code: string;
  status: RoomStatus;
  version: number;
  host_id: number;
  grid_size: number;
  players: Player[];
  moves: Move[];
  current_player_id: number | null;
  bomb_commitment: string | null;
  bomb_index: number | null;
  bomb_salt: string | null;
  loser_id: number | null;
  finish_reason: FinishReason | null;
  turn_seconds: number;
  turn_deadline: string | null;
  /** Server clock when the snapshot was made; used to correct client clock skew. */
  server_time: string;
  rates: Record<Currency, DecimalString> | null;
  totals: Record<Currency, DecimalString> | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface HistoryPlayer {
  user_id: number;
  username: string;
  meal_amount: DecimalString;
  meal_currency: Currency;
  paid: boolean;
}

export interface HistoryEntry {
  code: string;
  started_at: string;
  finished_at: string;
  players: HistoryPlayer[];
  loser_id: number;
  loser_username: string;
  finish_reason: FinishReason;
  totals: Record<Currency, DecimalString>;
  rates: Record<Currency, DecimalString>;
}

export interface HistoryPage {
  items: HistoryEntry[];
  has_more: boolean;
}

export interface RoomStateMessage {
  type: "room.state";
  room: Room;
}
