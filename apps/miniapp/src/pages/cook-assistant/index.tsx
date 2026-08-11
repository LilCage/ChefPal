/**
 * 语音烹饪助手（EXT-14.1）：做饭时解放双手
 * 左侧步骤卡片 + 当前步骤高亮/上一步/下一步 + 底部固定麦克风，长按说话提问
 * 录音 → /voice/transcribe 转文字 → /cook-assistant/query 基于菜谱上下文回答
 */
import { Text, View } from '@tarojs/components'
import Taro, { useLoad, useUnload } from '@tarojs/taro'
import { useEffect, useRef, useState } from 'react'
import NavBar from '../../components/NavBar'
import { askCookAssistant, fetchRecipe, transcribeVoice, type Recipe } from '../../services/api'
import './index.scss'

export default function CookAssistant() {
  const [recipe, setRecipe] = useState<Recipe | null>(null)
  const [current, setCurrent] = useState(0)
  const [recording, setRecording] = useState(false)
  const [processing, setProcessing] = useState(false)
  const [answer, setAnswer] = useState<string | null>(null)
  const [questionText, setQuestionText] = useState('')
  const recorderRef = useRef<Taro.RecorderManager | null>(null)
  const recordingRef = useRef(false)

  useLoad((params) => {
    const id = (params as any).id as string
    if (!id) {
      Taro.showToast({ title: '缺少菜谱参数', icon: 'none' })
      return
    }
    fetchRecipe(id)
      .then(setRecipe)
      .catch((e: any) => Taro.showToast({ title: e.message || '加载菜谱失败', icon: 'none' }))
  })

  useEffect(() => {
    const recorder = Taro.getRecorderManager()
    recorder.onStop((res) => {
      recordingRef.current = false
      setRecording(false)
      if (res && res.tempFilePath) {
        doAsk(res.tempFilePath)
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
          content: '语音提问需要麦克风权限，请在设置中开启后重试',
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
    if (recordingRef.current || processing || !recipe) return
    const ok = await ensureRecordPermission()
    if (!ok) return
    setAnswer(null)
    setQuestionText('正在听…')
    recordingRef.current = true
    setRecording(true)
    recorderRef.current?.start({ duration: 15000, format: 'mp3' })
  }

  const stopRec = () => {
    if (recordingRef.current && recorderRef.current) recorderRef.current.stop()
  }

  const doAsk = async (filePath: string) => {
    if (!recipe) return
    setProcessing(true)
    setQuestionText('识别中…')
    try {
      const text = await transcribeVoice(filePath)
      if (!text) {
        setQuestionText('')
        Taro.showToast({ title: '没听清，再试一次', icon: 'none' })
        return
      }
      setQuestionText(`🗣 "${text}"`)
      const res = await askCookAssistant(recipe.id, text)
      setAnswer(res.answer)
      if (res.current_step && res.current_step >= 1 && res.current_step <= recipe.steps.length) {
        setCurrent(res.current_step - 1)
      }
    } catch (e: any) {
      setQuestionText('')
      Taro.showToast({ title: e.message || '回答失败，请重试', icon: 'none' })
    } finally {
      setProcessing(false)
    }
  }

  const goPrev = () => setCurrent((c) => Math.max(0, c - 1))
  const goNext = () => setCurrent((c) => Math.min((recipe?.steps.length || 1) - 1, c + 1))

  if (!recipe) {
    return (
      <View className='page-content cook-asst'>
        <NavBar title='语音烹饪助手' showBack />
        <View className='note center-load'>加载菜谱中…</View>
      </View>
    )
  }

  return (
    <View className='page-content cook-asst'>
      <NavBar title={recipe.title} showBack />

      <View className='ca-top'>
        <View className='ca-title-row'>
          <Text userSelect className='ca-name'>{recipe.title}</Text>
          <View className='mini-chip gold'><Text userSelect>{recipe.style || '家常'}</Text></View>
        </View>

        <View className='ca-answer'>
          {questionText ? (
            <>
              <View className='bubble qbubble'><Text userSelect className='qtext'>{questionText}</Text></View>
              {answer && (
                <View className='bubble abubble'>
                  <View className='star-burst star-burst--sm'><Text userSelect>大厨说</Text></View>
                  <Text userSelect className='atext'>{answer}</Text>
                </View>
              )}
            </>
          ) : (
            <Text userSelect className='ca-hint'>长按下方麦克风提问，如"下一步做什么""放多少盐""要开多大火"</Text>
          )}
        </View>

        <View className='step-nav'>
          <View className='nav-btn' onClick={goPrev}><View className='ic ic-chev-l ic-sm' /><Text userSelect>上一步</Text></View>
          <View className='step-progress'><Text userSelect>第 {current + 1} / {recipe.steps.length} 步</Text></View>
          <View className='nav-btn' onClick={goNext}><Text userSelect>下一步</Text><View className='ic ic-chev-r ic-sm' /></View>
        </View>
      </View>

      <View className='ca-steps'>
        {recipe.steps.map((st, i) => (
          <View
            key={i}
            className={`ca-step ${i === current ? 'on' : ''} ${i < current ? 'done' : ''}`}
            onClick={() => setCurrent(i)}
          >
            <View className={`sno ${i % 2 === 1 ? 'gold' : ''}`}>
              <Text userSelect>{i < current ? '✓' : i + 1}</Text>
            </View>
            <View className='step-body'>
              <Text userSelect className='step-title'>{st.title}</Text>
              <Text userSelect className='step-detail'>{st.detail}</Text>
            </View>
          </View>
        ))}
      </View>

      <View className='ca-dock'>
        <View
          className={`mic-big ${recording ? 'recording' : ''} ${processing ? 'processing' : ''}`}
          onTouchStart={startRec}
          onTouchEnd={stopRec}
          onTouchCancel={stopRec}
        >
          <View className='ic ic-mic' />
        </View>
        <Text userSelect className='dock-hint'>
          {processing ? '小伴回答中…' : recording ? '正在录音… 松开结束' : '长按说话提问'}
        </Text>
        <Text userSelect className='dock-note'>双手不便？直接问就行，小伴结合当前步骤回答</Text>
      </View>
    </View>
  )
}
