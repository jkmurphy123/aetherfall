from __future__ import annotations
from dataclasses import dataclass
from typing import Callable, Dict, Optional, Any
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

    def cmd_select_factory(cmd: Command) -> None:
        fac_id = cmd.payload.get("factory_id")
        s.selected_factory_id = fac_id
        if fac_id:
            s.log(f"Selected: {fac_id}")

    def cmd_focus_selected(_: Command) -> None:
        fac = s.get_selected_factory()
        if not fac:
            s.log("No selection to focus.")
            return
        s.log(f"Focus requested for {fac.name} (hook this to camera later).")

    bus.register("pause", cmd_pause)
    bus.register("resume", cmd_resume)
    bus.register("toggle_pause", cmd_toggle_pause)
    bus.register("select_factory", cmd_select_factory)
    bus.register("focus_selected", cmd_focus_selected)
