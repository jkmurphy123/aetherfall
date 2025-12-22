from __future__ import annotations
import json
from typing import List
from model import Project, Goal, Task, GameState


def load_tasks(path: str) -> List[Project]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    projects: List[Project] = []
    for p in data.get("projects", []):
        proj = Project(
            id=p["id"],
            name=p.get("name", p["id"]),
            required=bool(p.get("required", True)),
            goals=[]
        )

        for g in p.get("goals", []):
            goal = Goal(
                id=g["id"],
                name=g.get("name", g["id"]),
                required=bool(g.get("required", True)),
                tasks=[]
            )

            for t in g.get("tasks", []):
                goal.tasks.append(Task(
                    id=t["id"],
                    name=t.get("name", t["id"]),
                    required=bool(t.get("required", True)),
                    completed=bool(t.get("completed", False))
                ))

            proj.goals.append(goal)

        projects.append(proj)

    return projects


def install_tasks_into_state(state: GameState, projects: List[Project]) -> None:
    state.projects = projects
    state.recompute_project_status()
    state.selected_pm_item = None
    state.log("Loaded projects/goals/tasks from tasks.json.")
