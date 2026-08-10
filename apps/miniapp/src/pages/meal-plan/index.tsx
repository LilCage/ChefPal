/**
 * 3 天膳食规划（原型 04 屏3）：今天/明天/后天 tabs + 早中晚三餐 + 汇总 + 一键购物清单
 */
import { Text, View } from '@tarojs/components'
import Taro, { useDidShow } from '@tarojs/taro'
import { useState } from 'react'
import NavBar from '../../components/NavBar'
import {
  fetchLatestPlan,
  generatePlan,
  generateShoppingList,
  type MealPlan,
} from '../../services/api'
import './index.scss'

const MEAL_ICONS: Record<string, string> = { 早餐: '🌅', 午餐: '☀️', 晚餐: '🌙' }

export default function MealPlanPage() {
  const [plan, setPlan] = useState<MealPlan | null>(null)
  const [activeDay, setActiveDay] = useState(0)
  const [loading, setLoading] = useState(false)
  const [generating, setGenerating] = useState(false)

  useDidShow(() => {
    if (!plan) loadLatest()
  })

  const loadLatest = async () => {
    try {
      setPlan(await fetchLatestPlan())
    } catch {
      /* 无计划：显示空状态，引导生成 */
    }
  }

  const regenerate = async () => {
    if (generating) return
    setGenerating(true)
    try {
      const p = await generatePlan()
      setPlan(p)
      setActiveDay(0)
      Taro.showToast({ title: '新计划生成！', icon: 'none' })
    } catch (e: any) {
      Taro.showToast({ title: e.message || '生成失败', icon: 'none' })
    } finally {
      setGenerating(false)
    }
  }

  const goShopping = async () => {
    if (generating) return
    setGenerating(true)
    try {
      await generateShoppingList()
      Taro.navigateTo({ url: '/pages/shopping-list/index' })
    } catch (e: any) {
      Taro.showToast({ title: e.message || '生成失败', icon: 'none' })
    } finally {
      setGenerating(false)
    }
  }

  if (!plan) {
    return (
      <View className='page-content meal-plan'>
        <NavBar title='3 天膳食计划' showBack />
        <View className='empty'>
          <View className='empty-art'>📅</View>
          <Text className='empty-title'>还没有膳食计划</Text>
          <Text className='empty-desc'>基于你的口味偏好，AI 生成 3 天 × 早中晚三餐</Text>
          <View className='btn btn--red btn--block' onClick={regenerate}>
            <Text>{generating ? '生成中…' : '生成我的膳食计划'}</Text>
          </View>
        </View>
      </View>
    )
  }

  const days = plan.data.days
  const day = days[activeDay] || days[0]
  const dishCount = day?.meals.reduce((sum, m) => sum + m.dishes.length, 0) || 0

  return (
    <View className='page-content meal-plan'>
      <NavBar title='3 天膳食计划' showBack />

      <View className='plan-tabs'>
        {days.map((d, i) => (
          <View key={d.day_label} className={`pt ${i === activeDay ? 'on' : ''}`} onClick={() => setActiveDay(i)}>
            <Text className='pt-label'>{d.day_label}</Text>
            {i > 0 && <Text className='pt-sub'>周{['六', '日'][i - 1] || ''}</Text>}
          </View>
        ))}
      </View>

      {day?.meals.map((meal) => (
        <View key={meal.name} className='meal-card'>
          <View className='meal-head'>
            <View className='m-ic'><Text>{MEAL_ICONS[meal.name] || '🍽'}</Text></View>
            <Text className='meal-name'>{meal.name}</Text>
            <Text className='meal-kcal'>约 {meal.total_kcal} 千卡</Text>
          </View>
          {meal.dishes.map((dish, di) => (
            <View key={di} className='meal-row'>
              <View className='done'><View className='ic ic-check ic-xs' /></View>
              <Text className='dish'>{dish.name}</Text>
            </View>
          ))}
        </View>
      ))}

      <View className='plan-summary'>
        <View className='ps'><Text className='ps-num'>{day?.total_kcal}</Text><Text className='ps-label'>今日千卡</Text></View>
        <View className='ps'><Text className='ps-num'>{day?.protein_g}g</Text><Text className='ps-label'>蛋白质</Text></View>
        <View className='ps'><Text className='ps-num'>{dishCount} 道</Text><Text className='ps-label'>今日菜品</Text></View>
      </View>

      <View className='sec'>
        <View className={`btn btn--white btn--block btn--sm btn--regen ${generating ? 'btn--disabled' : ''}`} onClick={regenerate}>
          <Text>{generating ? '…' : '↻ 重新生成'}</Text>
        </View>
        <View className={`btn btn--gold btn--block ${generating ? 'btn--disabled' : ''}`} onClick={goShopping}>
          <View className='ic ic-cart ic-sm' />
          <Text>{generating ? '生成购物清单中…' : '一键生成购物清单'}</Text>
        </View>
      </View>
    </View>
  )
}
