import { addDays, fmtDate, timeline } from "../lib/domain";
import { CATEGORY_LABEL } from "../lib/i18n";
import { usePrefs } from "../lib/prefs";
import type { Result } from "../lib/types";

/** What is changing at this address: upcoming effective dates, recent changes, proposed bills. */
export function Timeline({ results, asOf, onJump }: { results: Result[]; asOf: string; onJump: (d: string) => void }) {
  const { t, lang } = usePrefs();
  const items = timeline(results, asOf);
  return (
    <section className="card" aria-labelledby="tl">
      <div className="card-title">
        <h3 id="tl">{t("comingUp")}</h3>
      </div>
      {items.length === 0 ? (
        <p className="muted small" style={{ margin: 0 }}>
          {t("nothingComing")}
        </p>
      ) : (
        <ol className="timeline">
          {items.map((it) => (
            <li key={`${it.kind}-${it.result.team_rule_id}`} className={`k-${it.kind}`}>
              <div className="when">
                {it.kind === "proposed"
                  ? t("proposed")
                  : `${it.kind === "upcoming" ? t("takesEffect") : t("recently")} · ${fmtDate(it.date, lang)}`}
              </div>
              <div className="what">{it.result.rule.title}</div>
              <div className="small muted">
                {CATEGORY_LABEL[lang][it.result.rule.category]} · {it.result.rule.jurisdiction}
              </div>
              {it.kind === "upcoming" && it.date && it.date.split("-").length === 3 && (
                <button className="btn ghost small" style={{ paddingLeft: 0 }} onClick={() => onJump(addDays(it.date!, 1))}>
                  {t("seeOnDate")} →
                </button>
              )}
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
