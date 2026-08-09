"""ChefPal 图标生成器：把 SVG 图标转成 base64 data-URI，生成 icons.scss。

微信小程序 WXSS 对 background-image 的 SVG data-URI 兼容性差，
base64 是最稳的格式。用法（任意 Python 3）：
    python scripts/gen_icons.py
"""
import base64
import os

GRAY = "#8A6F5C"
RED = "#E8482A"
INK = "#4A2E1D"
GREEN = "#2FA37E"
GOLD = "#F0A73E"

PATHS = {
    "home": '<path d="M3 10.5 12 3l9 7.5"/><path d="M5 9.5V21h14V9.5"/><path d="M9 21v-6h6v6"/>',
    "kitchen": '<path d="M4 11h16a1 1 0 0 1 1 1v5a4 4 0 0 1-4 4H7a4 4 0 0 1-4-4v-5a1 1 0 0 1 1-1z"/><path d="M8 11V7a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v4"/><path d="M9.5 5.5 8.5 3M14.5 5.5l1-2.5"/>',
    "discover": '<circle cx="12" cy="12" r="9"/><path d="m15.5 8.5-2 5-5 2 2-5z"/>',
    "mine": '<circle cx="12" cy="8" r="4"/><path d="M4 21c0-4 3.5-6 8-6s8 2 8 6"/>',
    "search": '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
    "back": '<path d="M15 5l-7 7 7 7"/>',
    "share": '<path d="M4 12v8h16v-8"/><path d="m12 4 5 5h-3v7h-4V9H7z"/>',
    "plus": '<path d="M12 5v14M5 12h14"/>',
    "trash": '<path d="M4 7h16"/><path d="M10 7V4h4v3"/><path d="M6 7l1 13h10l1-13"/>',
    "mic": '<rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0"/><path d="M12 18v3"/>',
    "clock": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    "flame": '<path d="M12 3c1.2 3-4 5-4 9a4 4 0 0 0 8 0c0-2-.8-3-.8-3s1.4 1 2.3 2.6A5.5 5.5 0 0 1 12 21c-4.4 0-7.5-3-7.5-7 0-5.5 7.5-11 7.5-11z"/>',
    "spark": '<path d="M12 4l1.6 4.9L18.5 10 13.6 11.6 12 16.5l-1.6-4.9L5.5 10l4.9-1.1z"/>',
    "wechat": '<path d="M8 5h8a4.5 4.5 0 0 1 4.5 4.5v1a4.5 4.5 0 0 1-4.5 4.5h-5L7 18v-3.1A4.5 4.5 0 0 1 3.5 10.5v-1A4.5 4.5 0 0 1 8 5z"/>',
    "bell": '<path d="M6 9a6 6 0 0 1 12 0c0 5 2 6 2 6H4s2-1 2-6"/><path d="M10 19a2 2 0 0 0 4 0"/>',
    "heart": '<path d="M12 21S4 15 4 9.5A4.5 4.5 0 0 1 12 7a4.5 4.5 0 0 1 8 2.5C20 15 12 21 12 21z"/>',
    "check": '<path d="m5 12 5 5 9-11"/>',
    "edit": '<path d="M12 20h8"/><path d="M16.5 3.5 20 7 8 19l-4 1 1-4z"/>',
    "chev-r": '<path d="m9 5 7 7-7 7"/>',
    "comment": '<path d="M4 5h16v12H9l-5 4z"/>',
    "info": '<circle cx="12" cy="12" r="9"/><path d="M12 11v5"/><path d="M12 8h.01"/>',
    "cal": '<rect x="4" y="5" width="16" height="15" rx="2"/><path d="M8 3v4M16 3v4M4 10h16"/>',
    "award": '<circle cx="12" cy="9" r="6"/><path d="M9 14.5 8 21l4-2.5 4 2.5-1-6.5"/>',
    "sliders": '<path d="M4 7h9M17 7h3M4 17h5M13 17h7"/><circle cx="15" cy="7" r="2"/><circle cx="11" cy="17" r="2"/>',
    "lock": '<rect x="5" y="11" width="14" height="9" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/>',
    "star": '<path d="m12 3 2.7 5.5 6 .9-4.3 4.2 1 6L12 17l-5.4 2.6 1-6L3.3 9.4l6-.9z"/>',
}


def svg(path: str, stroke: str, width: float = 2.2, fill: str = "none") -> str:
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
        f'fill="{fill}" stroke="{stroke}" stroke-width="{width}" '
        'stroke-linecap="round" stroke-linejoin="round">'
        f"{path}</svg>"
    )


def b64(svg_str: str) -> str:
    return base64.b64encode(svg_str.encode("utf-8")).decode()


def rule(name: str, svg_str: str) -> str:
    return f'.{name} {{\n  background-image: url("data:image/svg+xml;base64,{b64(svg_str)}");\n}}'


def main() -> None:
    out = []
    out.append("/* 由 scripts/gen_icons.py 自动生成，请勿手改 */")
    out.append("/* ChefPal 图标：base64 SVG data-URI（微信 WXSS 背景图最稳格式） */\n")
    out.append(".ic {\n  display: inline-block;\n  width: 44px;\n  height: 44px;\n  background-repeat: no-repeat;\n  background-position: center;\n  background-size: contain;\n  flex: none;\n}\n")

    # TabBar：灰 / 红 两态
    for name in ("home", "kitchen", "discover", "mine"):
        out.append(rule(f"ic-{name}", svg(PATHS[name], GRAY)))
        out.append(rule(f"ic-{name}--on", svg(PATHS[name], RED)))

    # 常用（墨灰）
    for name in ("search", "back", "share", "plus", "trash", "mic", "clock", "flame",
                 "spark", "wechat", "bell", "heart", "edit", "comment", "info",
                 "cal", "award", "sliders"):
        out.append(rule(f"ic-{name}", svg(PATHS[name], INK)))

    # 特殊
    out.append(rule("ic-check", svg(PATHS["check"], GREEN, width=2.6)))
    out.append(rule("ic-chev-r", svg(PATHS["chev-r"], GRAY, width=2.4)))
    out.append(rule("ic-star", svg(PATHS["star"], GRAY)))
    out.append(rule("ic-star--on", svg(PATHS["star"], GOLD, width=2, fill=GOLD)))

    out.append("\n/* 尺寸微调 */")
    out.append(".ic-sm { width: 32px; height: 32px; }")
    out.append(".ic-xs { width: 26px; height: 26px; }")
    out.append(".ic-lg { width: 56px; height: 56px; }")

    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src", "styles", "icons.scss")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(out))
    print(f"✅ 已生成 {out_path}")


if __name__ == "__main__":
    main()
