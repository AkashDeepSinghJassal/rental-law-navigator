import { useEffect, useMemo, useState } from "react";
import { useOpenSource } from "../components/SourceDrawer";
import { TOPIC_ICON } from "../components/TopicSection";
import { api } from "../lib/api";
import { CATEGORIES, fmtDate } from "../lib/domain";
import { CATEGORY_LABEL } from "../lib/i18n";
import { usePrefs } from "../lib/prefs";
import { href, navigate } from "../lib/router";
import type { Category, LibraryRule } from "../lib/types";

export function Library({ params }: { params: URLSearchParams }) {
  const { t, lang } = usePrefs();
  const openSource = useOpenSource();
  const [rules, setRules] = useState<LibraryRule[] | null>(null);
  const [q, setQ] = useState("");
  const place = params.get("j") || "";
  const topic = (params.get("c") || "") as Category | "";

  useEffect(() => {
    api.rules().then(setRules).catch(() => setRules([]));
  }, []);

  const places = useMemo(() => [...new Set((rules || []).map((r) => r.jurisdiction))].sort(), [rules]);
  const shown = (rules || []).filter(
    (r) =>
      (!place || r.jurisdiction === place) &&
      (!topic || r.category === topic) &&
      (!q || `${r.title} ${r.requirement} ${r.citation} ${r.key_value ?? ""}`.toLowerCase().includes(q.toLowerCase())),
  );
  const status = (r: LibraryRule) =>
    r.failed ? ["s-pending", t("failed")] : !r.enacted ? ["s-pending", t("proposed")] : r.status === "not_yet_effective" ? ["s-not_yet_effective", t("notYet")] : ["s-applies", t("inForce")];
  const set = (k: string, v: string) => navigate(href("/library", { j: k === "j" ? v : place, c: k === "c" ? v : topic }));

  return (
    <div className="container">
      <header className="page-head">
        <h1>{t("libraryTitle")}</h1>
        <p>{t("libraryLede")}</p>
      </header>
      <div className="card filters">
        <label className="field" style={{ flex: "2 1 220px" }}>
          {t("searchRules")}
          <input className="input" type="search" value={q} onChange={(e) => setQ(e.target.value)} />
        </label>
        <label className="field">
          {t("location")}
          <select className="input" value={place} onChange={(e) => set("j", e.target.value)}>
            <option value="">{t("allPlaces")}</option>
            {places.map((p) => (
              <option key={p}>{p}</option>
            ))}
          </select>
        </label>
        <label className="field">
          {t("topic")}
          <select className="input" value={topic} onChange={(e) => set("c", e.target.value)}>
            <option value="">{t("allTopics")}</option>
            {CATEGORIES.map((c) => (
              <option key={c} value={c}>
                {CATEGORY_LABEL[lang][c]}
              </option>
            ))}
          </select>
        </label>
      </div>
      <p className="small muted">
        {rules ? `${shown.length} ${t("of")} ${rules.length}` : t("loading")}
      </p>
      {!rules && <div className="skeleton" style={{ height: 300 }} />}
      {shown.map((r) => {
        const [cls, label] = status(r);
        const off = r.quote_offsets?.quoted_span;
        return (
          <article key={r.team_rule_id} className="rule lib-item">
            <div className="row" style={{ alignItems: "center", gap: 8 }}>
              <span className={`chip ${cls}`}>{label}</span>
              <span className="chip neutral">
                <span aria-hidden="true">{TOPIC_ICON[r.category]}</span> {CATEGORY_LABEL[lang][r.category]}
              </span>
              <span className="small muted">{r.jurisdiction}</span>
            </div>
            <h3 style={{ margin: "10px 0 4px" }}>{r.title}</h3>
            <p style={{ margin: 0 }}>
              {r.requirement} {r.key_value && <b>{r.key_value}</b>}
            </p>
            <div className="small muted" style={{ marginTop: 6 }}>
              {r.citation}
              {r.effective_date && ` · ${fmtDate(r.effective_date, lang)}`}
              {r.conflict_flag && ` · ⚑ ${t("review")}`}
            </div>
            {off && (
              <button
                className="btn ghost small"
                style={{ paddingLeft: 0, marginTop: 4 }}
                onClick={() => openSource({ docId: r.source_doc_id, start: off[0], end: off[1], title: r.title, citation: r.citation })}
              >
                {t("viewSource")} →
              </button>
            )}
          </article>
        );
      })}
    </div>
  );
}
