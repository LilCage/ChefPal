/**
 * 我的菜谱（EXT-4.1）：个人创作的菜谱列表
 * 列表卡片 + 编辑/删除/发布到社区
 */
import { Image, Text, View } from '@tarojs/components'
import Taro, { useDidShow } from '@tarojs/taro'
import { useState } from 'react'
import NavBar from '../../components/NavBar'
import { deleteMyRecipe, fetchMyRecipes, type MyRecipe } from '../../services/api'
import './index.scss'

export default function MyRecipes() {
  const [recipes, setRecipes] = useState<MyRecipe[]>([])
  const [loaded, setLoaded] = useState(false)

  useDidShow(() => {
    load()
  })

  const load = async () => {
    try {
      const list = await fetchMyRecipes()
      setRecipes(list)
    } catch (e: any) {
      Taro.showToast({ title: e.message || '加载失败', icon: 'none' })
    } finally {
      setLoaded(true)
    }
  }

  const goCreate = () => Taro.navigateTo({ url: '/pages/my-recipe-create/index' })

  const goEdit = (id: string) =>
    Taro.navigateTo({ url: `/pages/my-recipe-create/index?id=${id}` })

  const goPublish = (id: string) =>
    Taro.navigateTo({ url: `/pages/post-create/index?my_recipe_id=${id}` })

  const goDetail = (r: MyRecipe) => {
    Taro.showModal({
      title: r.title,
      content: `${r.steps.length} 步 · ⏱ ${r.time_minutes}分钟 · 难度 ${r.difficulty}\n${r.tips[0] ? `避坑：${r.tips[0]}` : ''}`,
      showCancel: true,
      confirmText: '去发布',
      cancelText: '关闭',
      success: (res) => {
        if (res.confirm) goPublish(r.id)
      },
    })
  }

  const remove = (id: string) => {
    Taro.showModal({
      title: '删除菜谱',
      content: '确定删除这份自建菜谱吗？删除后不可恢复。',
      confirmColor: '#E8482A',
      success: async (r) => {
        if (!r.confirm) return
        try {
          await deleteMyRecipe(id)
          Taro.showToast({ title: '已删除', icon: 'none' })
          load()
        } catch (e: any) {
          Taro.showToast({ title: e.message || '删除失败', icon: 'none' })
        }
      },
    })
  }

  return (
    <View className='page-content my-recipes'>
      <NavBar title='我的菜谱' showBack />

      {recipes.length === 0 && loaded && (
        <View className='empty'>
          <View className='empty-art'>📝</View>
          <Text className='empty-title'>还没有自建菜谱</Text>
          <Text className='empty-desc'>把拿手菜记录下来，还能一键发布到社区</Text>
          <View className='btn btn--red btn--block' onClick={goCreate}>
            <Text>＋ 新建菜谱</Text>
          </View>
        </View>
      )}

      {recipes.length > 0 && (
        <View className='mr-list'>
          {recipes.map((r) => (
            <View key={r.id} className='mr-card' onClick={() => goDetail(r)}>
              <View className='mr-cover'>
                {r.cover_image ? (
                  <Image className='mr-cover-img' src={r.cover_image} mode='aspectFill' />
                ) : (
                  <Text className='mr-cover-emoji'>🍽</Text>
                )}
              </View>
              <View className='mr-body'>
                <View className='mr-title'>
                  <Text>{r.title}</Text>
                  {r.style && <View className='mini-chip gold'><Text>{r.style}</Text></View>}
                </View>
                <View className='mr-meta'>
                  <Text>⏱ {r.time_minutes}分钟</Text>
                  <Text>·</Text>
                  <Text>难度 {r.difficulty}</Text>
                  <Text>·</Text>
                  <Text>{r.steps.length} 步</Text>
                </View>
                <View className='mr-actions' onClick={(e) => e.stopPropagation()}>
                  <View className='btn btn--white btn--sm' onClick={() => goEdit(r.id)}>
                    <View className='ic ic-edit ic-sm' /><Text>编辑</Text>
                  </View>
                  <View className='btn btn--gold btn--sm' onClick={() => goPublish(r.id)}>
                    <View className='ic ic-share ic-sm' /><Text>发布</Text>
                  </View>
                  <View className='btn btn--white btn--sm danger' onClick={() => remove(r.id)}>
                    <View className='ic ic-trash ic-sm' /><Text>删除</Text>
                  </View>
                </View>
              </View>
            </View>
          ))}
        </View>
      )}

      {recipes.length > 0 && (
        <View className='save-wrap'>
          <View className='btn btn--red btn--block' onClick={goCreate}>
            <Text>＋ 新建菜谱</Text>
          </View>
        </View>
      )}
    </View>
  )
}
