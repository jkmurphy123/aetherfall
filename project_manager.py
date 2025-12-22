from __future__ import annotations
from typing import Optional
from model import GameState, Project, Goal, Task
from commands import Command, CommandBus


class ProjectManager:
    def __init__(self, state: GameState):
        self.state = state

    def find_task(self, project_id: str, goal_id: str, task_id: str) -> Optional[Task]:
        for p in self.state.projects:
            if p.id != project_id:
                continue
            for g in p.goals:
                if g.id != goal_id:
                    continue
                for t in g.tasks:
                    if t.id == task_id:
                        return t
        return None

    def toggle_task(self, project_id: str, goal_id: str, task_id: str) -> None:
        t = self.find_task(project_id, goal_id, task_id)
        if not t:
            self.state.log(f"Task not found: {project_id}/{goal_id}/{task_id}")
            return
        t.completed = not t.completed
        self.state.recompute_project_status()
        self.state.log(f"Task {'completed' if t.completed else 'reopened'}: {t.name}")


def install_project_manager_handlers(bus: CommandBus, pm: ProjectManager) -> None:
    s = bus.state

    def cmd_pm_select(cmd: Command) -> None:
        s.selected_pm_item = cmd.payload.get("key")
        # No log spam on selection by default; uncomment if you want.
        # s.log(f"PM selected: {s.selected_pm_item}")

    def cmd_pm_toggle_task(cmd: Command) -> None:
        pm.toggle_task(
            project_id=cmd.payload["project_id"],
            goal_id=cmd.payload["goal_id"],
            task_id=cmd.payload["task_id"]
        )

    bus.register("pm_select", cmd_pm_select)
    bus.register("pm_toggle_task", cmd_pm_toggle_task)
