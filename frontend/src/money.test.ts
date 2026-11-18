import { describe, expect, it } from "vitest";
import { estimateTotal, formatMoney, sha256Hex } from "./money";

describe("formatMoney", () => {
  it("formats koruna with two decimals and the Kč suffix", () => {
    expect(formatMoney("245", "CZK")).toBe("245.00 Kč");
    expect(formatMoney("1234.5", "CZK")).toBe("1,234.50 Kč");
  });

  it("formats euro with a leading symbol", () => {
    expect(formatMoney("11.9", "EUR")).toBe("€11.90");
  });

  it("rounds half-cents like the backend's two-decimal quantization", () => {
    expect(formatMoney("10.005", "EUR")).toBe("€10.01");
    expect(formatMoney("9.994", "CZK")).toBe("9.99 Kč");
  });

  it("shows bitcoin with up to eight decimals and no padding", () => {
    expect(formatMoney("0.00012000", "BTC")).toBe("₿0.00012");
    expect(formatMoney("0.000123456789", "BTC")).toBe("₿0.00012346");
    expect(formatMoney("1", "BTC")).toBe("₿1");
  });

  it("accepts numbers as well as decimal strings", () => {
    expect(formatMoney(544.509, "CZK")).toBe("544.51 Kč");
  });
});

describe("estimateTotal", () => {
  const rates = { CZK: "1", EUR: "25", BTC: "2000000" };

  it("sums meals of mixed currencies in the target currency", () => {
    const meals = [
      { amount: "250", currency: "CZK" as const },
      { amount: "12.5", currency: "EUR" as const },
    ];
    expect(estimateTotal(meals, rates, "CZK")).toBeCloseTo(562.5);
    expect(estimateTotal(meals, rates, "EUR")).toBeCloseTo(22.5);
    expect(estimateTotal(meals, rates, "BTC")).toBeCloseTo(0.00028125, 10);
  });

  it("is zero without meals", () => {
    expect(estimateTotal([], rates, "EUR")).toBe(0);
  });
});

describe("sha256Hex", () => {
  it("matches the backend's bomb commitment, so the fairness check agrees with the server", async () => {
    // From the backend: lunch.rooms.game.commitment(4, "f3a9c2e1d0b8a7f6e5d4c3b2a1908f7e")
    const expected = "b8345c294bf13441a216714178cfec3182f03a1add164a3f225488402a5ea078";
    expect(await sha256Hex("4:f3a9c2e1d0b8a7f6e5d4c3b2a1908f7e")).toBe(expected);
  });

  it("changes when the bomb position changes", async () => {
    expect(await sha256Hex("5:f3a9c2e1d0b8a7f6e5d4c3b2a1908f7e")).not.toBe(
      await sha256Hex("4:f3a9c2e1d0b8a7f6e5d4c3b2a1908f7e"),
    );
  });
});
