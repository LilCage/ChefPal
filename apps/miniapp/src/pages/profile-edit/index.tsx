/**
 * 编辑资料（用户系统）：微信头像昵称填写能力
 * 头像：Button openType="chooseAvatar" → 转 base64 入库
 * 昵称：Input type="nickname"（键盘上方可选用微信昵称）
 */
import { Button, Image, Input, Text, View } from '@tarojs/components'
import Taro, { useLoad } from '@tarojs/taro'
import { useState } from 'react'
import NavBar from '../../components/NavBar'
import { updateProfile } from '../../services/api'
import { useAuthStore } from '../../stores/auth'
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

export default function ProfileEdit() {
  const user = useAuthStore((s) => s.user)
  const setUser = useAuthStore((s) => s.setUser)
  const [nickname, setNickname] = useState('')
  const [avatar, setAvatar] = useState('') // data:image/...;base64,...
  const [saving, setSaving] = useState(false)

  useLoad(() => {
    setNickname(user?.nickname || '')
    setAvatar(user?.avatar_url || '')
  })

  const onChooseAvatar = async (e: any) => {
    const path: string = e.detail?.avatarUrl
    if (!path) return
    try {
      const base64 = await readAsBase64(path)
      const ext = (path.split('.').pop() || 'jpeg').toLowerCase()
      const mime = ext === 'png' ? 'image/png' : ext === 'gif' ? 'image/gif' : 'image/jpeg'
      setAvatar(`data:${mime};base64,${base64}`)
    } catch {
      Taro.showToast({ title: '头像读取失败，请重试', icon: 'none' })
    }
  }

  const clearAvatar = () => {
    Taro.showModal({
      title: '移除头像',
      content: '将恢复为默认头像，确定吗？',
      confirmColor: '#E8482A',
      success: (r) => {
        if (r.confirm) setAvatar('')
      },
    })
  }

  const save = async () => {
    if (saving) return
    setSaving(true)
    try {
      const updated = await updateProfile({
        nickname: nickname.trim() || undefined,
        avatar_url: avatar || undefined,
      })
      setUser(updated)
      Taro.showToast({ title: '保存成功', icon: 'none' })
      setTimeout(() => Taro.navigateBack(), 600)
    } catch (e: any) {
      Taro.showToast({ title: e.message || '保存失败', icon: 'none' })
    } finally {
      setSaving(false)
    }
  }

  return (
    <View className='page-content pedit'>
      <NavBar title='编辑资料' showBack />

      <View className='avatar-card'>
        <Button className='avatar-pick' openType='chooseAvatar' onChooseAvatar={onChooseAvatar}>
          {avatar ? (
            <Image className='avatar-img' src={avatar} mode='aspectFill' />
          ) : (
            <Text className='avatar-ph'>🍳</Text>
          )}
        </Button>
        <Text className='avatar-tip'>点击头像，从微信选择</Text>
        {avatar && (
          <View className='clear-avatar' onClick={clearAvatar}>
            <Text>移除头像</Text>
          </View>
        )}
      </View>

      <View className='field nick-field'>
        <Text className='field-label'>昵称</Text>
        <Input
          className='nick-input'
          type='nickname'
          value={nickname}
          maxlength={64}
          placeholder='请输入昵称'
          placeholderClass='nick-ph'
          onInput={(e) => setNickname(e.detail.value)}
        />
        <Text className='field-hint'>输入时键盘上方可直接选用微信昵称</Text>
      </View>

      <View className='save-wrap'>
        <View className='btn btn--red btn--block' onClick={save}>
          <Text>{saving ? '保存中…' : '保存资料'}</Text>
        </View>
      </View>
    </View>
  )
}
