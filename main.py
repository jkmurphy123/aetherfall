from __future__ import annotations
import sys
import pygame
import pygame_gui

from model import make_demo_state, Simulation
from commands import CommandBus, install_default_handlers, Command
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
