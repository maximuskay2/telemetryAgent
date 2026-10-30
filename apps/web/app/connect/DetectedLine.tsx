// L-N3: detected-language line for the /connect repo step.
// Renders nothing until the backend sends ConnectionTest.language (§3 H0).
"use client";

const LANGUAGE_LABELS: Record<string, string> = {
  python: "Python",
  javascript: "JavaScript",
  typescript: "TypeScript",
  java: "Java",
  kotlin: "Kotlin",
  go: "Go",
  rust: "Rust",
  php: "PHP",
};

export function languageLabel(language: string): string {
  return LANGUAGE_LABELS[language] ?? language;
}

export function DetectedLine({
  language,
  autofix,
}: {
  language?: string | null;
  autofix?: boolean | null;
}) {
  if (language == null || language === "") return null;
  const label = languageLabel(language);
  const suffix =
    autofix == null
      ? null
      : autofix
        ? "Auto-fix ✓"
        : "alerts and rollback only";
  return (
    <span className="text-xs text-text-muted">
      Detected: {label}
      {suffix != null ? ` · ${suffix}` : ""}
    </span>
  );
}
