/**
 * 作者主页（关注系统配套）：TA 的档案 + 关注按钮 + 作品数/关注/粉丝 + 作品瀑布流
 */
import { Image, Text, View } from '@tarojs/components'
import Taro, { useDidShow, usePullDownRefresh, useReachBottom, useRouter } from '@tarojs/taro'
import { useCallback, useState } from 'react'
import EmptyState from '../../components/EmptyState'
import NavBar from '../../components/NavBar'
import {
  fetchPosts,
  fetchUserProfile,
  followUser,
  unfollowUser,
  type Post,
  type UserProfile,
} from '../../services/api'
import './index.scss'

const SIZE = 10

export default function UserProfile() {
  const router = useRouter()
  const userId = router.params.id || ''
  const [profile, setProfile] = useState<UserProfile | null>(null)
  const [posts, setPosts] = useState<Post[]>([])
  const [page, setPage] = useState(1)
  const [hasMore, setHasMore] = useState(false)
  const [loading, setLoading] = useState(false)
  const [loaded, setLoaded] = useState(false)
  const [following, setFollowing] = useState(false)

  const loadPosts = useCallback(
    async (p: number, append: boolean) => {
      if (loading) return
      setLoading(true)
      try {
        const data = await fetchPosts(p, SIZE, undefined, userId)
        setPosts((prev) => (append ? [...prev, ...data.items] : data.items))
        setHasMore(data.has_more)
        setPage(p)
        setLoaded(true)
      } catch (e: any) {
        Taro.showToast({ title: e.message || '加载失败', icon: 'none' })
      } finally {
        setLoading(false)
      }
    },
    [loading, userId],
  )

  useDidShow(() => {
    if (!userId) {
      Taro.navigateBack()
      return
    }
    loadProfile()
    loadPosts(1, false)
  })

  usePullDownRefresh(async () => {
    await loadProfile()
    await loadPosts(1, false)
    Taro.stopPullDownRefresh()
  })

  useReachBottom(() => {
    if (hasMore && !loading) loadPosts(page + 1, true)
  })

  const loadProfile = async () => {
    try {
      const p = await fetchUserProfile(userId)
      setProfile(p)
      setFollowing(p.is_following)
    } catch (e: any) {
      Taro.showToast({ title: e.message || '加载失败', icon: 'none' })
    }
  }

  const toggleFollow = async () => {
    try {
      if (following) {
        const r = await unfollowUser(userId)
        setFollowing(false)
        setProfile((prev) => (prev ? { ...prev, is_following: false, follower_count: r.follower_count } : prev))
      } else {
        const r = await followUser(userId)
        setFollowing(true)
        setProfile((prev) => (prev ? { ...prev, is_following: true, follower_count: r.follower_count } : prev))
      }
    } catch (e: any) {
      Taro.showToast({ title: e.message || '操作失败', icon: 'none' })
    }
  }

  const goFollowList = (tab: 'followers' | 'following') =>
    Taro.navigateTo({ url: `/pages/follow-list/index?id=${userId}&tab=${tab}` })

  const goDetail = (p: Post) => Taro.navigateTo({ url: `/pages/post-detail/index?id=${p.id}` })

  return (
    <View className='page-content user-profile'>
      <NavBar title='TA 的主页' showBack />

      <View className='profile-card'>
        <View className='pc-top'>
          <View className='pc-avatar'>
            {profile?.avatar_url?.startsWith('data:') ? (
              <Image className='pc-avatar-img' src={profile.avatar_url} mode='aspectFill' />
            ) : (
              <Text userSelect>🍳</Text>
            )}
          </View>
          <View className='pc-info'>
            <View className='pc-name'><Text userSelect className='pop'>{profile?.nickname || '美食猎人'}</Text></View>
            <Text userSelect className='pc-sub'>下厨同好 · ChefPal</Text>
          </View>
        </View>

        <View className='pc-stats'>
          <View className='ps'><Text userSelect className='ps-num'>{profile?.post_count ?? 0}</Text><Text userSelect className='ps-label'>作品</Text></View>
          <View className='ps' onClick={() => goFollowList('following')}><Text userSelect className='ps-num'>{profile?.following_count ?? 0}</Text><Text userSelect className='ps-label'>关注</Text></View>
          <View className='ps' onClick={() => goFollowList('followers')}><Text userSelect className='ps-num'>{profile?.follower_count ?? 0}</Text><Text userSelect className='ps-label'>粉丝</Text></View>
        </View>

        <View
          className={`btn ${following ? 'btn--white' : 'btn--red'} btn--block btn--sm pc-follow`}
          onClick={toggleFollow}
        >
          <Text userSelect>{following ? '✓ 已关注' : '＋ 关注'}</Text>
        </View>
      </View>

      <View className='section'>
        <View className='sec-title'>TA 的作品</View>
      </View>

      {loaded && posts.length === 0 ? (
        <EmptyState icon='🍳' title='TA 还没有发布作品' desc='关注 TA，等待第一份下厨成果' />
      ) : (
        <View className='wf'>
          {posts.map((p) => (
            <View key={p.id} className='p-card' onClick={() => goDetail(p)}>
              {p.topic && <View className='p-tag'><Text userSelect>{p.topic}</Text></View>}
              {p.images.length > 0 ? (
                <Image className='p-img' src={p.images[0]} mode='aspectFill' lazyLoad />
              ) : (
                <View className='p-img p-img--text'><Text userSelect>🍳</Text></View>
              )}
              <View className='p-body'>
                <View className='p-name'>{p.content || '分享了下厨心得'}</View>
                <View className='p-foot'>
                  <Text userSelect className='p-who'>{profile?.nickname || '美食猎人'}</Text>
                  <View className='p-like'><View className='ic ic-heart ic-xs' /><Text userSelect>{p.like_count}</Text></View>
                </View>
              </View>
            </View>
          ))}
        </View>
      )}

      {loading && <View className='load-more'><Text userSelect>加载中…</Text></View>}
    </View>
  )
}
