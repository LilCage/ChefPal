/**
 * 黑暗料理拯救（原型 05 屏1）：上传翻车现场照 → 小伴诊断问题 + 补救方案
 * 数据源 POST /rescue/diagnose（复用智谱 GLM 视觉，原型 faile-img / diag-card）
 */
import { Image, Text, View } from '@tarojs/components'
import Taro from '@tarojs/taro'
import { useState } from 'react'
import NavBar from '../../components/NavBar'
import { diagnoseDish, type RescueIssue } from '../../services/api'
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

export default function DarkRescue() {
  const [photo, setPhoto] = useState<string | null>(null)
  const [issues, setIssues] = useState<RescueIssue[]>([])
  const [diagnosing, setDiagnosing] = useState(false)

  const pick = async (sourceType: 'camera' | 'album') => {
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
      setPhoto(`data:${mime};base64,${b64}`)
      setIssues([])
    } catch {
      /* 用户取消 */
    }
  }

  const diagnose = async () => {
    if (!photo) {
      Taro.showToast({ title: '先上传翻车现场照片', icon: 'none' })
      return
    }
    if (diagnosing) return
    setDiagnosing(true)
    try {
      const res = await diagnoseDish(photo)
      setIssues(res.issues)
      if (res.issues.length === 0) {
        Taro.showToast({ title: '看起来没翻车？再看看锅里的！', icon: 'none' })
      } else {
        Taro.showToast({ title: `诊断出 ${res.issues.length} 个问题！`, icon: 'none' })
      }
    } catch (e: any) {
      Taro.showToast({ title: e.message || '诊断失败，请重试', icon: 'none' })
    } finally {
      setDiagnosing(false)
    }
  }

  return (
    <View className='page-content dark-rescue'>
      <NavBar title='黑暗料理拯救' showBack />

      <View className='fail-img' onClick={() => pick('album')}>
        {photo ? (
          <Image className='fail-photo' src={photo} mode='aspectFill' />
        ) : (
          <>
            <Text className='emoji'>🥣</Text>
            <View className='add'><Text>上传翻车现场照片</Text></View>
          </>
        )}
      </View>

      <View className='sec'>
        <View className={`btn btn--red btn--block ${diagnosing ? 'btn--disabled' : ''}`} onClick={diagnose}>
          <Text>{diagnosing ? '诊断中…' : '🔍 一键小伴诊断'}</Text>
        </View>
      </View>

      {issues.length > 0 && (
        <View className='sec'>
          <View className='sec-title'>💊 诊断结果</View>
        </View>
      )}

      {issues.length > 0 && (
        <View className='diag-card'>
          {issues.map((it, idx) => (
            <View key={`${it.title}-${idx}`} className='diag-row'>
              <View className='d-ic'>
                <Text>{['⚠', '💧', '🧂'][idx % 3]}</Text>
              </View>
              <View className='diag-body'>
                <Text className='diag-title'>{it.title}</Text>
                <Text className='diag-detail'>{it.detail}</Text>
                <Text className='fix'>✅ 补救：{it.fix}</Text>
              </View>
            </View>
          ))}
        </View>
      )}

      <Text className='note rescue-note'>小伴补救仅供参考 · 拍照可再次诊断</Text>
    </View>
  )
}
