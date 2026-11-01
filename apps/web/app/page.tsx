import Attribution from "./components/Attribution";
import ActivityBar from "./mission/ActivityBar";
import FirstVisitGate from "./mission/FirstVisitGate";
import MissionPanes from "./mission/Panes";
import { MissionProvider } from "./mission/state";
import TopBar from "./mission/TopBar";

// S10: Mission Control is the home page. The old dashboard lives on at
// /classic (kept while the demo video in docs/demo-video-script.md still
// references it).
// J4: first-time visitors land on /welcome instead (D6).
export default function Home() {
  return (
    <FirstVisitGate>
      <MissionProvider>
        <div className="flex min-h-screen flex-col bg-bg font-sans text-text">
          <TopBar />
          <div className="min-h-0 flex-1">
            <MissionPanes />
          </div>
          <ActivityBar />
          <footer className="border-t border-border py-2 text-center">
            <Attribution className="inline" />
          </footer>
        </div>
      </MissionProvider>
    </FirstVisitGate>
  );
}
