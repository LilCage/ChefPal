/**
 * 评论列表（原型 03 屏3）：作者/楼主徽标/内容/时间/♥点赞 + 底部评论输入
 */
import { Image, Input, Text, View } from '@tarojs/components'
import Taro, { useLoad } from '@tarojs/taro'
import { useState } from 'react'
import NavBar from '../../components/NavBar'
import {
  createComment,
  fetchComments,
  likeComment,
  unlikeComment,
  type Comment,
  type CommentList,
} from '../../services/api'
import './index.scss'

function timeText(iso: string | null): string {
  if (!iso) return ''
  const t = new Date(iso).getTime()
  const diff = Date.now() - t
  if (diff < 60_000) return '刚刚'
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)} 分钟前`
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)} 小时前`
  const d = new Date(iso)
  return `${d.getMonth() + 1}月${d.getDate()}日`
}

export default function Comments() {
  const [postId, setPostId] = useState('')
  const [data, setData] = useState<CommentList>({ items: [], total: 0, page: 1, size: 20, has_more: false })
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)

  useLoad((params) => {
    const id = (params as any).id as string
    if (id) {
      setPostId(id)
      load(id)
    }
  })

  const load = async (id: string) => {
    try {
      const res = await fetchComments(id)
      setData(res)
    } catch (e: any) {
      Taro.showToast({ title: e.message || '加载失败', icon: 'none' })
    }
  }

  const send = async () => {
    const content = input.trim()
    if (!content || sending) return
    setSending(true)
    try {
      const c = await createComment(postId, content)
      setData((prev) => ({
        ...prev,
        items: [...prev.items, c],
        total: prev.total + 1,
      }))
      setInput('')
      Taro.showToast({ title: '评论成功', icon: 'none' })
    } catch (e: any) {
      Taro.showToast({ title: e.message || '评论失败', icon: 'none' })
    } finally {
      setSending(false)
    }
  }

  const toggleLike = async (c: Comment) => {
    try {
      if (c.is_liked) await unlikeComment(c.id)
      else await likeComment(c.id)
      setData((prev) => ({
        ...prev,
        items: prev.items.map((it) =>
          it.id === c.id
            ? { ...it, is_liked: !it.is_liked, like_count: it.like_count + (it.is_liked ? -1 : 1) }
            : it,
        ),
      }))
    } catch (e: any) {
      Taro.showToast({ title: e.message || '操作失败', icon: 'none' })
    }
  }

  return (
    <View className='page-content comments'>
      <NavBar title={`评论 (${data.total})`} showBack />

      <View className='cmt-list'>
        {data.items.map((c) => (
          <View key={c.id} className='cmt-item'>
            <View className='p-av'>
              {c.author.avatar_url?.startsWith('data:') ? (
                <Image className='p-av-img' src={c.author.avatar_url} mode='aspectFill' />
              ) : (
                <Text userSelect className='p-av-ph'>{c.author.nickname.slice(0, 1)}</Text>
              )}
            </View>
            <View className='cmt-box'>
              <View className='cmt-name'>
                <Text userSelect>{c.author.nickname}</Text>
                {c.is_owner && <Text userSelect className='owner'>楼主</Text>}
              </View>
              <Text userSelect className='cmt-content'>{c.content}</Text>
              <View className='cmt-foot'>
                <Text userSelect className='cmt-time'>{timeText(c.created_at)}</Text>
                <View className={`cmt-like ${c.is_liked ? 'on' : ''}`} onClick={() => toggleLike(c)}>
                  <View className='ic ic-heart ic-xs' />
                  <Text userSelect>{c.like_count}</Text>
                </View>
              </View>
            </View>
          </View>
        ))}
      </View>

      {data.items.length === 0 && (
        <View className='note note--center cmt-empty'>还没有评论，快来抢沙发～</View>
      )}

      <View className='actbar'>
        <View className='cmt-input'>
          <View className='ic ic-comment ic-sm' />
          <Input
            className='cmt-input-field'
            value={input}
            placeholder='友善评论，理性交流…'
            confirmType='send'
            maxlength={200}
            onInput={(e) => setInput(e.detail.value)}
            onConfirm={send}
          />
        </View>
        <View className='btn btn--red btn--sm btn--send' onClick={send}>
          <Text userSelect>{sending ? '…' : '发送'}</Text>
        </View>
      </View>
    </View>
  )
}
