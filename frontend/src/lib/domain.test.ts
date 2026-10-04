import { describe, expect, it } from "vitest";
import { addDays, parseDepositMonths, parseFeeCap, parsePercentCap, timeline } from "./domain";
import type { Result } from "./types";

// Inputs below are real key_value / requirement strings from the knowledge base.
describe("parsePercentCap", () => {
  it("reads a plain local cap", () => {
    expect(parsePercentCap("1.6% (base rent x .016)")).toEqual({ percent: 1.6, ceiling: false });
    expect(parsePercentCap("0% (rent increases prohibited)")).toEqual({ percent: 0, ceiling: false });
    expect(parsePercentCap("1.0% (65% of Bay Area CPI increase)")).toEqual({ percent: 1, ceiling: false });
  });
  it("reads only the ceiling of a CPI formula", () => {
    expect(parsePercentCap("5% + CPI change, max 10%, per 12 months")).toEqual({ percent: 10, ceiling: true });
  });
  it("ignores deposit interest and text without a cap", () => {
    expect(parsePercentCap("5% per year or lesser bank rate")).toBeNull();
    expect(parsePercentCap("4.2% interest")).toBeNull();
    expect(parsePercentCap("No state cap; local ordinances allowed")).toBeNull();
    expect(parsePercentCap("30 days' written notice for increases under 10%")).toBeNull();
  });
});

describe("parseDepositMonths", () => {
  it("reads month multiples only with a limiting word", () => {
    expect(parseDepositMonths("A security deposit may not exceed one and one-half months' rent.")).toBe(1.5);
    expect(parseDepositMonths("Capped at one month's rent for most landlords")).toBe(1);
    expect(parseDepositMonths("Extra deposit returned after no more than 6 months")).toBeNull();
    expect(parseDepositMonths("annual interest on deposit")).toBeNull();
  });
});

describe("parseFeeCap", () => {
  it("reads a dollar cap", () => {
    expect(parseFeeCap("$50 maximum application fee (CPI-adjusted annually); penalties $500/$750/$1,000")).toBe(50);
    expect(parseFeeCap("Cost of report; reasonable application fees")).toBeNull();
  });
});

describe("timeline", () => {
  const r = (result: Result["result"], eff: string | null): Result =>
    ({
      team_rule_id: `r-${result}-${eff}`,
      result,
      explanation: "",
      conflict_flag: false,
      missing_facts: [],
      rule: { effective_date: eff, level: "state", category: "algorithmic_rent_setting" },
    }) as unknown as Result;
  it("orders upcoming, recent, proposed", () => {
    const items = timeline(
      [r("pending", null), r("applies", "2026-01-01"), r("not_yet_effective", "2027-07-01"), r("applies", "2020-01-01")],
      "2026-10-01",
    );
    expect(items.map((i) => i.kind)).toEqual(["upcoming", "recent", "proposed"]);
  });
  it("adds days across month ends", () => {
    expect(addDays("2027-06-30", 2)).toBe("2027-07-02");
  });
});
