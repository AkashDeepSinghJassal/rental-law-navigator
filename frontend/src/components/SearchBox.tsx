import { useEffect, useId, useRef, useState, type FormEvent } from "react";
import { api } from "../lib/api";
import { usePrefs } from "../lib/prefs";
import type { AddressHit, CustomAddress } from "../lib/types";

/** Accessible combobox over the sample addresses. */
export function SearchBox({ onPick, autoFocus }: { onPick: (hit: AddressHit) => void; autoFocus?: boolean }) {
  const { t } = usePrefs();
  const [q, setQ] = useState("");
  const [hits, setHits] = useState<AddressHit[]>([]);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const listId = useId();
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    let alive = true;
    const h = setTimeout(() => {
      api.searchAddresses(q, 8).then((r) => alive && (setHits(r), setActive(0))).catch(() => alive && setHits([]));
    }, 140);
    return () => {
      alive = false;
      clearTimeout(h);
    };
  }, [q, open]);

  useEffect(() => {
    const close = (e: MouseEvent) => !box.current?.contains(e.target as Node) && setOpen(false);
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);

  const pick = (h: AddressHit) => {
    setOpen(false);
    setQ(h.label);
    onPick(h);
  };

  return (
    <div className="search" ref={box}>
      <label className="sr-only" htmlFor={`${listId}-input`}>
        {t("searchLabel")}
      </label>
      <span className="glass" aria-hidden="true">⌕</span>
      <input
        id={`${listId}-input`}
        className="input"
        type="search"
        autoComplete="off"
        autoFocus={autoFocus}
        placeholder={t("searchPlaceholder")}
        value={q}
        role="combobox"
        aria-expanded={open}
        aria-controls={listId}
        aria-activedescendant={open && hits[active] ? `${listId}-${active}` : undefined}
        onFocus={() => setOpen(true)}
        onChange={(e) => {
          setQ(e.target.value);
          setOpen(true);
        }}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown") (e.preventDefault(), setActive((a) => Math.min(a + 1, hits.length - 1)));
          else if (e.key === "ArrowUp") (e.preventDefault(), setActive((a) => Math.max(a - 1, 0)));
          else if (e.key === "Enter" && hits[active]) (e.preventDefault(), pick(hits[active]));
          else if (e.key === "Escape") setOpen(false);
        }}
      />
      {open && (
        <div className="suggest" role="listbox" id={listId}>
          {hits.length === 0 && <div style={{ padding: 14 }} className="muted">{t("noMatch")}</div>}
          {hits.map((h, i) => (
            <div
              key={h.address_id}
              id={`${listId}-${i}`}
              role="option"
              aria-selected={i === active}
              onMouseEnter={() => setActive(i)}
              onMouseDown={(e) => {
                e.preventDefault();
                pick(h);
              }}
            >
              <span>{h.label}</span>
              <span className="city">{h.legal_city ?? ""}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export function CustomAddressForm({ onSubmit }: { onSubmit: (a: CustomAddress) => void }) {
  const { t } = usePrefs();
  const submit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    onSubmit({
      street: String(f.get("street") || "").trim(),
      city: String(f.get("city") || "").trim(),
      state: String(f.get("state") || "CA"),
      zip: String(f.get("zip") || "").trim(),
    });
  };
  return (
    <form className="row" onSubmit={submit} style={{ marginTop: 12 }}>
      <label className="field" style={{ flex: "2 1 220px" }}>
        {t("street")}
        <input className="input" name="street" required placeholder="123 Main St" />
      </label>
      <label className="field" style={{ flex: "1 1 140px" }}>
        {t("city")}
        <input className="input" name="city" required />
      </label>
      <label className="field">
        {t("state")}
        <select className="input" name="state">
          <option>CA</option>
          <option>NJ</option>
          <option>MA</option>
        </select>
      </label>
      <label className="field" style={{ width: 110 }}>
        {t("zip")}
        <input className="input" name="zip" inputMode="numeric" />
      </label>
      <button className="btn">{t("check")}</button>
    </form>
  );
}
