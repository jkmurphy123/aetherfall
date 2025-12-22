from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple, List
import time


Inventory = Dict[str, int]


@dataclass
class Recipe:
    """
    A recipe maps required inputs to produced outputs.

    For now we support a very simple "transfer" mode:
      - If unit has input_id and output_id, move 1 unit of a chosen resource from input to output per 'duration_turns'.

    Later you'll expand this to:
      - multiple inputs/outputs
      - per-tick rates
      - power requirements, capacity, byproducts, etc.
    """
    name: str
    duration_turns: int = 1
    # For generic crafting later:
    inputs: Dict[str, int] = field(default_factory=dict)
    outputs: Dict[str, int] = field(default_factory=dict)

    # For transfer-type units (drones, belts, etc.)
    transfer_resource: Optional[str] = None   # if None, choose automatically


@dataclass
class ProcessingUnit:
    id: str
    name: str
    kind: str
    pos: Tuple[float, float]  # world coordinates for map display

    input_id: Optional[str] = None
    output_id: Optional[str] = None

    inventory: Inventory = field(default_factory=dict)
    recipe: Optional[Recipe] = None

    status: str = "Running"  # Running / Stalled / Paused
    notes: str = ""

    # Internal timing accumulator for turn-based actions
    _turn_progress: int = 0

    def inv_get(self, item: str) -> int:
        return int(self.inventory.get(item, 0))

    def inv_add(self, item: str, qty: int) -> None:
        if qty == 0:
            return
        self.inventory[item] = self.inv_get(item) + qty
        if self.inventory[item] <= 0:
            self.inventory.pop(item, None)

    def inv_remove(self, item: str, qty: int) -> bool:
        if self.inv_get(item) < qty:
            return False
        self.inv_add(item, -qty)
        return True


@dataclass
class GameState:
    units: Dict[str, ProcessingUnit] = field(default_factory=dict)
    selected_unit_id: Optional[str] = None
    events: List[str] = field(default_factory=list)

    paused: bool = False
    sim_turn: int = 0

    def log(self, msg: str) -> None:
        stamp = time.strftime("%H:%M:%S")
        self.events.append(f"[{stamp}] {msg}")
        if len(self.events) > 300:
            self.events = self.events[-300:]

    def get_unit(self, unit_id: Optional[str]) -> Optional[ProcessingUnit]:
        if not unit_id:
            return None
        return self.units.get(unit_id)

    def get_selected_unit(self) -> Optional[ProcessingUnit]:
        return self.get_unit(self.selected_unit_id)

    def all_inventories_summary(self) -> Dict[str, int]:
        """
        Useful for a global 'assets' view: sum inventories across all units.
        (Later you may want to exclude 'in-transit' drone cargo, etc.)
        """
        total: Dict[str, int] = {}
        for u in self.units.values():
            for k, v in u.inventory.items():
                total[k] = total.get(k, 0) + int(v)
        return total


def make_demo_state() -> GameState:
    s = GameState()

    # A special "player stockpile" unit (your control panel warehouse)
    s.units["central_supply"] = ProcessingUnit(
        id="central_supply",
        name="Central Supply",
        kind="CentralSupply",
        pos=(980, 90),              # map position (can be wherever)
        input_id=None,
        output_id=None,
        inventory={
            "Food Rations": 52,
            "Steel": 10,
            "Copper Wire": 20,
        },
        recipe=None,
        notes="Player inventory. Everything ultimately ends up here (unless you forget)."
    )

    # A resource pile: null input; output will be set when a drone docks.
    # It “crafts” 1 wood into 1 wood (transfer semantics for now).
    s.units["wood_pile"] = ProcessingUnit(
        id="wood_pile",
        name="Wood Pile (North Copse)",
        kind="ResourcePile",
        pos=(220, 160),
        inventory={"Wood": 20},
        recipe=Recipe(name="Pile Transfer", duration_turns=1, transfer_resource="Wood"),
        notes="A conveniently game-shaped pile of wood."
    )

    # A simple drone: moves one resource from its input to its output.
    s.units["drone_01"] = ProcessingUnit(
        id="drone_01",
        name="Drone-01",
        kind="Drone",
        pos=(360, 240),
        input_id="wood_pile",      # starts docked to wood pile
        output_id=None,            # later: factory / stockpile
        inventory={},              # you can keep cargo here later; for now it transfers through
        recipe=Recipe(name="Drone Transfer", duration_turns=1, transfer_resource=None),
        notes="Basic hauler drone. One thing at a time."
    )

    # A smelter: later will consume ore+carbon and produce steel.
    # For now we give it a placeholder recipe (crafting can come next).
    s.units["smelter"] = ProcessingUnit(
        id="smelter",
        name="Red Dune Smelter",
        kind="Factory",
        pos=(520, 310),
        input_id=None,
        output_id="central_supply",  # outputs to stockpile (conceptually)
        inventory={"Iron Ore": 12, "Carbon": 4},
        recipe=Recipe(
            name="Smelt Steel",
            duration_turns=2,
            inputs={"Iron Ore": 2, "Carbon": 1},
            outputs={"Steel": 1}
        ),
        notes="Runs hot. Smells like progress."
    )

    # Start with selection on the drone
    s.selected_unit_id = "drone_01"

    s.log("Console initialized. Logistics graph online.")
    s.log("Drone-01 is docked to Wood Pile (no output link yet).")
    return s


class Simulation:
    """
    Turn-based sim. Each tick = one 'turn' for now.
    We'll keep it deterministic and easy to debug.
    """
    def __init__(self, state: GameState):
        self.state = state

    def tick_turn(self) -> None:
        s = self.state
        if s.paused:
            return

        s.sim_turn += 1

        # Process each unit once per turn.
        # For stability, iterate in sorted ID order (debug-friendly).
        for uid in sorted(s.units.keys()):
            u = s.units[uid]
            if u.status != "Running":
                continue
            if not u.recipe:
                continue

            # Count turns toward the unit's duration
            u._turn_progress += 1
            if u._turn_progress < max(1, u.recipe.duration_turns):
                continue
            u._turn_progress = 0

            # 1) Transfer-mode behavior (drones, piles, conveyors)
            if u.input_id and u.output_id:
                self._do_transfer(u)
                continue

            # 2) Resource pile can transfer directly to its output if connected
            # (Wood pile: input is None, output is drone)
            if (u.kind == "ResourcePile") and (u.output_id is not None):
                self._do_pile_output(u)
                continue

            # 3) Craft-mode behavior (factories)
            if u.recipe.inputs and u.recipe.outputs:
                self._do_crafting(u)
                continue

    def _choose_transfer_item(self, source: ProcessingUnit, preferred: Optional[str]) -> Optional[str]:
        if preferred and source.inv_get(preferred) > 0:
            return preferred
        # otherwise pick any available item
        for k, v in source.inventory.items():
            if v > 0:
                return k
        return None

    def _do_transfer(self, u: ProcessingUnit) -> None:
        s = self.state
        src = s.get_unit(u.input_id)
        dst = s.get_unit(u.output_id)
        if not src or not dst:
            return

        item = self._choose_transfer_item(src, u.recipe.transfer_resource if u.recipe else None)
        if not item:
            # nothing to move
            return

        if src.inv_remove(item, 1):
            dst.inv_add(item, 1)
            s.log(f"{u.name}: moved 1 {item} from {src.name} -> {dst.name}")

    def _do_pile_output(self, pile: ProcessingUnit) -> None:
        s = self.state
        dst = s.get_unit(pile.output_id)
        if not dst:
            return

        item = pile.recipe.transfer_resource if pile.recipe else None
        item = self._choose_transfer_item(pile, item)
        if not item:
            return

        if pile.inv_remove(item, 1):
            dst.inv_add(item, 1)
            s.log(f"{pile.name}: output 1 {item} -> {dst.name}")

    def _do_crafting(self, u: ProcessingUnit) -> None:
        s = self.state
        r = u.recipe
        if not r:
            return

        # Check inputs are available in unit inventory
        for item, qty in r.inputs.items():
            if u.inv_get(item) < qty:
                # Not enough inputs; don't spam logs every turn
                return

        # Consume inputs
        for item, qty in r.inputs.items():
            u.inv_remove(item, qty)

        # Produce outputs
        for item, qty in r.outputs.items():
            u.inv_add(item, qty)

        s.log(f"{u.name}: crafted {', '.join([f'{v} {k}' for k, v in r.outputs.items()])}")
