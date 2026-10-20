"""Small reviewed local decorations, independent of landscape crop and controls."""

import base64
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def styles():
    static = Path(__file__).parent / "static"
    return "".join(
        f"--hs-decor-{name}:url(data:image/webp;base64,{base64.b64encode((static / f'decor-{name}.webp').read_bytes()).decode()});"
        for name in ("saucer", "owl", "atlas")
    )
