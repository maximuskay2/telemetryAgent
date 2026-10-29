import ActivityBar from "./mission/ActivityBar";
import FirstVisitGate from "./mission/FirstVisitGate";
import MissionPanes from "./mission/Panes";
import { MissionProvider } from "./mission/state";
import TopBar from "./mission/TopBar";

// S10: Mission Control is the home page. The old dashboard lives on at
// /classic until the final video is recorded, then it goes away.
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
        </div>
      </MissionProvider>
    </FirstVisitGate>
  );
}
