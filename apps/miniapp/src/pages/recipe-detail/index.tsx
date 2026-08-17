/**
 * 屏4 · 菜谱详情（原型 01）
 * 步骤 / 食材清单 / 避坑指南 三个分段 + 收藏/分享/开始做饭
 */
import { Text, View } from '@tarojs/components'
import Taro, { useLoad } from '@tarojs/taro'
import { useState } from 'react'
import NavBar from '../../components/NavBar'
import {
  addFavorite,
  fetchFavoriteStatus,
  fetchRecipe,
  removeFavorite,
  type Recipe,
} from '../../services/api'
import './index.scss'

const SEGS = ['烹饪步骤', '食材清单', '避坑指南']

export default function RecipeDetail() {
  const [recipe, setRecipe] = useState<Recipe | null>(null)
  const [seg, setSeg] = useState(0)
  const [loading, setLoading] = useState(true)
  const [fav, setFav] = useState(false) // 是否已收藏（星标选中态）

  useLoad((params) => {
    const id = (params as any).id as string
    fetchRecipe(id)
      .then((r) => {
        setRecipe(r)
        // 收藏选中态：查询失败静默置空，不影响详情展示
        fetchFavoriteStatus('recipe', r.id)
          .then(({ favorited }) => setFav(favorited))
          .catch(() => setFav(false))
      })
      .catch((e: any) => Taro.showToast({ title: e.message || '加载失败', icon: 'none' }))
      .finally(() => setLoading(false))
  })

  /* 收藏 / 取消收藏（AI 菜谱，仅本人可见） */
  const saveFavorite = async () => {
    if (!recipe) return
    try {
      if (fav) {
        await removeFavorite('recipe', recipe.id)
        setFav(false)
        Taro.showToast({ title: '已取消收藏', icon: 'none' })
      } else {
        await addFavorite('recipe', recipe.id)
        setFav(true)
        Taro.showToast({ title: '已收藏到「我的收藏」', icon: 'none' })
      }
    } catch (e: any) {
      Taro.showToast({ title: e.message || '操作失败', icon: 'none' })
    }
  }

  const share = () => {
    if (!recipe) return
    Taro.navigateTo({ url: `/pages/share-card/index?id=${recipe.id}` })
  }

  if (loading) return <View className='page-content'><View className='note center-load'>加载中…</View></View>
  if (!recipe) return <View className='page-content'><View className='note center-load'>菜谱不存在</View></View>

  return (
    <View className='page-content detail'>
      <NavBar title={recipe.title} showBack />

      <View className='hero'>
        <Text userSelect className='hero-emoji'>🍜</Text>
      </View>

      <View className='head'>
        <View className='head-title'>
          <Text userSelect className='head-name'>{recipe.title}</Text>
          <View className='star-burst star-burst--mini'>匹配 {recipe.match_score}%</View>
        </View>
        <View className='head-meta'>
          {recipe.style && <View className='mini-chip gold'><Text userSelect>{recipe.style}</Text></View>}
          <View className='mini-chip'><Text userSelect>⏱ {recipe.time_minutes}分钟</Text></View>
          <View className='mini-chip'><Text userSelect>难度 · {recipe.difficulty}</Text></View>
          {recipe.missing_seasonings.length > 0 && (
            <View className='mini-chip red'><Text userSelect>缺:{recipe.missing_seasonings.join('、')}</Text></View>
          )}
        </View>
        <View className='bubble core'>
          <View className='star-burst star-burst--mini'>核心秘诀</View>
          <Text userSelect className='core-text'>{recipe.tips[0] || '按步骤操作，注意火候是关键'}</Text>
        </View>
      </View>

      <View className='seg'>
        {SEGS.map((s, i) => (
          <View key={s} className={`seg-item ${i === seg ? 'on' : ''}`} onClick={() => setSeg(i)}>
            <Text userSelect>{s}</Text>
          </View>
        ))}
      </View>

      {seg === 0 && (
        <View className='step-list'>
          {recipe.steps.map((st, i) => (
            <View key={i} className='step'>
              <View className={`sno ${i % 2 === 1 ? 'gold' : ''}`}><Text userSelect>{i + 1}</Text></View>
              <View className='step-body'>
                <Text userSelect className='step-title'>{st.title}</Text>
                <Text userSelect className='step-detail'>{st.detail}</Text>
              </View>
            </View>
          ))}
        </View>
      )}

      {seg === 1 && (
        <View className='ing-list'>
          {recipe.ingredients.map((ing, i) => (
            <View key={i} className='ing-item'>
              <View className={`ic ${ing.is_missing ? 'ic-trash ic-sm' : 'ic-check ic-sm'}`} />
              <Text userSelect>{ing.name}</Text>
              <Text userSelect className='alt'>{ing.is_missing ? '缺 · 可替代' : '已备齐'}</Text>
            </View>
          ))}
        </View>
      )}

      {seg === 2 && (
        <View className='pit-list'>
          {recipe.tips.map((t, i) => (
            <View key={i} className='pit'><Text userSelect>⚠ {t}</Text></View>
          ))}
        </View>
      )}

      <View className='actbar'>
        <View className='btn btn--white btn--sm' onClick={share}><View className='ic ic-share ic-sm' /><Text userSelect>分享</Text></View>
        <View className='btn btn--white btn--sm' onClick={() => Taro.navigateTo({ url: `/pages/recipe-tree/index?id=${recipe.id}` })}><View className='ic ic-edit ic-sm' /><Text userSelect>进化树</Text></View>
        <View className={`btn btn--white btn--sm ${fav ? 'fav-on' : ''}`} onClick={saveFavorite}><View className={`ic ${fav ? 'ic-star--on' : 'ic-star'} ic-sm`} /><Text userSelect>{fav ? '已收藏' : '收藏'}</Text></View>
        <View className='btn btn--red btn--sm' onClick={() => Taro.navigateTo({ url: `/pages/cook-assistant/index?id=${recipe.id}` })}>
          <View className='ic ic-flame--white ic-sm' /><Text userSelect>开始做饭</Text>
        </View>
      </View>
    </View>
  )
}
