from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Dict, Optional, Tuple, Any

from model import GameState, ProcessingUnit, Recipe


@dataclass(frozen=True)
class ResourceDef:
    id: str
    name: str
    weight: float


class ResourceCatalog:
    def __init__(self, resources: Dict[str, ResourceDef]):
        self._resources = resources

    def name_of(self, rid: str) -> str:
        r = self._resources.get(rid)
        return r.name if r else f"(unknown:{rid})"

    def get(self, rid: str) -> Optional[ResourceDef]:
        return self._resources.get(rid)

    @property
    def ids(self):
        return self._resources.keys()


def _load_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_resources(path: str) -> ResourceCatalog:
    data = _load_json(path)
    resources = {}
    for r in data.get("resources", []):
        rid = r["id"]
        resources[rid] = ResourceDef(
            id=rid,
            name=r.get("name", rid),
            weight=float(r.get("weight", 1.0)),
        )
    if not resources:
        raise ValueError("resources.json contained no resources")
    return ResourceCatalog(resources)


def load_recipes(path: str, catalog: ResourceCatalog) -> Dict[str, Recipe]:
    data = _load_json(path)
    out: Dict[str, Recipe] = {}

    for r in data.get("recipes", []):
        rid = r["id"]
        mode = r.get("mode")  # "transfer" or None

        inputs = dict(r.get("inputs", {}))
        outputs = dict(r.get("outputs", {}))

        # Validate referenced resource ids exist
        for res_id in inputs.keys():
            if catalog.get(res_id) is None:
                raise ValueError(f"Recipe {rid} references unknown input resource id: {res_id}")
        for res_id in outputs.keys():
            if catalog.get(res_id) is None:
                raise ValueError(f"Recipe {rid} references unknown output resource id: {res_id}")

        # Transfer recipe can optionally specify a resource id
        transfer_res = r.get("transfer_resource", None)
        if transfer_res is not None and transfer_res != "" and catalog.get(transfer_res) is None:
            raise ValueError(f"Recipe {rid} references unknown transfer_resource id: {transfer_res}")

        out[rid] = Recipe(
            id=rid,
            name=r.get("name", rid),
            mode=r.get("mode", "transfer" if transfer_res is not None else "craft"),
            duration_turns=int(r.get("duration_turns", 1)),
            power_required=int(r.get("power_required", 0)),
            inputs=inputs,
            outputs=outputs,
            transfer_resource=transfer_res,
        )

    if not out:
        raise ValueError("recipes.json contained no recipes")
    return out


def load_units(path: str, recipes: Dict[str, Recipe], catalog: ResourceCatalog) -> GameState:
    data = _load_json(path)
    s = GameState()
    units = data.get("units", [])
    if not units:
        raise ValueError("units.json contained no units")

    # First pass: create units
    for u in units:
        uid = u["id"]
        inv = dict(u.get("inventory", {}))

        # Validate resource ids used in inventory
        for res_id in inv.keys():
            if catalog.get(res_id) is None:
                raise ValueError(f"Unit {uid} inventory references unknown resource id: {res_id}")

        recipe_obj = None
        recipe_id = u.get("recipe_id", None)
        if recipe_id:
            if recipe_id not in recipes:
                raise ValueError(f"Unit {uid} references unknown recipe_id: {recipe_id}")
            recipe_obj = recipes[recipe_id]

        pos_raw = u.get("pos", [0, 0])
        pos: Tuple[float, float] = (float(pos_raw[0]), float(pos_raw[1]))

        s.units[uid] = ProcessingUnit(
            id=uid,
            name=u.get("name", uid),
            kind=u.get("kind", "Unit"),
            pos=pos,
            input_id=u.get("input_id", None),
            output_id=u.get("output_id", None),
            inventory=inv,
            recipe=recipe_obj,
            status=u.get("status", "Running"),
            notes=u.get("notes", ""),
        )

    # Second pass: validate links point to existing units
    for uid, unit in s.units.items():
        if unit.input_id and unit.input_id not in s.units:
            raise ValueError(f"Unit {uid} has input_id={unit.input_id} which does not exist")
        if unit.output_id and unit.output_id not in s.units:
            raise ValueError(f"Unit {uid} has output_id={unit.output_id} which does not exist")

    s.selected_unit_id = data.get("selected_unit_id", None)
    if s.selected_unit_id and s.selected_unit_id not in s.units:
        s.selected_unit_id = None

    s.log("Loaded game state from JSON config.")
    return s
