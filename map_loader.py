from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional, Any


# ----------------------------
# RLE helpers
# ----------------------------

def rle_decode(pairs: List[List[int]], expected_len: int) -> List[int]:
    out: List[int] = []
    for pair in pairs:
        if not isinstance(pair, list) or len(pair) != 2:
            raise ValueError(f"Invalid RLE pair: {pair}")
        value, count = int(pair[0]), int(pair[1])
        if count < 0:
            raise ValueError(f"Invalid RLE count: {count}")
        out.extend([value] * count)
        if len(out) > expected_len:
            raise ValueError("RLE decode exceeded expected length")
    if len(out) != expected_len:
        raise ValueError(f"RLE decode length mismatch: got {len(out)} expected {expected_len}")
    return out


def rle_encode(values: List[int]) -> List[List[int]]:
    if not values:
        return []
    pairs: List[List[int]] = []
    cur = int(values[0])
    run = 1
    for v in values[1:]:
        v = int(v)
        if v == cur:
            run += 1
        else:
            pairs.append([cur, run])
            cur = v
            run = 1
    pairs.append([cur, run])
    return pairs


# ----------------------------
# Map definition + save slot
# ----------------------------

@dataclass(frozen=True)
class TerrainType:
    id: int
    name: str
    passable: bool
    cost: float


@dataclass
class MapDef:
    id: str
    name: str
    description: str
    image_path: str

    width: int
    height: int
    tile_world_size: int

    terrain_palette: Dict[int, TerrainType]
    tiles: List[int]  # length = width*height, each is terrain id

    @property
    def tile_count(self) -> int:
        return self.width * self.height

    @property
    def world_size(self) -> Tuple[int, int]:
        return (self.width * self.tile_world_size, self.height * self.tile_world_size)


@dataclass
class SaveSlot:
    map_id: str
    explored: List[int]  # 0 hidden, 1 visible (len = tile_count)


@dataclass
class MapState:
    map_def: MapDef
    save_slot_path: str
    save: SaveSlot

    # bitmap loaded later (pygame surface) to avoid importing pygame here
    map_image = None  # pygame.Surface

    def is_explored(self, tx: int, ty: int) -> bool:
        if tx < 0 or ty < 0 or tx >= self.map_def.width or ty >= self.map_def.height:
            return False
        idx = ty * self.map_def.width + tx
        return self.save.explored[idx] == 1

    def set_explored(self, tx: int, ty: int, val: int) -> None:
        if tx < 0 or ty < 0 or tx >= self.map_def.width or ty >= self.map_def.height:
            return
        idx = ty * self.map_def.width + tx
        self.save.explored[idx] = 1 if val else 0

    def reveal_all(self) -> None:
        for i in range(len(self.save.explored)):
            self.save.explored[i] = 1

    def hide_all(self) -> None:
        for i in range(len(self.save.explored)):
            self.save.explored[i] = 0

    def save_to_disk(self) -> None:
        save_save_slot(self.save_slot_path, self.map_def, self.save)


def load_map_def(path: str) -> MapDef:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    grid = data["grid"]
    width = int(grid["width"])
    height = int(grid["height"])
    tile_world_size = int(grid["tile_world_size"])

    palette_raw = data.get("terrain_palette", {})
    palette: Dict[int, TerrainType] = {}
    for k, v in palette_raw.items():
        tid = int(k)
        palette[tid] = TerrainType(
            id=tid,
            name=str(v.get("name", f"Terrain{tid}")),
            passable=bool(v.get("passable", True)),
            cost=float(v.get("cost", 1.0)),
        )

    tiles_block = data.get("tiles", {})
    enc = tiles_block.get("encoding", "rle")
    expected_len = width * height

    if enc == "rle":
        tiles = rle_decode(tiles_block.get("data", []), expected_len)
    elif enc == "raw_flat":
        raw = tiles_block.get("data", [])
        if len(raw) != expected_len:
            raise ValueError("raw_flat tiles length mismatch")
        tiles = [int(x) for x in raw]
    else:
        raise ValueError(f"Unsupported tiles encoding: {enc}")

    return MapDef(
        id=str(data["id"]),
        name=str(data.get("name", data["id"])),
        description=str(data.get("description", "")),
        image_path=str(data["image_path"]),
        width=width,
        height=height,
        tile_world_size=tile_world_size,
        terrain_palette=palette,
        tiles=tiles,
    )


def load_save_slot(save_path: str, map_def: MapDef) -> SaveSlot:
    if not os.path.exists(save_path):
        # default: everything hidden
        return SaveSlot(map_id=map_def.id, explored=[0] * map_def.tile_count)

    with open(save_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    map_id = str(data.get("map_id", map_def.id))
    if map_id != map_def.id:
        # map changed; safest v1 behavior: reset exploration
        return SaveSlot(map_id=map_def.id, explored=[0] * map_def.tile_count)

    exp_block = data.get("exploration", {"encoding": "rle", "data": [[0, map_def.tile_count]]})
    enc = exp_block.get("encoding", "rle")

    if enc == "rle":
        explored = rle_decode(exp_block.get("data", []), map_def.tile_count)
    elif enc == "raw_flat":
        raw = exp_block.get("data", [])
        if len(raw) != map_def.tile_count:
            raise ValueError("raw_flat exploration length mismatch")
        explored = [int(x) for x in raw]
    else:
        raise ValueError(f"Unsupported exploration encoding: {enc}")

    # clamp to 0/1
    explored = [1 if int(x) else 0 for x in explored]
    return SaveSlot(map_id=map_def.id, explored=explored)


def save_save_slot(save_path: str, map_def: MapDef, save: SaveSlot) -> None:
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    payload = {
        "version": 1,
        "map_id": map_def.id,
        "exploration": {
            "encoding": "rle",
            "data": rle_encode(save.explored),
        },
    }
    with open(save_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


def load_map_state(map_def_path: str, save_slot_path: str) -> MapState:
    m = load_map_def(map_def_path)
    s = load_save_slot(save_slot_path, m)
    return MapState(map_def=m, save_slot_path=save_slot_path, save=s)
