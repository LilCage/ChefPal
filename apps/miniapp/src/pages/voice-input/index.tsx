/**
 * 语音输入（原型 04 屏2）：长按麦克风 → 微信同声传译 ASR → 识别结果
 * → 切分食材 chips（可删改/手动补充）→ 去厨房生成菜谱
 *
 * 依赖微信「同声传译」插件（WechatSI）：需在 mp 后台 设置→第三方设置→插件管理 添加，
 * 未添加时给出引导并支持手动输入，不影响其他功能。
 */
import { Input, Text, View } from '@tarojs/components'
import Taro, { useUnload } from '@tarojs/taro'
import { useEffect, useRef, useState } from 'react'
import NavBar from '../../components/NavBar'
import { parseIngredients } from '../../utils/parseIngredients'
import './index.scss'

type RecManager = {
  start: (opts: { duration: number; lang: string }) => void
  stop: () => void
  onStart?: (res: any) => void
  onRecognize?: (res: any) => void
  onStop?: (res: any) => void
  onError?: (res: any) => void
}

function mergeUnique(prev: string[], next: string[]): string[] {
  const out = [...prev]
  for (const name of next) {
    if (!out.includes(name)) out.push(name)
  }
  return out
}

export default function VoiceInput() {
  const [recording, setRecording] = useState(false)
  const [liveText, setLiveText] = useState('')
  const [ingredients, setIngredients] = useState<string[]>([])
  const [manual, setManual] = useState('')
  const managerRef = useRef<RecManager | null>(null)
  const pluginReady = useRef(false)

  useEffect(() => {
    if (process.env.TARO_ENV !== 'weapp') return
    try {
      const plugin = Taro.requirePlugin('WechatSI')
      const m: RecManager = plugin.getRecordRecognitionManager()
      m.onStart = () => setRecording(true)
      m.onRecognize = (res) => setLiveText(res?.result || '')
      m.onStop = (res) => {
        setRecording(false)
        const text = res?.result || ''
        setLiveText('')
        if (!text) {
          Taro.showToast({ title: '没听清，再试一次', icon: 'none' })
          return
        }
        const items = parseIngredients(text)
        if (items.length) {
          setIngredients((prev) => mergeUnique(prev, items))
          Taro.showToast({ title: `识别出 ${items.length} 种食材！`, icon: 'none' })
        } else {
          Taro.showToast({ title: '没识别到食材，试试手动添加', icon: 'none' })
        }
      }
      m.onError = (res) => {
        setRecording(false)
        Taro.showToast({ title: res?.msg || '识别失败，请重试', icon: 'none' })
      }
      managerRef.current = m
      pluginReady.current = true
    } catch {
      /* 插件未添加：保持手动输入兜底 */
      pluginReady.current = false
    }
  }, [])

  useUnload(() => {
    if (recording) managerRef.current?.stop()
  })

  const startRec = () => {
    if (!pluginReady.current || !managerRef.current) {
      Taro.showModal({
        title: '语音识别不可用',
        content: '未配置「同声传译」插件。请在 mp.weixin.qq.com 后台：设置→第三方设置→插件管理，搜索「微信同声传译」添加后重试；也可以直接手动输入食材。',
        showCancel: false,
        confirmText: '知道了',
      })
      return
    }
    setLiveText('')
    managerRef.current.start({ duration: 60000, lang: 'zh_CN' })
  }

  const stopRec = () => {
    if (recording) managerRef.current?.stop()
  }

  const remove = (name: string) => setIngredients(ingredients.filter((i) => i !== name))

  const addManual = () => {
    const v = manual.trim()
    if (!v) return
    if (!ingredients.includes(v)) setIngredients([...ingredients, v])
    setManual('')
  }

  const goKitchen = () => {
    if (ingredients.length === 0) {
      Taro.showToast({ title: '先添加食材', icon: 'none' })
      return
    }
    Taro.setStorageSync('pending_ingredients', ingredients)
    Taro.switchTab({ url: '/pages/kitchen/index' })
  }

  return (
    <View className='page-content voice-input'>
      <NavBar title='语音描述食材' showBack />

      <View className='voice-zone'>
        <View
          className={`mic-big ${recording ? 'recording' : ''}`}
          onTouchStart={startRec}
          onTouchEnd={stopRec}
          onTouchCancel={stopRec}
        >
          <View className='ic ic-mic' />
        </View>
        <View className='wave'>
          <View className='w-bar' /><View className='w-bar' /><View className='w-bar' />
          <View className='w-bar' /><View className='w-bar' /><View className='w-bar' />
          <View className='w-bar' />
        </View>
        <Text className='voice-hint'>{recording ? '正在识别… 松开结束' : '长按说话，说出冰箱里的食材'}</Text>

        {liveText ? (
          <View className='bubble voice-bubble'>
            <View className='star-burst star-burst--sm'><Text>识别中</Text></View>
            <Text className='voice-text'>{liveText}</Text>
          </View>
        ) : null}

        <View className='field voice-field'>
          <View className='chips'>
            {ingredients.map((i) => (
              <View key={i} className='chip chip--on'>
                <Text>{i}</Text>
                <Text className='x' onClick={() => remove(i)}>×</Text>
              </View>
            ))}
            <View className='chip chip-add'>
              <Input
                className='chip-input'
                value={manual}
                placeholder='＋ 添加'
                confirmType='done'
                onInput={(e) => setManual(e.detail.value)}
                onConfirm={() => { addManual(); setManual('') }}
                onBlur={() => setManual('')}
              />
            </View>
          </View>
          <Text className='note note--mt'>识别结果仅供参考 · 点标签可删除，点添加可补充</Text>
        </View>

        <View className='btn btn--red btn--block' onClick={goKitchen}>
          <Text>用这些食材去生成菜谱 →</Text>
        </View>
      </View>
    </View>
  )
}
