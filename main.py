from __future__ import annotations
import sys
import pygame
import pygame_gui

from model import make_demo_state, Simulation
from commands import CommandBus, install_default_handlers
from ui import UI, Layout


def main() -> int:
    pygame.init()

    layout = Layout(screen_size=(1280, 720))
    screen = pygame.display.set_mode(layout.screen_size)
    pygame.display.set_caption("Planet Crafter Skeleton (pygame-ce + pygame_gui)")

    manager = pygame_gui.UIManager(layout.screen_size)

    state = make_demo_state()
    sim = Simulation(state)

    bus = CommandBus(state)
    install_default_handlers(bus)

    ui = UI(screen=screen, manager=manager, layout=layout, state=state, bus=bus)

    clock = pygame.time.Clock()
    running = True

    # simulation tick rate (separate from FPS)
    sim_accum = 0.0
    sim_hz = 10.0   # 10 ticks/sec is plenty for a management sim starter
    sim_dt = 1.0 / sim_hz

    while running:
        dt_s = clock.tick(60) / 1000.0
        sim_accum += dt_s

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
                    bus.dispatch(("toggle_pause"))  # intentionally wrong to prove bus logging

            ui.process_event(event)

        # fix the deliberate bus dispatch mistake above (kept for teaching)
        # Replace that block with:
        # bus.dispatch(Command("toggle_pause", {}))

        # Run simulation ticks
        while sim_accum >= sim_dt:
            sim.tick(sim_dt)
            sim_accum -= sim_dt

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
