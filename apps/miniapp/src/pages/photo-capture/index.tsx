/**
 * 拍照识食材（原型 04 屏1）：取景框 + 快门/相册 → 小伴识别 → 食材 chips → 去厨房生成菜谱
 */
import { Image, Input, Text, View } from '@tarojs/components'
import Taro from '@tarojs/taro'
import { useState } from 'react'
import NavBar from '../../components/NavBar'
import { recognizeIngredients } from '../../services/api'
import './index.scss'

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

export default function PhotoCapture() {
  const [photo, setPhoto] = useState<string | null>(null)
  const [ingredients, setIngredients] = useState<string[]>([])
  const [recognizing, setRecognizing] = useState(false)
  const [manual, setManual] = useState('')

  const pick = async (sourceType: ('camera' | 'album')) => {
    try {
      const res = await Taro.chooseMedia({
        count: 1,
        mediaType: ['image'],
        sourceType: [sourceType],
        sizeType: ['compressed'],
      })
      const f = (res.tempFiles as { tempFilePath: string }[])[0]
      const b64 = await readAsBase64(f.tempFilePath)
      const ext = (f.tempFilePath.split('.').pop() || 'jpeg').toLowerCase()
      const mime = ext === 'png' ? 'image/png' : ext === 'webp' ? 'image/webp' : 'image/jpeg'
      const dataUrl = `data:${mime};base64,${b64}`
      setPhoto(dataUrl)
      await doRecognize(dataUrl)
    } catch {
      /* 用户取消 */
    }
  }

  const doRecognize = async (dataUrl: string) => {
    setRecognizing(true)
    try {
      const res = await recognizeIngredients(dataUrl)
      setIngredients(res.ingredients)
      if (res.ingredients.length === 0) {
        Taro.showToast({ title: '没识别到食材，试试手动添加', icon: 'none' })
      } else {
        Taro.showToast({ title: `识别出 ${res.ingredients.length} 种食材！`, icon: 'none' })
      }
    } catch (e: any) {
      Taro.showToast({ title: e.message || '识别失败，请重试', icon: 'none' })
    } finally {
      setRecognizing(false)
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
    <View className='page-content photo-capture'>
      <NavBar title='拍照识食材' showBack />

      <View className='cam-view'>
        {photo ? (
          <Image className='cam-img' src={photo} mode='aspectFill' />
        ) : (
          <>
            <View className='cam-grid' />
            <View className='cam-corners' />
            <View className='cam-ghost'><Text userSelect>🍅🥚🥬</Text></View>
          </>
        )}
        <View className='cam-hint'><Text userSelect>{recognizing ? '小伴识别中…' : '对准冰箱里的食材 · 自动识别'}</Text></View>
      </View>

      <View className='shutter-zone'>
        <View className='shutter' onClick={() => pick('camera')}>
          <View className='shutter-inner' />
        </View>
        <Text userSelect className='note'>轻触拍照</Text>
        <View className='btn btn--white btn--sm btn--album' onClick={() => pick('album')}>
          <Text userSelect>🖼 从相册选择</Text>
        </View>
      </View>

      <View className='sec'>
        <View className='sec-title'>
          🔎 识别结果
          <View className='more' onClick={() => pick('camera')}>重新拍照</View>
        </View>
        <View className='field'>
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
                placeholder='＋ 手动添加'
                confirmType='done'
                onInput={(e) => setManual(e.detail.value)}
                onConfirm={() => { addManual(); setManual('') }}
                onBlur={() => setManual('')}
              />
            </View>
          </View>
          <Text userSelect className='note note--mt'>点标签可删除，点添加可补充 · 识别结果仅供参考</Text>
        </View>
      </View>

      <View className='sec'>
        <View className={`btn btn--red btn--block ${recognizing ? 'btn--disabled' : ''}`} onClick={goKitchen}>
          <Text userSelect>用这些食材去生成菜谱 →</Text>
        </View>
      </View>
    </View>
  )
}
