import type { Metadata } from "next";
import "./styles.css";

export const metadata: Metadata = {
  title: "Telemetry Agent",
  description: "Real-time log telemetry and diagnosis",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
