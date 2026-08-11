"""菜谱知识库服务测试：upsert 去重 / 向量检索排序 / 阈值过滤 / 精确查标题。"""
import pytest
from sqlalchemy import func, select

from app.models.recipe_kb import RecipeKB
from app.services import kb as kb_service
from app.services.llm.embedding import EmbeddingError

DIM = 1024


def _v(*idx: int) -> list[float]:
    """构造 1024 维向量：指定位置为 1，其余为 0。"""
    v = [0.0] * DIM
    for i in idx:
        v[i] = 1.0
    return v


def _mock_embeddings(monkeypatch, mapping: dict[str, list[float]], default=None):
    """mock aembed_texts：输入文本命中关键字返回对应向量（长关键字优先）。

    未命中时返回 default（默认一个与任何条目都正交的向量，保证 cosine 可算）。
    """
    keys = sorted(mapping.keys(), key=len, reverse=True)
    fallback = default if default is not None else _v(DIM - 1)

    async def fake(texts, *, input_type="document"):
        out = []
        for t in texts:
            vec = fallback
            for kw in keys:
                if kw in t:
                    vec = mapping[kw]
                    break
            out.append(vec)
        return out

    monkeypatch.setattr(kb_service, "aembed_texts", fake)


async def test_upsert_creates_entry(db, monkeypatch):
    _mock_embeddings(monkeypatch, {"红烧肉": _v(0)})
    entry = await kb_service.upsert_kb_entry(
        db,
        kind="recipe",
        title="红烧肉",
        summary="肥而不腻",
        ingredients=["五花肉"],
        steps=["焯水", "小火焖 40 分钟"],
        prep_steps=["1. 焯水"],
        cook_steps=["1. 小火焖 40 分钟"],
        tips=["不要大火焯水"],
        difficulty="中等",
        category="肉菜",
        source_type="howtocook",
        source_id="dishes/meat_dish/红烧肉.md",
    )
    assert entry.id
    assert entry.kind == "recipe"
    assert entry.ingredients == ["五花肉"]
    assert entry.steps == ["焯水", "小火焖 40 分钟"]
    assert entry.prep_steps == ["1. 焯水"]
    assert entry.cook_steps == ["1. 小火焖 40 分钟"]
    assert entry.tips == ["不要大火焯水"]
    assert entry.embedding[0] == 1.0  # 向量已写入

    # to_kb_out 序列化含切分字段
    out = kb_service.to_kb_out(entry)
    assert out["prep_steps"] == ["1. 焯水"]
    assert out["cook_steps"] == ["1. 小火焖 40 分钟"]


async def test_upsert_stores_images(db, monkeypatch):
    _mock_embeddings(monkeypatch, {"红烧肉": _v(0)})
    entry = await kb_service.upsert_kb_entry(
        db,
        kind="recipe",
        title="红烧肉",
        images=["dishes/meat_dish/红烧肉/000.jpg", "dishes/meat_dish/红烧肉/001.jpg"],
        source_type="howtocook",
    )
    await db.commit()
    out = kb_service.to_kb_out(entry)
    assert out["images"] == ["dishes/meat_dish/红烧肉/000.jpg", "dishes/meat_dish/红烧肉/001.jpg"]


async def test_upsert_dedupes_by_kind_title(db, monkeypatch):
    _mock_embeddings(monkeypatch, {"红烧肉": _v(0)})
    e1 = await kb_service.upsert_kb_entry(db, kind="recipe", title="红烧肉", summary="旧简介", source_type="howtocook")
    e2 = await kb_service.upsert_kb_entry(db, kind="recipe", title="红烧肉", summary="新简介", source_type="howtocook")
    await db.commit()

    count = (await db.execute(select(func.count()).select_from(RecipeKB))).scalar()
    assert count == 1
    assert e1.id == e2.id
    assert e2.summary == "新简介"

    # kind 不同则不去重（recipe 与 tip 可同标题）
    t = await kb_service.upsert_kb_entry(db, kind="tip", title="红烧肉", content="正文", source_type="howtocook")
    await db.commit()
    assert (await db.execute(select(func.count()).select_from(RecipeKB))).scalar() == 2
    assert t.kind == "tip"


async def test_search_hit_above_threshold(db, monkeypatch):
    _mock_embeddings(monkeypatch, {"红烧肉": _v(0), "凉拌黄瓜": _v(1)})
    await kb_service.upsert_kb_entry(db, kind="recipe", title="红烧肉", source_type="howtocook")
    await kb_service.upsert_kb_entry(db, kind="recipe", title="凉拌黄瓜", source_type="howtocook")
    await db.commit()

    hits = await kb_service.search_kb(db, "红烧肉怎么做不腻")
    assert len(hits) == 1
    assert hits[0]["entry"].title == "红烧肉"
    assert hits[0]["similarity"] == pytest.approx(1.0)


async def test_search_filters_below_threshold(db, monkeypatch):
    _mock_embeddings(monkeypatch, {"凉拌黄瓜": _v(1)})
    await kb_service.upsert_kb_entry(db, kind="recipe", title="凉拌黄瓜", source_type="howtocook")
    await db.commit()

    # 查询与任何知识条目正交 → 相似度 0，低于阈值
    hits = await kb_service.search_kb(db, "红烧肉怎么做不腻")
    assert hits == []


async def test_search_orders_by_similarity(db, monkeypatch):
    _mock_embeddings(monkeypatch, {"红烧肉": _v(0), "红烧肉汤": _v(0, 1), "凉拌黄瓜": _v(1)})
    await kb_service.upsert_kb_entry(db, kind="recipe", title="红烧肉", source_type="howtocook")
    await kb_service.upsert_kb_entry(db, kind="recipe", title="红烧肉汤", source_type="howtocook")
    await kb_service.upsert_kb_entry(db, kind="recipe", title="凉拌黄瓜", source_type="howtocook")
    await db.commit()

    hits = await kb_service.search_kb(db, "红烧肉怎么做")
    titles = [h["entry"].title for h in hits]
    assert titles == ["红烧肉", "红烧肉汤"]
    assert hits[0]["similarity"] == pytest.approx(1.0, abs=1e-3)
    # cosine([1,0],[1,1]) = 1/sqrt(2)
    assert hits[1]["similarity"] == pytest.approx(1 / (2**0.5), abs=1e-3)


async def test_search_kinds_filter(db, monkeypatch):
    _mock_embeddings(monkeypatch, {"红烧肉": _v(0), "去腥": _v(0)})
    await kb_service.upsert_kb_entry(db, kind="recipe", title="红烧肉", source_type="howtocook")
    await kb_service.upsert_kb_entry(db, kind="tip", title="去腥", content="料酒去腥", source_type="howtocook")
    await db.commit()

    hits = await kb_service.search_kb(db, "红烧肉", kinds=["tip"])
    assert len(hits) == 1
    assert hits[0]["entry"].kind == "tip"
    assert hits[0]["entry"].title == "去腥"


async def test_get_by_title_with_suffix_fallback(db, monkeypatch):
    _mock_embeddings(monkeypatch, {"红烧肉": _v(0), "去腥": _v(1)})
    await kb_service.upsert_kb_entry(db, kind="recipe", title="红烧肉", source_type="howtocook")
    await kb_service.upsert_kb_entry(db, kind="tip", title="去腥", content="正文", source_type="howtocook")
    await db.commit()

    found = await kb_service.get_kb_entry_by_title(db, "红烧肉的做法")
    assert found is not None and found.title == "红烧肉"

    # kind 隔离
    assert await kb_service.get_kb_entry_by_title(db, "去腥", kind="tip") is not None
    assert await kb_service.get_kb_entry_by_title(db, "去腥", kind="recipe") is None


def test_build_embedding_text_composes():
    text = kb_service.build_embedding_text(
        {
            "title": "红烧肉",
            "summary": "肥而不腻",
            "ingredients": ["五花肉"],
            "steps": ["焯水", "焖 40 分钟"],
            "tips": ["小火"],
        }
    )
    for part in ("红烧肉", "肥而不腻", "五花肉", "焯水", "小火"):
        assert part in text


async def test_upsert_propagates_embedding_error(db, monkeypatch):
    async def boom(texts, *, input_type="document"):
        raise EmbeddingError("mock 向量服务不可用")

    monkeypatch.setattr(kb_service, "aembed_texts", boom)
    with pytest.raises(EmbeddingError):
        await kb_service.upsert_kb_entry(db, kind="recipe", title="红烧肉", source_type="howtocook")


async def test_upsert_ai_does_not_overwrite_howtocook(db, monkeypatch):
    """HowToCook 是权威种子：AI 生成的同名菜不得覆盖它。"""
    _mock_embeddings(monkeypatch, {"红烧肉": _v(0)})
    seed = await kb_service.upsert_kb_entry(
        db, kind="recipe", title="红烧肉", summary="HowToCook 内容",
        steps=["1. 权威步骤"], source_type="howtocook", source_id="dishes/x.md",
    )
    # AI 生成同名菜 → 应跳过，保留 HowToCook 内容
    ai = await kb_service.upsert_kb_entry(
        db, kind="recipe", title="红烧肉", summary="AI 内容",
        steps=["1. AI 步骤"], source_type="ai_recipe",
    )
    await db.commit()
    assert ai.id == seed.id
    assert ai.source_type == "howtocook"  # 未被覆盖
    assert ai.summary == "HowToCook 内容"
    assert ai.steps == ["1. 权威步骤"]
    # 数量仍为 1
    assert (await db.execute(select(func.count()).select_from(RecipeKB))).scalar() == 1


async def test_upsert_howtocook_refresh_overwrites(db, monkeypatch):
    """HowToCook 源自身重新导入（刷新）允许覆盖更新。"""
    _mock_embeddings(monkeypatch, {"红烧肉": _v(0)})
    await kb_service.upsert_kb_entry(db, kind="recipe", title="红烧肉", summary="旧", source_type="howtocook")
    await kb_service.upsert_kb_entry(db, kind="recipe", title="红烧肉", summary="新", source_type="howtocook")
    await db.commit()
    e = await kb_service.get_kb_entry_by_title(db, "红烧肉")
    assert e is not None and e.summary == "新"
