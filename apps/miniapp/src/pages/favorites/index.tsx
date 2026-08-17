/**
 * 菜谱收藏（我的收藏）：自建菜谱 + 知识库菜谱 合集，每项可取消收藏。
 * （问答收藏已下线：历史问答走「首页→历史对话」，不再占用收藏位。）
 */
import { Text, View } from '@tarojs/components'
import Taro, { useDidShow } from '@tarojs/taro'
import { useState } from 'react'
import EmptyState from '../../components/EmptyState'
import NavBar from '../../components/NavBar'
import RecipeCard from '../../components/RecipeCard'
import { fetchFavorites, removeFavorite, type FavoriteItem } from '../../services/api'
import './index.scss'

export default function Favorites() {
  const [recipeFavs, setRecipeFavs] = useState<FavoriteItem[]>([])
  const [kbFavs, setKbFavs] = useState<FavoriteItem[]>([])
  const [loaded, setLoaded] = useState(false)

  useDidShow(() => {
    loadAll()
  })

  const loadAll = async () => {
    try {
      const [recipe, kb] = await Promise.all([fetchFavorites('recipe'), fetchFavorites('kb')])
      setRecipeFavs(recipe)
      setKbFavs(kb)
    } catch (e: any) {
      Taro.showToast({ title: e.message || '加载失败', icon: 'none' })
    } finally {
      setLoaded(true)
    }
  }

  const list = [...recipeFavs, ...kbFavs]

  const removeFav = async (f: FavoriteItem, e?: any) => {
    if (e?.stopPropagation) e.stopPropagation() // 不触发展开详情的卡片点击
    try {
      await removeFavorite(f.content_type, f.content_id)
      setRecipeFavs((prev) => prev.filter((x) => x.favorite_id !== f.favorite_id))
      setKbFavs((prev) => prev.filter((x) => x.favorite_id !== f.favorite_id))
      Taro.showToast({ title: '已取消收藏', icon: 'none' })
    } catch (e: any) {
      Taro.showToast({ title: e.message || '操作失败', icon: 'none' })
    }
  }

  return (
    <View className='page-content fav'>
      <NavBar title='菜谱收藏' showBack />

      {loaded && list.length === 0 ? (
        <EmptyState
          icon='🍜'
          title='还没有收藏的菜谱'
          desc='去「厨房」生成菜谱，或在小伴问答里点亮星标收藏'
          btnText='去厨房生成'
          onBtn={() => Taro.switchTab({ url: '/pages/kitchen/index' })}
        />
      ) : (
        <View className='fav-list'>
          {list.map((f) => {
            // 知识库菜谱无 match_score；收藏卡右上角匹配度对 KB 菜无含义 → 隐藏（顶部留给成品图）
            const isKb = f.content_type === 'kb'
            return (
              <View className='fav-recipe' key={f.favorite_id}>
                <RecipeCard
                  name={f.content?.title || '菜谱'}
                  matchScore={0}
                  timeMinutes={f.content?.time_minutes || 0}
                  difficulty={f.content?.difficulty || '简单'}
                  style={f.content?.style || ''}
                  hideMatch
                  onClick={() =>
                    Taro.navigateTo({
                      url: isKb
                        ? `/pages/kb-detail/index?id=${f.content_id}`
                        : `/pages/recipe-detail/index?id=${f.content_id}`,
                    })
                  }
                  action={
                    <View className='fav-remove' onClick={(e) => removeFav(f, e)}>
                      <View className='ic ic-trash ic-xs' />
                      <Text userSelect>取消收藏</Text>
                    </View>
                  }
                />
              </View>
            )
          })}
        </View>
      )}
    </View>
  )
}
