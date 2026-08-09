"""ChefPal 自定义线条图标字体生成器。

把原型 SVG 路径（gen_icons.PATHS）编译为 iconfont（WOFF），
base64 内嵌进 icons.scss，并用 font-family + content 码点实现图标。
微信小程序对 @font-face + base64 字体原生支持（线条图标最稳方案）。

用法（任意 Python 3，需 fonttools）：
    python scripts/gen_iconfont.py
"""
import base64
import io
import os

from fontTools.fontBuilder import FontBuilder
from fontTools.pens.cu2quPen import Cu2QuPen
from fontTools.pens.transformPen import TransformPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.svgLib import SVGPath

from gen_icons import PATHS

UPEM = 1000
SCALE = 900 / 24.0  # 24 设计盒 -> 900 字身
OFF_X = 50.0
OFF_Y = 24.0 * SCALE + 50.0  # 950

FONT_FAMILY = "chefpal-icons"


def make_glyph(d: str):
    glyph_pen = TTGlyphPen(None)
    # SVG 是三次贝塞尔，TTF 需要二次贝塞尔：经 Cu2QuPen 转换
    qu_pen = Cu2QuPen(glyph_pen, max_err=1.0, reverse_direction=True)
    transform_pen = TransformPen(qu_pen, (SCALE, 0, 0, -SCALE, OFF_X, OFF_Y))
    svg_xml = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
        f"{d}</svg>"
    )
    SVGPath(io.BytesIO(svg_xml.encode("utf-8"))).draw(transform_pen)
    return glyph_pen.glyph()


def build_font() -> bytes:
    names = sorted(PATHS.keys())
    glyph_order = [".notdef"]
    glyphs = {}
    advances = {}
    cmap = {}
    for i, name in enumerate(names):
        gname = f"g{i:02d}"
        glyph_order.append(gname)
        glyphs[gname] = make_glyph(PATHS[name])
        advances[gname] = (UPEM, 0)
        cmap[0xE001 + i] = gname
    # 空 notdef
    glyphs[".notdef"] = make_glyph("M0 0h24v24H0z")  # 一个占位方块
    advances[".notdef"] = (UPEM, 0)

    fb = FontBuilder(UPEM, isTTF=True)
    fb.setupGlyphOrder(glyph_order)
    fb.setupCharacterMap(cmap)
    fb.setupGlyf(glyphs)
    fb.setupHorizontalMetrics(advances)
    fb.setupHorizontalHeader(ascent=UPEM, descent=0)
    fb.setupNameTable(
        {
            "familyName": FONT_FAMILY,
            "styleName": "Regular",
            "uniqueFontIdentifier": FONT_FAMILY,
            "fullName": FONT_FAMILY,
            "psName": "ChefPalIcons-Regular",
        },
        mac=True,
    )
    fb.setupOS2(sTypoAscender=UPEM, sTypoDescender=0, usWinAscent=UPEM, usWinDescent=0)
    fb.setupPost()
    fb.setupMaxp()

    # 微信对 base64 TTF 的支持最稳定（WOFF 有兼容性问题），输出 TTF
    buf = io.BytesIO()
    fb.font.save(buf)
    return buf.getvalue()


def main() -> None:
    names = sorted(PATHS.keys())
    font_data = build_font()
    b64 = base64.b64encode(font_data).decode()

    lines = []
    lines.append("/* ============================================================")
    lines.append("   ChefPal 线条图标：自定义 iconfont（由 scripts/gen_iconfont.py 自动生成）")
    lines.append("   微信 @font-face + base64 TTF，线条图标最稳格式，形状源自原型 SVG")
    lines.append("   ============================================================ */\n")
    lines.append("@font-face {")
    lines.append(f"  font-family: '{FONT_FAMILY}';")
    lines.append(f'  src: url("data:font/truetype;base64,{b64}") format("truetype");')
    lines.append("}\n")
    lines.append(".ic {")
    lines.append(f"  font-family: '{FONT_FAMILY}';")
    lines.append("  display: inline-flex;")
    lines.append("  align-items: center;")
    lines.append("  justify-content: center;")
    lines.append("  width: 44px;")
    lines.append("  height: 44px;")
    lines.append("  font-size: 40px;")
    lines.append("  line-height: 1;")
    lines.append("  flex: none;")
    lines.append("  color: var(--ink);")
    lines.append("}\n")

    for i, name in enumerate(names):
        lines.append(f".ic-{name}::before {{ content: \"\\{0xE001 + i:04x}\"; }}")
    lines.append("")
    # 激活/收藏 等彩色变体（--on 需自带 ::before 内容 + 配色）
    for name in ("home", "kitchen", "discover", "mine"):
        idx = names.index(name)
        lines.append(f".ic-{name}--on::before {{ content: \"\\{0xE001 + idx:04x}\"; }}")
        lines.append(f".ic-{name}--on {{ color: var(--red); }}")
    idx = names.index("star")
    lines.append(f".ic-star--on::before {{ content: \"\\{0xE001 + idx:04x}\"; }}")
    lines.append(".ic-star--on { color: var(--gold); }")
    lines.append("")

    lines.append("/* 尺寸微调 */")
    lines.append(".ic-sm { width: 32px; height: 32px; font-size: 28px; }")
    lines.append(".ic-xs { width: 26px; height: 26px; font-size: 24px; }")
    lines.append(".ic-lg { width: 56px; height: 56px; font-size: 52px; }")

    out_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "src", "styles", "icons.scss"
    )
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"✅ 已生成 {out_path}（{len(names)} 个图标，字体 {len(font_data)} 字节）")


if __name__ == "__main__":
    main()
