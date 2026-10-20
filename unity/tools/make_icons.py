"""Make the app's icons: Lucide (https://lucide.dev, ISC licence) SVGs rendered white on transparent at 48 px, so the
theme can tint them (UI Toolkit tints a background image with -unity-background-image-tint-color).

    python -m venv iconenv && iconenv/Scripts/pip install resvg-py
    iconenv/Scripts/python unity/tools/make_icons.py

Writes unity/SpongeParkApp/Assets/SpongePark/Resources/UI/Icons/<name>.png and the licence. The app refers to an
icon by the name on the left.
"""

import sys
import urllib.request
from pathlib import Path

import resvg_py

VERSION = "0.452.0"
OUT = Path(__file__).resolve().parents[1] / "SpongeParkApp" / "Assets" / "SpongePark" / "Resources" / "UI" / "Icons"

# app name -> Lucide name
ICONS = {
    "site": "mountain", "import": "file-up", "layers": "layers", "confirm": "circle-check-big", "setup": "sliders-horizontal",
    "flow-lines": "waves", "arrows": "move-right", "ponding": "droplets", "exits": "log-out", "analyse": "activity",
    "baseline": "chart-no-axes-column", "measure": "ruler",
    "select": "mouse-pointer-2", "rain-garden": "flower-2", "bioswale": "spline", "detention-pond": "square-dashed",
    "retention-pond": "circle-dot", "recharge-well": "cylinder", "delete": "trash-2", "undo": "undo-2", "redo": "redo-2",
    "suggest": "wand-sparkles", "optimise": "sparkles", "least-area": "minimize-2", "generate": "layout-grid",
    "targets": "target", "verify": "shield-check",
    "simulate": "cloud-rain", "play": "play", "pause": "pause", "restart": "rotate-ccw", "gpu": "cpu", "gpu-check": "gauge",
    "load": "download", "results": "chart-column-big", "split": "columns-2", "table": "table-2",
    "report": "file-text", "web": "globe", "video": "video", "folder": "folder-open", "export": "share",
    "search": "search", "settings": "settings", "checklist": "list-checks", "present": "presentation",
    "collapse-left": "chevrons-left", "collapse-right": "chevrons-right", "expand-down": "chevron-down",
    "expand-up": "chevron-up", "eye": "eye", "eye-off": "eye-off", "lock": "lock", "unlock": "lock-open",
    "maximise": "maximize-2", "home": "house", "north": "navigation-2", "view-3d": "box", "view-2d": "map",
    "extents": "scan", "tour": "rotate-3d", "close": "x", "info": "info", "warning": "triangle-alert",
    "check": "check", "circle": "circle", "locked": "lock-keyhole", "save": "save", "swap": "arrow-left-right",
    "snap": "magnet", "engine": "server", "storm": "cloud-rain-wind", "legend": "list",
    "draw-curve": "pen-tool", "draw-straight": "slash", "green-bridge": "brick-wall",
}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, lucide in ICONS.items():
        url = f"https://cdn.jsdelivr.net/npm/lucide-static@{VERSION}/icons/{lucide}.svg"
        svg = urllib.request.urlopen(url, timeout=30).read().decode("utf-8").replace("currentColor", "#FFFFFF")
        png = resvg_py.svg_to_bytes(svg_string=svg, width=48, height=48)
        (OUT / f"{name}.png").write_bytes(bytes(png))
    lic = urllib.request.urlopen(f"https://cdn.jsdelivr.net/npm/lucide-static@{VERSION}/LICENSE", timeout=30).read()
    (OUT / "LICENSE-lucide.txt").write_bytes(lic)
    print(f"{len(ICONS)} icons in {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
