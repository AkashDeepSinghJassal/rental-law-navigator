import { useState } from "react";
import { governing, money, parseDepositMonths, parseFeeCap, parsePercentCap } from "../lib/domain";
import { usePrefs } from "../lib/prefs";
import type { Category, Result } from "../lib/types";
import { StatusChip } from "./StatusChip";

/** Quick estimates from rules that state a simple number. Nothing is shown when the text has no clear figure. */
export function Calculators({ byCat }: { byCat: Record<Category, Result[]> }) {
  const { t, lang } = usePrefs();
  const [rent, setRent] = useState("2000");
  const rentN = Number(rent) || 0;

  const live = (c: Category) => byCat[c].filter((r) => r.result === "applies" || r.result === "unknown");
  const capRule = live("rent_increase_limits").find((r) => parsePercentCap(r.rule.key_value));
  const cap = capRule ? parsePercentCap(capRule.rule.key_value) : null;
  const depRule = live("security_deposits").find((r) => parseDepositMonths(`${r.rule.key_value ?? ""}. ${r.rule.requirement}`));
  const months = depRule ? parseDepositMonths(`${depRule.rule.key_value ?? ""}. ${depRule.rule.requirement}`) : null;
  const feeRule = live("application_screening_fees").find((r) => parseFeeCap(r.rule.key_value));
  const fee = feeRule ? parseFeeCap(feeRule.rule.key_value) : null;
  const rentGov = governing(byCat.rent_increase_limits);

  const any = cap || months || fee != null;
  return (
    <section className="card no-print" aria-labelledby="calc">
      <div className="card-title">
        <h3 id="calc">{t("tools")}</h3>
      </div>
      {!any ? (
        <p className="small muted" style={{ margin: 0 }}>
          {t("noCalc")}
        </p>
      ) : (
        <>
          {(cap || months) && (
            <label className="field">
              {t("rentNow")}
              <input className="input" type="number" min={0} inputMode="decimal" value={rent} onChange={(e) => setRent(e.target.value)} />
            </label>
          )}
          {cap && capRule && (
            <div className="calc-out">
              <div className="small muted">
                {t("maxIncrease")} {capRule.rule.title}
              </div>
              <b>
                {cap.ceiling ? "≤ " : ""}
                {money((rentN * cap.percent) / 100, lang)}
              </b>{" "}
              <span className="small">
                ({cap.ceiling ? "≤ " : ""}
                {cap.percent}% → {money(rentN * (1 + cap.percent / 100), lang)})
              </span>
              <div style={{ marginTop: 6 }}>
                <StatusChip status={capRule.result} />
                {rentGov && rentGov.team_rule_id !== capRule.team_rule_id && (
                  <span className="small muted"> · another rule may govern here</span>
                )}
              </div>
            </div>
          )}
          {months && depRule && (
            <div className="calc-out">
              <div className="small muted">
                {t("maxDeposit")} {depRule.rule.title}
              </div>
              <b>{money(rentN * months, lang)}</b> <span className="small">({months}× rent)</span>
              <div style={{ marginTop: 6 }}>
                <StatusChip status={depRule.result} />
              </div>
            </div>
          )}
          {fee != null && feeRule && (
            <div className="calc-out">
              <div className="small muted">{t("feeCap")}</div>
              <b>{money(fee, lang)}</b> <span className="small">· {feeRule.rule.title}</span>
              <div style={{ marginTop: 6 }}>
                <StatusChip status={feeRule.result} />
              </div>
            </div>
          )}
          <p className="small muted" style={{ marginBottom: 0 }}>
            {t("calcNote")}
          </p>
        </>
      )}
    </section>
  );
}
