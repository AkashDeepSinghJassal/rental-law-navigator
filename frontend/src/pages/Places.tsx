import { useSavedPlaces } from "../lib/places";
import { usePrefs } from "../lib/prefs";
import { href } from "../lib/router";
import { reportHref } from "../lib/target";

export function Places() {
  const { t } = usePrefs();
  const { items, remove } = useSavedPlaces();
  const sampleIds = items.filter((p) => p.target.kind === "sample").map((p) => (p.target as { id: string }).id);
  return (
    <div className="container">
      <header className="page-head">
        <h1>{t("placesTitle")}</h1>
        <p>{t("placesLede")}</p>
      </header>
      {items.length === 0 ? (
        <div className="card muted">{t("placesEmpty")}</div>
      ) : (
        <>
          {sampleIds.length > 1 && (
            <p>
              <a className="btn secondary small" href={href("/compare", { ids: sampleIds.slice(0, 3).join(",") })}>
                ⇆ {t("nav_compare")}
              </a>
            </p>
          )}
          <div className="grid" style={{ gap: 10 }}>
            {items.map((p) => (
              <div key={p.key} className="card place">
                <div>
                  <a href={reportHref(p.target)} style={{ fontWeight: 800, textDecoration: "none" }}>
                    {p.label}
                  </a>
                  <div className="small muted">{p.city ?? ""}</div>
                </div>
                <button className="btn ghost small" onClick={() => remove(p.key)}>
                  {t("remove")}
                </button>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
