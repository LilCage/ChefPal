/**
 * 菜谱DNA进化树（原型 05 屏6）：菜谱版本轨迹时间线 + 保存我的版本
 * 数据源 POST /recipes/{id}/fork、GET /recipes/{id}/tree
 * 通过 ?id= 进入（菜谱 id 或版本 id）
 */
import { Text, View } from '@tarojs/components'
import Taro, { useLoad } from '@tarojs/taro'
import { useState } from 'react'
import NavBar from '../../components/NavBar'
import { fetchRecipeTree, forkRecipe, type RecipeTreeData, type RecipeVersion } from '../../services/api'
import './index.scss'

export default function RecipeTree() {
  const [tree, setTree] = useState<RecipeTreeData | null>(null)
  const [loading, setLoading] = useState(false)

  useLoad((params) => {
    const id = (params as any).id as string
    if (id) loadTree(id)
  })

  const loadTree = async (id: string) => {
    try {
      const t = await fetchRecipeTree(id)
      setTree(t)
    } catch (e: any) {
      Taro.showToast({ title: e.message || '加载失败', icon: 'none' })
    }
  }

  const saveVersion = async () => {
    if (!tree || loading) return
    setLoading(true)
    try {
      const v = await forkRecipe(tree.recipe_id, '我的尝试：起锅前加半勺糖 + 一点番茄酱')
      await loadTree(tree.recipe_id)
      Taro.showToast({ title: `已保存 ${v.version_label}！`, icon: 'none' })
    } catch (e: any) {
      Taro.showToast({ title: e.message || '保存失败', icon: 'none' })
    } finally {
      setLoading(false)
    }
  }

  const tagOf = (v: RecipeVersion, idx: number) => {
    if (v.is_root) return `✓ ${idx + 1} 人收藏`
    return idx === tree!.versions.length - 1 ? '✏ 正在编辑 · 未发布' : `🔥 ${(idx + 1) * 33} 次跟做`
  }

  return (
    <View className='page-content recipe-tree'>
      <NavBar title={tree ? `${tree.title} · 进化树` : '菜谱进化树'} showBack />

      <View className='evo-tree'>
        {(tree?.versions || []).map((v, idx) => (
          <View key={v.id || `root-${idx}`} className='evo-node'>
            <View className={`dot ${idx === 0 ? 'root' : idx === 1 ? 'mid' : ''}`}>
              <Text>{v.version_label.replace('v', '').split('.')[0]}</Text>
            </View>
            <View className='evo-card'>
              <View className='ev-title'>
                <Text className='ev-ver'>{v.version_label}{v.is_root ? ' 原版' : idx === 1 ? ' 改进' : ' 我的分支'}</Text>
                <Text className='ev-name'>{v.title}</Text>
              </View>
              <Text className='ev-desc'>
                {v.is_root
                  ? `第一次 AI 生成 · 经典家常做法`
                  : v.changes || '基于上一版的改进'}
              </Text>
              <Text className='ev-tag'>{tagOf(v, idx)}</Text>
            </View>
          </View>
        ))}
      </View>

      <View className='sec'>
        <View className={`btn btn--red btn--block ${loading ? 'btn--disabled' : ''}`} onClick={saveVersion}>
          <Text>{loading ? '保存中…' : '💾 保存我的版本'}</Text>
        </View>
      </View>
      <Text className='note evo-note'>每道菜记录修改轨迹 · 社区内容自然生长</Text>
    </View>
  )
}
