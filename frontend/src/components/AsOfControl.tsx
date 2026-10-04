import { addDays, fmtDate, timeline } from "../lib/domain";
import { usePrefs } from "../lib/prefs";
import type { Result } from "../lib/types";

export const DEFAULT_AS_OF = "2026-10-01";

/** Time travel: today, one year out, and each known upcoming effective date. */
export function AsOfControl({ asOf, results, onChange }: { asOf: string; results: Result[]; onChange: (d: string) => void }) {
  const { t, lang } = usePrefs();
  const upcoming = timeline(results, asOf)
    .filter((i) => i.kind === "upcoming" && i.date && i.date.split("-").length === 3)
    .map((i) => addDays(i.date!, 1));
  const presets = [
    { d: DEFAULT_AS_OF, label: t("today") },
    { d: addDays(DEFAULT_AS_OF, 365), label: t("inOneYear") },
    ...[...new Set(upcoming)].map((d) => ({ d, label: fmtDate(d, lang) })),
  ];
  return (
    <div className="asof">
      <label className="field" style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
        {t("asOf")}
        <input className="input" type="date" value={asOf} onChange={(e) => e.target.value && onChange(e.target.value)} />
      </label>
      <div className="chips" role="group" aria-label={t("asOf")}>
        {presets.map((p) => (
          <button key={p.d} aria-pressed={p.d === asOf} onClick={() => onChange(p.d)}>
            {p.label}
          </button>
        ))}
      </div>
    </div>
  );
}
