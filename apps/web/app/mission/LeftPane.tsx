"use client";

import { useState } from "react";
import { useSession } from "../lib/session";
import FridgeTile from "./FridgeTile";
import GatedTile from "./GatedTile";
import ProdTile from "./ProdTile";
import ShopTile from "./ShopTile";
import { useMission } from "./state";

/** Demo-tagged walkthrough systems (bootstrap generates their ids). */
function isDemoSystem(system: { demo: boolean }): boolean {
  return system.demo;
}

/**
 * Topology + state rail: connected production systems on top, then the
 * demo shop map and freezer. Demo tiles stay gated on their system
 * being armed — delete or disarm a system and its tile stops working
 * until setup runs again. Signed-in users see only their provisioned
 * systems — no demo tiles — except during the guided demo tour.
 */
export default function LeftPane() {
  const { systems } = useMission();
  const { status } = useSession();
  const [tour] = useState(
    () =>
      typeof window !== "undefined" &&
      new URLSearchParams(window.location.search).get("tour") === "1",
  );
  const showDemo = status !== "signed-in" || tour;
  const prod = systems.filter((s) => !isDemoSystem(s));
  const shop =
    systems.find((s) => s.kind === "software" && isDemoSystem(s)) ?? null;
  const fridge =
    systems.find((s) => s.kind === "appliance" && isDemoSystem(s)) ?? null;
  const shopArmed = shop !== null && shop.status === "armed";
  const fridgeArmed = fridge !== null && fridge.status === "armed";

  return (
    <div className="flex min-h-0 flex-col gap-3 overflow-y-auto">
      {prod.map((system) => (
        <ProdTile key={system.system_id} system={system} />
      ))}
      {showDemo && (
        <>
          {shopArmed ? (
            <ShopTile systemId={shop?.system_id ?? null} />
          ) : (
            <GatedTile
              domain="software"
              title="Shop topology"
              systemId={shop?.system_id ?? null}
              systemName={shop?.name ?? null}
              status={shop?.status ?? null}
            />
          )}
          {fridgeArmed ? (
            <FridgeTile systemId={fridge?.system_id ?? null} />
          ) : (
            <GatedTile
              domain="appliance"
              title="Cold chain freezer"
              systemId={fridge?.system_id ?? null}
              systemName={fridge?.name ?? null}
              status={fridge?.status ?? null}
            />
          )}
        </>
      )}
    </div>
  );
}
