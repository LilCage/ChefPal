"""补丁：单独生成某个墨色图标并追加到 icons.scss（避免整体重跑影响已定稿图标）。

用法：python scripts/gen_lock_icon.py  lock
会读取 gen_icons.PATHS[name]，用 Edge 无头栅格化 64px 透明 PNG，base64 追加 .ic-<name> 规则。
"""
import base64
import io
import os
import subprocess
import sys

from PIL import Image

from gen_icons import PATHS

CELL = 64
INK = "#4A2E1D"
STROKE_WIDTH = 2.2

EDGE_CANDIDATES = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]


def find_edge() -> str:
    for c in EDGE_CANDIDATES:
        if os.path.exists(c):
            return c
    raise SystemExit("未找到 Edge，请安装 Microsoft Edge")


def render(name: str) -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    work = os.path.join(here, ".iconwork")
    os.makedirs(work, exist_ok=True)

    scale = CELL / 24.0
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 64 64">'
        f'<g transform="scale({scale})" fill="none" stroke="{INK}" stroke-width="{STROKE_WIDTH}" '
        'stroke-linecap="round" stroke-linejoin="round">'
        f"{PATHS[name]}</g></svg>"
    )
    svg_path = os.path.join(work, f"{name}.svg")
    png_path = os.path.join(work, f"{name}.png")
    with open(svg_path, "w", encoding="utf-8") as f:
        f.write(svg)

    subprocess.run(
        [
            find_edge(), "--headless=new", "--disable-gpu",
            "--default-background-color=00000000",
            f"--user-data-dir={os.path.join(work, 'edge-profile-lock')}",
            f"--screenshot={png_path}",
            "--window-size=64,64",
            "--force-device-scale-factor=1",
            f"file:///{svg_path.replace(os.sep, '/')}",
        ],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    im = Image.open(png_path).convert("RGBA")
    buf = io.BytesIO()
    im.save(buf, "PNG", optimize=True)
    return base64.b64encode(buf.getvalue()).decode()


def main() -> None:
    name = sys.argv[1] if len(sys.argv) > 1 else "lock"
    b64 = render(name)

    scss = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src", "styles", "icons.scss")
    cls = f"ic-{name}"
    with open(scss, "r", encoding="utf-8") as f:
        content = f.read()

    if f".{cls} " in content:
        print(f"⚠️  {cls} 已存在，跳过")
        return

    rule = f".{cls} {{\n  background-image: url(\"data:image/png;base64,{b64}\");\n}}\n"
    # 追加到 .ic-chev-r 之后（保留 .ic-* 区块，随后是尺寸微调注释）
    marker = '.ic-chev-r'
    idx = content.find(marker)
    if idx == -1:
        content += rule
    else:
        # 找到该规则的结束大括号所在行末
        end = content.index("\n", content.index("}", idx)) + 1
        content = content[:end] + rule + content[end:]
    with open(scss, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"✅ 已追加 .{cls} 到 {scss}")


if __name__ == "__main__":
    main()
