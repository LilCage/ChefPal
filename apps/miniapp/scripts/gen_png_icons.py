"""ChefPal 线条图标：Edge 无头浏览器把描边 SVG 栅格化为透明 PNG，base64 内嵌。

背景：微信不支持 SVG 渲染（背景图/内联都不行），字体字形无法表现描边线条。
方案：把原型 SVG（stroke 描边）用 Edge headless 转成透明 PNG —— 微信对 base64 PNG 100% 支持。

用法（需本机 Edge + PIL）：
    python scripts/gen_png_icons.py
"""
import base64
import io
import os
import subprocess

from PIL import Image

from gen_icons import PATHS

RED = "#E8482A"
GRAY = "#8A6F5C"
INK = "#4A2E1D"
GREEN = "#2FA37E"
GOLD = "#F0A73E"
WHITE = "#FFFFFF"

# 每种配色变体：icons 里填用到的图标名
VARIANTS = [
    {"key": "tab-gray", "stroke": GRAY, "width": 2.2, "icons": ["home", "kitchen", "discover", "mine", "star"]},
    {"key": "tab-red", "stroke": RED, "width": 2.2, "icons": ["home", "kitchen", "discover", "mine"]},
    {"key": "ink", "stroke": INK, "width": 2.2, "icons": ["search", "back", "share", "plus", "trash", "mic", "clock", "flame", "spark", "wechat", "bell", "heart", "edit", "comment", "info", "cal", "award", "sliders"]},
    {"key": "white", "stroke": WHITE, "width": 2.2, "icons": ["search", "spark", "flame"]},
    {"key": "green", "stroke": GREEN, "width": 2.6, "icons": ["check"]},
    {"key": "chev-gray", "stroke": GRAY, "width": 2.4, "icons": ["chev-r"]},
    {"key": "star-gold", "fill": GOLD, "stroke": GOLD, "width": 2.0, "icons": ["star"]},
]

CELL = 64  # 每个图标 64 单位（viewBox 24 -> 缩放 2.6667）
DPR = 1  # 64px 已够 22px 显示 3 倍，避免包体过大


def find_edge() -> str:
    candidates = [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    raise SystemExit("未找到 Edge，请安装 Microsoft Edge")


def render_sprite(svg_path: str, out_path: str, width: int) -> None:
    edge = find_edge()
    subprocess.run(
        [
            edge, "--headless=new", "--disable-gpu",
            "--default-background-color=00000000",
            f"--user-data-dir={os.path.dirname(out_path)}/edge-profile",
            f"--screenshot={out_path}",
            f"--window-size={width},{CELL}",
            f"--force-device-scale-factor={DPR}",
            f"file:///{svg_path.replace(os.sep, '/')}",
        ],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def main() -> None:
    here = os.path.dirname(os.path.abspath(__file__))
    work = os.path.join(here, ".iconwork")
    os.makedirs(work, exist_ok=True)

    # 收集每个 (variant, icon) -> PNG base64
    results: dict[tuple[str, str], str] = {}

    for v in VARIANTS:
        icons = v["icons"]
        n = len(icons)
        width = n * CELL
        scale = CELL / 24.0
        stroke = v.get("stroke", "none")
        fill = v.get("fill", "none")
        sw = v["width"]

        parts = []
        for i, name in enumerate(icons):
            g = (
                f'<g transform="translate({i * CELL} 0) scale({scale})" '
                f'fill="{fill}" stroke="{stroke}" stroke-width="{sw}" '
                'stroke-linecap="round" stroke-linejoin="round">'
                f"{PATHS[name]}</g>"
            )
            parts.append(g)
        svg = (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{CELL}" '
            f'viewBox="0 0 {width} {CELL}">{"".join(parts)}</svg>'
        )
        svg_path = os.path.join(work, f"{v['key']}.svg")
        png_path = os.path.join(work, f"{v['key']}.png")
        with open(svg_path, "w", encoding="utf-8") as f:
            f.write(svg)
        render_sprite(svg_path, png_path, width)

        im = Image.open(png_path).convert("RGBA")
        cell_px = CELL * DPR
        for i, name in enumerate(icons):
            crop = im.crop((i * cell_px, 0, (i + 1) * cell_px, cell_px))
            buf = io.BytesIO()
            crop.save(buf, "PNG", optimize=True)
            results[(v["key"], name)] = base64.b64encode(buf.getvalue()).decode()

    # 生成 icons.scss
    def rule(cls: str, key: str, name: str) -> str:
        return f'.{cls} {{\n  background-image: url("data:image/png;base64,{results[(key, name)]}");\n}}'

    lines = []
    lines.append("/* ============================================================")
    lines.append("   ChefPal 线条图标：原型 SVG 栅格化透明 PNG（scripts/gen_png_icons.py 生成）")
    lines.append("   微信对 base64 PNG 背景图 100% 支持，描边线条完整保留")
    lines.append("   ============================================================ */\n")
    lines.append(".ic {")
    lines.append("  display: inline-block;")
    lines.append("  width: 44px;")
    lines.append("  height: 44px;")
    lines.append("  background-repeat: no-repeat;")
    lines.append("  background-position: center;")
    lines.append("  background-size: contain;")
    lines.append("  flex: none;")
    lines.append("}\n")

    # TabBar 灰/红
    for name in ("home", "kitchen", "discover", "mine"):
        lines.append(rule(f"ic-{name}", "tab-gray", name))
        lines.append(rule(f"ic-{name}--on", "tab-red", name))
    # 常用（墨色）
    for name in ("search", "back", "share", "plus", "trash", "mic", "clock", "flame", "spark", "wechat", "bell", "heart", "edit", "comment", "info", "cal", "award", "sliders"):
        lines.append(rule(f"ic-{name}", "ink", name))
    # 白色变体（红/绿按钮上）
    for name in ("search", "spark", "flame"):
        lines.append(rule(f"ic-{name}--white", "white", name))
    # 特殊
    lines.append(rule("ic-check", "green", "check"))
    lines.append(rule("ic-chev-r", "chev-gray", "chev-r"))
    lines.append(rule("ic-star", "tab-gray", "star"))
    lines.append(rule("ic-star--on", "star-gold", "star"))
    lines.append("")

    lines.append("/* 尺寸微调 */")
    lines.append(".ic-sm { width: 32px; height: 32px; }")
    lines.append(".ic-xs { width: 26px; height: 26px; }")
    lines.append(".ic-lg { width: 56px; height: 56px; }")

    out_path = os.path.join(here, "..", "src", "styles", "icons.scss")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"✅ 已生成 {out_path}（{len(results)} 个图标 PNG）")


if __name__ == "__main__":
    main()
