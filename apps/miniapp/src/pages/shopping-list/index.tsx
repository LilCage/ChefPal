/**
 * 购物清单（原型 04 屏5）：分类分组 + 勾选项 + 已选统计 + 复制清单（不含价格）
 */
import { Text, View } from '@tarojs/components'
import Taro, { useDidShow, useLoad } from '@tarojs/taro'
import { useState } from 'react'
import NavBar from '../../components/NavBar'
import {
  fetchLatestShoppingList,
  generateShoppingList,
  toggleShopItem,
  type ShoppingList,
} from '../../services/api'
import './index.scss'

const CAT_EMOJI: Record<string, string> = {
  蔬菜: '🥬', 水果: '🍎', 蛋: '🥚', 肉: '🍖', 禽: '🍗',
  水产: '🐟', 海鲜: '🦐', 主食: '🍚', 豆: '🫘', 调料: '🧂',
}

function catEmoji(name: string): string {
  const hit = Object.keys(CAT_EMOJI).find((k) => name.includes(k))
  return hit ? CAT_EMOJI[hit] : '🛒'
}

export default function ShoppingListPage() {
  const [list, setList] = useState<ShoppingList | null>(null)
  const [loading, setLoading] = useState(false)
  const [generateOnShow, setGenerateOnShow] = useState(false)

  useLoad((params) => {
    if ((params as any).generate === '1') setGenerateOnShow(true)
  })

  useDidShow(() => {
    if (generateOnShow) {
      setGenerateOnShow(false)
      doGenerate()
    } else {
      loadLatest()
    }
  })

  const loadLatest = async () => {
    setLoading(true)
    try {
      setList(await fetchLatestShoppingList())
    } catch {
      /* 无清单：空状态引导生成 */
    } finally {
      setLoading(false)
    }
  }

  const doGenerate = async () => {
    setLoading(true)
    try {
      setList(await generateShoppingList())
      Taro.showToast({ title: '购物清单已生成！', icon: 'none' })
    } catch (e: any) {
      Taro.showToast({ title: e.message || '生成失败', icon: 'none' })
    } finally {
      setLoading(false)
    }
  }

  const toggle = async (itemId: string, checked: boolean) => {
    if (!list) return
    const prev = list.data.categories
    const next = prev.map((cat) => ({
      ...cat,
      items: cat.items.map((it) => (it.item_id === itemId ? { ...it, checked: !checked } : it)),
    }))
    setList({ ...list, data: { categories: next } })
    try {
      await toggleShopItem(list.id, itemId, !checked)
    } catch (e: any) {
      setList({ ...list }) // 失败回滚
      Taro.showToast({ title: e.message || '操作失败', icon: 'none' })
    }
  }

  const copyList = () => {
    if (!list) return
    const lines: string[] = []
    for (const cat of list.data.categories) {
      const items = cat.items.map((it) => (it.quantity ? `${it.name} ${it.quantity}` : it.name))
      if (items.length) lines.push(`${cat.name}：${items.join('、')}`)
    }
    if (!lines.length) return
    Taro.setClipboardData({ data: lines.join('\n') })
  }

  const allItems = list ? list.data.categories.flatMap((c) => c.items) : []
  const checkedCount = allItems.filter((i) => i.checked).length

  if (!list) {
    return (
      <View className='page-content shopping'>
        <NavBar title='购物清单' showBack />
        <View className='empty'>
          <View className='empty-art'>🛒</View>
          <Text className='empty-title'>还没有购物清单</Text>
          <Text className='empty-desc'>先生成 3 天膳食计划，再一键汇总采购清单</Text>
          <View className='btn btn--red btn--block' onClick={doGenerate}>
            <Text>{loading ? '生成中…' : '生成本周购物清单'}</Text>
          </View>
        </View>
      </View>
    )
  }

  return (
    <View className='page-content shopping'>
      <NavBar title='购物清单' showBack />

      {list.data.categories.map((cat) => (
        <View key={cat.name} className='cart-cat'>
          <View className='cc-t'>
            <Text>{catEmoji(cat.name)} {cat.name}</Text>
            <Text className='cc-count'>{cat.items.length} 项</Text>
          </View>
          {cat.items.map((it) => (
            <View key={it.item_id} className={`check-item ${it.checked ? 'done' : ''}`} onClick={() => toggle(it.item_id, it.checked)}>
              <View className={`check-box ${it.checked ? 'on' : ''}`}>
                <View className='ic ic-check ic-xs' />
              </View>
              <Text className='ci-name'>{it.name}</Text>
              {it.quantity && <Text className='ci-num'>{it.quantity}</Text>}
            </View>
          ))}
        </View>
      ))}

      <View className='cart-total'>
        <Text className='ct-label'>已选 <Text className='ct-green'>{checkedCount}</Text> / {allItems.length} 项</Text>
        <Text className='ct-note'>数量为 AI 估算，仅供参考</Text>
      </View>

      <View className='sec'>
        <View className='btn btn--red btn--block' onClick={copyList}>
          <View className='ic ic-cart--white ic-sm' />
          <Text>复制清单</Text>
        </View>
      </View>
    </View>
  )
}
