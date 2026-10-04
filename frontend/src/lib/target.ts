import { href } from "./router";
import type { FactsInput, Target } from "./types";

/** Report URLs carry everything needed to reproduce the answer (shareable). */
export function reportHref(target: Target, asOf?: string, facts?: FactsInput): string {
  const f = facts || {};
  const common = {
    as_of: asOf,
    yb: f.year_built ?? undefined,
    u: f.units ?? undefined,
    sub: f.subsidized ?? undefined,
    occ: f.owner_occupied ?? undefined,
  };
  if (target.kind === "sample") return href(`/a/${encodeURIComponent(target.id)}`, common);
  const a = target.address;
  return href("/custom", { street: a.street, city: a.city, state: a.state, zip: a.zip, ...common });
}

export function targetFromRoute(path: string[], params: URLSearchParams): Target | null {
  if (path[0] === "a" && path[1]) return { kind: "sample", id: decodeURIComponent(path[1]) };
  if (path[0] === "custom" && params.get("street") && params.get("city")) {
    return {
      kind: "custom",
      address: {
        street: params.get("street")!,
        city: params.get("city")!,
        state: params.get("state") || "CA",
        zip: params.get("zip") || "",
      },
    };
  }
  return null;
}

export function factsFromParams(p: URLSearchParams): FactsInput {
  const num = (k: string) => (p.get(k) ? Number(p.get(k)) : null);
  const bool = (k: string) => (p.get(k) === "true" ? true : p.get(k) === "false" ? false : null);
  return { year_built: num("yb"), units: num("u"), subsidized: bool("sub"), owner_occupied: bool("occ") };
}
