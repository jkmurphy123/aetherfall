from __future__ import annotations
from dataclasses import dataclass
from typing import Callable, Dict, Any
from model import GameState


@dataclass(frozen=True)
class Command:
    name: str
    payload: Dict[str, Any]


class CommandBus:
    def __init__(self, state: GameState):
        self.state = state
        self.handlers: Dict[str, Callable[[Command], None]] = {}

    def register(self, name: str, fn: Callable[[Command], None]) -> None:
        self.handlers[name] = fn

    def dispatch(self, cmd: Command) -> None:
        handler = self.handlers.get(cmd.name)
        if not handler:
            self.state.log(f"Unknown command: {cmd.name}")
            return
        handler(cmd)


def install_default_handlers(bus: CommandBus) -> None:
    s = bus.state

    def cmd_pause(_: Command) -> None:
        s.paused = True
        s.log("Simulation paused.")

    def cmd_resume(_: Command) -> None:
        s.paused = False
        s.log("Simulation resumed.")

    def cmd_toggle_pause(_: Command) -> None:
        s.paused = not s.paused
        s.log("Simulation paused." if s.paused else "Simulation resumed.")

    def cmd_select_unit(cmd: Command) -> None:
        unit_id = cmd.payload.get("unit_id")
        s.selected_unit_id = unit_id
        if unit_id:
            u = s.get_unit(unit_id)
            s.log(f"Selected: {u.name if u else unit_id}")
        else:
            s.log("Selection cleared.")

    bus.register("pause", cmd_pause)
    bus.register("resume", cmd_resume)
    bus.register("toggle_pause", cmd_toggle_pause)
    bus.register("select_unit", cmd_select_unit)
