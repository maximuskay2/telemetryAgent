import type { Metadata } from "next";
import HowTo from "../welcome/HowTo";
import WelcomeHeader from "../welcome/WelcomeHeader";

export const metadata: Metadata = {
  title: "How to use TelemetryAgent",
  description:
    "A short guide to the live demo, connecting production, and Mission Control.",
};

export default function GuidePage() {
  return (
    <div className="min-h-screen bg-bg font-sans text-text">
      <WelcomeHeader />
      <main className="mx-auto w-full max-w-5xl px-4 py-12">
        <HowTo />
      </main>
    </div>
  );
}
