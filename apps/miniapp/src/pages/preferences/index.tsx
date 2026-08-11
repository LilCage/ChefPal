/**
 * 口味设置（原型 02 屏2）：忌口 / 辣度 / 咸淡 / 技能 → 注入 AI 推荐偏好
 * + AI 口味记忆（EXT-13.1/13.2）：展示学习到的偏好画像，可一键清空
 */
import { Input, Text, View } from '@tarojs/components'
import Taro, { useDidShow } from '@tarojs/taro'
import { useState } from 'react'
import NavBar from '../../components/NavBar'
import { clearTasteMemory, fetchTasteMemory, updatePreferences, type TasteMemory } from '../../services/api'
import { useAuthStore } from '../../stores/auth'
import './index.scss'

const ALLERGIES = ['花生', '海鲜', '乳制品', '香菜', '无忌口']
const SPICINESS = [
  { label: '不吃辣', value: 0 },
  { label: '微辣', value: 1 },
  { label: '中辣', value: 2 },
  { label: '特辣', value: 3 },
]
const SALTINESS = ['偏淡', '适中', '偏咸']
const SKILLS = ['厨房小白', '进阶达人', '实力大厨']

export default function Preferences() {
  const user = useAuthStore((s) => s.user)
  const setUser = useAuthStore((s) => s.setUser)

  const prefs = user?.preferences || {}
  const [allergies, setAllergies] = useState<string[]>(prefs.allergies || [])
  const [newAllergy, setNewAllergy] = useState('')
  const [spiciness, setSpiciness] = useState<number>(prefs.spiciness ?? 1)
  const [saltiness, setSaltiness] = useState<string>(prefs.saltiness || '适中')
  const [skill, setSkill] = useState<string>(prefs.skill || '厨房小白')
  const [saving, setSaving] = useState(false)
  const [taste, setTaste] = useState<TasteMemory | null>(null)

  useDidShow(() => {
    fetchTasteMemory()
      .then(setTaste)
      .catch(() => setTaste(null))
  })

  const resetTaste = () => {
    Taro.showModal({
      title: '清空口味记忆',
      content: '清空后 AI 将不再根据你的历史收藏/点赞调整推荐。确定清空吗？',
      confirmColor: '#E8482A',
      success: async (r) => {
        if (!r.confirm) return
        try {
          await clearTasteMemory()
          setTaste(null)
          Taro.showToast({ title: '已清空口味记忆', icon: 'none' })
        } catch (e: any) {
          Taro.showToast({ title: e.message || '清空失败', icon: 'none' })
        }
      },
    })
  }

  // 自定义忌口（非预设项）
  const customAllergies = allergies.filter((a) => !ALLERGIES.includes(a))

  const toggleAllergy = (a: string) => {
    if (a === '无忌口') {
      setAllergies([])
      return
    }
    setAllergies((prev) => (prev.includes(a) ? prev.filter((x) => x !== a) : [...prev, a]))
  }

  const addCustomAllergy = () => {
    const v = newAllergy.trim()
    if (!v) return
    if (allergies.includes(v)) {
      Taro.showToast({ title: '该忌口已添加', icon: 'none' })
      return
    }
    if (allergies.length >= 10) {
      Taro.showToast({ title: '最多添加 10 项', icon: 'none' })
      return
    }
    if (v.length > 20) {
      Taro.showToast({ title: '忌口名称请控制在 20 字内', icon: 'none' })
      return
    }
    setAllergies((prev) => [...prev, v])
    setNewAllergy('')
  }

  const save = async () => {
    if (saving) return
    setSaving(true)
    try {
      const updated = await updatePreferences({
        allergies,
        spiciness,
        saltiness,
        skill,
      })
      setUser(updated)
      Taro.showToast({ title: '保存成功，AI 将按此偏好推荐', icon: 'none' })
      setTimeout(() => Taro.navigateBack(), 600)
    } catch (e: any) {
      Taro.showToast({ title: e.message || '保存失败', icon: 'none' })
    } finally {
      setSaving(false)
    }
  }

  return (
    <View className='page-content pref'>
      <NavBar title='口味设置' showBack />

      <View className='set-group'>
        <View className='set-t'>⚠ 忌口 <Text className='set-tip'>过敏 / 宗教 · 可多选，支持自定义</Text></View>
        <View className='chips'>
          {ALLERGIES.map((a) => (
            <View key={a} className={`chip ${a === '无忌口' ? (allergies.length === 0 ? 'chip--hot' : '') : allergies.includes(a) ? 'chip--on' : ''}`} onClick={() => toggleAllergy(a)}>
              <Text>{a}</Text>
            </View>
          ))}
          {customAllergies.map((a) => (
            <View key={a} className='chip chip--on' onClick={() => toggleAllergy(a)}>
              <Text>{a}</Text>
              <Text className='x'>×</Text>
            </View>
          ))}
        </View>

        <View className='custom-add'>
          <Input
            className='custom-input'
            value={newAllergy}
            maxlength={20}
            placeholder='自定义忌口，如：蘑菇'
            placeholderClass='custom-ph'
            onInput={(e) => setNewAllergy(e.detail.value)}
            onConfirm={addCustomAllergy}
          />
          <View className='btn btn--sm btn--gold custom-add-btn' onClick={addCustomAllergy}>
            <Text>添加</Text>
          </View>
        </View>
        <Text className='custom-hint'>输入忌口后点「添加」，点击标签可移除</Text>
      </View>

      <View className='set-group'>
        <View className='set-t'>🌶 辣度偏好</View>
        <View className='chips'>
          {SPICINESS.map((s) => (
            <View key={s.value} className={`chip ${spiciness === s.value ? 'chip--on' : ''}`} onClick={() => setSpiciness(s.value)}>
              <Text>{s.label}</Text>
            </View>
          ))}
        </View>
      </View>

      <View className='set-group'>
        <View className='set-t'>🧂 咸淡口味</View>
        <View className='opt-row'>
          {SALTINESS.map((s) => (
            <View key={s} className={`opt ${saltiness === s ? 'on' : ''}`} onClick={() => setSaltiness(s)}>
              <Text>{s}</Text>
            </View>
          ))}
        </View>
      </View>

      <View className='set-group'>
        <View className='set-t'>👨‍🍳 技能水平</View>
        <View className='opt-row'>
          {SKILLS.map((s) => (
            <View key={s} className={`opt ${skill === s ? 'on' : ''}`} onClick={() => setSkill(s)}>
              <Text>{s}</Text>
            </View>
          ))}
        </View>
        <Text className='note'>技能越高，步骤讲解越精简、术语越多</Text>
      </View>

      <View className='set-group'>
        <View className='set-t'>🧠 AI 口味记忆 <Text className='set-tip'>自动学习 · 注入推荐</Text></View>
        {taste && taste.total_signals > 0 ? (
          <View className='taste-box'>
            <View className='taste-line'>
              <Text className='taste-label'>收藏偏好</Text>
              <Text className='taste-value'>
                {taste.preferred_styles.length ? taste.preferred_styles.join(' / ') : '暂未记录'}
              </Text>
            </View>
            <View className='taste-line'>
              <Text className='taste-label'>关注话题</Text>
              <Text className='taste-value'>
                {taste.preferred_topics.length ? taste.preferred_topics.join(' / ') : '暂未记录'}
              </Text>
            </View>
            <Text className='note'>已学习 {taste.total_signals} 次行为 · 生成菜谱时自动按此调整风味</Text>
            <View className='btn btn--sm btn--white taste-reset' onClick={resetTaste}>
              <Text>清空口味记忆</Text>
            </View>
          </View>
        ) : (
          <View className='taste-empty'>
            <Text>收藏菜谱、点赞作品后，AI 会自动记住你的口味偏好</Text>
          </View>
        )}
      </View>

      <View className='save-wrap'>
        <View className='btn btn--red btn--block' onClick={save}>
          <Text>{saving ? '保存中…' : '保存偏好设置'}</Text>
        </View>
        <Text className='note note--center'>保存后，AI 生成菜谱将自动注入你的口味偏好</Text>
      </View>
    </View>
  )
}
