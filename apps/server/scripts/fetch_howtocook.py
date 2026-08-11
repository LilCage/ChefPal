"""从 GitHub 拉取 HowToCook 菜谱 markdown + 成品图到 kb_data/howtocook/（gitignore）。

只抽 dishes/ 与 tips/ 下的 .md 文本（仓库大头是图片与历史）。
成品图是 Git LFS 指针，需从 media.githubusercontent.com 下载真实图片。
默认 ref=master 跟随最新；可传固定 commit hash 锁定版本：
    .venv/Scripts/python scripts/fetch_howtocook.py <ref>
"""
import io
import re
import sys
import tarfile
import urllib.request
from pathlib import Path
from urllib.parse import quote

REPO = "Anduin2017/HowToCook"
DEFAULT_REF = "master"
KB_DATA = Path(__file__).resolve().parent.parent / "kb_data" / "howtocook"
LFS_MEDIA = "https://media.githubusercontent.com/media"
_IMAGE_LINK = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")
_USER_AGENT = "chefpal-import"


def _http(url: str, timeout: int = 60) -> bytes:
    # 路径含中文，需百分号编码（保留 / 与 :），否则 Windows urllib 报 ascii 编码错
    encoded = quote(url, safe="/:")
    req = urllib.request.Request(encoded, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def main(ref: str) -> int:
    tarball_url = f"https://codeload.github.com/{REPO}/tar.gz/{ref}"
    print(f"下载 {tarball_url} ...")
    data = _http(tarball_url, timeout=180)
    print(f"下载完成 {len(data) / 1024 / 1024:.1f} MB")

    tf = tarfile.open(fileobj=io.BytesIO(data), mode="r:gz")
    top = tf.getnames()[0].split("/")[0]  # 顶层目录名，如 HowToCook-master

    # 1. 抽取 markdown
    md_count = 0
    image_refs: set[str] = set()
    for member in tf.getmembers():
        if not member.isfile():
            continue
        rel = member.name[len(top) + 1 :]
        if not (rel.startswith("dishes/") or rel.startswith("tips/")):
            continue
        if rel.endswith(".md"):
            target = KB_DATA / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            f = tf.extractfile(member)
            md = f.read().decode("utf-8", errors="replace")
            target.write_bytes(md.encode("utf-8"))
            md_count += 1
            # 收集图片引用 → 仓库内相对路径（as_posix 保证正斜杠，Windows 反斜杠会 404）
            base = Path(rel).parent.as_posix()
            for m in _IMAGE_LINK.finditer(md):
                raw = m.group(1).strip()
                if raw.startswith(("http://", "https://", "//")):
                    continue
                image_refs.add(f"{base}/{raw.lstrip('./')}")
    tf.close()
    print(f"已抽取 {md_count} 个 markdown；发现 {len(image_refs)} 个图片引用")

    # 2. 下载成品图（Git LFS → media.githubusercontent.com）
    ok = skip = 0
    for rel in sorted(image_refs):
        target = KB_DATA / rel
        try:
            img = _http(f"{LFS_MEDIA}/{REPO}/{ref}/{rel}")
            if len(img) < 500:  # 仍是 LFS 指针/极小占位 → 跳过
                skip += 1
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(img)
            ok += 1
        except Exception as exc:  # noqa: BLE001
            skip += 1
            print(f"  ✗ {rel}: {exc}")
    print(f"成品图下载完成：{ok} 成功，{skip} 跳过/失败")

    return md_count


if __name__ == "__main__":
    ref = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_REF
    main(ref)
