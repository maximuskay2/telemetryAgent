// Color-mode helpers (commercial sales-ready look).
// Light is the default: a first visit with no saved choice opens light.
// The choice persists in localStorage and is applied to <html> as
// data-theme before first paint (see THEME_INIT_SCRIPT in layout).

export type Theme = "light" | "dark";

export const THEME_STORAGE_KEY = "ta-theme";

/** Saved choice wins; anything else (including nothing) means light. */
export function resolveTheme(saved: string | null | undefined): Theme {
  return saved === "dark" ? "dark" : "light";
}

/** Inline head script: apply the saved theme before first paint. */
export const THEME_INIT_SCRIPT = `(function(){try{var t=localStorage.getItem("${THEME_STORAGE_KEY}");if(t==="dark"){document.documentElement.setAttribute("data-theme","dark");}}catch(e){}})();`;
