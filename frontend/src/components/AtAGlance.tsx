import { CATEGORIES, governing, statusCounts } from "../lib/domain";
import { CATEGORY_LABEL, STATUS_LABEL } from "../lib/i18n";
import { usePrefs } from "../lib/prefs";
import type { Category, Result, ResultStatus } from "../lib/types";
import { StatusChip } from "./StatusChip";
import { TOPIC_ICON } from "./TopicSection";

const BAR: Record<ResultStatus, string> = {
  applies: "var(--ok)",
  superseded: "var(--sup)",
  unknown: "var(--unk)",
  not_yet_effective: "var(--nye)",
  pending: "var(--pen)",
};

/** Headline tile per topic (the rule that governs here) + a status distribution bar. */
export function AtAGlance({ byCat, all }: { byCat: Record<Category, Result[]>; all: Result[] }) {
  const { t, lang } = usePrefs();
  const counts = statusCounts(all);
  const total = all.length || 1;
  return (
    <section aria-labelledby="glance">
      <div className="card-title">
        <h3 id="glance">{t("keyNumbers")}</h3>
        <span className="small muted">
          {all.length} {t("rulesFound")}
        </span>
      </div>
      <div className="summary-bar" role="img" aria-label={Object.entries(counts).map(([k, v]) => `${v} ${STATUS_LABEL[lang][k as ResultStatus]}`).join(", ")}>
        {(Object.keys(counts) as ResultStatus[]).map((k) =>
          counts[k] ? <span key={k} style={{ width: `${(100 * counts[k]) / total}%`, background: BAR[k] }} /> : null,
        )}
      </div>
      <div className="legend" style={{ marginBottom: 14 }}>
        {(Object.keys(counts) as ResultStatus[])
          .filter((k) => counts[k])
          .map((k) => (
            <span key={k} className={`chip s-${k}`}>
              {counts[k]} {STATUS_LABEL[lang][k]}
            </span>
          ))}
      </div>
      <div className="tiles">
        {CATEGORIES.map((c) => {
          const g = governing(byCat[c]);
          const fallback = byCat[c][0];
          const shown = g ?? fallback;
          return (
            <button
              key={c}
              className="tile"
              onClick={() => document.getElementById(`topic-${c}`)?.scrollIntoView({ behavior: "smooth" })}
            >
              <div className="label">
                <span aria-hidden="true">{TOPIC_ICON[c]}</span> {CATEGORY_LABEL[lang][c]}
              </div>
              <div className="value">{shown ? shown.rule.key_value || shown.rule.title : "—"}</div>
              {shown ? <StatusChip status={shown.result} /> : <span className="chip s-none">{t("noRule").split(".")[0]}</span>}
            </button>
          );
        })}
      </div>
    </section>
  );
}
