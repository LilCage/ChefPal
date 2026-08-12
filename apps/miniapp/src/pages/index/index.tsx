/**
 * 屏1/2 · 首页 对话式烹饪百科（原型 07）
 * 多轮会话聊天：消息气泡 + 流式打字机 + 结构化菜谱卡 + 链接自动解析 + 📎附件 + 长按说话 + 新对话。
 *
 * 输入坞：2 行大输入框（左上对齐·自适应增高） + 按钮行「＋新对话 | 📎上传 | 🎤⇄➤发送」。
 * 粘贴链接自动识别（输入框上方提示条）→ 发送走解析；上传文档（PDF/Word）→ 解析入对话。
 */
import { Image, ScrollView, Text, Textarea, View } from '@tarojs/components'
import Taro, { useDidShow, useUnload } from '@tarojs/taro'
import { useEffect, useRef, useState } from 'react'
import {
  addFavorite,
  askQAStream,
  fetchQASession,
  parseDocument,
  parseUrl,
  transcribeVoice,
  type QARecord,
  type QARecommendation,
} from '../../services/api'
import { useAuthStore } from '../../stores/auth'
import { useTabStore } from '../../stores/tab'
import { getSafeTop } from '../../utils/safeArea'
import './index.scss'

const HOT_QUESTIONS = [
  '红烧肉怎么做才能肥而不腻、入口即化',
  '蒸蛋怎么蒸才嫩滑没有蜂窝',
  '炖肉怎么去腥增香，肉质更软烂',
  '冰箱里的剩菜怎么变身新花样',
  '煎鱼怎么才能不破皮不粘锅',
  '青菜怎么炒才翠绿不变色',
  '天气太热了，推荐几道爽口的凉拌菜',
  '下班太累，推荐几道15分钟快手晚餐',
  '想吃辣，推荐几道香辣过瘾的下饭菜',
  '一个人住，一周的省事晚餐怎么安排',
  '减脂期晚餐吃什么，有肉有菜又不胖',
  '周末招待朋友，推荐一桌有面子的家常菜',
]

const SESSION_KEY = 'chefpal_session_id'
const URL_RE = /^https?:\/\/\S+/i
const PARSE_LABEL: Record<string, string> = { web: '网页', video: '视频', doc: '文档' }

/** 生成 UUID v4（会话 id，后端要求 UUID） */
function genUUID(): string {
  const s = 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'
  return s.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0
    const v = c === 'x' ? r : (r & 0x3) | 0x8
    return v.toString(16)
  })
}

/* placeholder 断行：单行可显示约 14 字，长文案在逗号或 ~14 字处断成两行 */
function wrapQuestion(q: string): string {
  if (q.length <= 14) return q
  const commaIdx = q.indexOf('，')
  if (commaIdx > 4 && commaIdx < q.length - 4) {
    return `${q.slice(0, commaIdx + 1)}\n${q.slice(commaIdx + 1)}`
  }
  return `${q.slice(0, 14)}\n${q.slice(14)}`
}

interface ChatMsg {
  id: string
  role: 'user' | 'assistant'
  text?: string // 用户文本 / 助理打字或错误文本
  record?: QARecord // 助理完整结构化回答
  pending?: boolean // 助理生成中（流式/解析中）
}

export default function Index() {
  const setTab = useTabStore((s) => s.setIndex)
  const user = useAuthStore((s) => s.user)
  const [messages, setMessages] = useState<ChatMsg[]>([])
  const [input, setInput] = useState('')
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [sending, setSending] = useState(false) // 有请求进行中，阻止并发发送
  const [attachOpen, setAttachOpen] = useState(false)
  const [voiceMode, setVoiceMode] = useState(false) // 🎤 按住说话模式
  const [recording, setRecording] = useState(false)
  const [anchor, setAnchor] = useState('') // 滚动锚点
  const [phIndex, setPhIndex] = useState(0)
  const streamAbortRef = useRef<(() => void) | null>(null)
  const phTimerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const lastTapRef = useRef(0)
  const recorderRef = useRef<Taro.RecorderManager | null>(null)
  const recordingRef = useRef(false)

  const isLinkInput = URL_RE.test(input.trim())

  /* 轮播 placeholder */
  useEffect(() => {
    phTimerRef.current = setInterval(() => setPhIndex((i) => (i + 1) % HOT_QUESTIONS.length), 3000)
    return () => {
      if (phTimerRef.current) clearInterval(phTimerRef.current)
    }
  }, [])

  /* 录音管理器：onStop → 百炼 ASR → 填入输入框（退出语音态，切回发送） */
  useEffect(() => {
    const recorder = Taro.getRecorderManager()
    recorder.onStop((res: any) => {
      recordingRef.current = false
      setRecording(false)
      if (res && res.tempFilePath) {
        Taro.showLoading({ title: '识别中…' })
        transcribeVoice(res.tempFilePath)
          .then((text) => {
            Taro.hideLoading()
            setInput(text)
            setVoiceMode(false)
          })
          .catch((e: any) => {
            Taro.hideLoading()
            Taro.showToast({ title: e?.message || '识别失败，请重试', icon: 'none' })
          })
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

  useDidShow(() => {
    setTab(0)
    if (!useAuthStore.getState().token) {
      Taro.reLaunch({ url: '/pages/login/index' })
      return
    }
    loadSession()
  })

  useUnload(() => {
    if (streamAbortRef.current) streamAbortRef.current()
    streamAbortRef.current = null
    if (recordingRef.current && recorderRef.current) recorderRef.current.stop()
  })

  /* 会话：持久化 session_id，恢复历史消息 */
  const loadSession = async () => {
    const sid = Taro.getStorageSync(SESSION_KEY) as string
    if (sid) {
      try {
        const records = await fetchQASession(sid)
        setSessionId(sid)
        setMessages(recordsToMessages(records))
        return
      } catch {
        /* 会话失效 → 开新会话 */
      }
    }
    startNewSession(false)
  }

  const recordsToMessages = (records: QARecord[]): ChatMsg[] => {
    const msgs: ChatMsg[] = []
    for (const rec of records) {
      msgs.push({ id: `${rec.id}-u`, role: 'user', text: rec.question })
      msgs.push({ id: rec.id, role: 'assistant', record: rec })
    }
    return msgs
  }

  const ensureSession = (): string => {
    if (sessionId) return sessionId
    const id = genUUID()
    Taro.setStorageSync(SESSION_KEY, id)
    setSessionId(id)
    return id
  }

  const startNewSession = (toast = true) => {
    const id = genUUID()
    Taro.setStorageSync(SESSION_KEY, id)
    setSessionId(id)
    setMessages([])
    setInput('')
    setVoiceMode(false)
    setAttachOpen(false)
    if (toast) Taro.showToast({ title: '已开启新对话', icon: 'none' })
  }

  const scrollToBottom = () => setAnchor('chat-end')

  const patchMsg = (id: string, patch: Partial<ChatMsg>) =>
    setMessages((prev) => prev.map((m) => (m.id === id ? { ...m, ...patch } : m)))

  const pushUser = (text: string) => setMessages((prev) => [...prev, { id: `u-${Date.now()}-${Math.random()}`, role: 'user', text }])

  const pushAssistantPending = (hint: string): string => {
    const id = `a-${Date.now()}-${Math.random()}`
    setMessages((prev) => [...prev, { id, role: 'assistant', text: hint, pending: true }])
    return id
  }

  /* ---------- 发送 ---------- */
  const send = () => {
    const text = input.trim()
    if (!text || sending) return
    setInput('')
    if (isLinkInput) {
      sendParseUrl(text)
    } else {
      sendQA(text)
    }
  }

  const sendQA = (q: string) => {
    const sid = ensureSession()
    pushUser(q)
    const aid = pushAssistantPending('')
    setSending(true)
    streamAbortRef.current = askQAStream(
      q,
      {
        onDelta: (t) =>
          setMessages((prev) =>
            prev.map((m) => (m.id === aid ? { ...m, text: (m.text || '') + t } : m)),
          ),
        onDone: (rec) => {
          patchMsg(aid, { record: rec, pending: false, text: undefined })
          setSending(false)
          streamAbortRef.current = null
          scrollToBottom()
        },
        onOpening: (t) =>
          // 卡片已渲染后，把 AI 现写的开场白补进卡内 intro（多做法/多菜回答）
          setMessages((prev) =>
            prev.map((m) =>
              m.id === aid && m.record
                ? { ...m, record: { ...m.record, answer: { ...m.record.answer, core_secret: t } } }
                : m,
            ),
          ),
        onError: (msg) => {
          patchMsg(aid, { text: msg || '提问失败，请稍后重试', pending: false })
          setSending(false)
          streamAbortRef.current = null
          scrollToBottom()
        },
      },
      sid,
    )
  }

  const sendParseUrl = async (url: string) => {
    const sid = ensureSession()
    pushUser(url)
    const aid = pushAssistantPending('正在解析链接…')
    setSending(true)
    try {
      const rec = await parseUrl(url, sid)
      patchMsg(aid, { record: rec, pending: false, text: undefined })
    } catch (e: any) {
      patchMsg(aid, { text: e?.message || '解析失败，请稍后重试', pending: false })
    } finally {
      setSending(false)
      scrollToBottom()
    }
  }

  const chooseDocument = async () => {
    setAttachOpen(false)
    try {
      const res = await Taro.chooseMessageFile({ count: 1, type: 'file', extension: ['pdf', 'docx', 'doc', 'txt'] })
      const file = res.tempFiles[0]
      if (!file) return
      const sid = ensureSession()
      pushUser(`📄 ${file.name}`)
      const aid = pushAssistantPending('正在解析文档…')
      setSending(true)
      try {
        const rec = await parseDocument(file.path, sid)
        patchMsg(aid, { record: rec, pending: false, text: undefined })
      } catch (e: any) {
        patchMsg(aid, { text: e?.message || '文档解析失败', pending: false })
      } finally {
        setSending(false)
        scrollToBottom()
      }
    } catch {
      /* 用户取消选择 */
    }
  }

  const goPhoto = () => {
    setAttachOpen(false)
    Taro.navigateTo({ url: '/pages/photo-capture/index' })
  }

  /* ---------- 语音（长按输入框说话） ---------- */
  const toggleVoice = () => {
    if (input.trim()) return // 有文字时按钮是发送
    setVoiceMode((v) => !v)
  }

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
          content: '按住说话需要麦克风权限，请在设置中开启后重试',
          confirmText: '去开启',
          success: (r) => { if (r.confirm) Taro.openSetting() },
        })
        return false
      }
    } catch {
      return true
    }
  }

  const onHoldStart = async () => {
    if (!voiceMode || recordingRef.current || sending) return
    const ok = await ensureRecordPermission()
    if (!ok) return
    recordingRef.current = true
    setRecording(true)
    recorderRef.current?.start({ format: 'mp3', duration: 60000 })
  }

  const onHoldEnd = () => {
    if (!recordingRef.current) return
    recorderRef.current?.stop()
  }

  /* ---------- 收藏 / 详情 ---------- */
  const saveFavorite = async (rec: QARecord) => {
    try {
      await addFavorite('qa', rec.id)
      Taro.showToast({ title: '已收藏到「我的收藏」', icon: 'none' })
    } catch (e: any) {
      Taro.showToast({ title: e?.message || '收藏失败', icon: 'none' })
    }
  }

  /* 收藏某道推荐/做法：知识库菜谱（kb_id 由后端入库后回填） */
  const saveKBRecipe = async (r: QARecommendation) => {
    if (!r.kb_id) {
      Taro.showToast({ title: '该做法暂未收录，无法单独收藏', icon: 'none' })
      return
    }
    try {
      await addFavorite('kb', r.kb_id)
      Taro.showToast({ title: '已收藏到「我的收藏」', icon: 'none' })
    } catch (e: any) {
      Taro.showToast({ title: e?.message || '收藏失败', icon: 'none' })
    }
  }

  const openDish = (r: QARecommendation) => {
    const q = r.kb_id ? `id=${r.kb_id}` : `title=${encodeURIComponent(r.name)}`
    Taro.navigateTo({ url: `/pages/kb-detail/index?${q}` })
  }

  /* 秘诀类回答后的追问：点"需要帮你查菜谱吗" → 发起一次查菜谱 */
  const askFollowup = (dish: string) => {
    if (!dish || sending) return
    sendQA(`帮我查一下「${dish}」的完整菜谱`)
  }

  /* ---------- 渲染：结构化答案正文 ---------- */
  const renderAnswerBody = (rec: QARecord) => {
    const ans = rec.answer
    if (ans.recommendations) {
      return (
        <View className='qa-recs'>
          {ans.core_secret && <Text className='qa-recs-intro' userSelect>{ans.core_secret}</Text>}
          {ans.recommendations.map((r, i) => (
            <View key={i} className='rec-card'>
              <View className='rec-head'>
                <Text className='rec-no'>{i + 1}</Text>
                <Text className='rec-name' onClick={() => openDish(r)}>{r.name}</Text>
                {r.time_minutes > 0 && <View className='mini-chip'><Text userSelect>⏱ {r.time_minutes}分钟</Text></View>}
                <View className='mini-chip kb' onClick={() => openDish(r)}><Text userSelect>做法 ›</Text></View>
              </View>
              <Text className='rec-secret' userSelect>{r.core_secret}</Text>
              {r.ingredients.length > 0 && <Text className='rec-ings' userSelect>食材：{r.ingredients.join('、')}</Text>}
              <View className='rec-actions'>
                <View className='btn btn--red btn--xs' onClick={() => openDish(r)}>
                  <Text userSelect>查看完整菜谱 ›</Text>
                </View>
                <View className='btn btn--white btn--xs' onClick={() => saveKBRecipe(r)}>
                  <View className='ic ic-star ic-sm' />
                  <Text userSelect>收藏</Text>
                </View>
              </View>
            </View>
          ))}
        </View>
      )
    }
    const hasSplit = (ans.prep_steps?.length || 0) > 0
    const stepText = (s: string) => s.replace(/^\s*\d+[.、)]\s*/, '')
    const renderStep = (s: string, i: number) => (
      <View key={i} className='qa-step'><Text className='qa-step-no'>{i + 1}</Text><Text userSelect>{stepText(s)}</Text></View>
    )
    return (
      <>
        <Text className='qa-ans-secret' userSelect>{ans.core_secret}</Text>
        {ans.ingredients.length > 0 && (
          <>
            <Text className='qa-ans-label'>食材清单</Text>
            <Text className='qa-ans-ings' userSelect>{ans.ingredients.join('、')}</Text>
          </>
        )}
        {hasSplit ? (
          <>
            {ans.prep_steps!.length > 0 && (
              <>
                <Text className='qa-ans-label'>食材处理</Text>
                <View className='qa-ans-steps'>{ans.prep_steps!.map(renderStep)}</View>
              </>
            )}
            <Text className='qa-ans-label'>烹饪步骤</Text>
            <View className='qa-ans-steps'>{ans.cook_steps!.map(renderStep)}</View>
          </>
        ) : (
          ans.steps.length > 0 && (
            <>
              <Text className='qa-ans-label'>烹饪步骤</Text>
              <View className='qa-ans-steps'>{ans.steps.map(renderStep)}</View>
            </>
          )
        )}
        {ans.avoid_pitfalls.length > 0 && (
          <>
            <Text className='qa-ans-label'>避坑指南</Text>
            {ans.avoid_pitfalls.map((p, i) => (
              <View key={i} className='qa-pit'>⚠ <Text userSelect>{p}</Text></View>
            ))}
          </>
        )}
      </>
    )
  }

  /* ---------- 渲染：助理消息 ---------- */
  const renderAssistant = (m: ChatMsg) => {
    if (m.pending) {
      return (
        <View className='msg assistant'>
          <View className='avatar'>🍳</View>
          <View className='mbox'>
            <Text className='mbox-text' userSelect>{m.text || '小伴正在思考…'}</Text>
            {m.text && <View className='caret' />}
          </View>
        </View>
      )
    }
    if (!m.record) {
      // 错误/提示文本
      return (
        <View className='msg assistant'>
          <View className='avatar'>🍳</View>
          <View className='mbox mbox--error'><Text className='mbox-text' userSelect>{m.text}</Text></View>
        </View>
      )
    }
    const rec = m.record
    const ans = rec.answer
    return (
      <View className='msg assistant'>
        <View className='avatar'>🍳</View>
        <View className='mbox mbox--card'>
          {ans.parse_type && (
            <View className='src-banner'>
              <View className='sb-ic'>{(ans.parse_type === 'video' && '▶️') || (ans.parse_type === 'doc' && '📄') || '🌐'}</View>
              <View className='sb-body'>
                <Text className='sb-title' userSelect>{PARSE_LABEL[ans.parse_type]}解析 · {ans.parse_source}</Text>
                <Text className='sb-sub' userSelect>小伴已整理为结构化菜谱</Text>
              </View>
              <View className='mini-chip green'><Text userSelect>已收录知识库</Text></View>
            </View>
          )}
          {rec.kb_hit && (
            <View className='kb-badge'><Text userSelect>📚 知识库命中 · {ans.dish_name || '已有菜谱'}</Text></View>
          )}
          {ans.dish_name && (
            <View className='card-title'><Text className='dish-name' userSelect>{ans.dish_name}</Text>
              <View className='mini-chip red'><Text userSelect>约 {ans.steps.length * 10 || 30} 分钟</Text></View>
            </View>
          )}
          {renderAnswerBody(rec)}
          {/* 秘诀/技巧类回答后的追问提示：点它发起查菜谱 */}
          {ans.followup && (
            <View
              className={`qa-followup ${ans.dish_name ? 'go' : ''}`}
              onClick={() => ans.dish_name && askFollowup(ans.dish_name)}
            >
              <Text userSelect>{ans.followup}</Text>
              {ans.dish_name && <Text userSelect className='qf-go'>›</Text>}
            </View>
          )}
          {/* 多做法/多菜列表：每张做法卡自带「查看完整菜谱/收藏」，底部不再重复 */}
          {!ans.recommendations && (
            <View className='mbox-actions'>
              {rec.kb_id && (
                <View className='btn btn--red btn--xs' onClick={() => Taro.navigateTo({ url: `/pages/kb-detail/index?id=${rec.kb_id}` })}>
                  <Text userSelect>查看完整菜谱 ›</Text>
                </View>
              )}
              <View className='btn btn--white btn--xs' onClick={() => saveFavorite(rec)}>
                <View className='ic ic-star ic-sm' />
                <Text userSelect>收藏</Text>
              </View>
            </View>
          )}
        </View>
      </View>
    )
  }

  const renderUser = (m: ChatMsg) => (
    <View className='msg user'>
      <View className='avatar av-ic'>
        {user?.avatar_url?.startsWith('data:') ? (
          <Image className='avatar-img' src={user.avatar_url} mode='aspectFill' />
        ) : (
          <View className='ic ic-mine ic-sm' />
        )}
      </View>
      <View className='mbox mbox--user'><Text className='mbox-text' userSelect>{m.text}</Text></View>
    </View>
  )

  /* ---------- 输入框交互 ---------- */
  const onInputTap = () => {
    if (input.trim()) {
      lastTapRef.current = 0
      return
    }
    const now = Date.now()
    if (lastTapRef.current && now - lastTapRef.current < 600) {
      lastTapRef.current = 0
      setInput(HOT_QUESTIONS[phIndex]) // 双击 → 填入当前轮播问题
    } else {
      lastTapRef.current = now
    }
  }

  return (
    <View className='page-content chat-page'>
      {/* 顶部导航 */}
      <View className='nav' style={{ paddingTop: `${getSafeTop()}px` }}>
        <View className='nav-title'><Text className='pop'>ChefPal</Text> 美食百科</View>
      </View>

      {/* 消息区 */}
      <ScrollView
        className='chat-scroll'
        scrollY
        scrollIntoView={anchor}
        scrollWithAnimation
      >
        <View className='chat-slot'>
          {messages.length === 0 && (
            <View className='welcome'>
              <View className='msg assistant'>
                <View className='avatar'>🍳</View>
                <View className='mbox'><Text className='mbox-text' userSelect>嗨！我是小伴，你的口袋厨师 🥢 想做菜直接问我，或粘贴菜谱链接 / 上传文档，我帮你解析成步骤。</Text></View>
              </View>
            </View>
          )}
          {messages.map((m) => (m.role === 'user' ? renderUser(m) : renderAssistant(m)))}
          <View id='chat-end' />
        </View>
      </ScrollView>

      {/* 链接识别提示条 */}
      {isLinkInput && (
        <View className='link-detect'>
          <View className='ld-ic'><Text>🔗</Text></View>
          <View className='ld-body'>
            <Text className='ld-title'>已识别链接 · 将自动解析</Text>
            <Text className='ld-sub'>发送后小伴提取内容 → 生成结构化菜谱</Text>
          </View>
          <View className='ld-x' onClick={() => setInput('')}><Text>✕</Text></View>
        </View>
      )}

      {/* 📎 附件面板 */}
      {attachOpen && (
        <View className='attach-sheet'>
          <View className='at-item' onClick={goPhoto}><View className='at-ic'><View className='ic ic-camera ic-sm' /></View><Text>拍照识食材</Text><Text className='at-sub'>对准冰箱拍</Text></View>
          <View className='at-item' onClick={goPhoto}><View className='at-ic'><Text className='at-emoji'>🖼</Text></View><Text>从相册选择</Text><Text className='at-sub'>选照片识别</Text></View>
          <View className='at-item' onClick={chooseDocument}><View className='at-ic'><Text className='at-emoji'>📄</Text></View><Text>上传文档</Text><Text className='at-sub'>PDF / Word</Text></View>
        </View>
      )}

      {/* 输入坞 */}
      <View className='input-dock'>
        {voiceMode ? (
          <View
            className={`id-input voice-hold ${recording ? 'recording' : ''}`}
            onTouchStart={onHoldStart}
            onTouchEnd={onHoldEnd}
          >
            <Text className='vh-main'>{(recording ? '松开 发送' : '🎤 按住说话')}</Text>
            <Text className='vh-sub'>长按说话 · 松开发送 · 上滑取消</Text>
          </View>
        ) : (
          <View className='id-input-wrap'>
            <Textarea
              className='id-textarea'
              value={input}
              autoHeight
              maxlength={500}
              placeholder={`问小伴：${wrapQuestion(HOT_QUESTIONS[phIndex])}？`}
              placeholderClass='id-ph'
              onClick={onInputTap}
              onInput={(e) => setInput(e.detail.value)}
              onConfirm={() => send()}
            />
            {!input && <Text className='id-hint'>双击输入框，提问当前问题</Text>}
          </View>
        )}
        <View className='id-actions'>
          <View className='btn-newchat' onClick={() => startNewSession(true)}>
            <View className='ic ic-plus ic-xs' /><Text>新对话</Text>
          </View>
          <View className='sp' />
          <View className={`id-attach ${attachOpen ? 'on' : ''}`} onClick={() => setAttachOpen(!attachOpen)}>
            <View className='ic ic-plus ic-sm' />
          </View>
          {input.trim() ? (
            <View className='id-act send' onClick={send}><Text className='send-glyph'>➤</Text></View>
          ) : (
            <View className={`id-act mic ${voiceMode ? 'on' : ''}`} onClick={toggleVoice}><View className='ic ic-mic ic-sm' /></View>
          )}
        </View>
      </View>
    </View>
  )
}
