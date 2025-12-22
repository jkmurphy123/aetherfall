from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple, List
import time


# ---------- Core game concepts ----------

Inventory = Dict[str, int]


@dataclass
class Recipe:
    """
    Recipe definition for a ProcessingUnit.

    Two main behaviors:
      1) Transfer mode:
         - Moves 1 resource per activation from input -> output
         - transfer_resource can lock to a specific resource id, else choose any available.

      2) Craft mode:
         - Consumes 'inputs' from the unit's own inventory
         - Produces 'outputs' into the unit's own inventory
         - Power can be checked later.
    """
    id: str
    name: str
    mode: str = "craft"  # "craft" or "transfer"
    duration_turns: int = 1
    power_required: int = 0

    # craft mode fields
    inputs: Dict[str, int] = field(default_factory=dict)   # resource_id -> qty
    outputs: Dict[str, int] = field(default_factory=dict)  # resource_id -> qty

    # transfer mode fields
    transfer_resource: Optional[str] = None  # resource_id or None


@dataclass
class ProcessingUnit:
    id: str
    name: str
    kind: str
    pos: Tuple[float, float]  # world coords for map rendering

    input_id: Optional[str] = None
    output_id: Optional[str] = None

    inventory: Inventory = field(default_factory=dict)
    recipe: Optional[Recipe] = None

    status: str = "Running"  # Running / Stalled / Paused
    notes: str = ""

    # internal progress for duration-based actions
    _turn_progress: int = 0

    # optional future-friendly fields (safe to ignore for now)
    inventory_capacity: Optional[int] = None
    power_capacity: Optional[int] = None

    def inv_get(self, item_id: str) -> int:
        return int(self.inventory.get(item_id, 0))

    def inv_add(self, item_id: str, qty: int) -> None:
        if qty == 0:
            return
        self.inventory[item_id] = self.inv_get(item_id) + qty
        if self.inventory[item_id] <= 0:
            self.inventory.pop(item_id, None)

    def inv_remove(self, item_id: str, qty: int) -> bool:
        if self.inv_get(item_id) < qty:
            return False
        self.inv_add(item_id, -qty)
        return True


# ---------- Project management ----------

@dataclass
class Task:
    id: str
    name: str
    required: bool = True
    completed: bool = False


@dataclass
class Goal:
    id: str
    name: str
    required: bool = True
    tasks: List[Task] = field(default_factory=list)
    completed: bool = False  # derived


@dataclass
class Project:
    id: str
    name: str
    required: bool = True
    goals: List[Goal] = field(default_factory=list)
    completed: bool = False  # derived


# ---------- Game state ----------

@dataclass
class GameState:
    # simulation graph
    units: Dict[str, ProcessingUnit] = field(default_factory=dict)
    selected_unit_id: Optional[str] = None

    # projects/goals/tasks
    projects: List[Project] = field(default_factory=list)
    selected_pm_item: Optional[str] = None  # e.g. "project:x" / "goal:x/y" / "task:x/y/z"

    # logs + time
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

    def recompute_project_status(self) -> None:
        """
        Goal is complete when all REQUIRED tasks are completed.
        Project is complete when all REQUIRED goals are completed.
        Optional goals/tasks do not block completion.
        """
        for p in self.projects:
            for g in p.goals:
                req_tasks = [t for t in g.tasks if t.required]
                g.completed = (len(req_tasks) == 0) or all(t.completed for t in req_tasks)

            req_goals = [g for g in p.goals if g.required]
            p.completed = (len(req_goals) == 0) or all(g.completed for g in req_goals)

    def all_inventories_summary(self) -> Dict[str, int]:
        """
        Global resource counts across all units (by resource id).
        Useful for "Assets (Global)" views.
        """
        total: Dict[str, int] = {}
        for u in self.units.values():
            for rid, qty in u.inventory.items():
                total[rid] = total.get(rid, 0) + int(qty)
        return total


# ---------- Simulation ----------

class Simulation:
    """
    Turn-based simulation.
    Each tick_turn() increments sim_turn and processes each unit once.
    """
    def __init__(self, state: GameState):
        self.state = state

    def tick_turn(self) -> None:
        s = self.state
        if s.paused:
            return

        s.sim_turn += 1

        # stable iteration order for debuggability
        for uid in sorted(s.units.keys()):
            u = s.units[uid]
            if u.status != "Running":
                continue
            if not u.recipe:
                continue

            # duration gating
            u._turn_progress += 1
            dur = max(1, int(u.recipe.duration_turns))
            if u._turn_progress < dur:
                continue
            u._turn_progress = 0

            if u.recipe.mode == "transfer":
                self._process_transfer(u)
            else:
                self._process_craft(u)

    # ----- internals -----

    def _choose_transfer_item(self, source: ProcessingUnit, preferred: Optional[str]) -> Optional[str]:
        if preferred and source.inv_get(preferred) > 0:
            return preferred
        for rid, qty in source.inventory.items():
            if qty > 0:
                return rid
        return None

    def _process_transfer(self, u: ProcessingUnit) -> None:
        """
        Transfer rules:
          - If u.kind == ResourcePile: it can output directly to its output_id
          - Otherwise, transfer unit moves from its input_id -> output_id
        """
        s = self.state

        # Resource piles: input is None; output is where extracted resources go
        if u.kind == "ResourcePile":
            dst = s.get_unit(u.output_id)
            if not dst:
                return

            item = self._choose_transfer_item(u, u.recipe.transfer_resource)
            if not item:
                return

            if u.inv_remove(item, 1):
                dst.inv_add(item, 1)
                s.log(f"{u.name}: output 1 {item} -> {dst.name}")
            return

        # Transfer units: require input and output
        src = s.get_unit(u.input_id)
        dst = s.get_unit(u.output_id)
        if not src or not dst:
            return

        item = self._choose_transfer_item(src, u.recipe.transfer_resource)
        if not item:
            return

        if src.inv_remove(item, 1):
            dst.inv_add(item, 1)
            s.log(f"{u.name}: moved 1 {item} from {src.name} -> {dst.name}")

    def _process_craft(self, u: ProcessingUnit) -> None:
        """
        Crafting consumes inputs and produces outputs in the unit's own inventory.
        (Later: power checks, input links, output links, queues, etc.)
        """
        s = self.state
        r = u.recipe
        if not r:
            return

        # verify inputs exist
        for rid, qty in r.inputs.items():
            if u.inv_get(rid) < qty:
                return

        # consume
        for rid, qty in r.inputs.items():
            u.inv_remove(rid, qty)

        # produce
        for rid, qty in r.outputs.items():
            u.inv_add(rid, qty)

        # optional: auto-push outputs to output_id later; for now leave in local inventory
        produced = ", ".join([f"{qty} {rid}" for rid, qty in r.outputs.items()]) if r.outputs else "(nothing)"
        s.log(f"{u.name}: crafted {produced}")
