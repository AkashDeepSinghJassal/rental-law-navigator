import type {
  AddressHit,
  FactsInput,
  LibraryRule,
  Lookup,
  Resource,
  SourceExcerpt,
  Target,
} from "./types";

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(path, init);
  const body = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error((body as { detail?: string }).detail || r.statusText);
  return body as T;
}

const post = (body: unknown): RequestInit => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

const hasFacts = (f?: FactsInput) => !!f && Object.values(f).some((v) => v !== null && v !== undefined);

export const api = {
  searchAddresses: (q: string, limit = 8) =>
    req<AddressHit[]>(`/api/addresses?q=${encodeURIComponent(q)}&limit=${limit}`),

  lookup(target: Target, asOf: string, facts?: FactsInput): Promise<Lookup> {
    const qs = `as_of=${encodeURIComponent(asOf)}`;
    if (target.kind === "custom") {
      return req<Lookup>(`/api/lookup-custom?${qs}`, post({ ...target.address, ...facts }));
    }
    const path = `/api/lookup/${encodeURIComponent(target.id)}?${qs}`;
    return hasFacts(facts) ? req<Lookup>(path, post(facts)) : req<Lookup>(path);
  },

  rules: () => req<LibraryRule[]>("/api/rules"),

  source: (docId: string, start: number, end: number) =>
    req<SourceExcerpt>(`/api/source/${encodeURIComponent(docId)}?start=${start}&end=${end}&ctx=1200`),

  resources: (state: string, city: string | null) =>
    req<Resource[]>(`/api/resources?state=${encodeURIComponent(state)}${city ? `&city=${encodeURIComponent(city)}` : ""}`),
};
