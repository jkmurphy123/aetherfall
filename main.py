from __future__ import annotations
import sys
import pygame
import pygame_gui

from model import Simulation
from config_loaders import load_resources, load_recipes, load_units
from commands import CommandBus, install_default_handlers, Command
from ui import UI, Layout
from tasks_loader import load_tasks, install_tasks_into_state
from project_manager import ProjectManager, install_project_manager_handlers


def main() -> int:
    pygame.init()

    layout = Layout(screen_size=(1280, 720))
    screen = pygame.display.set_mode(layout.screen_size)
    pygame.display.set_caption("Planet Crafter Skeleton (pygame-ce + pygame_gui)")

    manager = pygame_gui.UIManager(layout.screen_size)

    # create game state from config
    catalog = load_resources("data/resources.json")
    recipes = load_recipes("data/recipes.json", catalog)
    state = load_units("data/units.json", recipes, catalog)

    # after state is created
    projects = load_tasks("data/tasks.json")
    install_tasks_into_state(state, projects)

    sim = Simulation(state)

    bus = CommandBus(state)
    install_default_handlers(bus)

    pm = ProjectManager(state)
    install_project_manager_handlers(bus, pm)

    ui = UI(screen=screen, manager=manager, layout=layout, state=state, bus=bus, resources=catalog)

    clock = pygame.time.Clock()
    running = True

    # turn rate (turns per second)
    turn_accum = 0.0
    turns_per_sec = 2.0
    turn_dt = 1.0 / turns_per_sec

    while running:
        dt_s = clock.tick(60) / 1000.0

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
                break

            # global hotkeys
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                    break
                if event.key == pygame.K_SPACE:
                    bus.dispatch(Command("toggle_pause", {}))

            ui.process_event(event)

        # fix the deliberate bus dispatch mistake above (kept for teaching)
        # Replace that block with:
        # bus.dispatch(Command("toggle_pause", {}))

        # Run simulation ticks
        turn_accum += dt_s
        while turn_accum >= turn_dt:
            sim.tick_turn()
            turn_accum -= turn_dt

        # Draw
        screen.fill((0, 0, 0))
        ui.draw_map()
        ui.update(dt_s)
        manager.draw_ui(screen)

        pygame.display.flip()

    pygame.quit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
