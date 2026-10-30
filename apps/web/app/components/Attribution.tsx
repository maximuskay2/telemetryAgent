// Model attribution (commercial Brand rule: style yes, brand no).
// Plain text only — never a Meta/Facebook logo or ownership claim.

export default function Attribution({ className = "" }: { className?: string }) {
  return (
    <p className={`text-xs text-text-faint ${className}`}>
      Built with Muse Spark
    </p>
  );
}
