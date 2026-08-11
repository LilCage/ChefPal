/**
 * 膳食规划（原型 04 屏3 + 屏4）：3天/7天 切换
 * - 3 天：今天/明天/后天 tabs + 早中晚三餐 + 汇总 + 一键购物清单
 * - 7 天：周一~周日周条 + 当日三餐 + 营养分析条（热量/蛋白/脂肪/碳水）+ 生成本周购物清单
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
  type PlanDay,
} from '../../services/api'
import './index.scss'

const MEAL_ICONS: Record<string, string> = { 早餐: '🌅', 午餐: '☀️', 晚餐: '🌙' }

type Mode = 3 | 7

/** 宏量营养目标基线：以约 2000 千卡为参考，蛋白 18% / 脂肪 25% / 碳水 55% */
function macroTargets(kcalRef = 2000) {
  return {
    kcal: kcalRef,
    protein: Math.round((kcalRef * 0.18) / 4),
    fat: Math.round((kcalRef * 0.25) / 9),
    carbs: Math.round((kcalRef * 0.55) / 4),
  }
}

export default function MealPlanPage() {
  const [mode, setMode] = useState<Mode>(3)
  const [plan, setPlan] = useState<MealPlan | null>(null)
  const [activeDay, setActiveDay] = useState(0)
  const [loading, setLoading] = useState(false)
  const [generating, setGenerating] = useState(false)

  useDidShow(() => {
    if (!plan) loadLatest()
  })

  const loadLatest = async () => {
    try {
      const p = await fetchLatestPlan()
      setPlan(p)
      setMode(p.data.days.length === 7 ? 7 : 3)
      setActiveDay(0)
    } catch {
      /* 无计划：显示空状态，引导生成 */
    }
  }

  const switchMode = (m: Mode) => {
    if (m === mode) return
    setMode(m)
    if (plan && plan.data.days.length !== m) {
      setPlan(null) // 新模式下无现成计划，引导生成
      setActiveDay(0)
    }
  }

  const regenerate = async () => {
    if (generating) return
    setGenerating(true)
    try {
      const p = await generatePlan(undefined, mode)
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

  const title = mode === 3 ? '3 天膳食计划' : '7 天膳食计划'

  return (
    <View className='page-content meal-plan'>
      <NavBar title={title} showBack />

      <View className='seg'>
        <View className={`seg-item ${mode === 3 ? 'on' : ''}`} onClick={() => switchMode(3)}><Text>3 天</Text></View>
        <View className={`seg-item ${mode === 7 ? 'on' : ''}`} onClick={() => switchMode(7)}><Text>7 天 + 营养</Text></View>
      </View>

      {!plan ? (
        <View className='empty'>
          <View className='empty-art'><Text>📅</Text></View>
          <Text className='empty-title'>还没有{mode === 3 ? '3 天' : '7 天'}膳食计划</Text>
          <Text className='empty-desc'>
            {mode === 3
              ? '基于你的口味偏好，小伴生成 3 天 × 早中晚三餐'
              : '基于你的口味偏好，小伴生成 7 天计划 + 每天营养分析（热量/蛋白/脂肪/碳水）'}
          </Text>
          <View className='btn btn--red btn--block' onClick={regenerate}>
            <Text>{generating ? '生成中…' : `生成我的${mode === 3 ? '3 天' : '7 天'}膳食计划`}</Text>
          </View>
        </View>
      ) : mode === 3 ? (
        <ThreeDayView
          plan={plan}
          activeDay={activeDay}
          setActiveDay={setActiveDay}
          generating={generating}
          regenerate={regenerate}
          goShopping={goShopping}
        />
      ) : (
        <SevenDayView
          plan={plan}
          activeDay={activeDay}
          setActiveDay={setActiveDay}
          generating={generating}
          regenerate={regenerate}
          goShopping={goShopping}
        />
      )}
    </View>
  )
}

/* ---------- 3 天视图 ---------- */
function ThreeDayView({
  plan,
  activeDay,
  setActiveDay,
  generating,
  regenerate,
  goShopping,
}: {
  plan: MealPlan
  activeDay: number
  setActiveDay: (i: number) => void
  generating: boolean
  regenerate: () => void
  goShopping: () => void
}) {
  const days = plan.data.days
  const day = days[activeDay] || days[0]
  const dishCount = day?.meals.reduce((sum, m) => sum + m.dishes.length, 0) || 0

  return (
    <>
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
    </>
  )
}

/* ---------- 7 天视图 ---------- */
function SevenDayView({
  plan,
  activeDay,
  setActiveDay,
  generating,
  regenerate,
  goShopping,
}: {
  plan: MealPlan
  activeDay: number
  setActiveDay: (i: number) => void
  generating: boolean
  regenerate: () => void
  goShopping: () => void
}) {
  const days = plan.data.days
  const day: PlanDay | undefined = days[activeDay] || days[0]

  return (
    <>
      <View className='week-strip'>
        {days.map((d, i) => (
          <View key={d.day_label} className={`wday ${i === activeDay ? 'on' : ''}`} onClick={() => setActiveDay(i)}>
            <Text className='wday-label'>{d.day_label}</Text>
          </View>
        ))}
      </View>

      <View className='today-plan'>
        <View className='tp-head'>
          <Text className='tp-date'>📅 {day?.day_label}</Text>
          <Text className='tp-kcal'>目标约 {day?.total_kcal} 千卡</Text>
        </View>
        {day?.meals.map((meal) => (
          <View key={meal.name} className='tp-row'>
            <View className='tp-ic'><Text>{MEAL_ICONS[meal.name] || '🍽'}</Text></View>
            <Text className='tp-meal'>{meal.name} · {meal.dishes.map((d) => d.name).join('、')}</Text>
            <Text className='tp-kcal-num'>{meal.total_kcal}</Text>
          </View>
        ))}
      </View>

      <NutritionBars day={day} />

      <View className='sec'>
        <View className={`btn btn--white btn--block btn--sm btn--regen ${generating ? 'btn--disabled' : ''}`} onClick={regenerate}>
          <Text>{generating ? '…' : '↻ 重新生成'}</Text>
        </View>
        <View className={`btn btn--red btn--block ${generating ? 'btn--disabled' : ''}`} onClick={goShopping}>
          <View className='ic ic-cart ic-sm' />
          <Text>{generating ? '生成购物清单中…' : '生成本周购物清单'}</Text>
        </View>
      </View>
      <Text className='note nutri-note'>营养分析以约 2000 千卡为参考基线，实际请按你的目标调整</Text>
    </>
  )
}

/* ---------- 营养条 ---------- */
function NutritionBars({ day }: { day?: PlanDay }) {
  const targets = macroTargets()
  const rows = [
    { label: '热量', unit: '千卡', value: day?.total_kcal || 0, target: targets.kcal, grad: true },
    { label: '蛋白质', unit: 'g', value: day?.protein_g || 0, target: targets.protein, grad: false },
    { label: '脂肪', unit: 'g', value: day?.fat_g || 0, target: targets.fat, grad: false },
    { label: '碳水', unit: 'g', value: day?.carbs_g || 0, target: targets.carbs, grad: false },
  ]

  return (
    <View className='nutri-block'>
      <View className='nutri-title'><Text>🍎 营养分析 · 全天合计</Text></View>
      {rows.map((r) => {
        const pct = Math.min(100, Math.round((r.value / r.target) * 100))
        const bg = r.grad
          ? 'linear-gradient(90deg, var(--gold), var(--red))'
          : r.label === '蛋白质' ? 'var(--red)' : r.label === '脂肪' ? 'var(--gold)' : 'var(--green)'
        return (
          <View key={r.label} className='nutri-row'>
            <Text className='nlabel'>{r.label}</Text>
            <View className='track'><View className='track-fill' style={{ width: `${pct}%`, background: bg }} /></View>
            <Text className='nval'>{r.value}/{r.target}{r.unit === '千卡' ? '' : 'g'}</Text>
          </View>
        )
      })}
    </View>
  )
}
