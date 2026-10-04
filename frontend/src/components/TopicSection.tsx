import { CATEGORY_LABEL } from "../lib/i18n";
import { usePrefs } from "../lib/prefs";
import type { Category, Result } from "../lib/types";
import { RuleCard } from "./RuleCard";

export const TOPIC_ICON: Record<Category, string> = {
  rent_increase_limits: "↗",
  just_cause_eviction: "⌂",
  security_deposits: "$",
  application_screening_fees: "✉",
  screening_restrictions: "⚖",
  algorithmic_rent_setting: "⚙",
};

export function TopicSection({ cat, results, expandAll }: { cat: Category; results: Result[]; expandAll?: boolean }) {
  const { t, lang } = usePrefs();
  return (
    <section className="topic" id={`topic-${cat}`} aria-labelledby={`h-${cat}`}>
      <div className="topic-head">
        <span className="topic-icon" aria-hidden="true">
          {TOPIC_ICON[cat]}
        </span>
        <h2 id={`h-${cat}`}>{CATEGORY_LABEL[lang][cat]}</h2>
        <span className="chip neutral">{results.length}</span>
      </div>
      {results.length === 0 ? (
        <div className="empty-topic">{t("noRule")}</div>
      ) : (
        results.map((r) => <RuleCard key={r.team_rule_id} r={r} forceOpen={expandAll} />)
      )}
    </section>
  );
}
