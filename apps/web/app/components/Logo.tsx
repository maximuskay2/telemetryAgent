// Brand mark: a telemetry pulse trace resolving into a check.
// Inline SVG (crisp in both themes, no extra request); matches the
// docs/brand master and apps/web/public/logo.svg geometry.

export default function Logo({
  size = 18,
  className = "",
}: {
  size?: number;
  className?: string;
}) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 64 64"
      aria-hidden="true"
      className={className}
    >
      <rect width="64" height="64" rx="14" fill="#0866FF" />
      <path
        d="M7 37 H20 L26 49 L36 19 L42 37 H49 L57 25"
        fill="none"
        stroke="#FFFFFF"
        strokeWidth="7"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
