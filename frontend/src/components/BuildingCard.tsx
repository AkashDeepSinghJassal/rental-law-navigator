import { usePrefs } from "../lib/prefs";
import type { Lookup } from "../lib/types";
import { MapView } from "./MapView";

export function BuildingCard({ data }: { data: Lookup }) {
  const { t } = usePrefs();
  const f = data.facts;
  const units =
    f.units ?? (f.units_min || f.units_max ? `${f.units_min ?? "?"}${f.units_max ? `–${f.units_max}` : "+"}` : null);
  const unitsDerived = !f.units && units != null;
  const fact = (k: string, v: string | number | null | undefined, note?: string | false) => (
    <div className="fact">
      <div className="k">{k}</div>
      <div className={`v${v == null || v === "" ? " na" : ""}`}>{v == null || v === "" ? t("notInData") : v}</div>
      {note && <div className="small muted">{note}</div>}
    </div>
  );
  const st = data.stack;
  return (
    <section className="card" aria-labelledby="bld">
      <div className="card-title">
        <h3 id="bld">{t("buildingFacts")}</h3>
        {st.method === "postal_fallback" && <span className="chip s-unknown">{t("matchedPostal")}</span>}
      </div>
      <div className="facts">
        {fact(t("yearBuilt"), f.year_built)}
        {fact(t("units"), units, unitsDerived && t("derived"))}
      </div>
      {f.use_description && <p className="small muted" style={{ margin: "10px 0 0" }}>{f.use_description}</p>}
      {st.lat != null && st.lon != null && (
        <MapView lat={st.lat} lon={st.lon} label={st.matched ?? data.address.street_address} />
      )}
      {st.note && <p className="small muted" style={{ marginBottom: 0 }}>{st.note}</p>}
    </section>
  );
}
