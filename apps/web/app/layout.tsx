import type { Metadata } from "next";
import { GeistMono } from "geist/font/mono";
import "./styles.css";
import "./tailwind.css";
import { THEME_INIT_SCRIPT } from "./lib/theme";

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
      <body className={GeistMono.variable}>
        <script dangerouslySetInnerHTML={{ __html: THEME_INIT_SCRIPT }} />
        {children}
      </body>
    </html>
  );
}
