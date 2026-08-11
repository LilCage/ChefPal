/**
 * 语音输入（原型 04 屏2）：长按麦克风录音 → 上传后端百炼 ASR 转文字
 * → 切分食材 chips（可删改/手动补充）→ 去厨房生成菜谱
 *
 * 无任何微信插件依赖；录音用 Taro.getRecorderManager（mp3），识别走后端 /voice/transcribe。
 */
import { Input, Text, View } from '@tarojs/components'
import Taro, { useUnload } from '@tarojs/taro'
import { useEffect, useRef, useState } from 'react'
import NavBar from '../../components/NavBar'
import { transcribeVoice } from '../../services/api'
import { parseIngredients } from '../../utils/parseIngredients'
import './index.scss'

function mergeUnique(prev: string[], next: string[]): string[] {
  const out = [...prev]
  for (const name of next) {
    if (!out.includes(name)) out.push(name)
  }
  return out
}

export default function VoiceInput() {
  const [recording, setRecording] = useState(false)
  const [transcribing, setTranscribing] = useState(false)
  const [liveText, setLiveText] = useState('')
  const [ingredients, setIngredients] = useState<string[]>([])
  const [manual, setManual] = useState('')
  const recorderRef = useRef<Taro.RecorderManager | null>(null)
  const recordingRef = useRef(false)

  useEffect(() => {
    const recorder = Taro.getRecorderManager()
    recorder.onStop((res) => {
      recordingRef.current = false
      setRecording(false)
      if (res && res.tempFilePath) {
        doTranscribe(res.tempFilePath)
      }
    })
    recorder.onError(() => {
      recordingRef.current = false
      setRecording(false)
      Taro.showToast({ title: '录音失败，请检查麦克风权限', icon: 'none' })
    })
    recorderRef.current = recorder
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useUnload(() => {
    if (recordingRef.current && recorderRef.current) recorderRef.current.stop()
  })

  const ensureRecordPermission = async (): Promise<boolean> => {
    try {
      const setting = await Taro.getSetting()
      if (setting.authSetting['scope.record']) return true
      try {
        await Taro.authorize({ scope: 'scope.record' })
        return true
      } catch {
        Taro.showModal({
          title: '需要麦克风权限',
          content: '语音输入需要麦克风权限，请在设置中开启后重试',
          confirmText: '去开启',
          success: (r) => { if (r.confirm) Taro.openSetting() },
        })
        return false
      }
    } catch {
      return true
    }
  }

  const startRec = async () => {
    if (recordingRef.current || transcribing) return
    const ok = await ensureRecordPermission()
    if (!ok) return
    setLiveText('')
    recordingRef.current = true
    setRecording(true)
    recorderRef.current?.start({ duration: 30000, format: 'mp3' })
  }

  const stopRec = () => {
    if (recordingRef.current && recorderRef.current) recorderRef.current.stop()
  }

  const doTranscribe = async (filePath: string) => {
    setTranscribing(true)
    setLiveText('正在识别…')
    try {
      const text = await transcribeVoice(filePath)
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
    } catch (e: any) {
      Taro.showToast({ title: e.message || '识别失败，请重试', icon: 'none' })
    } finally {
      setTranscribing(false)
    }
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
    // 延迟跳转：避免 setStorageSync 后立即 switchTab，触发渲染层「first rendering data」竞态
    setTimeout(() => Taro.switchTab({ url: '/pages/kitchen/index' }), 50)
  }

  return (
    <View className='page-content voice-input'>
      <NavBar title='语音描述食材' showBack />

      {/* 上区：提示 + 识别结果 + 食材 chips（可滚动） */}
      <View className='voice-top'>
        <Text userSelect className='voice-hint'>长按下方麦克风，说出冰箱里的食材</Text>

        {liveText ? (
          <View className='bubble voice-bubble'>
            <View className='star-burst star-burst--sm'><Text userSelect>{transcribing ? '识别中' : '录音中'}</Text></View>
            <Text userSelect className='voice-text'>{liveText}</Text>
          </View>
        ) : null}

        <View className='field voice-field'>
          <View className='chips'>
            {ingredients.map((i) => (
              <View key={i} className='chip chip--on'>
                <Text userSelect>{i}</Text>
                <Text userSelect className='x' onClick={() => remove(i)}>×</Text>
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
          <Text userSelect className='note note--mt'>识别结果仅供参考 · 点标签可删除，点添加可补充</Text>
        </View>
      </View>

      {/* 下区：固定底部操作坞（生成按钮 + 麦克风），拇指区 */}
      <View className='voice-dock'>
        <View className='btn btn--red btn--block voice-go' onClick={goKitchen}>
          <Text userSelect>用这些食材去生成菜谱 →</Text>
        </View>
        <View
          className={`mic-big ${recording ? 'recording' : ''} ${transcribing ? 'transcribing' : ''}`}
          onTouchStart={startRec}
          onTouchEnd={stopRec}
          onTouchCancel={stopRec}
        >
          <View className='ic ic-mic' />
        </View>
        <Text userSelect className='dock-hint'>
          {transcribing ? '小伴识别中…' : recording ? '正在录音… 松开结束' : '长按说话'}
        </Text>
      </View>
    </View>
  )
}
