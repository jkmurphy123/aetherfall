from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Tuple, List, Dict

import pygame
import pygame_gui
from pygame_gui.elements import UIPanel, UIButton, UILabel, UITextEntryLine, UISelectionList, UITextBox

from model import GameState, Factory
from commands import CommandBus, Command


@dataclass
class Layout:
    screen_size: Tuple[int, int] = (1280, 720)
    menu_h: int = 44
    bottom_h: int = 170
    left_w: int = 320
    right_w: int = 340
    pad: int = 8

    def rect_menu(self) -> pygame.Rect:
        return pygame.Rect(0, 0, self.screen_size[0], self.menu_h)

    def rect_bottom(self) -> pygame.Rect:
        return pygame.Rect(0, self.screen_size[1] - self.bottom_h, self.screen_size[0], self.bottom_h)

    def rect_left(self) -> pygame.Rect:
        y = self.menu_h
        h = self.screen_size[1] - self.menu_h - self.bottom_h
        return pygame.Rect(0, y, self.left_w, h)

    def rect_right(self) -> pygame.Rect:
        y = self.menu_h
        h = self.screen_size[1] - self.menu_h - self.bottom_h
        return pygame.Rect(self.screen_size[0] - self.right_w, y, self.right_w, h)

    def rect_center(self) -> pygame.Rect:
        y = self.menu_h
        h = self.screen_size[1] - self.menu_h - self.bottom_h
        x = self.left_w
        w = self.screen_size[0] - self.left_w - self.right_w
        return pygame.Rect(x, y, w, h)


class UI:
    def __init__(self, screen: pygame.Surface, manager: pygame_gui.UIManager, layout: Layout,
                 state: GameState, bus: CommandBus):
        self.screen = screen
        self.manager = manager
        self.layout = layout
        self.state = state
        self.bus = bus

        # ---- menu bar ----
        self.menu_panel = UIPanel(relative_rect=self.layout.rect_menu(), manager=self.manager)
        self.btn_pause = UIButton(pygame.Rect(8, 8, 90, 28), "Pause", manager=self.manager, container=self.menu_panel)
        self.btn_resume = UIButton(pygame.Rect(106, 8, 90, 28), "Resume", manager=self.manager, container=self.menu_panel)
        self.btn_focus = UIButton(pygame.Rect(204, 8, 130, 28), "Focus Selected", manager=self.manager, container=self.menu_panel)

        self.lbl_status = UILabel(pygame.Rect(350, 8, 600, 28), "", manager=self.manager, container=self.menu_panel)

        # ---- left: assets ----
        self.left_panel = UIPanel(self.layout.rect_left(), manager=self.manager)
        UILabel(pygame.Rect(8, 8, 220, 24), "Assets", manager=self.manager, container=self.left_panel)
        self.asset_search = UITextEntryLine(pygame.Rect(8, 36, self.layout.left_w - 16, 28), manager=self.manager, container=self.left_panel)
        self.asset_list = UISelectionList(
            pygame.Rect(8, 70, self.layout.left_w - 16, self.layout.rect_left().height - 78),
            item_list=[],
            manager=self.manager,
            container=self.left_panel
        )

        # ---- right: inspector ----
        self.right_panel = UIPanel(self.layout.rect_right(), manager=self.manager)
        UILabel(pygame.Rect(8, 8, 220, 24), "Inspector", manager=self.manager, container=self.right_panel)
        self.inspect_box = UITextBox(
            html_text="Select something on the map…",
            relative_rect=pygame.Rect(8, 36, self.layout.right_w - 16, self.layout.rect_right().height - 44),
            manager=self.manager,
            container=self.right_panel
        )

        # ---- bottom: event log ----
        self.bottom_panel = UIPanel(self.layout.rect_bottom(), manager=self.manager)
        UILabel(pygame.Rect(8, 8, 220, 24), "Event Log", manager=self.manager, container=self.bottom_panel)
        self.log_box = UITextBox(
            html_text="",
            relative_rect=pygame.Rect(8, 36, self.layout.rect_bottom().width - 16, self.layout.bottom_h - 44),
            manager=self.manager,
            container=self.bottom_panel
        )

        # ---- center: map viewport (custom drawn) ----
        self.map_rect = self.layout.rect_center()
        self._camera = pygame.Vector2(0, 0)  # world offset
        self._zoom = 1.0
        self._panning = False
        self._pan_anchor_mouse = pygame.Vector2(0, 0)
        self._pan_anchor_cam = pygame.Vector2(0, 0)

        # throttled UI refresh
        self._ui_accum = 0.0
        self._ui_refresh_hz = 6.0  # refresh UI about 6 times/second
        self._last_asset_filter = ""

        # initial populate
        self.refresh_all()

    # ---------- rendering ----------
    def draw_map(self) -> None:
        # background
        pygame.draw.rect(self.screen, (8, 8, 10), self.map_rect)
        pygame.draw.rect(self.screen, (40, 40, 50), self.map_rect, 1)

        # subtle grid
        grid_step = 80
        for x in range(self.map_rect.left, self.map_rect.right, grid_step):
            pygame.draw.line(self.screen, (18, 18, 24), (x, self.map_rect.top), (x, self.map_rect.bottom))
        for y in range(self.map_rect.top, self.map_rect.bottom, grid_step):
            pygame.draw.line(self.screen, (18, 18, 24), (self.map_rect.left, y), (self.map_rect.right, y))

        # world -> screen transform helpers
        def world_to_screen(p: pygame.Vector2) -> pygame.Vector2:
            # map rect local coordinates:
            local = (p - self._camera) * self._zoom
            return pygame.Vector2(self.map_rect.topleft) + local

        # factories as circles + labels
        font = pygame.font.Font(None, 20)
        selected_id = self.state.selected_factory_id

        for fac in self.state.factories:
            wp = pygame.Vector2(fac.pos)
            sp = world_to_screen(wp)

            # cull if outside map rect
            if not self.map_rect.collidepoint(int(sp.x), int(sp.y)):
                continue

            is_sel = (fac.id == selected_id)
            color = (120, 220, 180) if fac.status == "Running" else (220, 160, 80)
            if fac.status == "Paused":
                color = (150, 150, 160)

            r = 10 if not is_sel else 14
            pygame.draw.circle(self.screen, color, (int(sp.x), int(sp.y)), r)
            if is_sel:
                pygame.draw.circle(self.screen, (240, 240, 255), (int(sp.x), int(sp.y)), r + 3, 2)

            label = font.render(fac.name, True, (220, 220, 235))
            self.screen.blit(label, (sp.x + r + 6, sp.y - 10))

        # map HUD (zoom)
        hud = font.render(f"Zoom: {self._zoom:.2f}  |  Pan: {int(self._camera.x)}, {int(self._camera.y)}", True, (200, 200, 215))
        self.screen.blit(hud, (self.map_rect.left + 10, self.map_rect.top + 10))

    # ---------- input handling ----------
    def process_event(self, event: pygame.event.Event) -> None:
        # Let pygame_gui consume it first
        self.manager.process_events(event)

        if event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 2 and self.map_rect.collidepoint(event.pos):
                # middle mouse pan
                self._panning = True
                self._pan_anchor_mouse = pygame.Vector2(event.pos)
                self._pan_anchor_cam = self._camera.copy()

            elif event.button == 1 and self.map_rect.collidepoint(event.pos):
                # left click: select nearest factory
                fac = self.pick_factory_at_screen(event.pos)
                if fac:
                    self.bus.dispatch(Command("select_factory", {"factory_id": fac.id}))
                else:
                    self.bus.dispatch(Command("select_factory", {"factory_id": None}))

            elif event.button in (4, 5) and self.map_rect.collidepoint(event.pos):
                # mouse wheel up/down (some systems)
                self._apply_zoom(1.10 if event.button == 4 else 0.90, pivot=event.pos)

        elif event.type == pygame.MOUSEBUTTONUP:
            if event.button == 2:
                self._panning = False

        elif event.type == pygame.MOUSEWHEEL:
            # pygame 2.0+ wheel event
            if self.map_rect.collidepoint(pygame.mouse.get_pos()):
                factor = 1.10 if event.y > 0 else 0.90
                self._apply_zoom(factor, pivot=pygame.mouse.get_pos())

        elif event.type == pygame.MOUSEMOTION:
            if self._panning:
                cur = pygame.Vector2(event.pos)
                delta = (cur - self._pan_anchor_mouse) / max(self._zoom, 0.001)
                self._camera = self._pan_anchor_cam - delta

        elif event.type == pygame_gui.UI_BUTTON_PRESSED:
            if event.ui_element == self.btn_pause:
                self.bus.dispatch(Command("pause", {}))
            elif event.ui_element == self.btn_resume:
                self.bus.dispatch(Command("resume", {}))
            elif event.ui_element == self.btn_focus:
                self.bus.dispatch(Command("focus_selected", {}))

        elif event.type == pygame_gui.UI_TEXT_ENTRY_FINISHED:
            if event.ui_element == self.asset_search:
                self.refresh_assets()

    def _apply_zoom(self, factor: float, pivot: Tuple[int, int]) -> None:
        # zoom around a pivot point so it feels anchored
        old_zoom = self._zoom
        new_zoom = max(0.35, min(3.0, self._zoom * factor))
        if abs(new_zoom - old_zoom) < 1e-6:
            return

        pivot = pygame.Vector2(pivot)
        pivot_local = pivot - pygame.Vector2(self.map_rect.topleft)

        # world point under cursor before zoom:
        world_before = self._camera + (pivot_local / old_zoom)
        # update zoom:
        self._zoom = new_zoom
        # world point under cursor after zoom should remain the same:
        self._camera = world_before - (pivot_local / new_zoom)

    def pick_factory_at_screen(self, pos: Tuple[int, int]) -> Optional[Factory]:
        # convert screen pos -> world pos
        p = pygame.Vector2(pos)
        local = p - pygame.Vector2(self.map_rect.topleft)
        world = self._camera + (local / max(self._zoom, 0.001))

        best = None
        best_d2 = 999999.0
        for fac in self.state.factories:
            fp = pygame.Vector2(fac.pos)
            d2 = (fp - world).length_squared()
            if d2 < best_d2:
                best_d2 = d2
                best = fac

        # selection radius in world units (tweakable)
        if best and best_d2 <= (22.0 ** 2):
            return best
        return None

    # ---------- UI refresh ----------
    def update(self, dt_s: float) -> None:
        self.manager.update(dt_s)

        # throttle expensive UI rebuilds
        self._ui_accum += dt_s
        if self._ui_accum >= (1.0 / self._ui_refresh_hz):
            self._ui_accum = 0.0
            self.refresh_status()
            self.refresh_inspector()
            self.refresh_log()

            # update assets if filter changed (live-ish search)
            cur_filter = self.asset_search.get_text().strip().lower()
            if cur_filter != self._last_asset_filter:
                self._last_asset_filter = cur_filter
                self.refresh_assets()

    def refresh_all(self) -> None:
        self.refresh_status()
        self.refresh_assets()
        self.refresh_inspector()
        self.refresh_log()

    def refresh_status(self) -> None:
        paused = "PAUSED" if self.state.paused else "RUNNING"
        sel = self.state.get_selected_factory()
        sel_txt = sel.name if sel else "None"
        self.lbl_status.set_text(f"Sim: {paused}   |   Selected: {sel_txt}")

    def refresh_assets(self) -> None:
        filt = self.asset_search.get_text().strip().lower()
        items: List[str] = []
        for name, qty in sorted(self.state.assets.items(), key=lambda kv: kv[0].lower()):
            if filt and filt not in name.lower():
                continue
            items.append(f"{name}  [{qty}]")

        # pygame_gui selection list needs a full reset
        self.asset_list.set_item_list(items)

    def refresh_inspector(self) -> None:
        fac = self.state.get_selected_factory()
        if not fac:
            self.inspect_box.set_text("Select a factory on the map to inspect it.")
            return

        def fmt_rates(d: Dict[str, float]) -> str:
            if not d:
                return "None"
            return "<br>".join([f"{k}: {v:.1f}/min" for k, v in d.items()])

        html = (
            f"<b>{fac.name}</b><br>"
            f"Type: {fac.kind}<br>"
            f"Status: {fac.status}<br><br>"
            f"<b>Producing</b><br>{fmt_rates(fac.producing)}<br><br>"
            f"<b>Consuming</b><br>{fmt_rates(fac.consuming)}<br><br>"
            f"{('<i>' + fac.notes + '</i>') if fac.notes else ''}"
        )
        self.inspect_box.set_text(html)

    def refresh_log(self) -> None:
        # show last N lines
        tail = self.state.events[-18:]
        html = "<br>".join([line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;") for line in tail])
        self.log_box.set_text(html)
