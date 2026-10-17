// Tiny hash router: #/survey, #/options/auto ...
import { useEffect, useState } from "react";

export type Route = { page: string; arg?: string };

const parse = (): Route => {
  const [page = "", arg] = window.location.hash.replace(/^#\/?/, "").split("/");
  return { page: page || "overview", arg: arg ? decodeURIComponent(arg) : undefined };
};

export function useRoute(): Route {
  const [r, setR] = useState(parse);
  useEffect(() => {
    const f = () => { setR(parse()); window.scrollTo({ top: 0, behavior: "smooth" }); };
    window.addEventListener("hashchange", f);
    return () => window.removeEventListener("hashchange", f);
  }, []);
  return r;
}

export const go = (page: string, arg?: string) => { window.location.hash = `/${page}${arg ? "/" + encodeURIComponent(arg) : ""}`; };
