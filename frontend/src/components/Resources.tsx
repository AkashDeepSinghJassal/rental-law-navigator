import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { usePrefs } from "../lib/prefs";
import type { Resource } from "../lib/types";

/** Official pages for this city and state, taken from the source library (no invented links). */
export function Resources({ state, city }: { state: string; city: string | null }) {
  const { t } = usePrefs();
  const [items, setItems] = useState<Resource[] | null>(null);
  useEffect(() => {
    let alive = true;
    api.resources(state, city).then((r) => alive && setItems(r)).catch(() => alive && setItems([]));
    return () => {
      alive = false;
    };
  }, [state, city]);
  return (
    <section className="card" aria-labelledby="res">
      <div className="card-title">
        <h3 id="res">{t("resources")}</h3>
      </div>
      {items === null ? (
        <div className="skeleton" style={{ height: 80 }} />
      ) : items.length === 0 ? (
        <p className="small muted" style={{ margin: 0 }}>{t("noResources")}</p>
      ) : (
        <ul className="res-list">
          {items.slice(0, 8).map((r) => (
            <li key={r.doc_id}>
              <a href={r.url} target="_blank" rel="noopener noreferrer">
                {r.title} ↗
              </a>
              <div className="small muted">
                {r.host} · {r.jurisdiction}
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
