import { useEffect, useId, useState } from "react";
import { fmtDate, sourceRef } from "../lib/domain";
import { FACT_LABEL } from "../lib/i18n";
import { usePrefs } from "../lib/prefs";
import type { Result } from "../lib/types";
import { useOpenSource } from "./SourceDrawer";
import { StatusChip } from "./StatusChip";

export function RuleCard({ r, forceOpen }: { r: Result; forceOpen?: boolean }) {
  const { t, lang } = usePrefs();
  const [open, setOpen] = useState(false);
  const openSource = useOpenSource();
  const bodyId = useId();
  const ref = sourceRef(r);
  const rule = r.rule;
  useEffect(() => {
    if (forceOpen) setOpen(true);
  }, [forceOpen]);

  return (
    <article className="rule" data-open={open}>
      <button className="rule-head" aria-expanded={open} aria-controls={bodyId} onClick={() => setOpen((o) => !o)}>
        <StatusChip status={r.result} />
        <div>
          <div className="title">{rule.title}</div>
          <p className="req">
            {rule.requirement} {rule.key_value && <span className="kv">{rule.key_value}</span>}
          </p>
          <div className="meta">
            {rule.jurisdiction} · {rule.citation}
            {rule.effective_date && ` · ${t("takesEffect").toLowerCase()} ${fmtDate(rule.effective_date, lang)}`}
          </div>
        </div>
        <span className="chev" aria-hidden="true">
          ▸
        </span>
      </button>
      {open && (
        <div className="rule-body" id={bodyId}>
          <p>
            <b>{t("why")}:</b> {r.explanation}
          </p>
          {r.missing_facts.length > 0 && (
            <p className="small">
              <b>{t("needs")}:</b> {r.missing_facts.map((m) => FACT_LABEL[lang][m] ?? m).join(", ")}
            </p>
          )}
          {r.conflict_flag && (
            <div className="flag">
              ⚑ {t("review")}
              {rule.conflict_note ? `: ${rule.conflict_note.slice(0, 220)}` : ""}
            </div>
          )}
          {rule.interaction && <p className="small muted">{rule.interaction}</p>}
          <div className="small muted" style={{ fontWeight: 700, textTransform: "uppercase", letterSpacing: ".05em" }}>
            {t("quote")}
          </div>
          <blockquote className="law">“{rule.quoted_span}”</blockquote>
          <div className="row" style={{ alignItems: "center" }}>
            {ref && (
              <button
                className="btn secondary small"
                onClick={() => openSource({ ...ref, title: rule.title, citation: rule.citation })}
              >
                {t("viewSource")}
              </button>
            )}
            <span className="small muted">
              {rule.secondary_source ? `${t("secondary")} · ` : ""}
              {t("confidence")} {rule.confidence != null ? `${Math.round(rule.confidence * 100)}%` : "n/a"}
            </span>
          </div>
        </div>
      )}
    </article>
  );
}
