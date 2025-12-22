from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
import time


@dataclass
class Factory:
    id: str
    name: str
    kind: str
    pos: Tuple[float, float]  # world coordinates
    producing: Dict[str, float] = field(default_factory=dict)   # item -> rate / min
    consuming: Dict[str, float] = field(default_factory=dict)   # item -> rate / min
    status: str = "Running"  # Running / Stalled / Paused
    notes: str = ""


@dataclass
class GameState:
    assets: Dict[str, int] = field(default_factory=dict)
    factories: List[Factory] = field(default_factory=list)
    selected_factory_id: Optional[str] = None
    events: List[str] = field(default_factory=list)

    # sim controls
    paused: bool = False
    sim_time_s: float = 0.0

    def log(self, msg: str) -> None:
        stamp = time.strftime("%H:%M:%S")
        self.events.append(f"[{stamp}] {msg}")
        # keep log bounded
        if len(self.events) > 200:
            self.events = self.events[-200:]

    def get_selected_factory(self) -> Optional[Factory]:
        if self.selected_factory_id is None:
            return None
        for f in self.factories:
            if f.id == self.selected_factory_id:
                return f
        return None


def make_demo_state() -> GameState:
    s = GameState(
        assets={
            "Iron Ore": 320,
            "Carbon": 110,
            "Steel": 40,
            "Copper Ore": 180,
            "Copper Wire": 65,
            "Circuit Board": 8,
            "Food Rations": 52,
        }
    )
    s.factories = [
        Factory(
            id="fac-001",
            name="Red Dune Smelter",
            kind="Smelter",
            pos=(220, 160),
            producing={"Steel": 12.0},
            consuming={"Iron Ore": 24.0, "Carbon": 6.0},
            status="Running",
            notes="High efficiency with new lining."
        ),
        Factory(
            id="fac-002",
            name="Copper Spooler",
            kind="Assembler",
            pos=(520, 310),
            producing={"Copper Wire": 30.0},
            consuming={"Copper Ore": 18.0},
            status="Stalled",
            notes="Missing lubricant (or patience)."
        ),
        Factory(
            id="fac-003",
            name="Circuit Bench A",
            kind="Assembler",
            pos=(430, 520),
            producing={"Circuit Board": 2.0},
            consuming={"Copper Wire": 10.0, "Steel": 2.0},
            status="Running",
            notes=""
        ),
    ]
    s.log("Welcome. Colony console initialized.")
    return s


class Simulation:
    """
    Keep it intentionally simple: this is where you'll later implement
    production chains, crafting queues, power, logistics, etc.
    """
    def __init__(self, state: GameState):
        self.state = state

    def tick(self, dt_s: float) -> None:
        if self.state.paused:
            return

        self.state.sim_time_s += dt_s

        # Demo: every 5 seconds, emit a tiny status ping
        if int(self.state.sim_time_s) % 5 == 0:
            # avoid spamming by logging only on exact boundary
            # (we keep it naive but stable enough for now)
            pass
