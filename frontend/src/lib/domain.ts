import type { Category, Result, ResultStatus } from "./types";

export const CATEGORIES: Category[] = [
  "rent_increase_limits",
  "just_cause_eviction",
  "security_deposits",
  "application_screening_fees",
  "screening_restrictions",
  "algorithmic_rent_setting",
];

export const STATUS_ORDER: Record<ResultStatus, number> = {
  applies: 0,
  superseded: 1,
  unknown: 2,
  not_yet_effective: 3,
  pending: 4,
};

export const STATUS_ICON: Record<ResultStatus, string> = {
  applies: "✓",
  unknown: "?",
  superseded: "⇄",
  not_yet_effective: "◷",
  pending: "✎",
};

export function byCategory(results: Result[]): Record<Category, Result[]> {
  const out = Object.fromEntries(CATEGORIES.map((c) => [c, [] as Result[]])) as Record<Category, Result[]>;
  for (const r of results) out[r.rule.category]?.push(r);
  for (const c of CATEGORIES) {
    out[c].sort(
      (a, b) =>
        STATUS_ORDER[a.result] - STATUS_ORDER[b.result] ||
        (a.rule.level === "city" ? -1 : 1) - (b.rule.level === "city" ? -1 : 1),
    );
  }
  return out;
}

/** The rule that governs a topic here: the first that applies (city before state), else the first unknown. */
export function governing(results: Result[]): Result | null {
  return (
    results.find((r) => r.result === "applies" && r.rule.level === "city") ||
    results.find((r) => r.result === "applies") ||
    results.find((r) => r.result === "unknown") ||
    null
  );
}

export function statusCounts(results: Result[]): Record<ResultStatus, number> {
  const c: Record<ResultStatus, number> = { applies: 0, unknown: 0, superseded: 0, not_yet_effective: 0, pending: 0 };
  results.forEach((r) => (c[r.result] += 1));
  return c;
}

/* ---------------- dates & timeline ---------------- */

export function parsePartialDate(d: string | null | undefined): Date | null {
  if (!d) return null;
  const [y, m, day] = d.split("-").map(Number);
  if (!y) return null;
  return new Date(Date.UTC(y, (m || 1) - 1, day || 1));
}

export const iso = (d: Date) => d.toISOString().slice(0, 10);

export function addDays(isoDate: string, n: number): string {
  const d = new Date(`${isoDate}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + n);
  return iso(d);
}

export function fmtDate(d: string | null | undefined, lang: string): string {
  const p = parsePartialDate(d);
  if (!p || !d) return d || "";
  const parts = d.split("-").length;
  const opts: Intl.DateTimeFormatOptions =
    parts === 1 ? { year: "numeric" } : parts === 2 ? { year: "numeric", month: "long" } : { dateStyle: "medium" };
  return new Intl.DateTimeFormat(lang === "es" ? "es-US" : "en-US", { ...opts, timeZone: "UTC" }).format(p);
}

export interface TimelineItem {
  kind: "upcoming" | "recent" | "proposed";
  date: string | null;
  result: Result;
}

/** Changes at this address: rules taking effect later, recently effective rules, and proposed bills. */
export function timeline(results: Result[], asOf: string): TimelineItem[] {
  const now = parsePartialDate(asOf)!;
  const yearAgo = new Date(now);
  yearAgo.setUTCFullYear(yearAgo.getUTCFullYear() - 1);
  const items: TimelineItem[] = [];
  for (const r of results) {
    const eff = parsePartialDate(r.rule.effective_date);
    if (r.result === "not_yet_effective") items.push({ kind: "upcoming", date: r.rule.effective_date, result: r });
    else if (r.result === "pending") items.push({ kind: "proposed", date: null, result: r });
    else if (eff && eff > yearAgo && eff <= now && r.result !== "superseded")
      items.push({ kind: "recent", date: r.rule.effective_date, result: r });
  }
  const rank = { upcoming: 0, recent: 1, proposed: 2 } as const;
  return items.sort(
    (a, b) =>
      rank[a.kind] - rank[b.kind] ||
      (parsePartialDate(a.date)?.getTime() ?? 0) - (parsePartialDate(b.date)?.getTime() ?? 0),
  );
}

/* ---------------- calculators (parse only unambiguous rule text) ---------------- */

export interface PercentCap {
  percent: number; // the figure to apply
  ceiling: boolean; // true when only a maximum is known (e.g. "5% + CPI, max 10%")
}

export function parsePercentCap(text: string | null | undefined): PercentCap | null {
  if (!text) return null;
  const t = text.toLowerCase();
  if (/interest|bank rate|per year or lesser/.test(t)) return null; // deposit interest, not a rent cap
  const lead = t.match(/^\s*(\d+(?:\.\d+)?)\s*%/);
  if (lead && !/cpi|\+/.test(t.slice(0, lead[0].length + 4))) return { percent: Number(lead[1]), ceiling: false };
  const max = t.match(/max(?:imum)?\.?\s*(?:of\s*)?(\d+(?:\.\d+)?)\s*%/);
  if (max) return { percent: Number(max[1]), ceiling: true };
  return null;
}

const WORD_MONTHS: [RegExp, number][] = [
  [/one and one[- ]half|one and a half|1\.5|1½/, 1.5],
  [/\btwo\b|\b2\b/, 2],
  [/\bone\b|\b1\b/, 1],
];

/** "may not exceed one and one-half months' rent" -> 1.5 ; requires a limiting word. */
export function parseDepositMonths(text: string | null | undefined): number | null {
  if (!text) return null;
  const t = text.toLowerCase();
  const m = t.match(/(not exceed|no more than|up to|maximum|max\.?|cap(?:ped)? at|limit(?:ed)? to|equal to)([^.;]{0,60}?)months?['’]?s?\s+rent/);
  if (!m) return null;
  for (const [re, n] of WORD_MONTHS) if (re.test(m[2])) return n;
  return null;
}

/** "$50 maximum application fee" -> 50 */
export function parseFeeCap(text: string | null | undefined): number | null {
  if (!text) return null;
  const t = text.toLowerCase();
  const m = t.match(/\$\s?(\d+(?:\.\d{2})?)/);
  if (!m || !/(max|cap|not exceed|no more than|limit)/.test(t)) return null;
  return Number(m[1]);
}

export const money = (n: number, lang = "en") =>
  new Intl.NumberFormat(lang === "es" ? "es-US" : "en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 2,
  }).format(n);

export const sourceRef = (r: Result) => {
  const off = r.rule.quote_offsets?.quoted_span;
  return off ? { docId: r.rule.source_doc_id, start: off[0], end: off[1] } : null;
};
