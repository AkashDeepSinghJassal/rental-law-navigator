import { useEffect, useState } from "react";
import { CustomAddressForm, SearchBox } from "../components/SearchBox";
import { api } from "../lib/api";
import { useRecent, useSavedPlaces, type Place } from "../lib/places";
import { usePrefs } from "../lib/prefs";
import { navigate } from "../lib/router";
import { reportHref } from "../lib/target";
import type { AddressHit } from "../lib/types";

const EXAMPLE_CITIES = ["San Francisco, CA", "Los Angeles, CA", "Hoboken, NJ", "Jersey City, NJ", "Cambridge, MA", "Boston, MA"];

export function Home() {
  const { t, audience, setAudience } = usePrefs();
  const [examples, setExamples] = useState<AddressHit[]>([]);
  const saved = useSavedPlaces();
  const recent = useRecent();

  useEffect(() => {
    api
      .searchAddresses("", 500)
      .then((all) => setExamples(EXAMPLE_CITIES.map((c) => all.find((a) => a.legal_city === c)).filter(Boolean) as AddressHit[]))
      .catch(() => setExamples([]));
  }, []);

  const go = (h: AddressHit) => navigate(reportHref({ kind: "sample", id: h.address_id }));
  const placeList = (items: Place[]) => (
    <div className="grid g3">
      {items.slice(0, 6).map((p) => (
        <a key={p.key} className="card example" href={reportHref(p.target)}>
          <b>{p.label}</b>
          <span className="small muted">{p.city ?? ""}</span>
        </a>
      ))}
    </div>
  );

  return (
    <>
      <section className="hero">
        <div className="container">
          <div className="audience">
            <span>{t("iAm")}</span>
            <div className="seg" role="group" aria-label={t("iAm")}>
              <button aria-pressed={audience === "renter"} onClick={() => setAudience("renter")}>
                {t("renter")}
              </button>
              <button aria-pressed={audience === "provider"} onClick={() => setAudience("provider")}>
                {t("provider")}
              </button>
            </div>
          </div>
          <h1>{t(audience === "renter" ? "heroTitle_renter" : "heroTitle_provider")}</h1>
          <p className="lede">{t(audience === "renter" ? "heroLede_renter" : "heroLede_provider")}</p>
        </div>
      </section>

      <div className="container search-panel">
        <div className="card" style={{ padding: 18 }}>
          <SearchBox onPick={go} />
          <details className="disclosure">
            <summary>{t("otherAddress")}</summary>
            <CustomAddressForm onSubmit={(a) => navigate(reportHref({ kind: "custom", address: a }))} />
          </details>
        </div>
      </div>

      <div className="container">
        {saved.items.length > 0 && (
          <section className="section">
            <h2>{t("saved")}</h2>
            {placeList(saved.items)}
          </section>
        )}
        {recent.items.length > 0 && (
          <section className="section">
            <h2>{t("recent")}</h2>
            {placeList(recent.items)}
          </section>
        )}
        <section className="section">
          <h2>{t("tryOne")}</h2>
          <div className="grid g3">
            {examples.length === 0
              ? Array.from({ length: 6 }, (_, i) => <div key={i} className="skeleton" style={{ height: 76 }} />)
              : examples.map((h) => (
                  <a key={h.address_id} className="card example" href={reportHref({ kind: "sample", id: h.address_id })}>
                    <b>{h.label}</b>
                    <span className="small muted">{h.legal_city}</span>
                  </a>
                ))}
          </div>
        </section>
        <section className="section">
          <h2>{t("howItWorks")}</h2>
          <div className="grid g3">
            {(["1", "2", "3"] as const).map((n) => (
              <div key={n} className="card">
                <div className="step-n">{n}</div>
                <h3 style={{ marginBottom: 6 }}>{t(`how${n}t` as const)}</h3>
                <p className="muted" style={{ margin: 0 }}>
                  {t(`how${n}` as const)}
                </p>
              </div>
            ))}
          </div>
        </section>
      </div>
    </>
  );
}
