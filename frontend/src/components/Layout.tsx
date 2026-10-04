import type { ReactNode } from "react";
import { useSavedPlaces } from "../lib/places";
import { usePrefs, type Theme } from "../lib/prefs";

const NAV = [
  { key: "home", href: "#/", label: "nav_home", icon: "⌕" },
  { key: "compare", href: "#/compare", label: "nav_compare", icon: "⇆" },
  { key: "places", href: "#/places", label: "nav_places", icon: "★" },
  { key: "library", href: "#/library", label: "nav_library", icon: "§" },
] as const;

const THEMES: Theme[] = ["system", "light", "dark"];
const THEME_ICON: Record<Theme, string> = { system: "◐", light: "☀", dark: "☾" };

export function Layout({ active, children }: { active: string; children: ReactNode }) {
  const { t, lang, setLang, theme, setTheme } = usePrefs();
  const { items } = useSavedPlaces();
  const nextTheme = THEMES[(THEMES.indexOf(theme) + 1) % THEMES.length];
  return (
    <>
      <a className="skip" href="#main-content" onClick={(e) => { e.preventDefault(); document.getElementById("main-content")?.focus(); }}>
        Skip to content
      </a>
      <div className="disclaimer" role="note">
        <b>{t("disclaimer").split(".")[0]}.</b> {t("disclaimer").split(".").slice(1).join(".").trim()}
      </div>
      <header className="header">
        <div className="container">
          <a className="brand" href="#/" aria-label={t("brand")}>
            <span className="brand-mark" aria-hidden="true">§</span>
            <span>{t("brand")}</span>
          </a>
          <nav className="nav" aria-label="Main">
            {NAV.map((n) => (
              <a key={n.key} href={n.href} aria-current={active === n.key ? "page" : undefined}>
                {t(n.label)}
                {n.key === "places" && items.length > 0 && <span className="badge">{items.length}</span>}
              </a>
            ))}
          </nav>
          <div className="header-tools">
            <div className="seg" role="group" aria-label={t("language")}>
              {(["en", "es"] as const).map((l) => (
                <button key={l} aria-pressed={lang === l} onClick={() => setLang(l)}>
                  {l.toUpperCase()}
                </button>
              ))}
            </div>
            <button
              className="icon-btn"
              onClick={() => setTheme(nextTheme)}
              aria-label={`${t("theme")}: ${theme}. Switch to ${nextTheme}`}
              title={`${t("theme")}: ${theme}`}
            >
              {THEME_ICON[theme]}
            </button>
          </div>
        </div>
      </header>
      <main id="main-content" tabIndex={-1} style={{ outline: "none" }}>
        {children}
      </main>
      <footer className="footer">
        <div className="container">
          <div>
            <b>{t("disclaimer")}</b> {t("disclaimerMore")}
          </div>
          <div>{t("aboutData")}</div>
        </div>
      </footer>
      <nav className="bottom-nav" aria-label="Main">
        {NAV.map((n) => (
          <a key={n.key} href={n.href} aria-current={active === n.key ? "page" : undefined}>
            <span className="ic" aria-hidden="true">{n.icon}</span>
            {t(n.label)}
          </a>
        ))}
      </nav>
    </>
  );
}
