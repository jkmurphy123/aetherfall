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
    project_list_h: int = 170  # height of project panel area (same as bottom_h works too)

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

    def rect_bottom_left(self) -> pygame.Rect:
        # bottom-left half (event log)
        w = self.screen_size[0] // 2
        return pygame.Rect(0, self.screen_size[1] - self.bottom_h, w, self.bottom_h)

    def rect_bottom_right(self) -> pygame.Rect:
        # bottom-right half (project manager)
        w = self.screen_size[0] - (self.screen_size[0] // 2)
        x = self.screen_size[0] // 2
        return pygame.Rect(x, self.screen_size[1] - self.bottom_h, w, self.bottom_h)

    def rect_right_top(self) -> pygame.Rect:
        # right column above bottom strip
        y = self.menu_h
        h = self.screen_size[1] - self.menu_h - self.bottom_h
        return pygame.Rect(self.screen_size[0] - self.right_w, y, self.right_w, h)


class UI:
    def __init__(self, screen: pygame.Surface, manager: pygame_gui.UIManager, layout: Layout,
                 state: GameState, bus: CommandBus, resources, map_state):
        self.screen = screen
        self.manager = manager
        self.layout = layout
        self.state = state
        self.bus = bus
        self.resources = resources

        self.map_state = map_state
        self.map_state.map_image = pygame.image.load(self.map_state.map_def.image_path).convert()

        # ---- menu bar ----
        self.menu_panel = UIPanel(relative_rect=self.layout.rect_menu(), manager=self.manager)
        self.btn_pause = UIButton(pygame.Rect(8, 8, 90, 28), "Pause", manager=self.manager, container=self.menu_panel)
        self.btn_resume = UIButton(pygame.Rect(106, 8, 90, 28), "Resume", manager=self.manager, container=self.menu_panel)
        self.btn_focus = UIButton(pygame.Rect(204, 8, 130, 28), "Focus Selected", manager=self.manager, container=self.menu_panel)

        self.lbl_status = UILabel(pygame.Rect(350, 8, 600, 28), "", manager=self.manager, container=self.menu_panel)

        # ---- left: assets ----
        self.left_panel = UIPanel(self.layout.rect_left(), manager=self.manager)
        UILabel(pygame.Rect(8, 8, 220, 24), "Processing Units", manager=self.manager, container=self.left_panel)
        self.asset_search = UITextEntryLine(pygame.Rect(8, 36, self.layout.left_w - 16, 28), manager=self.manager, container=self.left_panel)
        self.asset_list = UISelectionList(
            pygame.Rect(8, 70, self.layout.left_w - 16, self.layout.rect_left().height - 78),
            item_list=[],
            manager=self.manager,
            container=self.left_panel
        )

        # ---- assets tree state ----
        self._expanded_units = set()           # unit_ids currently expanded
        self._asset_row_map = {}               # display_string -> metadata dict

        # ---- right: inspector ----
        self.right_panel = UIPanel(self.layout.rect_right_top(), manager=self.manager)
        UILabel(pygame.Rect(8, 8, 220, 24), "Inspector", manager=self.manager, container=self.right_panel)
        self.inspect_box = UITextBox(
            html_text="Select something on the map…",
            relative_rect=pygame.Rect(8, 36, self.layout.right_w - 16, self.layout.rect_right().height - 44),
            manager=self.manager,
            container=self.right_panel
        )

        # ---- bottom-left: event log ----
        self.log_panel = UIPanel(self.layout.rect_bottom_left(), manager=self.manager)
        UILabel(pygame.Rect(8, 8, 220, 24), "Event Log", manager=self.manager, container=self.log_panel)
        self.log_box = UITextBox(
            html_text="",
            relative_rect=pygame.Rect(8, 36, self.layout.rect_bottom_left().width - 16, self.layout.bottom_h - 44),
            manager=self.manager,
            container=self.log_panel
        )

        # ---- bottom-right: project manager ----
        self.pm_panel = UIPanel(self.layout.rect_bottom_right(), manager=self.manager)
        UILabel(pygame.Rect(8, 8, 240, 24), "Projects", manager=self.manager, container=self.pm_panel)

        self.pm_search = UITextEntryLine(
            pygame.Rect(8, 36, self.layout.rect_bottom_right().width - 16, 28),
            manager=self.manager,
            container=self.pm_panel
        )

        self.pm_list = UISelectionList(
            pygame.Rect(8, 70, self.layout.rect_bottom_right().width - 16, self.layout.bottom_h - 78),
            item_list=[],
            manager=self.manager,
            container=self.pm_panel
        )

        self._pm_expanded_projects = set()
        self._pm_expanded_goals = set()
        self._pm_row_map = {}
        self._last_pm_filter = ""


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

    def _handle_assets_click(self, row_text: str) -> None:
        meta = self._asset_row_map.get(row_text)
        if not meta:
            return

        if meta["type"] == "unit":
            unit_id = meta["unit_id"]
            if meta.get("toggle_expand", False):
                # expand/collapse
                if unit_id in self._expanded_units:
                    self._expanded_units.remove(unit_id)
                else:
                    self._expanded_units.add(unit_id)
                self.refresh_assets()
                return

            # normal unit click = select unit (same as map)
            self.bus.dispatch(Command("select_unit", {"unit_id": unit_id}))
            return

        # resource line clicked: for now do nothing (later: show tooltip, pin, etc.)
        if meta["type"] == "resource":
            # Example future: selecting resource could filter tasks/recipes
            return

    def _handle_pm_click(self, row_text: str) -> None:
        meta = self._pm_row_map.get(row_text)
        if not meta:
            return

        # Store selection via bus (separation of concerns)
        self.bus.dispatch(Command("pm_select", {"key": meta["key"]}))

        if meta["type"] == "task":
            # Single-click toggles completion (pleasantly direct)
            self.bus.dispatch(Command("pm_toggle_task", {
                "project_id": meta["project_id"],
                "goal_id": meta["goal_id"],
                "task_id": meta["task_id"],
            }))
            # Refresh the tree to update checkmarks/completions
            self.refresh_projects()

    def _handle_pm_double_click(self, row_text: str) -> None:
        meta = self._pm_row_map.get(row_text)
        if not meta:
            return

        if meta["type"] == "project":
            pid = meta["project_id"]
            if pid in self._pm_expanded_projects:
                self._pm_expanded_projects.remove(pid)
            else:
                self._pm_expanded_projects.add(pid)
            self.refresh_projects()

        elif meta["type"] == "goal":
            gid = meta["goal_key"]  # composite key
            if gid in self._pm_expanded_goals:
                self._pm_expanded_goals.remove(gid)
            else:
                self._pm_expanded_goals.add(gid)
            self.refresh_projects()

    # ---------- rendering ----------
    def draw_map(self) -> None:
        # panel background
        pygame.draw.rect(self.screen, (8, 8, 10), self.map_rect)
        pygame.draw.rect(self.screen, (40, 40, 50), self.map_rect, 1)

        m = self.map_state.map_def
        img = self.map_state.map_image

        # world -> screen
        def world_to_screen(p: pygame.Vector2) -> pygame.Vector2:
            local = (p - self._camera) * self._zoom
            return pygame.Vector2(self.map_rect.topleft) + local

        # ----- draw bitmap background -----
        world_w, world_h = m.world_size  # in world units
        map_top_left_screen = world_to_screen(pygame.Vector2(0, 0))

        # Scale bitmap to match world size * zoom
        # Assumption: bitmap represents entire map area.
        scaled_w = max(1, int(world_w * self._zoom))
        scaled_h = max(1, int(world_h * self._zoom))

        # Scaling each frame is OK to start; later we can cache by zoom step
        bg_scaled = pygame.transform.smoothscale(img, (scaled_w, scaled_h))
        self.screen.blit(bg_scaled, (map_top_left_screen.x, map_top_left_screen.y))

        # ----- fog of war overlay (draw only visible tiles) -----
        tile = m.tile_world_size
        # viewport in world coords
        viewport_w = self.map_rect.width
        viewport_h = self.map_rect.height
        world_tl = self._camera
        world_br = self._camera + pygame.Vector2(viewport_w / max(self._zoom, 0.001),
                                                viewport_h / max(self._zoom, 0.001))

        tx0 = max(0, int(world_tl.x // tile))
        ty0 = max(0, int(world_tl.y // tile))
        tx1 = min(m.width - 1, int(world_br.x // tile) + 1)
        ty1 = min(m.height - 1, int(world_br.y // tile) + 1)

        fog_color = (0, 0, 0)

        for ty in range(ty0, ty1 + 1):
            for tx in range(tx0, tx1 + 1):
                if self.map_state.is_explored(tx, ty):
                    continue

                # tile rect in world coords
                wx = tx * tile
                wy = ty * tile
                # convert to screen rect
                screen_pos = world_to_screen(pygame.Vector2(wx, wy))
                rect = pygame.Rect(
                    int(screen_pos.x),
                    int(screen_pos.y),
                    max(1, int(tile * self._zoom)),
                    max(1, int(tile * self._zoom))
                )
                # Clip to map panel so fog doesn't spill
                if rect.colliderect(self.map_rect):
                    pygame.draw.rect(self.screen, fog_color, rect)

        # ----- draw units on top -----
        font = pygame.font.Font(None, 20)
        selected_id = self.state.selected_unit_id

        for u in self.state.units.values():
            wp = pygame.Vector2(u.pos)
            sp = world_to_screen(wp)
            if not self.map_rect.collidepoint(int(sp.x), int(sp.y)):
                continue

            is_sel = (u.id == selected_id)
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

        hud = font.render(f"Zoom: {self._zoom:.2f}  |  Cam: {int(self._camera.x)}, {int(self._camera.y)}", True, (200, 200, 215))
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

        elif event.type == pygame_gui.UI_SELECTION_LIST_NEW_SELECTION:
            if event.ui_element == self.asset_list:
                self._handle_assets_click(event.text)

        elif event.type == pygame_gui.UI_SELECTION_LIST_DOUBLE_CLICKED_SELECTION:
            if event.ui_element == self.asset_list:
                meta = self._asset_row_map.get(event.text)
                if meta and meta["type"] == "unit":
                    unit_id = meta["unit_id"]
                    if unit_id in self._expanded_units:
                        self._expanded_units.remove(unit_id)
                    else:
                        self._expanded_units.add(unit_id)
                    self.refresh_assets()

        elif event.type == pygame_gui.UI_SELECTION_LIST_NEW_SELECTION:
            if event.ui_element == self.pm_list:
                self._handle_pm_click(event.text)

        elif event.type == pygame_gui.UI_SELECTION_LIST_DOUBLE_CLICKED_SELECTION:
            if event.ui_element == self.pm_list:
                self._handle_pm_double_click(event.text)

        elif event.type == pygame_gui.UI_TEXT_ENTRY_FINISHED:
            if event.ui_element == self.pm_search:
                self.refresh_projects()


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
        self.refresh_projects() 

    def refresh_status(self) -> None:
        paused = "PAUSED" if self.state.paused else "RUNNING"
        sel = self.state.get_selected_unit()
        sel_txt = sel.name if sel else "None"
        self.lbl_status.set_text(f"Sim: {paused}  |  Turn: {self.state.sim_turn}  |  Selected: {sel_txt}")

    def refresh_assets(self) -> None:
        filt = self.asset_search.get_text().strip().lower()

        rows = []
        self._asset_row_map = {}

        # Sort units by name for stable display
        units = sorted(self.state.units.values(), key=lambda u: u.name.lower())

        for u in units:
            # filter: if filter matches unit name OR any inventory item
            unit_match = (not filt) or (filt in u.name.lower())

            inv_items = sorted(u.inventory.items(), key=lambda kv: kv[0].lower())
            inv_match = False
            if filt and not unit_match:
                for item, qty in inv_items:
                    if filt in item.lower():
                        inv_match = True
                        break

            if filt and not (unit_match or inv_match):
                continue

            expanded = (u.id in self._expanded_units)
            tri = "▼" if expanded else "▶"

            unit_line = f"{tri}  {u.name}  ({u.kind})"
            rows.append(unit_line)
            self._asset_row_map[unit_line] = {"type": "unit", "unit_id": u.id}

            if expanded:
                if inv_items:
                    for item, qty in inv_items:
                        # resource child line
                        child = f"    • {item}: {qty}"
                        # apply filter to children too (if filter is active and didn't match unit name)
                        if filt and (not unit_match) and (filt not in item.lower()):
                            continue
                        rows.append(child)
                        self._asset_row_map[child] = {
                            "type": "resource",
                            "unit_id": u.id,
                            "resource": item
                        }
                else:
                    child = "    • (empty)"
                    rows.append(child)
                    self._asset_row_map[child] = {"type": "resource", "unit_id": u.id, "resource": None}

        self.asset_list.set_item_list(rows)


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

    def refresh_projects(self) -> None:
        filt = self.pm_search.get_text().strip().lower()

        rows = []
        self._pm_row_map = {}

        def checkbox(done: bool) -> str:
            return "☑" if done else "☐"

        for p in sorted(self.state.projects, key=lambda x: x.name.lower()):
            # filter match for project or any descendants
            project_matches = (not filt) or (filt in p.name.lower())

            # compute descendant match
            descendant_matches = False
            if filt and not project_matches:
                for g in p.goals:
                    if filt in g.name.lower():
                        descendant_matches = True
                        break
                    for t in g.tasks:
                        if filt in t.name.lower():
                            descendant_matches = True
                            break
                    if descendant_matches:
                        break

            if filt and not (project_matches or descendant_matches):
                continue

            tri = "▼" if p.id in self._pm_expanded_projects else "▶"
            req = "R" if p.required else "O"
            line_p = f"{tri} {checkbox(p.completed)} [{req}] {p.name}"
            rows.append(line_p)
            self._pm_row_map[line_p] = {
                "type": "project",
                "project_id": p.id,
                "key": f"project:{p.id}"
            }

            if p.id not in self._pm_expanded_projects:
                continue

            for g in sorted(p.goals, key=lambda x: x.name.lower()):
                goal_key = f"{p.id}/{g.id}"
                goal_matches = (not filt) or (filt in g.name.lower())
                if filt and not (project_matches or goal_matches):
                    # only show matching tasks under this goal
                    pass

                tri_g = "▼" if goal_key in self._pm_expanded_goals else "▶"
                req_g = "R" if g.required else "O"
                line_g = f"    {tri_g} {checkbox(g.completed)} [{req_g}] {g.name}"
                # show goal line if it matches filter, or any task matches filter
                if filt and not (project_matches or goal_matches):
                    any_task_match = any(filt in t.name.lower() for t in g.tasks)
                    if not any_task_match:
                        continue

                rows.append(line_g)
                self._pm_row_map[line_g] = {
                    "type": "goal",
                    "project_id": p.id,
                    "goal_id": g.id,
                    "goal_key": goal_key,
                    "key": f"goal:{p.id}/{g.id}"
                }

                if goal_key not in self._pm_expanded_goals:
                    continue

                for t in sorted(g.tasks, key=lambda x: x.name.lower()):
                    if filt and not (project_matches or goal_matches or (filt in t.name.lower())):
                        continue
                    req_t = "R" if t.required else "O"
                    line_t = f"        {checkbox(t.completed)} [{req_t}] {t.name}"
                    rows.append(line_t)
                    self._pm_row_map[line_t] = {
                        "type": "task",
                        "project_id": p.id,
                        "goal_id": g.id,
                        "task_id": t.id,
                        "key": f"task:{p.id}/{g.id}/{t.id}"
                    }

        self.pm_list.set_item_list(rows)
