/**
 * 屏3 · 厨房 食材魔方（核心差异化，原型 01）
 * 标签式食材输入 → 小伴生成 TOP3 菜谱
 */
import { Input, Text, View } from '@tarojs/components'
import Taro, { useDidShow } from '@tarojs/taro'
import { useState } from 'react'
import RecipeCard from '../../components/RecipeCard'
import { generateRecipes, type Recipe } from '../../services/api'
import { useAuthStore } from '../../stores/auth'
import { useTabStore } from '../../stores/tab'
import { getSafeTop } from '../../utils/safeArea'
import './index.scss'

const QUICK_INGREDIENTS = ['西红柿', '鸡蛋', '面条', '土豆', '鸡翅']

export default function Kitchen() {
  const setTab = useTabStore((s) => s.setIndex)
  const preferences = useAuthStore((s) => s.user?.preferences)
  const [ingredients, setIngredients] = useState<string[]>([])
  const [input, setInput] = useState('')
  const [recipes, setRecipes] = useState<Recipe[]>([])
  const [loading, setLoading] = useState(false)

  useDidShow(() => {
    // 延后到首渲染完成再更新状态：useDidShow 首次触发时同步 setData
    // 会与微信基础库首渲染快照竞态（Expected updated data but get first rendering data）。
    Taro.nextTick(() => {
      setTab(1)
      // 拍照识食材/语音输入页跳转过来时，读取待注入食材并清空
      const pending = Taro.getStorageSync('pending_ingredients')
      if (Array.isArray(pending) && pending.length > 0) {
        setIngredients((prev) => {
          const merged = [...prev]
          for (const name of pending) {
            if (typeof name === 'string' && name.trim() && !merged.includes(name.trim())) {
              merged.push(name.trim())
            }
          }
          return merged
        })
        Taro.removeStorageSync('pending_ingredients')
      }
    })
  })

  const addIngredient = (name: string) => {
    const v = name.trim()
    if (!v) return
    if (ingredients.includes(v)) {
      Taro.showToast({ title: '已添加该食材', icon: 'none' })
      return
    }
    setIngredients([...ingredients, v])
  }

  const removeIngredient = (name: string) => {
    setIngredients(ingredients.filter((i) => i !== name))
  }

  const generate = async () => {
    if (ingredients.length === 0) {
      Taro.showToast({ title: '先告诉我冰箱里有什么', icon: 'none' })
      return
    }
    setLoading(true)
    try {
      const list = await generateRecipes(ingredients)
      setRecipes(list)
      Taro.showToast({ title: '捕获成功！', icon: 'none' })
    } catch (e: any) {
      Taro.showToast({ title: e.message || '生成失败', icon: 'none' })
    } finally {
      setLoading(false)
    }
  }

  const spicinessMap: Record<number, string> = { 0: '不吃辣', 1: '微辣', 2: '中辣', 3: '特辣' }
  const prefsText = preferences
    ? [
        typeof preferences.spiciness === 'number' ? spicinessMap[preferences.spiciness] || `辣度${preferences.spiciness}` : '',
        preferences.saltiness || '',
        Array.isArray(preferences.allergies) && preferences.allergies.filter((a: string) => a && a !== '无忌口').length
          ? `忌口:${preferences.allergies.filter((a: string) => a && a !== '无忌口').join('/')}`
          : '',
      ]
        .filter(Boolean)
        .join(' · ')
    : ''

  const goPhoto = () => Taro.navigateTo({ url: '/pages/photo-capture/index' })
  const goVoice = () => Taro.navigateTo({ url: '/pages/voice-input/index' })
  const goRescue = () => Taro.navigateTo({ url: '/pages/dark-rescue/index' })
  const goAgents = () => Taro.navigateTo({ url: '/pages/multi-agent/index' })
  const goFridge = () => Taro.navigateTo({ url: '/pages/fridge/index' })

  return (
    <View className='page-content kitchen'>
      <View className='nav' style={{ paddingTop: `${getSafeTop()}px` }}>
        <View className='nav-title pop'>食材魔方</View>
      </View>

      <View className='section'>
        <View className='sec-title'>✨ 告诉我冰箱里有什么</View>
        <View className='field'>
          <View className='chips'>
            {ingredients.map((i) => (
              <View key={i} className='chip chip--on'>
                <Text>{i}</Text>
                <Text className='x' onClick={() => removeIngredient(i)}>×</Text>
              </View>
            ))}
          </View>

          {/* 大输入框 + 添加按钮 */}
          <View className='add-row'>
            <Input
              className='add-input'
              value={input}
              placeholder='输入食材名，如：西红柿'
              confirmType='done'
              onInput={(e) => setInput(e.detail.value)}
              onConfirm={() => { addIngredient(input); setInput('') }}
              onBlur={() => setInput('')}
            />
            <View className='btn btn--gold add-btn' onClick={() => { addIngredient(input); setInput('') }}>
              <Text>添加</Text>
            </View>
          </View>

          {/* 输入方式：拍照 / 语音，贴着输入框 */}
          <View className='input-row'>
            <View className='photo-chip' onClick={goPhoto}>
              <View className='ic ic-camera ic-sm' />
              <Text>拍照识食材</Text>
            </View>
            <View className='photo-chip' onClick={goVoice}>
              <View className='ic ic-mic ic-sm' />
              <Text>语音输入</Text>
            </View>
          </View>

          <View className='quick-row'>
            {QUICK_INGREDIENTS.filter((q) => !ingredients.includes(q)).map((q) => (
              <View key={q} className='chip' onClick={() => addIngredient(q)}><Text>+{q}</Text></View>
            ))}
          </View>

          <Text className='note'>
            {prefsText ? `已读取你的口味偏好 · ${prefsText}` : '尚未设置口味偏好，可在「我的」中设置'}
          </Text>
        </View>
      </View>

      <View className='section generate-sec'>
        <View className='btn btn--red generate-btn' onClick={generate}>
          <View className='ic ic-spark--white' />
          <Text>{loading ? '生成魔法菜谱中…' : '生成魔法菜谱'}</Text>
        </View>
        <Text className='note generate-note'>基于 {ingredients.length} 种食材 · 小伴实时生成 TOP3</Text>

        {/* 趣味工具：移到生成按钮下方 */}
        <View className='fun-row'>
          <View className='fun-chip' onClick={goRescue}>
            <Text className='fun-emoji'>🥣</Text>
            <Text>翻车拯救</Text>
          </View>
          <View className='fun-chip' onClick={goAgents}>
            <Text className='fun-emoji'>🤝</Text>
            <Text>小伴主厨团</Text>
          </View>
          <View className='fun-chip' onClick={goFridge}>
            <Text className='fun-emoji'>🧊</Text>
            <Text>冰箱管家</Text>
          </View>
        </View>
      </View>

      {recipes.length > 0 && (
        <View className='section'>
          <View className='sec-title'>
            今日推荐 · 匹配度 TOP3
            <View className='more' onClick={generate}>换一批</View>
          </View>
          <View className='r-grid'>
            {recipes.map((r, i) => (
              <RecipeCard
                key={r.id}
                name={r.title}
                matchScore={r.match_score}
                timeMinutes={r.time_minutes}
                difficulty={r.difficulty}
                style={r.style}
                missing={r.missing_seasonings}
                wide={i === 2}
                onClick={() => Taro.navigateTo({ url: `/pages/recipe-detail/index?id=${r.id}` })}
              />
            ))}
          </View>
        </View>
      )}
    </View>
  )
}
