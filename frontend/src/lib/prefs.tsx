import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { DICTS, type Audience, type Lang, type TKey } from "./i18n";
import { load, save } from "./storage";

export type Theme = "system" | "light" | "dark";

interface Prefs {
  lang: Lang;
  audience: Audience;
  theme: Theme;
  setLang: (l: Lang) => void;
  setAudience: (a: Audience) => void;
  setTheme: (t: Theme) => void;
  t: (k: TKey) => string;
}

const Ctx = createContext<Prefs | null>(null);

export function PrefsProvider({ children }: { children: ReactNode }) {
  const [lang, setLang] = useState<Lang>(() => load("nav.lang", "en"));
  const [audience, setAudience] = useState<Audience>(() => load("nav.audience", "renter"));
  const [theme, setTheme] = useState<Theme>(() => load("nav.theme", "system"));

  useEffect(() => save("nav.lang", lang), [lang]);
  useEffect(() => save("nav.audience", audience), [audience]);
  useEffect(() => {
    save("nav.theme", theme);
    const root = document.documentElement;
    if (theme === "system") root.removeAttribute("data-theme");
    else root.setAttribute("data-theme", theme);
  }, [theme]);
  useEffect(() => {
    document.documentElement.lang = lang;
  }, [lang]);

  const value = useMemo<Prefs>(
    () => ({ lang, audience, theme, setLang, setAudience, setTheme, t: (k) => DICTS[lang][k] }),
    [lang, audience, theme],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function usePrefs(): Prefs {
  const v = useContext(Ctx);
  if (!v) throw new Error("usePrefs outside PrefsProvider");
  return v;
}
