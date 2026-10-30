// Light / Dark switch (commercial sales-ready look).
"use client";

import { Moon, Sun } from "lucide-react";
import { useEffect, useState } from "react";
import { THEME_STORAGE_KEY, resolveTheme, type Theme } from "../lib/theme";

export default function ThemeToggle({ className = "" }: { className?: string }) {
  const [theme, setTheme] = useState<Theme>("light");

  useEffect(() => {
    setTheme(
      resolveTheme(document.documentElement.getAttribute("data-theme")),
    );
  }, []);

  function toggle() {
    const next: Theme = theme === "dark" ? "light" : "dark";
    setTheme(next);
    if (next === "dark") {
      document.documentElement.setAttribute("data-theme", "dark");
    } else {
      document.documentElement.removeAttribute("data-theme");
    }
    try {
      localStorage.setItem(THEME_STORAGE_KEY, next);
    } catch {
      // Private mode etc: the switch still works for this visit.
    }
  }

  const Icon = theme === "dark" ? Sun : Moon;
  return (
    <button
      type="button"
      onClick={toggle}
      title={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
      aria-label={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
      className={`inline-flex cursor-pointer items-center justify-center rounded-lg border border-border bg-surface-2 p-1.5 text-text-muted outline-none hover:text-text focus-visible:ring-2 focus-visible:ring-brand ${className}`}
    >
      <Icon size={15} aria-hidden />
    </button>
  );
}
