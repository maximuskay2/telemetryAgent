import type { Metadata } from "next";
import "./styles.css";

export const metadata: Metadata = {
  title: "Telemetry Agent",
  description: "Autonomous incident diagnosis and verified repair",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body>{children}</body>
    </html>
  );
}
