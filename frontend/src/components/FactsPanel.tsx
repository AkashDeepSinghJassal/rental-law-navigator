import type { FormEvent } from "react";
import { usePrefs } from "../lib/prefs";
import type { FactsInput, Lookup } from "../lib/types";

const ASKABLE = ["year_built", "units", "subsidized", "owner_occupied"] as const;

/** "Improve this answer": the person adds facts the records lack; the same deterministic checks re-run. */
export function FactsPanel({
  data,
  current,
  onApply,
}: {
  data: Lookup;
  current: FactsInput;
  onApply: (f: FactsInput) => void;
}) {
  const { t } = usePrefs();
  const needed = new Set<string>();
  data.results.forEach((r) => r.missing_facts.forEach((m) => needed.add(m)));
  (["year_built", "units"] as const).forEach((m) => data.facts.missing.includes(m) && needed.add(m));
  Object.entries(current).forEach(([k, v]) => v !== null && v !== undefined && needed.add(k));
  const ask = ASKABLE.filter((k) => needed.has(k));
  const using = Object.entries(current).filter(([, v]) => v !== null && v !== undefined);
  if (ask.length === 0) return null;

  const submit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    const num = (k: string) => (f.get(k) ? Number(f.get(k)) : null);
    const tri = (k: string) => (f.get(k) === "true" ? true : f.get(k) === "false" ? false : null);
    onApply({ year_built: num("year_built"), units: num("units"), subsidized: tri("subsidized"), owner_occupied: tri("owner_occupied") });
  };
  const yn = (name: string, label: string, val: boolean | null | undefined) => (
    <label className="field" style={{ width: "100%" }}>
      {label}
      <select className="input" name={name} defaultValue={val == null ? "" : String(val)}>
        <option value="">{t("notSure")}</option>
        <option value="true">{t("yes")}</option>
        <option value="false">{t("no")}</option>
      </select>
    </label>
  );
  return (
    <section className="card no-print" aria-labelledby="improve" style={{ borderStyle: "dashed", borderColor: "var(--accent)" }}>
      <div className="card-title">
        <h3 id="improve">{t("improve")}</h3>
      </div>
      <p className="small muted" style={{ marginTop: 0 }}>
        {t("improveLede")}
      </p>
      {using.length > 0 && (
        <p className="small">
          <span className="chip neutral">{t("usingYourFacts")}</span>{" "}
          <button className="btn ghost small" onClick={() => onApply({})}>
            {t("clear")}
          </button>
        </p>
      )}
      <form onSubmit={submit} className="row" key={JSON.stringify(current)}>
        {ask.includes("year_built") && (
          <label className="field" style={{ flex: "1 1 120px" }}>
            {t("yearBuilt")}
            <input className="input" name="year_built" type="number" min={1700} max={2030} defaultValue={current.year_built ?? ""} />
          </label>
        )}
        {ask.includes("units") && (
          <label className="field" style={{ flex: "1 1 120px" }}>
            {t("units")}
            <input className="input" name="units" type="number" min={1} defaultValue={current.units ?? ""} />
          </label>
        )}
        {ask.includes("subsidized") && yn("subsidized", t("govRent"), current.subsidized)}
        {ask.includes("owner_occupied") && yn("owner_occupied", t("ownerLives"), current.owner_occupied)}
        <button className="btn" style={{ width: "100%" }}>
          {t("recheck")}
        </button>
      </form>
    </section>
  );
}
