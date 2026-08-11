/**
 * 家庭口味投票（原型 05 屏2）：小伴生成 3 道菜 → 全家投票决定今晚吃什么
 * - 创建模式：输入冰箱食材 → 生成 3 选项
 * - 受邀模式：分享链接带 ?id= → 直接查看并投票
 * 数据源 POST /votes/generate、GET/POST /votes/{id}、GET /votes/{id}/share-card
 */
import { Button, Input, Text, View } from '@tarojs/components'
import Taro, { useLoad, useShareAppMessage } from '@tarojs/taro'
import { useState } from 'react'
import NavBar from '../../components/NavBar'
import {
  castVote,
  fetchVote,
  generateVote,
  type VoteDetail,
} from '../../services/api'
import './index.scss'

const LETTERS = ['A', 'B', 'C']

export default function FamilyVote() {
  const [vote, setVote] = useState<VoteDetail | null>(null)
  const [ingredients, setIngredients] = useState<string[]>([])
  const [input, setInput] = useState('')
  const [generating, setGenerating] = useState(false)
  const [voting, setVoting] = useState(false)

  useShareAppMessage(() => ({
    title: '🍲 今晚吃什么？全家投票来决定！',
    path: vote ? `/pages/family-vote/index?id=${vote.id}` : '/pages/index/index',
  }))

  useLoad((params) => {
    const id = (params as any).id as string | undefined
    if (id) loadVote(id)
  })

  const loadVote = async (id: string) => {
    try {
      const v = await fetchVote(id)
      setVote(v)
    } catch (e: any) {
      Taro.showToast({ title: e.message || '加载失败', icon: 'none' })
    }
  }

  const addIngredient = () => {
    const v = input.trim()
    if (!v) return
    if (ingredients.includes(v)) {
      Taro.showToast({ title: '已添加', icon: 'none' })
      return
    }
    setIngredients([...ingredients, v])
    setInput('')
  }

  const generate = async () => {
    if (ingredients.length === 0) {
      Taro.showToast({ title: '先告诉小伴冰箱里有什么', icon: 'none' })
      return
    }
    if (generating) return
    setGenerating(true)
    try {
      const v = await generateVote(ingredients)
      setVote(v)
    } catch (e: any) {
      Taro.showToast({ title: e.message || '生成失败', icon: 'none' })
    } finally {
      setGenerating(false)
    }
  }

  const doVote = async (idx: number) => {
    if (!vote || voting) return
    if (vote.my_choice === idx) return
    setVoting(true)
    try {
      const v = await castVote(vote.id, idx)
      setVote(v)
      Taro.showToast({ title: '投票成功！', icon: 'none' })
    } catch (e: any) {
      Taro.showToast({ title: e.message || '投票失败', icon: 'none' })
    } finally {
      setVoting(false)
    }
  }

  const shareToGroup = () => {
    Taro.showShareMenu({
      withShareTicket: true,
      success: () => Taro.showToast({ title: '点击右上角…分享给家庭群', icon: 'none' }),
    })
  }

  // 无投票：创建模式
  if (!vote) {
    return (
      <View className='page-content family-vote'>
        <NavBar title='家庭口味投票' showBack />

        <View className='field'>
          <View className='field-label'>✨ 冰箱里有什么（小伴生成 3 道菜）</View>
          <View className='chips'>
            {ingredients.map((i) => (
              <View key={i} className='chip chip--on'>
                <Text userSelect>{i}</Text>
                <Text userSelect className='x' onClick={() => setIngredients(ingredients.filter((x) => x !== i))}>×</Text>
              </View>
            ))}
            <View className='chip chip-add'>
              <Input
                className='chip-input'
                value={input}
                placeholder='＋ 添加食材'
                confirmType='done'
                onInput={(e) => setInput(e.detail.value)}
                onConfirm={() => { addIngredient(); }}
              />
            </View>
          </View>
        </View>

        <View className='sec'>
          <View className={`btn btn--red btn--block ${generating ? 'btn--disabled' : ''}`} onClick={generate}>
            <Text userSelect>{generating ? '生成中…' : '🍲 生成 3 道菜投票'}</Text>
          </View>
        </View>
      </View>
    )
  }

  const total = vote.total_count || 0

  return (
    <View className='page-content family-vote'>
      <NavBar title='今晚吃什么？' showBack />

      <View className='vote-q'>
        <Text userSelect className='vote-title'>🍲 3 道菜 · 全家投票</Text>
        <Text userSelect className='vote-sub'>小伴已结合冰箱食材生成 · {vote.status === 'closed' ? '投票已结束' : '投票决定今晚吃什么'}</Text>
      </View>

      {vote.options.map((opt, idx) => {
        const pct = total > 0 ? Math.round((opt.count / total) * 100) : 0
        const win = total > 0 && opt.count > 0 && opt.count === Math.max(...vote.options.map((o) => o.count))
        return (
          <View
            key={idx}
            className={`vote-opt ${win ? 'win' : ''}`}
            onClick={() => doVote(idx)}
          >
            {win && <View className='v-tag'><Text userSelect>已胜出</Text></View>}
            <View className='v-letter'><Text userSelect>{LETTERS[idx]}</Text></View>
            <View className='v-main'>
              <Text userSelect className='v-name'>{opt.name}</Text>
              <Text userSelect className='v-num'>{pct}%</Text>
            </View>
            <View className='v-bar' style={{ width: `${pct}%` }} />
          </View>
        )
      })}

      {vote.my_choice !== null && (
        <Text userSelect className='note vote-note'>你投了 {LETTERS[vote.my_choice as number]} · 共 {total} 人参与</Text>
      )}

      <View className='sec'>
        <Button className='btn btn--red btn--block' openType='share' onClick={shareToGroup}>
          <Text userSelect>分享到家庭群投票</Text>
        </Button>
      </View>

      {vote.status === 'active' && (
        <Text userSelect className='note vote-note'>投票结果实时同步 · 分享给家人一起决定</Text>
      )}
    </View>
  )
}
