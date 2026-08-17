/**
 * 菜谱知识库详情（RAG）
 * 多菜推荐"菜名点详情"进入：按菜名查 HowToCook/沉淀菜谱；
 * 未收录时提供「让知识库生成」→ AI 现生成完整做法并入库。
 */
import { Image, ScrollView, Text, View } from '@tarojs/components'
import Taro, { useLoad } from '@tarojs/taro'
import { useState } from 'react'
import NavBar from '../../components/NavBar'
import { STATIC_BASE_URL } from '../../config/env'
import {
  addFavorite,
  fetchFavoriteStatus,
  fetchKBEntry,
  fetchKBRecipeByTitle,
  generateKBRecipe,
  removeFavorite,
  type KBEntry,
} from '../../services/api'
import { ApiError } from '../../utils/request'
import './index.scss'

const CATEGORY_EMOJI: Record<string, string> = {
  肉菜: '🍖', 素菜: '🥬', 汤: '🍲', 主食: '🍚', 早餐: '🥪', 水产: '🐟',
  甜点: '🍰', 饮品: '🧋', 佐料: '🧂', 半成品: '🥟',
  新手技巧: '👨‍🍳', 进阶技巧: '🧑‍🍳', 厨房基础: '🧑‍🍳',
}

/** KB 步骤为 "1. 用菜刀..." 文本，拆出序号与正文 */
function stepParts(s: string): { no: string; text: string } {
  const m = /^\s*(\d+)[.、)．]?\s*(.*)$/.exec(s)
  if (m) return { no: m[1], text: m[2] }
  return { no: '', text: s }
}

export default function KbDetail() {
  const [entry, setEntry] = useState<KBEntry | null>(null)
  const [seg, setSeg] = useState(0)
  const [loading, setLoading] = useState(true)
  const [notFound, setNotFound] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [title, setTitle] = useState('')
  const [fav, setFav] = useState(false) // 是否已收藏（星标选中态）

  useLoad((params) => {
    const { id, title } = params as any
    // 优先用知识库条目 id（UUID 纯 ASCII，无中文编码问题）
    if (id) {
      setTitle('')
      loadById(id)
      return
    }
    let t = title as string
    if (!t) {
      Taro.showToast({ title: '缺少菜名', icon: 'none' })
      Taro.navigateBack()
      return
    }
    // Taro useLoad 返回的 params 可能是未解码的 URL 编码串；decodeURIComponent 幂等
    // （已明文时原样通过），避免二次编码导致后端查库 404
    try {
      t = decodeURIComponent(t)
    } catch {
      /* 已是明文 */
    }
    setTitle(t)
    loadByTitle(t)
  })

  const loadFavStatus = async (id: string) => {
    try {
      const { favorited } = await fetchFavoriteStatus('kb', id)
      setFav(favorited)
    } catch {
      setFav(false)
    }
  }

  const loadById = async (id: string) => {
    setLoading(true)
    setNotFound(false)
    try {
      const e = await fetchKBEntry(id)
      setEntry(e)
      loadFavStatus(e.id)
    } catch (e: any) {
      Taro.showToast({ title: e.message || '加载失败', icon: 'none' })
      setNotFound(true)
    } finally {
      setLoading(false)
    }
  }

  const loadByTitle = async (t: string) => {
    setLoading(true)
    setNotFound(false)
    try {
      const e = await fetchKBRecipeByTitle(t)
      setEntry(e)
      loadFavStatus(e.id)
    } catch (e: any) {
      if (e instanceof ApiError && e.code === 404) {
        setNotFound(true) // 暂未收录 → 引导生成
      } else {
        Taro.showToast({ title: e.message || '加载失败', icon: 'none' })
        setNotFound(true)
      }
    } finally {
      setLoading(false)
    }
  }

  const generate = async () => {
    setGenerating(true)
    try {
      const e = await generateKBRecipe(title)
      setEntry(e)
      loadFavStatus(e.id)
      setNotFound(false)
      Taro.showToast({ title: '美食库已收录，做法如下', icon: 'none' })
    } catch (e: any) {
      Taro.showToast({ title: e.message || '生成失败', icon: 'none' })
    } finally {
      setGenerating(false)
    }
  }

  /* 补全完整做法：已收录但只有摘要无步骤（AI 推荐条目标签）→ force 重新生成覆盖 */
  const fillSteps = async () => {
    if (!entry || generating) return
    setGenerating(true)
    try {
      const e = await generateKBRecipe(entry.title, true)
      setEntry(e)
      loadFavStatus(e.id)
      Taro.showToast({ title: '完整做法已补全', icon: 'none' })
    } catch (e: any) {
      Taro.showToast({ title: e.message || '生成失败', icon: 'none' })
    } finally {
      setGenerating(false)
    }
  }

  /* 收藏 / 取消收藏（知识库菜谱） */
  const toggleFavorite = async () => {
    if (!entry) return
    try {
      if (fav) {
        await removeFavorite('kb', entry.id)
        setFav(false)
        Taro.showToast({ title: '已取消收藏', icon: 'none' })
      } else {
        await addFavorite('kb', entry.id)
        setFav(true)
        Taro.showToast({ title: '已收藏到「我的收藏」', icon: 'none' })
      }
    } catch (e: any) {
      Taro.showToast({ title: e?.message || '操作失败', icon: 'none' })
    }
  }

  if (loading) return <View className='page-content detail'><NavBar title='菜谱详情' showBack /><View className='note center-load'>加载中…</View></View>

  if (notFound || !entry) {
    return (
      <View className='page-content detail'>
        <NavBar title='菜谱详情' showBack />
        <View className='kb-empty'>
          <Text userSelect className='kb-empty-emoji'>📚</Text>
          <Text userSelect className='kb-empty-title'>「{title}」暂未收录</Text>
          <Text userSelect className='kb-empty-desc'>美食库里还没有这道菜，可以让小伴现生成完整做法并加入美食库</Text>
          <View className='btn btn--red kb-gen-btn' onClick={generate}>
            {generating ? <Text userSelect>正在生成…</Text> : <><View className='ic ic-flame--white ic-sm' /><Text userSelect>让美食库生成这道菜</Text></>}
          </View>
        </View>
      </View>
    )
  }

  // 技巧条目：直接展示正文
  if (entry.kind === 'tip') {
    return (
      <View className='page-content detail'>
        <NavBar title={entry.title} showBack />
        <View className='tip-content bubble'>
          <View className='star-burst star-burst--mini'>美食库技巧</View>
          <Text userSelect className='tip-body'>{entry.content}</Text>
        </View>
      </View>
    )
  }

  const emoji = CATEGORY_EMOJI[entry.category] || '🍽'
  const hasSplit = (entry.prep_steps?.length || 0) > 0
  /* 推荐条目只有摘要无步骤 → 引导补全完整做法 */
  const hasSteps =
    (entry.prep_steps?.length || 0) > 0 ||
    (entry.cook_steps?.length || 0) > 0 ||
    (entry.steps?.length || 0) > 0
  /* 四个分段一行：食材清单 → 食材处理 → 烹饪步骤 → 避坑指南；无切分的菜去掉食材处理 */
  const SEGS = hasSplit ? ['食材清单', '食材处理', '烹饪步骤', '避坑指南'] : ['食材清单', '烹饪步骤', '避坑指南']
  const renderSteps = (list: string[]) => (
    <View className='step-list'>
      {list.length === 0 && <View className='note'>暂无步骤</View>}
      {list.map((s, i) => {
        const { no, text } = stepParts(s)
        return (
          <View key={i} className='step'>
            <View className={`sno ${i % 2 === 1 ? 'gold' : ''}`}><Text userSelect>{no || i + 1}</Text></View>
            <View className='step-body'>
              <Text userSelect className='step-detail'>{text}</Text>
            </View>
          </View>
        )
      })}
    </View>
  )

  /* 内容索引：0=食材清单 1=食材处理 2=烹饪步骤 3=避坑指南 */
  const renderSegContent = () => {
    const i = seg
    if (SEGS[i] === '食材清单') {
      return (
        <View className='ing-list'>
          {entry.ingredients.length === 0 && <View className='note'>暂无食材清单</View>}
          {entry.ingredients.map((ing, idx) => (
            <View key={idx} className='ing-item'>
              <View className='ic ic-check ic-sm' />
              <Text userSelect>{ing}</Text>
            </View>
          ))}
        </View>
      )
    }
    if (SEGS[i] === '食材处理') return renderSteps(entry.prep_steps)
    if (SEGS[i] === '烹饪步骤') return renderSteps(hasSplit ? entry.cook_steps : entry.steps)
    // 避坑指南
    return (
      <View className='pit-list'>
        {entry.tips.length === 0 && <View className='note'>暂无避坑提示</View>}
        {entry.tips.map((t, idx) => (
          <View key={idx} className='pit'><Text userSelect>⚠ {t}</Text></View>
        ))}
      </View>
    )
  }

  return (
    <View className='page-content detail'>
      <NavBar title={entry.title} showBack />

      {/* 顶部：HowToCook 有成品图 → 图片画廊；无 → 漫画 emoji */}
      {entry.images.length > 0 ? (
        <ScrollView className='img-gallery' scrollX>
          {entry.images.map((img, i) => (
            <Image key={i} className='gallery-img' src={`${STATIC_BASE_URL}/kb-data/${img}`} mode='widthFix' />
          ))}
        </ScrollView>
      ) : (
        <View className='hero' style={{ background: 'linear-gradient(135deg,#d9f2d6,#7ec8a0)' }}>
          <Text userSelect className='hero-emoji'>{emoji}</Text>
        </View>
      )}

      <View className='head'>
        <View className='head-title'>
          <Text userSelect className='head-name'>{entry.title}</Text>
          {entry.category && <View className='star-burst star-burst--mini'>{entry.category}</View>}
        </View>
        <View className='head-meta'>
          {entry.style && <View className='mini-chip gold'><Text userSelect>{entry.style}</Text></View>}
          {entry.time_minutes > 0 && <View className='mini-chip'><Text userSelect>⏱ {entry.time_minutes}分钟</Text></View>}
          <View className='mini-chip'><Text userSelect>难度 · {entry.difficulty}</Text></View>
          <View className='mini-chip green'><Text userSelect>📚 美食库</Text></View>
        </View>
        {entry.summary && (
          <View className='bubble core'>
            <View className='star-burst star-burst--mini'>核心秘诀</View>
            <Text userSelect className='core-text'>{entry.summary}</Text>
          </View>
        )}
      </View>

      {/* 分段一行：食材清单 → 食材处理 → 烹饪步骤 → 避坑指南，点哪个显示哪个 */}
      <View className='seg'>
        {SEGS.map((s, i) => (
          <View key={s} className={`seg-item ${i === seg ? 'on' : ''}`} onClick={() => setSeg(i)}>
            <Text userSelect>{s}</Text>
          </View>
        ))}
      </View>

      {renderSegContent()}

      {/* 推荐条目标签（只有摘要无步骤）→ 引导补全完整做法 */}
      {!hasSteps && (
        <View className='kb-empty kb-full'>
          <Text userSelect className='kb-empty-desc'>
            这条菜谱来自推荐，目前只有一句简介，还没有完整烹饪步骤。让小伴生成完整做法补上吧。
          </Text>
          <View className='btn btn--red kb-gen-btn' onClick={fillSteps}>
            {generating ? <Text userSelect>正在生成…</Text> : <><View className='ic ic-flame--white ic-sm' /><Text userSelect>生成完整做法</Text></>}
          </View>
        </View>
      )}

      {/* 底部操作条：收藏 / 已收藏（星标实心态） */}
      <View className='actbar'>
        <View className={`btn btn--white btn--sm ${fav ? 'fav-on' : ''}`} onClick={toggleFavorite}>
          <View className={`ic ${fav ? 'ic-star--on' : 'ic-star'} ic-sm`} />
          <Text userSelect>{fav ? '已收藏' : '收藏'}</Text>
        </View>
      </View>
    </View>
  )
}
