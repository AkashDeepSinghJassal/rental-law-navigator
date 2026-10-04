import { useEffect, useMemo, useState } from "react";
import { AsOfControl, DEFAULT_AS_OF } from "../components/AsOfControl";
import { AtAGlance } from "../components/AtAGlance";
import { BuildingCard } from "../components/BuildingCard";
import { Calculators } from "../components/Calculators";
import { FactsPanel } from "../components/FactsPanel";
import { Resources } from "../components/Resources";
import { Timeline } from "../components/Timeline";
import { useToast } from "../components/Toast";
import { TopicSection } from "../components/TopicSection";
import { api } from "../lib/api";
import { byCategory, CATEGORIES } from "../lib/domain";
import { placeKey, useRecent, useSavedPlaces } from "../lib/places";
import { usePrefs } from "../lib/prefs";
import { href, navigate } from "../lib/router";
import { factsFromParams, reportHref } from "../lib/target";
import type { FactsInput, Lookup, Target } from "../lib/types";

export function Report({ target, params }: { target: Target; params: URLSearchParams }) {
  const { t, audience } = usePrefs();
  const asOf = params.get("as_of") || DEFAULT_AS_OF;
  const facts = useMemo(() => factsFromParams(params), [params]);
  const [data, setData] = useState<Lookup | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [printing, setPrinting] = useState(false);
  const saved = useSavedPlaces();
  const recent = useRecent();
  const toast = useToast();
  const key = placeKey(target);
  const reqKey = JSON.stringify([target, asOf, facts]);

  useEffect(() => {
    let alive = true;
    setErr(null);
    api
      .lookup(target, asOf, facts)
      .then((d) => {
        if (!alive) return;
        setData(d);
        const label = `${d.address.street_address}, ${d.address.postal_city}, ${d.address.state}`;
        recent.push({ key, label, city: d.stack.city, target });
      })
      .catch((e: Error) => alive && setErr(e.message));
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reqKey]);

  useEffect(() => {
    const before = () => setPrinting(true);
    const after = () => setPrinting(false);
    window.addEventListener("beforeprint", before);
    window.addEventListener("afterprint", after);
    return () => {
      window.removeEventListener("beforeprint", before);
      window.removeEventListener("afterprint", after);
    };
  }, []);

  const byCat = useMemo(() => (data ? byCategory(data.results) : null), [data]);
  const go = (nextAsOf: string, nextFacts: FactsInput = facts) => navigate(reportHref(target, nextAsOf, nextFacts));

  if (err)
    return (
      <div className="container" style={{ paddingTop: 30 }}>
        <div className="err">
          {t("error")}: {err}
        </div>
        <p>
          <a href="#/">← {t("back")}</a>
        </p>
      </div>
    );
  if (!data || !byCat)
    return (
      <div className="container" style={{ paddingTop: 30 }} aria-busy="true">
        <div className="skeleton" style={{ height: 40, width: "60%" }} />
        <div className="skeleton" style={{ height: 120, marginTop: 20 }} />
        <div className="skeleton" style={{ height: 300, marginTop: 20 }} />
        <span className="sr-only">{t("loading")}</span>
      </div>
    );

  const label = `${data.address.street_address}, ${data.address.postal_city}, ${data.address.state}`;
  const st = data.stack;
  const isSaved = saved.isSaved(key);

  return (
    <div className="container">
      <header className="report-head">
        <a href="#/" className="small">
          ← {t("back")}
        </a>
        <h1 style={{ marginTop: 8 }}>{label}</h1>
        <div className="trail" aria-label={t("location")}>
          <span>{st.state}</span>
          {st.county && (
            <>
              <span className="sep">›</span>
              <span>{st.county}</span>
            </>
          )}
          {st.city && (
            <>
              <span className="sep">›</span>
              <span className="chip neutral">{st.city}</span>
            </>
          )}
        </div>
        <div className="actions">
          <button
            className={`btn small ${isSaved ? "" : "secondary"}`}
            aria-pressed={isSaved}
            onClick={() => {
              saved.toggle({ key, label, city: st.city, target });
              toast.show(isSaved ? t("remove") : t("savedOk"));
            }}
          >
            {isSaved ? "★" : "☆"} {isSaved ? t("savedOk") : t("save")}
          </button>
          <button
            className="btn secondary small"
            onClick={() => {
              navigator.clipboard?.writeText(window.location.href).then(
                () => toast.show(t("copied")),
                () => toast.show(window.location.href),
              );
            }}
          >
            ⧉ {t("share")}
          </button>
          <button className="btn secondary small" onClick={() => window.print()}>
            ⎙ {t("print")}
          </button>
          {target.kind === "sample" && (
            <a className="btn secondary small" href={href("/compare", { ids: target.id })}>
              ⇆ {t("compareThis")}
            </a>
          )}
        </div>
      </header>

      <div className="card" style={{ marginTop: 18 }}>
        <AsOfControl asOf={asOf} results={data.results} onChange={(d) => go(d)} />
      </div>

      <div className="report-grid">
        <div>
          <div className="card">
            <AtAGlance byCat={byCat} all={data.results} />
          </div>
          <h2 style={{ marginTop: 30, fontSize: "1.35rem" }}>
            {t(audience === "renter" ? "sectionTitle_renter" : "sectionTitle_provider")}
          </h2>
          {CATEGORIES.map((c) => (
            <TopicSection key={c} cat={c} results={byCat[c]} expandAll={printing} />
          ))}
        </div>
        <aside className="sidebar">
          <Timeline results={data.results} asOf={asOf} onJump={(d) => go(d)} />
          <FactsPanel data={data} current={facts} onApply={(f) => go(asOf, f)} />
          <BuildingCard data={data} />
          <Calculators byCat={byCat} />
          <Resources state={st.state} city={st.city} />
        </aside>
      </div>
      {toast.node}
    </div>
  );
}
