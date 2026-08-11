/**
 * 新建/编辑个人菜谱（EXT-4.1）：封面 + 标题 + 几人份 + 食材(名+备注) + 调味料(chips)
 * + 处理食材/烹饪步骤两区块 + 避坑 + 风味/时间/难度
 * 有 ?id= 为编辑模式（回填后 PUT），否则新建
 */
import { Image, Input, Text, Textarea, View } from '@tarojs/components'
import Taro, { useLoad, useUnload } from '@tarojs/taro'
import { useEffect, useRef, useState } from 'react'
import NavBar from '../../components/NavBar'
import {
  createMyRecipe,
  fetchMyRecipe,
  updateMyRecipe,
  type MyRecipeIngredient,
  type MyRecipeSeasoning,
  type MyRecipeStep,
} from '../../services/api'
import './index.scss'

const STYLES = ['浓香下饭', '清爽快手', '蒸煮清淡', '香辣过瘾', '甜口绵密', '汤羹温润']
const DIFFS = ['简单', '中等', '较难']
const SERVING_OPTIONS = [1, 2, 3, 4, 6, 8]
/* 常用调味料 chips（点选即加入清单，避免逐个输入） */
const COMMON_SEASONINGS = [
  '食用油', '盐', '生抽', '老抽', '蚝油', '料酒', '白糖', '香醋', '淀粉',
  '白胡椒粉', '味精', '鸡精', '姜', '蒜', '葱', '辣椒', '花椒', '八角',
]

function readAsBase64(filePath: string): Promise<string> {
  return new Promise((resolve, reject) => {
    Taro.getFileSystemManager().readFile({
      filePath,
      encoding: 'base64',
      success: (res) => resolve(res.data as string),
      fail: reject,
    })
  })
}

export default function MyRecipeCreate() {
  const [id, setId] = useState<string | null>(null)
  const [title, setTitle] = useState('')
  const [cover, setCover] = useState<string | null>(null)
  const [servings, setServings] = useState(2)
  const [ingredients, setIngredients] = useState<MyRecipeIngredient[]>([{ name: '', note: '' }])
  const [prepSteps, setPrepSteps] = useState<MyRecipeStep[]>([])
  const [cookSteps, setCookSteps] = useState<MyRecipeStep[]>([{ title: '', detail: '' }])
  const [seasonings, setSeasonings] = useState<MyRecipeSeasoning[]>([{ name: '食用油', amount: '适量' }])
  const [customSeasoning, setCustomSeasoning] = useState('')
  const [tips, setTips] = useState<string[]>([''])
  const [style, setStyle] = useState('')
  const [timeMinutes, setTimeMinutes] = useState('30')
  const [difficulty, setDifficulty] = useState('简单')
  const [saving, setSaving] = useState(false)
  const [showExitModal, setShowExitModal] = useState(false)
  const [loaded, setLoaded] = useState(false)
  const initialSnapshotRef = useRef<string>('')
  const savedRef = useRef(false)
  const initializedRef = useRef(false)

  /* 采集当前表单的"可比较快照"（忽略空行/尾随空格，用于判断是否有未保存修改） */
  const captureSnapshot = () =>
    JSON.stringify({
      title: title.trim(),
      cover,
      servings,
      ingredients: ingredients.filter((x) => x.name.trim()).map((x) => ({ name: x.name.trim(), note: (x.note || '').trim() })),
      prepSteps: prepSteps.filter((x) => x.title.trim()).map((x) => ({ title: x.title.trim(), detail: (x.detail || '').trim() })),
      cookSteps: cookSteps.filter((x) => x.title.trim()).map((x) => ({ title: x.title.trim(), detail: (x.detail || '').trim() })),
      seasonings: seasonings.filter((x) => x.name.trim()).map((x) => ({ name: x.name.trim(), amount: (x.amount || '').trim() })),
      tips: tips.map((t) => t.trim()).filter(Boolean),
      style,
      timeMinutes: timeMinutes.trim(),
      difficulty,
    })

  const hasUnsavedChanges = () => {
    if (!loaded) return false
    return !savedRef.current && captureSnapshot() !== initialSnapshotRef.current
  }

  useLoad((params) => {
    const rid = (params as any).id as string | undefined
    if (rid) {
      setId(rid)
      fetchMyRecipe(rid)
        .then((r) => {
          setTitle(r.title)
          setCover(r.cover_image)
          setServings(r.servings || 2)
          setIngredients(r.ingredients?.length ? r.ingredients : [{ name: '', note: '' }])
          setPrepSteps(r.prep_steps?.length ? r.prep_steps : [])
          setCookSteps(r.cook_steps?.length ? r.cook_steps : [{ title: '', detail: '' }])
          setSeasonings(r.seasonings?.length ? r.seasonings : [{ name: '食用油', amount: '适量' }])
          setTips(r.tips?.length ? r.tips : [''])
          setStyle(r.style || '')
          setTimeMinutes(String(r.time_minutes || 30))
          setDifficulty(r.difficulty || '简单')
          setLoaded(true)
        })
        .catch((e: any) => Taro.showToast({ title: e.message || '加载失败', icon: 'none' }))
    } else {
      setLoaded(true) // 新建模式：默认值即为初始状态
    }
  })

  /* 数据就绪（loaded=true）后，在本次重渲染完成时采集初始快照，记为"无未保存修改"基线 */
  useEffect(() => {
    if (!loaded || initializedRef.current) return
    initializedRef.current = true
    initialSnapshotRef.current = captureSnapshot()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loaded])

  /* 系统返回手势兜底：有未保存修改时，微信弹"离开确认"防误退（无法自定义按钮） */
  useEffect(() => {
    if (!loaded) return
    if (hasUnsavedChanges()) {
      Taro.enableAlertBeforeUnload({
        message: '还有未保存的修改，退出后内容将丢失',
      })
    } else {
      Taro.disableAlertBeforeUnload()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [title, cover, servings, ingredients, prepSteps, cookSteps, seasonings, tips, style, timeMinutes, difficulty, loaded])

  useUnload(() => {
    Taro.disableAlertBeforeUnload()
  })

  /* 拦截返回：有未保存修改 → 弹自定义确认 */
  const handleBack = () => {
    if (hasUnsavedChanges()) {
      setShowExitModal(true)
    } else {
      Taro.navigateBack({ delta: 1 })
    }
  }

  const exitWithoutSaving = () => {
    savedRef.current = true // 放弃修改也标记，避免二次弹窗
    setShowExitModal(false)
    Taro.disableAlertBeforeUnload()
    Taro.navigateBack({ delta: 1 })
  }

  const cancelExit = () => setShowExitModal(false)

  const pickCover = async () => {
    try {
      const res = await Taro.chooseMedia({
        count: 1,
        mediaType: ['image'],
        sourceType: ['album', 'camera'],
        sizeType: ['compressed'],
      })
      const f = res.tempFiles[0] as { tempFilePath: string }
      const b64 = await readAsBase64(f.tempFilePath)
      const ext = (f.tempFilePath.split('.').pop() || 'jpeg').toLowerCase()
      const mime = ext === 'png' ? 'image/png' : ext === 'webp' ? 'image/webp' : 'image/jpeg'
      setCover(`data:${mime};base64,${b64}`)
    } catch {
      /* 用户取消 */
    }
  }

  const updateIng = (i: number, patch: Partial<MyRecipeIngredient>) =>
    setIngredients((prev) => prev.map((x, idx) => (idx === i ? { ...x, ...patch } : x)))
  const updatePrepStep = (i: number, patch: Partial<MyRecipeStep>) =>
    setPrepSteps((prev) => prev.map((x, idx) => (idx === i ? { ...x, ...patch } : x)))
  const updateCookStep = (i: number, patch: Partial<MyRecipeStep>) =>
    setCookSteps((prev) => prev.map((x, idx) => (idx === i ? { ...x, ...patch } : x)))
  const updateSeasoning = (i: number, patch: Partial<MyRecipeSeasoning>) =>
    setSeasonings((prev) => prev.map((x, idx) => (idx === i ? { ...x, ...patch } : x)))
  const updateTip = (i: number, v: string) =>
    setTips((prev) => prev.map((x, idx) => (idx === i ? v : x)))

  const addIng = () => setIngredients((prev) => [...prev, { name: '', note: '' }])
  const rmIng = (i: number) => setIngredients((prev) => (prev.length > 1 ? prev.filter((_, idx) => idx !== i) : prev))
  const addPrep = () => setPrepSteps((prev) => [...prev, { title: '', detail: '' }])
  const rmPrep = (i: number) => setPrepSteps((prev) => prev.filter((_, idx) => idx !== i))
  const addCook = () => setCookSteps((prev) => [...prev, { title: '', detail: '' }])
  const rmCook = (i: number) => setCookSteps((prev) => (prev.length > 1 ? prev.filter((_, idx) => idx !== i) : prev))
  const addTip = () => setTips((prev) => [...prev, ''])
  const rmTip = (i: number) => setTips((prev) => (prev.length > 1 ? prev.filter((_, idx) => idx !== i) : prev))

  /* 调味料 chips 点选：已加入则移除，未加入则追加 */
  const toggleSeasoning = (name: string) => {
    const exists = seasonings.find((s) => s.name === name)
    if (exists) {
      setSeasonings(seasonings.filter((s) => s.name !== name))
    } else {
      setSeasonings([...seasonings, { name, amount: '适量' }])
    }
  }
  const addCustomSeasoning = () => {
    const v = customSeasoning.trim()
    if (!v) return
    if (seasonings.some((s) => s.name === v)) {
      Taro.showToast({ title: '已添加该调味料', icon: 'none' })
      return
    }
    setSeasonings([...seasonings, { name: v, amount: '适量' }])
    setCustomSeasoning('')
  }
  const rmSeasoning = (i: number) => setSeasonings((prev) => prev.filter((_, idx) => idx !== i))

  const validate = (): string | null => {
    if (!title.trim()) return '请填写菜谱标题'
    const validIngs = ingredients.filter((x) => x.name.trim())
    if (validIngs.length === 0) return '至少填写 1 种食材'
    const validCook = cookSteps.filter((x) => x.title.trim())
    if (validCook.length === 0) return '至少填写 1 个烹饪步骤'
    return null
  }

  const buildPayload = () => ({
    title: title.trim(),
    cover_image: cover || undefined,
    servings,
    ingredients: ingredients.filter((x) => x.name.trim()),
    prep_steps: prepSteps.filter((x) => x.title.trim()),
    cook_steps: cookSteps.filter((x) => x.title.trim()),
    seasonings: seasonings.filter((x) => x.name.trim()),
    tips: tips.map((t) => t.trim()).filter(Boolean),
    style,
    time_minutes: Number(timeMinutes) || 0,
    difficulty,
  })

  /* 保存并返回：保存成功后标记已保存 + 关闭系统离开确认 + 返回 */
  const save = async (goBack = true) => {
    if (saving) return
    const err = validate()
    if (err) {
      Taro.showToast({ title: err, icon: 'none' })
      return
    }
    setSaving(true)
    try {
      if (id) {
        await updateMyRecipe(id, buildPayload())
        Taro.showToast({ title: '已保存', icon: 'none' })
      } else {
        await createMyRecipe(buildPayload())
        Taro.showToast({ title: '创建成功！', icon: 'none' })
      }
      savedRef.current = true
      setShowExitModal(false)
      Taro.disableAlertBeforeUnload()
      if (goBack) setTimeout(() => Taro.navigateBack(), 600)
    } catch (e: any) {
      Taro.showToast({ title: e.message || '保存失败', icon: 'none' })
    } finally {
      setSaving(false)
    }
  }

  return (
    <View className='page-content mrc'>
      <NavBar title={id ? '编辑菜谱' : '新建菜谱'} showBack onBack={handleBack} />

      <View className='section'>
        <View className='sec-title'>🖼 封面（选填）</View>
        <View className='cover-row'>
          {cover ? (
            <View className='cover-box' onClick={pickCover}>
              <Image className='cover-img' src={cover} mode='aspectFill' />
              <View className='cover-edit'><Text>换图</Text></View>
            </View>
          ) : (
            <View className='cover-box add' onClick={pickCover}>
              <View className='ic ic-camera ic-lg' />
              <Text className='cover-t'>添加封面</Text>
            </View>
          )}
        </View>
      </View>

      <View className='section'>
        <View className='sec-title'>📛 菜谱标题</View>
        <Input
          className='mrc-input'
          value={title}
          maxlength={128}
          placeholder='如：祖传红烧肉'
          placeholderClass='mrc-ph'
          onInput={(e) => setTitle(e.detail.value)}
        />
      </View>

      <View className='section'>
        <View className='sec-title'>👥 几人份</View>
        <View className='chips'>
          {SERVING_OPTIONS.map((n) => (
            <View key={n} className={`chip ${servings === n ? 'chip--on' : ''}`} onClick={() => setServings(n)}>
              <Text>{n}人</Text>
            </View>
          ))}
        </View>
      </View>

      <View className='section'>
        <View className='sec-title'>🥬 食材清单 <Text className='sec-note'>名称 + 备注（用量/选材）</Text></View>
        {ingredients.map((ing, i) => (
          <View key={i} className='ing-card'>
            <View className='ing-head'>
              <Input
                className='mrc-input ing-name'
                value={ing.name}
                placeholder={`食材 ${i + 1}`}
                placeholderClass='mrc-ph'
                onInput={(e) => updateIng(i, { name: e.detail.value })}
              />
              <View className='row-del' onClick={() => rmIng(i)}>×</View>
            </View>
            <Input
              className='mrc-input ing-note'
              value={ing.note || ''}
              placeholder='备注：用量/选材，如 300g，选带皮五花'
              placeholderClass='mrc-ph'
              onInput={(e) => updateIng(i, { note: e.detail.value })}
            />
          </View>
        ))}
        <View className='btn btn--sm btn--gold add-row' onClick={addIng}><Text>＋ 添加食材</Text></View>
      </View>

      <View className='section'>
        <View className='sec-title'>🧂 调味料 <Text className='sec-note'>点选常用项，可自定义</Text></View>
        <View className='chips'>
          {COMMON_SEASONINGS.map((s) => (
            <View
              key={s}
              className={`chip ${seasonings.some((x) => x.name === s) ? 'chip--on' : ''}`}
              onClick={() => toggleSeasoning(s)}
            >
              <Text>{s}</Text>
            </View>
          ))}
        </View>
        <View className='season-list'>
          {seasonings.map((s, i) => (
            <View key={i} className='season-item'>
              <Text className='season-name'>{s.name}</Text>
              <Input
                className='mrc-input season-amount'
                value={s.amount || ''}
                placeholder='用量（如 1勺 / 适量）'
                placeholderClass='mrc-ph'
                onInput={(e) => updateSeasoning(i, { amount: e.detail.value })}
              />
              <View className='row-del' onClick={() => rmSeasoning(i)}>×</View>
            </View>
          ))}
        </View>
        <View className='custom-add-row'>
          <Input
            className='mrc-input'
            value={customSeasoning}
            maxlength={40}
            placeholder='自定义调味料，如：十三香'
            placeholderClass='mrc-ph'
            onInput={(e) => setCustomSeasoning(e.detail.value)}
            onConfirm={addCustomSeasoning}
          />
          <View className='btn btn--sm btn--gold' onClick={addCustomSeasoning}><Text>添加</Text></View>
        </View>
      </View>

      <View className='section'>
        <View className='sec-title'>✂️ 处理食材 <Text className='sec-note'>洗 / 切 / 腌（选填）</Text></View>
        {prepSteps.map((st, i) => (
          <View key={i} className='step-card'>
            <View className='step-head'>
              <View className='sno green'><Text>{i + 1}</Text></View>
              <Input
                className='mrc-input step-title'
                value={st.title}
                placeholder='步骤名，如：切块'
                placeholderClass='mrc-ph'
                onInput={(e) => updatePrepStep(i, { title: e.detail.value })}
              />
              <View className='row-del' onClick={() => rmPrep(i)}>×</View>
            </View>
            <Textarea
              className='mrc-textarea'
              value={st.detail}
              maxlength={500}
              placeholder='如：五花肉切 3cm 见方块，冷水下锅焯 3 分钟'
              placeholderClass='mrc-ph'
              autoHeight
              onInput={(e) => updatePrepStep(i, { detail: e.detail.value })}
            />
          </View>
        ))}
        <View className='btn btn--sm btn--gold add-row' onClick={addPrep}><Text>＋ 添加处理步骤</Text></View>
      </View>

      <View className='section'>
        <View className='sec-title'>🍳 烹饪步骤</View>
        {cookSteps.map((st, i) => (
          <View key={i} className='step-card'>
            <View className='step-head'>
              <View className='sno'><Text>{i + 1}</Text></View>
              <Input
                className='mrc-input step-title'
                value={st.title}
                placeholder='步骤名，如：炒糖色'
                placeholderClass='mrc-ph'
                onInput={(e) => updateCookStep(i, { title: e.detail.value })}
              />
              <View className='row-del' onClick={() => rmCook(i)}>×</View>
            </View>
            <Textarea
              className='mrc-textarea'
              value={st.detail}
              maxlength={500}
              placeholder='详细做法，写给厨房小白，写清火候与时长'
              placeholderClass='mrc-ph'
              autoHeight
              onInput={(e) => updateCookStep(i, { detail: e.detail.value })}
            />
          </View>
        ))}
        <View className='btn btn--sm btn--gold add-row' onClick={addCook}><Text>＋ 添加烹饪步骤</Text></View>
      </View>

      <View className='section'>
        <View className='sec-title'>⚠ 避坑指南（选填）</View>
        {tips.map((t, i) => (
          <View key={i} className='tip-row'>
            <Input
              className='mrc-input'
              value={t}
              maxlength={100}
              placeholder='如：糖色宁浅勿深'
              placeholderClass='mrc-ph'
              onInput={(e) => updateTip(i, e.detail.value)}
            />
            <View className='row-del' onClick={() => rmTip(i)}>×</View>
          </View>
        ))}
        <View className='btn btn--sm btn--gold add-row' onClick={addTip}><Text>＋ 添加避坑</Text></View>
      </View>

      <View className='section'>
        <View className='sec-title'>🍲 风味 / 时间 / 难度</View>
        <View className='chips'>
          {STYLES.map((s) => (
            <View key={s} className={`chip ${style === s ? 'chip--on' : ''}`} onClick={() => setStyle(style === s ? '' : s)}>
              <Text>{s}</Text>
            </View>
          ))}
        </View>
        <View className='time-row'>
          <Text className='time-label'>预计耗时</Text>
          <Input
            className='mrc-input time-input'
            value={timeMinutes}
            type='number'
            maxlength={4}
            onInput={(e) => setTimeMinutes(e.detail.value)}
          />
          <Text className='time-unit'>分钟</Text>
        </View>
        <View className='chips'>
          {DIFFS.map((d) => (
            <View key={d} className={`chip ${difficulty === d ? 'chip--on' : ''}`} onClick={() => setDifficulty(d)}>
              <Text>{d}</Text>
            </View>
          ))}
        </View>
      </View>

      <View className='save-wrap'>
        <View className='btn btn--red btn--block' onClick={() => save(true)}>
          <Text>{saving ? '保存中…' : id ? '保存修改' : '创建菜谱'}</Text>
        </View>
        {!id && <Text className='note note--center'>创建后可到「我的菜谱」一键发布到社区</Text>}
      </View>

      {/* 未保存修改退出确认（漫画风自定义弹窗） */}
      {showExitModal && (
        <View className='exit-mask' onClick={cancelExit}>
          <View className='exit-card' onClick={(e) => e.stopPropagation()}>
            <View className='exit-title pop'>⚠ 未保存的修改</View>
            <Text className='exit-desc'>你还没有保存修改，退出后这些内容将丢失。</Text>
            <View className='btn btn--red btn--block' onClick={() => save(true)}>
              <Text>{saving ? '保存中…' : '保存并退出'}</Text>
            </View>
            <View className='exit-row'>
              <View className='btn btn--white btn--sm' onClick={exitWithoutSaving}><Text>不保存退出</Text></View>
              <View className='btn btn--white btn--sm' onClick={cancelExit}><Text>继续编辑</Text></View>
            </View>
          </View>
        </View>
      )}
    </View>
  )
}
