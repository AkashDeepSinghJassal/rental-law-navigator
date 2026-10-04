import { useEffect, useState } from "react";
import { DEFAULT_AS_OF } from "../components/AsOfControl";
import { SearchBox } from "../components/SearchBox";
import { StatusChip } from "../components/StatusChip";
import { TOPIC_ICON } from "../components/TopicSection";
import { api } from "../lib/api";
import { byCategory, CATEGORIES, governing } from "../lib/domain";
import { CATEGORY_LABEL } from "../lib/i18n";
import { usePrefs } from "../lib/prefs";
import { href, navigate } from "../lib/router";
import { reportHref } from "../lib/target";
import type { Lookup } from "../lib/types";

const MAX = 3;

export function Compare({ params }: { params: URLSearchParams }) {
  const { t, lang } = usePrefs();
  const ids = (params.get("ids") || "").split(",").filter(Boolean).slice(0, MAX);
  const [data, setData] = useState<Record<string, Lookup>>({});

  useEffect(() => {
    ids.forEach((id) => {
      if (!data[id])
        api
          .lookup({ kind: "sample", id }, DEFAULT_AS_OF)
          .then((d) => setData((prev) => ({ ...prev, [id]: d })))
          .catch(() => undefined);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ids.join(",")]);

  const setIds = (next: string[]) => navigate(href("/compare", { ids: next.join(",") }));
  const cols = ids.map((id) => ({ id, d: data[id] }));

  return (
    <div className="container">
      <header className="page-head">
        <h1>{t("compareTitle")}</h1>
        <p>{t("compareLede")}</p>
      </header>
      {ids.length < MAX && (
        <div className="card" style={{ marginBottom: 18 }}>
          <div className="small muted" style={{ fontWeight: 700, marginBottom: 8 }}>
            {t("addAddress")} ({ids.length}/{MAX})
          </div>
          <SearchBox onPick={(h) => !ids.includes(h.address_id) && setIds([...ids, h.address_id])} />
        </div>
      )}
      {ids.length > 0 && (
        <div className="card" style={{ overflowX: "auto", padding: 0 }}>
          <table className="cmp">
            <thead>
              <tr>
                <th style={{ width: 190 }}>{t("topic")}</th>
                {cols.map(({ id, d }) => (
                  <th key={id}>
                    {d ? (
                      <>
                        <a href={reportHref({ kind: "sample", id })} style={{ fontWeight: 800 }}>
                          {d.address.street_address}
                        </a>
                        <div className="small muted">{d.stack.city ?? d.stack.state}</div>
                      </>
                    ) : (
                      <div className="skeleton" style={{ height: 36 }} />
                    )}
                    <button className="btn ghost small" style={{ paddingLeft: 0 }} onClick={() => setIds(ids.filter((x) => x !== id))}>
                      {t("remove")}
                    </button>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {CATEGORIES.map((c) => (
                <tr key={c}>
                  <th scope="row">
                    <span aria-hidden="true">{TOPIC_ICON[c]}</span> {CATEGORY_LABEL[lang][c]}
                  </th>
                  {cols.map(({ id, d }) => {
                    const g = d ? governing(byCategory(d.results)[c]) : null;
                    const n = d ? byCategory(d.results)[c].length : 0;
                    return (
                      <td key={id}>
                        {!d ? (
                          <div className="skeleton" style={{ height: 50 }} />
                        ) : g ? (
                          <>
                            <StatusChip status={g.result} />
                            <span className="kv">{g.rule.key_value || g.rule.title}</span>
                            <div className="small muted">
                              {g.rule.jurisdiction} · {g.rule.citation}
                              {n > 1 ? ` · +${n - 1}` : ""}
                            </div>
                          </>
                        ) : (
                          <span className="chip s-none">{n ? `${n}` : "—"}</span>
                        )}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
