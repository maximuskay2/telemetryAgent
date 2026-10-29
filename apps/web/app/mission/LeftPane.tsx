"use client";

import FridgeTile from "./FridgeTile";
import GatedTile from "./GatedTile";
import ShopTile from "./ShopTile";
import { useMission } from "./state";

/**
 * Topology + state rail: shop map above, freezer below.
 * Each tile is gated on its system being armed — delete or disarm a
 * system and its tile stops working until setup runs again.
 */
export default function LeftPane() {
  const { systems } = useMission();
  const shop = systems.find((s) => s.kind === "software") ?? null;
  const fridge = systems.find((s) => s.kind === "appliance") ?? null;
  const shopArmed = shop !== null && shop.status === "armed";
  const fridgeArmed = fridge !== null && fridge.status === "armed";

  return (
    <div className="flex min-h-0 flex-col gap-3 overflow-y-auto">
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
    </div>
  );
}
