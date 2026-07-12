"""Closed, side-effect-free manifest and lazy Tk image cache for the 2D client."""

from pathlib import Path
from types import MappingProxyType


ASSET_ROOT = Path(__file__).resolve().parent / "assets" / "two_d"
_ASSET_PATHS = MappingProxyType({
    f"goblin/{object_name}/lod{lod}": (
        Path("goblin") / object_name / f"lod{lod}.png"
    )
    for object_name in ("well", "shrine", "lookout", "herbhut", "elderhouse")
    for lod in range(4)
})
ASSET_KEYS = tuple(_ASSET_PATHS)


def relative_asset_path_for_key(asset_key: str) -> Path | None:
    if type(asset_key) is not str or not asset_key or Path(asset_key).is_absolute():
        return None
    return _ASSET_PATHS.get(asset_key)


def asset_path_for_key(asset_key: str) -> Path | None:
    relative = relative_asset_path_for_key(asset_key)
    return None if relative is None else ASSET_ROOT / relative


class TkImageCache:
    """Load after Tk startup; retain every image reference for canvas lifetime."""

    def __init__(self, photo_factory, *, resolver=asset_path_for_key):
        self._photo_factory = photo_factory
        self._resolver = resolver
        self._cache = {}

    def image_for(self, asset_key: str, cell_size: int):
        if type(cell_size) is not int or cell_size <= 0:
            return None
        cache_key = (asset_key, cell_size)
        if cache_key in self._cache:
            return self._cache[cache_key]
        path = self._resolver(asset_key)
        if path is None:
            self._cache[cache_key] = None
            return None
        try:
            image = self._photo_factory(file=str(path))
            target = max(1, cell_size - 8)
            factor = max(1, (max(image.width(), image.height()) + target - 1) // target)
            if factor > 1:
                image = image.subsample(factor, factor)
        except Exception:
            image = None
        self._cache[cache_key] = image
        return image
