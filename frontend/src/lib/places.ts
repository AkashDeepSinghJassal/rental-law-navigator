import { useCallback, useEffect, useState } from "react";
import { load, save } from "./storage";
import type { Target } from "./types";

export interface Place {
  key: string; // stable id: sample id or custom address string
  label: string;
  city: string | null;
  target: Target;
  savedAt: string;
}

const SAVED = "nav.places";
const RECENT = "nav.recent";
const EVENT = "nav-places-changed";

export const placeKey = (t: Target) =>
  t.kind === "sample" ? t.id : `${t.address.street}|${t.address.city}|${t.address.state}|${t.address.zip}`.toLowerCase();

function useList(storageKey: string) {
  const [items, setItems] = useState<Place[]>(() => load(storageKey, [] as Place[]));
  useEffect(() => {
    const on = () => setItems(load(storageKey, [] as Place[]));
    window.addEventListener(EVENT, on);
    return () => window.removeEventListener(EVENT, on);
  }, [storageKey]);
  const write = useCallback(
    (next: Place[]) => {
      save(storageKey, next);
      setItems(next);
      window.dispatchEvent(new Event(EVENT));
    },
    [storageKey],
  );
  return [items, write] as const;
}

export function useSavedPlaces() {
  const [items, write] = useList(SAVED);
  const isSaved = (key: string) => items.some((p) => p.key === key);
  const toggle = (p: Omit<Place, "savedAt">) =>
    write(isSaved(p.key) ? items.filter((x) => x.key !== p.key) : [{ ...p, savedAt: new Date().toISOString() }, ...items]);
  const remove = (key: string) => write(items.filter((x) => x.key !== key));
  return { items, isSaved, toggle, remove };
}

export function useRecent() {
  const [items, write] = useList(RECENT);
  const push = (p: Omit<Place, "savedAt">) =>
    write([{ ...p, savedAt: new Date().toISOString() }, ...items.filter((x) => x.key !== p.key)].slice(0, 6));
  return { items, push };
}
