/**
 * 烹饪挑战（原型 05 屏4）：挑战 hero 卡（速度线+进度）+ 排行榜 + 我要挑战/创建挑战
 * 数据源 /challenges 系列（无 AI 调用）
 */
import { Input, Text, View } from '@tarojs/components'
import Taro, { useDidShow } from '@tarojs/taro'
import { useState } from 'react'
import NavBar from '../../components/NavBar'
import {
  createChallenge,
  fetchChallenges,
  fetchLeaderboard,
  joinChallenge,
  updateChallengeProgress,
  type Challenge,
  type LeaderboardItem,
} from '../../services/api'
import './index.scss'

export default function CookingChallenge() {
  const [list, setList] = useState<Challenge[]>([])
  const [active, setActive] = useState<Challenge | null>(null)
  const [board, setBoard] = useState<LeaderboardItem[]>([])
  const [mySpend, setMySpend] = useState('')
  const [myMeals, setMyMeals] = useState('')
  const [creating, setCreating] = useState(false)
  const [newTitle, setNewTitle] = useState('')
  const [newBudget, setNewBudget] = useState('')

  useDidShow(() => {
    load()
  })

  const load = async () => {
    try {
      const data = await fetchChallenges()
      setList(data.items)
      if (data.items.length > 0 && !active) {
        setActive(data.items[0])
        loadBoard(data.items[0].id)
      }
    } catch (e: any) {
      Taro.showToast({ title: e.message || '加载失败', icon: 'none' })
    }
  }

  const loadBoard = async (id: string) => {
    try {
      const data = await fetchLeaderboard(id)
      setBoard(data.items)
    } catch {
      /* 忽略 */
    }
  }

  const switchChallenge = (c: Challenge) => {
    setActive(c)
    loadBoard(c.id)
  }

  const join = async () => {
    if (!active) return
    try {
      const res = await joinChallenge(active.id)
      setActive({ ...active, participant_count: res.participant_count })
      Taro.showToast({ title: res.joined ? '挑战开始！' : '已在挑战中', icon: 'none' })
    } catch (e: any) {
      Taro.showToast({ title: e.message || '加入失败', icon: 'none' })
    }
  }

  const updateProgress = async () => {
    if (!active) return
    try {
      await updateChallengeProgress(active.id, Number(mySpend) || 0, Number(myMeals) || 0)
      Taro.showToast({ title: '进度已更新！', icon: 'none' })
      loadBoard(active.id)
      load()
    } catch (e: any) {
      Taro.showToast({ title: e.message || '更新失败', icon: 'none' })
    }
  }

  const create = async () => {
    if (!newTitle.trim()) {
      Taro.showToast({ title: '先给挑战起个名字', icon: 'none' })
      return
    }
    if (creating) return
    setCreating(true)
    try {
      await createChallenge({
        title: newTitle.trim(),
        budget: Number(newBudget) || 0,
        description: `新挑战：${newTitle.trim()}`,
      })
      setNewTitle('')
      setNewBudget('')
      Taro.showToast({ title: '挑战创建成功！', icon: 'none' })
      await load()
    } catch (e: any) {
      Taro.showToast({ title: e.message || '创建失败', icon: 'none' })
    } finally {
      setCreating(false)
    }
  }

  return (
    <View className='page-content cooking-challenge'>
      <NavBar title={<Text className='pop'>烹饪挑战</Text>} showBack />

      {active ? (
        <View className='chal-hero'>
          <View className='speedlines' />
          <Text className='chal-title'>🏆 {active.title}</Text>
          <Text className='chal-desc'>
            {active.description || `${active.budget ? `预算 ${active.budget} 元` : ''} · 挑战进行中`}
          </Text>
          <View className='chal-progress'>
            <View className='chal-progress-fill' style={{ width: `${Math.min(100, (active.participant_count % 101))}%` }} />
          </View>
          <View className='chal-meta'>
            <Text>预算 ¥{active.budget}</Text>
            <Text>{active.participant_count} 人参与</Text>
          </View>
        </View>
      ) : (
        <View className='empty'>
          <Text className='empty-art'>🏆</Text>
          <Text className='empty-title'>还没有挑战</Text>
          <Text className='empty-desc'>发起第一个烹饪挑战，和大家一起玩</Text>
        </View>
      )}

      <View className='sec'>
        <View className='sec-title'>🥇 挑战排行榜</View>
      </View>

      <View className='rank-list'>
        {board.length === 0 ? (
          <View className='rank-empty'>
            <Text className='note'>还没有人参与，快来抢占榜首！</Text>
          </View>
        ) : (
          board.map((it, idx) => (
            <View key={it.user_id} className={`rank-item ${it.is_me ? 'me' : ''}`}>
              <View className='r-no'><Text>{idx + 1}</Text></View>
              <Text className='r-name'>{it.nickname}{it.is_me ? '（我）' : ''}</Text>
              <Text className='r-days'>{it.meal_count} 餐 · ¥{it.spend}</Text>
            </View>
          ))
        )}
      </View>

      {list.length > 1 && (
        <View className='sec'>
          <View className='sec-title'>🔥 全部挑战</View>
          <View className='chips'>
            {list.map((c) => (
              <View
                key={c.id}
                className={`chip ${active?.id === c.id ? 'chip--on' : ''}`}
                onClick={() => switchChallenge(c)}
              >
                <Text>{c.title}</Text>
              </View>
            ))}
          </View>
        </View>
      )}

      <View className='sec'>
        <View className='sec-title'>💸 更新我的进度</View>
        <View className='field'>
          <View className='progress-row'>
            <Input
              className='progress-input'
              type='number'
              value={mySpend}
              placeholder='已花 ¥'
              onInput={(e) => setMySpend(e.detail.value)}
            />
            <Input
              className='progress-input'
              type='number'
              value={myMeals}
              placeholder='完成餐数'
              onInput={(e) => setMyMeals(e.detail.value)}
            />
          </View>
          <View className={`btn btn--gold btn--block ${!active ? 'btn--disabled' : ''}`} onClick={updateProgress}>
            <Text>更新进度</Text>
          </View>
        </View>
      </View>

      <View className='sec'>
        <View className={`btn btn--red btn--block ${!active ? 'btn--disabled' : ''}`} onClick={join}>
          <Text>我要挑战 →</Text>
        </View>
      </View>

      <View className='sec create-sec'>
        <View className='sec-title'>＋ 创建挑战</View>
        <View className='field'>
          <Input
            className='create-input'
            value={newTitle}
            placeholder='挑战名称，如「一周只花 50 元」'
            onInput={(e) => setNewTitle(e.detail.value)}
          />
          <Input
            className='create-input'
            type='number'
            value={newBudget}
            placeholder='预算（元）'
            onInput={(e) => setNewBudget(e.detail.value)}
          />
          <View className={`btn btn--white btn--block btn--sm ${creating ? 'btn--disabled' : ''}`} onClick={create}>
            <Text>{creating ? '创建中…' : '＋ 创建挑战'}</Text>
          </View>
        </View>
      </View>
    </View>
  )
}
