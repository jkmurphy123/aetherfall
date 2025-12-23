from __future__ import annotations

import sys
import pygame
import pygame_gui

from model import Simulation
from commands import Command, CommandBus, install_default_handlers
from ui import UI, Layout

from config_loaders import load_resources, load_recipes, load_units
from tasks_loader import load_tasks, install_tasks_into_state
from project_manager import ProjectManager, install_project_manager_handlers
from map_loader import load_map_state


def main() -> int:
    # ------------------------------------------------------------
    # pygame setup
    # ------------------------------------------------------------
    pygame.init()

    layout = Layout(screen_size=(1280, 720))
    screen = pygame.display.set_mode(layout.screen_size)
    pygame.display.set_caption("Aetherfall — Logistics Console")

    map_state = load_map_state(
        map_def_path="data/maps/argonaut_surface.json",
        save_slot_path="data/saves/save_slot_01.json"
    )

    manager = pygame_gui.UIManager(layout.screen_size, "data/theme.json")

    clock = pygame.time.Clock()

    # ------------------------------------------------------------
    # load configuration (JSON-driven)
    # ------------------------------------------------------------
    try:
        resources = load_resources("data/resources.json")
        recipes = load_recipes("data/recipes.json", resources)
        state = load_units("data/units.json", recipes, resources)

        projects = load_tasks("data/tasks.json")
        install_tasks_into_state(state, projects)

        print(f"Projects loaded: {len(state.projects)}")  #temp

    except Exception as e:
        print("FATAL: Failed to load configuration")
        print(e)
        pygame.quit()
        return 1

    # ------------------------------------------------------------
    # simulation + command bus
    # ------------------------------------------------------------
    sim = Simulation(state)

    bus = CommandBus(state)
    install_default_handlers(bus)

    project_manager = ProjectManager(state)
    install_project_manager_handlers(bus, project_manager)

    # ------------------------------------------------------------
    # UI
    # ------------------------------------------------------------
    ui = UI(
        screen=screen,
        manager=manager,
        layout=layout,
        state=state,
        bus=bus,
        resources=resources, 
        map_state=map_state
    )

    # ------------------------------------------------------------
    # main loop timing
    # ------------------------------------------------------------
    running = True

    # turn-based simulation rate
    turn_accum = 0.0
    turns_per_sec = 2.0
    turn_dt = 1.0 / turns_per_sec

    # ------------------------------------------------------------
    # main loop
    # ------------------------------------------------------------
    while running:
        dt_s = clock.tick(60) / 1000.0
        turn_accum += dt_s

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
                break

            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                    break

                if event.key == pygame.K_SPACE:
                    bus.dispatch(Command("toggle_pause", {}))

                # optional hot reload later
                # if event.key == pygame.K_r:
                #     reload configs

                mods = pygame.key.get_mods()

                if event.key == pygame.K_e:
                    map_state.reveal_all()
                    state.log("DEBUG: Reveal all tiles.")

                if event.key == pygame.K_h:
                    map_state.hide_all()
                    state.log("DEBUG: Hide all tiles.")

                if event.key == pygame.K_s and (mods & pygame.KMOD_CTRL):
                    map_state.save_to_disk()
                    state.log("Saved exploration to slot.")                

            ui.process_event(event)

        # run turn-based sim
        while turn_accum >= turn_dt:
            sim.tick_turn()
            turn_accum -= turn_dt

        # draw
        screen.fill((0, 0, 0))
        ui.draw_map()
        ui.update(dt_s)
        manager.draw_ui(screen)
        pygame.display.flip()

    pygame.quit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
