"""ChefPal 品牌字体（ZCOOL KuaiLe）子集化生成器。

ZCOOL KuaiLe 完整中文字体 ~1.5MB，微信主包限 2MB，不能整包内置。
这里只子集化用到的那几个汉字 + 拉丁，缩到几 KB，再 base64 内嵌 @font-face。

用法（需 fonttools）：
    python scripts/gen_brandfont.py
"""
import base64
import io
import os

from fontTools import subset
from fontTools.ttLib import TTFont

FONT_FAMILY = "chefpal-brand"
# .pop 品牌字实际用到的字符（ChefPal + 食材魔方 + 发现 + 我的厨房）+ 保险字符
TEXT = "ChefPal发现食材魔方我的厨房美食猎人口袋AI0123456789"

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_TTF = os.path.join(HERE, "zcool-kuaile.ttf")


def main() -> None:
    if not os.path.exists(SRC_TTF):
        print(f"缺少源字体 {SRC_TTF}，请先下载 ZCOOL KuaiLe")
        return

    font = TTFont(SRC_TTF)
    opts = subset.Options()
    opts.recalc_bounds = True
    opts.name_IDs = ["*"]
    sub = subset.Subsetter(opts)
    sub.populate(text=TEXT)
    sub.subset(font)

    buf = io.BytesIO()
    font.save(buf)
    data = buf.getvalue()
    b64 = base64.b64encode(data).decode()

    lines = []
    lines.append("/* ============================================================")
    lines.append("   品牌字体 chefpal-brand（ZCOOL KuaiLe 子集，由 scripts/gen_brandfont.py 生成）")
    lines.append("   仅含项目用到的字符，约几 KB。微信 @font-face + base64 TTF。")
    lines.append("   ============================================================ */\n")
    lines.append("@font-face {")
    lines.append(f"  font-family: '{FONT_FAMILY}';")
    lines.append("  font-style: normal;")
    lines.append("  font-weight: 400;")
    lines.append(f'  src: url("data:font/truetype;base64,{b64}") format("truetype");')
    lines.append("}\n")

    out_path = os.path.join(HERE, "..", "src", "styles", "brandfont.scss")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"✅ 已生成 {out_path}（子集 {len(data)} 字节 = {len(data)/1024:.1f}KB）")


if __name__ == "__main__":
    main()
