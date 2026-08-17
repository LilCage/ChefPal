/**
 * 我的作品：展示当前用户发布的社区作品（「我的」页统计入口直达）。
 * 单列作品卡，点击进详情；空状态引导去发现页发布。
 */
import { Image, Text, View } from '@tarojs/components'
import Taro, { useDidShow } from '@tarojs/taro'
import { useState } from 'react'
import EmptyState from '../../components/EmptyState'
import NavBar from '../../components/NavBar'
import { fetchMyPosts, type Post } from '../../services/api'
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

export default function MyPosts() {
  const [posts, setPosts] = useState<Post[]>([])
  const [loaded, setLoaded] = useState(false)

  useDidShow(() => {
    fetchMyPosts()
      .then(setPosts)
      .catch((e: any) => Taro.showToast({ title: e.message || '加载失败', icon: 'none' }))
      .finally(() => setLoaded(true))
  })

  const goDetail = (id: string) => Taro.navigateTo({ url: `/pages/post-detail/index?id=${id}` })

  return (
    <View className='page-content my-posts'>
      <NavBar title='我的作品' showBack />

      {loaded && posts.length === 0 ? (
        <EmptyState
          icon='🍳'
          title='还没有发布过作品'
          desc='去「发现」页右下角 ＋ 发布你的下厨成果吧'
          btnText='去发布'
          onBtn={() => Taro.switchTab({ url: '/pages/discover/index' })}
        />
      ) : (
        <View className='mp-list'>
          {posts.map((p) => (
            <View key={p.id} className='p-card' onClick={() => goDetail(p.id)}>
              {p.topic && <View className='p-tag'><Text userSelect>{p.topic}</Text></View>}
              {p.images.length > 0 ? (
                <Image className='p-img' src={p.images[0]} mode='aspectFill' lazyLoad />
              ) : (
                <View className='p-img p-img--text'><Text userSelect>🍳</Text></View>
              )}
              <View className='p-body'>
                <View className='p-name'>{p.content || '分享了下厨心得'}</View>
                <View className='p-foot'>
                  <View className={`p-like ${p.is_liked ? 'on' : ''}`}>
                    <View className='ic ic-heart ic-xs' />
                    <Text userSelect>{p.like_count}</Text>
                  </View>
                </View>
                <View className='p-time'><Text userSelect>{timeText(p.created_at)}</Text></View>
              </View>
            </View>
          ))}
        </View>
      )}
    </View>
  )
}
