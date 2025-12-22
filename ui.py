from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Tuple, List, Dict

import pygame
import pygame_gui
from pygame_gui.elements import UIPanel, UIButton, UILabel, UITextEntryLine, UISelectionList, UITextBox

from model import GameState, ProcessingUnit
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
        UILabel(pygame.Rect(8, 8, 220, 24), "Assets (Global)", manager=self.manager, container=self.left_panel)
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

        # units as circles + labels
        font = pygame.font.Font(None, 20)
        # inside draw_map()

        selected_id = self.state.selected_unit_id

        for u in self.state.units.values():
            wp = pygame.Vector2(u.pos)
            sp = world_to_screen(wp)
            if not self.map_rect.collidepoint(int(sp.x), int(sp.y)):
                continue

            is_sel = (u.id == selected_id)

            # simple color coding by kind
            if u.kind == "Drone":
                color = (140, 200, 255)
            elif u.kind == "ResourcePile":
                color = (180, 230, 160)
            elif u.kind == "Factory":
                color = (230, 180, 120)
            else:
                color = (200, 200, 210)

            r = 10 if not is_sel else 14
            pygame.draw.circle(self.screen, color, (int(sp.x), int(sp.y)), r)
            if is_sel:
                pygame.draw.circle(self.screen, (240, 240, 255), (int(sp.x), int(sp.y)), r + 3, 2)

            label = font.render(u.name, True, (220, 220, 235))
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
                unit = self.pick_unit_at_screen(event.pos)
                if unit:
                    self.bus.dispatch(Command("select_unit", {"unit_id": unit.id}))
                else:
                    self.bus.dispatch(Command("select_unit", {"unit_id": None}))

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

    def pick_unit_at_screen(self, pos):
        p = pygame.Vector2(pos)
        local = p - pygame.Vector2(self.map_rect.topleft)
        world = self._camera + (local / max(self._zoom, 0.001))

        best = None
        best_d2 = 999999.0
        for u in self.state.units.values():
            up = pygame.Vector2(u.pos)
            d2 = (up - world).length_squared()
            if d2 < best_d2:
                best_d2 = d2
                best = u

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
        sel = self.state.get_selected_unit()
        sel_txt = sel.name if sel else "None"
        self.lbl_status.set_text(f"Sim: {paused}  |  Turn: {self.state.sim_turn}  |  Selected: {sel_txt}")

    def refresh_assets(self) -> None:
        filt = self.asset_search.get_text().strip().lower()

        summary = self.state.all_inventories_summary()
        items = []
        for name, qty in sorted(summary.items(), key=lambda kv: kv[0].lower()):
            if filt and filt not in name.lower():
                continue
            items.append(f"{name}  [{qty}]")

        self.asset_list.set_item_list(items)

    def refresh_inspector(self) -> None:
        u = self.state.get_selected_unit()
        if not u:
            self.inspect_box.set_text("Select a unit on the map to inspect it.")
            return

        def fmt_inv(inv):
            if not inv:
                return "None"
            return "<br>".join([f"{k}: {v}" for k, v in sorted(inv.items())])

        def fmt_link(unit_id):
            if not unit_id:
                return "None"
            x = self.state.get_unit(unit_id)
            return x.name if x else unit_id

        recipe_txt = "None"
        if u.recipe:
            r = u.recipe
            parts = [f"<b>{r.name}</b>", f"Duration: {r.duration_turns} turn(s)"]
            if r.transfer_resource:
                parts.append(f"Transfer resource: {r.transfer_resource}")
            if r.inputs:
                parts.append("<br><b>Inputs</b><br>" + "<br>".join([f"{k}: {v}" for k, v in r.inputs.items()]))
            if r.outputs:
                parts.append("<br><b>Outputs</b><br>" + "<br>".join([f"{k}: {v}" for k, v in r.outputs.items()]))
            recipe_txt = "<br>".join(parts)

        html = (
            f"<b>{u.name}</b><br>"
            f"Kind: {u.kind}<br>"
            f"Status: {u.status}<br><br>"
            f"<b>Links</b><br>"
            f"Input: {fmt_link(u.input_id)}<br>"
            f"Output: {fmt_link(u.output_id)}<br><br>"
            f"<b>Inventory</b><br>{fmt_inv(u.inventory)}<br><br>"
            f"{recipe_txt}<br><br>"
            f"{('<i>' + u.notes + '</i>') if u.notes else ''}"
        )
        self.inspect_box.set_text(html)


    def refresh_log(self) -> None:
        # show last N lines
        tail = self.state.events[-18:]
        html = "<br>".join([line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;") for line in tail])
        self.log_box.set_text(html)
