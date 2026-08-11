/**
 * 我的收藏（原型 02 屏1）：问答 / 菜谱 双 Tab
 */
import { Text, View } from '@tarojs/components'
import Taro, { useDidShow } from '@tarojs/taro'
import { useState } from 'react'
import EmptyState from '../../components/EmptyState'
import NavBar from '../../components/NavBar'
import QACard from '../../components/QACard'
import RecipeCard from '../../components/RecipeCard'
import { fetchFavorites, type FavoriteItem } from '../../services/api'
import './index.scss'

export default function Favorites() {
  const [tab, setTab] = useState<0 | 1>(0)
  const [qaFavs, setQaFavs] = useState<FavoriteItem[]>([])
  const [recipeFavs, setRecipeFavs] = useState<FavoriteItem[]>([])
  const [loaded, setLoaded] = useState(false)

  useDidShow(() => {
    loadAll()
  })

  const loadAll = async () => {
    try {
      const [qa, recipe] = await Promise.all([fetchFavorites('qa'), fetchFavorites('recipe')])
      setQaFavs(qa)
      setRecipeFavs(recipe)
    } catch (e: any) {
      Taro.showToast({ title: e.message || '加载失败', icon: 'none' })
    } finally {
      setLoaded(true)
    }
  }

  const list = tab === 0 ? qaFavs : recipeFavs

  return (
    <View className='page-content fav'>
      <NavBar title='我的收藏' showBack />

      <View className='seg'>
        <View className={`seg-item ${tab === 0 ? 'on' : ''}`} onClick={() => setTab(0)}>
          <Text>问答收藏 {qaFavs.length}</Text>
        </View>
        <View className={`seg-item ${tab === 1 ? 'on' : ''}`} onClick={() => setTab(1)}>
          <Text>菜谱收藏 {recipeFavs.length}</Text>
        </View>
      </View>

      {loaded && list.length === 0 ? (
        <EmptyState
          icon={tab === 0 ? '💬' : '🍜'}
          title={tab === 0 ? '还没有收藏的问答' : '还没有收藏的菜谱'}
          desc={tab === 0 ? '问小伴一个问题，把「核心秘诀」收藏起来\n下次下厨随时翻看' : '去「厨房」生成菜谱，点亮星标收藏'}
          btnText={tab === 0 ? '去小伴百科逛逛' : '去厨房生成'}
          onBtn={() => Taro.switchTab({ url: tab === 0 ? '/pages/index/index' : '/pages/kitchen/index' })}
        />
      ) : (
        <View className='fav-list'>
          {tab === 0 &&
            qaFavs.map((f) => (
              <QACard
                key={f.favorite_id}
                question={f.content?.question || '问答'}
                summary={f.content?.core_secret ? `核心秘诀：${f.content.core_secret}` : undefined}
                starred
              />
            ))}
          {tab === 1 &&
            recipeFavs.map((f) => (
              <View className='fav-recipe' key={f.favorite_id}>
                <RecipeCard
                  name={f.content?.title || '菜谱'}
                  matchScore={f.content?.match_score || 0}
                  timeMinutes={f.content?.time_minutes || 0}
                  difficulty={f.content?.difficulty || '简单'}
                  onClick={() => Taro.navigateTo({ url: `/pages/recipe-detail/index?id=${f.content_id}` })}
                />
              </View>
            ))}
        </View>
      )}
    </View>
  )
}
