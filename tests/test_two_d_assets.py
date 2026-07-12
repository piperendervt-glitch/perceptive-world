import hashlib
import struct
import zlib

from trpg_core.two_d_assets import (
    ASSET_KEYS, ASSET_ROOT, TkImageCache, relative_asset_path_for_key,
)


def test_manifest_is_closed_relative_and_complete():
    assert ASSET_KEYS == tuple(f"goblin/well/lod{i}" for i in range(4))
    paths = [relative_asset_path_for_key(key) for key in ASSET_KEYS]
    assert all(path is not None and not path.is_absolute() for path in paths)
    assert relative_asset_path_for_key("goblin/well") is None
    assert relative_asset_path_for_key("../well/lod0") is None
    assert relative_asset_path_for_key("/tmp/lod0") is None


def test_png_assets_are_same_size_distinct_and_reasonable():
    hashes = set(); dimensions = set()
    for key in ASSET_KEYS:
        data = (ASSET_ROOT / relative_asset_path_for_key(key)).read_bytes()
        assert data.startswith(b"\x89PNG\r\n\x1a\n") and 100 < len(data) < 20000
        dimensions.add(struct.unpack(">II", data[16:24]))
        hashes.add(hashlib.sha256(data).hexdigest())
    assert dimensions == {(64, 64)} and len(hashes) == 4


def _rgba_pixels(path):
    data = path.read_bytes(); pos = 8; compressed = []
    while pos < len(data):
        length = struct.unpack(">I", data[pos:pos+4])[0]
        kind = data[pos+4:pos+8]; payload = data[pos+8:pos+8+length]
        if kind == b"IDAT": compressed.append(payload)
        pos += 12 + length
    raw = zlib.decompress(b"".join(compressed)); stride = 64 * 4
    assert all(raw[y*(stride+1)] == 0 for y in range(64))
    return tuple(tuple(raw[y*(stride+1)+1+x*4:y*(stride+1)+1+x*4+4]
                       for x in range(64)) for y in range(64))


def test_lod3_adds_readable_faded_emblem_only_in_front_rim_region():
    lod2 = _rgba_pixels(ASSET_ROOT / relative_asset_path_for_key("goblin/well/lod2"))
    lod3 = _rgba_pixels(ASSET_ROOT / relative_asset_path_for_key("goblin/well/lod3"))
    region = {(x, y) for y in range(44, 58) for x in range(24, 41)}
    changed_inside = {(x, y) for x, y in region if lod2[y][x] != lod3[y][x]}
    changed_outside = {
        (x, y) for y in range(64) for x in range(64)
        if (x, y) not in region and lod2[y][x] != lod3[y][x]
    }
    emblem_colors = {(201, 181, 158, 255), (170, 151, 139, 255)}
    assert len(changed_inside) >= 35
    assert changed_outside == set()
    assert not any(tuple(lod2[y][x]) in emblem_colors for x, y in region)
    assert sum(tuple(lod3[y][x]) in emblem_colors for x, y in region) >= 30


class _Image:
    def __init__(self, width=64): self._width = width; self.factor = None
    def width(self): return self._width
    def height(self): return self._width
    def subsample(self, x, y): self.factor = (x, y); return self


def test_lazy_cache_success_resize_unknown_and_failure():
    calls = []
    def factory(**kwargs): calls.append(kwargs); return _Image()
    cache = TkImageCache(factory, resolver=lambda key: None if key == "unknown" else "asset.png")
    first = cache.image_for("known", 40)
    assert first is cache.image_for("known", 40) and len(calls) == 1
    assert first.factor == (2, 2)
    assert cache.image_for("unknown", 40) is None and len(calls) == 1
    broken = TkImageCache(lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("bad")), resolver=lambda _key: "bad.png")
    assert broken.image_for("known", 64) is None
