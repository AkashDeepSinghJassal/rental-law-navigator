import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { api } from "../lib/api";
import { usePrefs } from "../lib/prefs";
import type { SourceExcerpt } from "../lib/types";

export interface SourceRef {
  docId: string;
  start: number;
  end: number;
  title?: string;
  citation?: string;
}

const Ctx = createContext<(ref: SourceRef) => void>(() => {});
export const useOpenSource = () => useContext(Ctx);

/** One drawer for the whole app: shows the law text with the quoted passage highlighted. */
export function SourceDrawerProvider({ children }: { children: ReactNode }) {
  const { t } = usePrefs();
  const [ref, setRef] = useState<SourceRef | null>(null);
  const [data, setData] = useState<SourceExcerpt | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const closeBtn = useRef<HTMLButtonElement>(null);
  const markRef = useRef<HTMLElement>(null);
  const lastFocus = useRef<Element | null>(null);

  const open = useCallback((r: SourceRef) => {
    lastFocus.current = document.activeElement;
    setRef(r);
    setData(null);
    setErr(null);
    api.source(r.docId, r.start, r.end).then(setData).catch((e: Error) => setErr(e.message));
  }, []);

  const close = useCallback(() => {
    setRef(null);
    (lastFocus.current as HTMLElement | null)?.focus?.();
  }, []);

  useEffect(() => {
    if (!ref) return;
    closeBtn.current?.focus();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && close();
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [ref, close]);

  useEffect(() => {
    markRef.current?.scrollIntoView({ block: "center" });
  }, [data]);

  return (
    <Ctx.Provider value={open}>
      {children}
      {ref && (
        <>
          <div className="scrim" onClick={close} />
          <aside className="drawer" role="dialog" aria-modal="true" aria-label={t("quote")}>
            <div className="drawer-head">
              <div>
                <div style={{ fontWeight: 800, color: "var(--head)" }}>{ref.title ?? t("quote")}</div>
                {ref.citation && <div className="small muted">{ref.citation}</div>}
              </div>
              <button ref={closeBtn} className="icon-btn" onClick={close} aria-label="Close">
                ✕
              </button>
            </div>
            <div className="drawer-body">
              {err && <div className="err">{err}</div>}
              {!data && !err && <div className="skeleton" style={{ height: 240 }} />}
              {data && (
                <>
                  <p className="small muted" style={{ marginTop: 0 }}>
                    {data.in_corpus ? "Official source" : t("secondary")} · {data.retrieved_at ?? ""} ·{" "}
                    <a href={data.url} target="_blank" rel="noopener noreferrer">
                      {t("openOriginal")} ↗
                    </a>
                  </p>
                  <pre>
                    {data.before}
                    <mark ref={markRef}>{data.quote}</mark>
                    {data.after}
                  </pre>
                </>
              )}
            </div>
          </aside>
        </>
      )}
    </Ctx.Provider>
  );
}
