import { useEffect, useState } from "react";

export interface Route {
  path: string[];
  params: URLSearchParams;
}

function parse(): Route {
  const [path, qs] = window.location.hash.replace(/^#/, "").split("?");
  return { path: (path || "/").split("/").filter(Boolean), params: new URLSearchParams(qs || "") };
}

export function useRoute(): Route {
  const [route, setRoute] = useState(parse);
  useEffect(() => {
    const on = () => {
      const next = parse();
      setRoute((prev) => {
        // only a new page scrolls to the top; changing a date or a fact keeps your place
        if (prev.path.join("/") !== next.path.join("/")) window.scrollTo({ top: 0 });
        return next;
      });
    };
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  return route;
}

export function href(path: string, params?: Record<string, string | number | boolean | null | undefined>): string {
  const qs = new URLSearchParams();
  Object.entries(params || {}).forEach(([k, v]) => {
    if (v !== null && v !== undefined && v !== "") qs.set(k, String(v));
  });
  const s = qs.toString();
  return `#${path}${s ? `?${s}` : ""}`;
}

export const navigate = (h: string) => {
  window.location.hash = h.replace(/^#/, "");
};

/** Replace query params without adding history entries or scrolling. */
export function replaceParams(params: Record<string, string | number | boolean | null | undefined>) {
  const [path] = window.location.hash.replace(/^#/, "").split("?");
  const next = href(path || "/", params);
  window.history.replaceState(null, "", next);
  window.dispatchEvent(new HashChangeEvent("hashchange"));
}
