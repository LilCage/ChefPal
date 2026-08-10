/**
 * 关注/粉丝列表（关注系统配套）：分段 关注/粉丝 切换 + 用户行（带关注按钮）+ 触底分页
 */
import { Image, Text, View } from '@tarojs/components'
import Taro, { useDidShow, useReachBottom, useRouter } from '@tarojs/taro'
import { useState } from 'react'
import EmptyState from '../../components/EmptyState'
import NavBar from '../../components/NavBar'
import {
  fetchFollowers,
  fetchFollowing,
  followUser,
  unfollowUser,
  type UserListItem,
} from '../../services/api'
import './index.scss'

const SIZE = 20

export default function FollowList() {
  const router = useRouter()
  const userId = router.params.id || ''
  const initialTab = router.params.tab === 'following' ? 'following' : 'followers'
  const [tab, setTab] = useState<'followers' | 'following'>(initialTab)
  const [items, setItems] = useState<UserListItem[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [hasMore, setHasMore] = useState(false)
  const [loaded, setLoaded] = useState(false)
  const [loading, setLoading] = useState(false)

  const load = async (t: 'followers' | 'following', p: number, append: boolean) => {
    if (loading) return
    setLoading(true)
    try {
      const fn = t === 'followers' ? fetchFollowers : fetchFollowing
      const data = await fn(userId, p, SIZE)
      setItems((prev) => (append ? [...prev, ...data.items] : data.items))
      setTotal(data.total)
      setHasMore(data.has_more)
      setPage(p)
      setLoaded(true)
    } catch (e: any) {
      Taro.showToast({ title: e.message || '加载失败', icon: 'none' })
    } finally {
      setLoading(false)
    }
  }

  useDidShow(() => {
    load(tab, 1, false)
  })

  const switchTab = (t: 'followers' | 'following') => {
    if (t === tab) return
    setTab(t)
    setLoaded(false)
    load(t, 1, false)
  }

  useReachBottom(() => {
    if (hasMore && !loading) load(tab, page + 1, true)
  })

  const toggleFollow = async (u: UserListItem) => {
    try {
      if (u.is_following) {
        await unfollowUser(u.id)
      } else {
        await followUser(u.id)
      }
      setItems((prev) =>
        prev.map((x) => (x.id === u.id ? { ...x, is_following: !x.is_following } : x)),
      )
    } catch (e: any) {
      Taro.showToast({ title: e.message || '操作失败', icon: 'none' })
    }
  }

  const goProfile = (u: UserListItem) =>
    Taro.navigateTo({ url: `/pages/user-profile/index?id=${u.id}` })

  return (
    <View className='page-content follow-list'>
      <NavBar title={tab === 'following' ? '关注列表' : '粉丝列表'} showBack />

      <View className='seg'>
        <View className={`seg-item ${tab === 'following' ? 'on' : ''}`} onClick={() => switchTab('following')}>
          <Text>关注 {tab === 'following' ? total : ''}</Text>
        </View>
        <View className={`seg-item ${tab === 'followers' ? 'on' : ''}`} onClick={() => switchTab('followers')}>
          <Text>粉丝 {tab === 'followers' ? total : ''}</Text>
        </View>
      </View>

      {loaded && items.length === 0 ? (
        <EmptyState icon={tab === 'following' ? '👋' : '👥'} title='这里还没有人' desc='去广场逛逛，认识更多下厨同好' />
      ) : (
        <View className='u-list'>
          {items.map((u) => (
            <View key={u.id} className='u-row' onClick={() => goProfile(u)}>
              <View className='u-av'>
                {u.avatar_url?.startsWith('data:') ? (
                  <Image className='u-av-img' src={u.avatar_url} mode='aspectFill' />
                ) : (
                  <Text>{u.nickname.slice(0, 1)}</Text>
                )}
              </View>
              <View className='u-info'>
                <Text className='u-name'>{u.nickname}</Text>
                <Text className='u-sub'>{u.follower_count} 粉丝</Text>
              </View>
              <View
                className={`btn ${u.is_following ? 'btn--white' : 'btn--red'} btn--xs u-follow`}
                onClick={(e) => {
                  e.stopPropagation()
                  toggleFollow(u)
                }}
              >
                <Text>{u.is_following ? '已关注' : '关注'}</Text>
              </View>
            </View>
          ))}
        </View>
      )}

      {loading && <View className='load-more'><Text>加载中…</Text></View>}
      {loaded && !hasMore && items.length > 0 && (
        <View className='load-more'><Text>到底啦</Text></View>
      )}
    </View>
  )
}
