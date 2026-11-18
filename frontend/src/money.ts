import type { Currency, DecimalString } from "./api/types";

const DIGITS: Record<Currency, number> = { CZK: 2, EUR: 2, BTC: 8 };

export function formatMoney(amount: DecimalString | number, currency: Currency): string {
  const value = Number(amount).toLocaleString("en-US", {
    minimumFractionDigits: currency === "BTC" ? 0 : 2,
    maximumFractionDigits: DIGITS[currency],
  });
  switch (currency) {
    case "CZK":
      return `${value} Kč`;
    case "EUR":
      return `€${value}`;
    case "BTC":
      return `₿${value}`;
  }
}

/** Rough client-side total for the lobby preview; final totals come from the server. */
export function estimateTotal(
  meals: { amount: DecimalString; currency: Currency }[],
  rates: Record<Currency, DecimalString>,
  target: Currency,
): number {
  const czk = meals.reduce((sum, m) => sum + Number(m.amount) * Number(rates[m.currency]), 0);
  return czk / Number(rates[target]);
}

export function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString("en-GB", { dateStyle: "medium", timeStyle: "short" });
}

export async function sha256Hex(text: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}
