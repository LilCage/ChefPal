/**
 * 屏5 · 发现 社区广场（原型 03 屏4 话题广场 + 屏5 关注动态）
 * 关注动态流 + 话题筛选 + 瀑布流作品卡 + FAB 发布 + 下拉刷新 + 触底分页
 */
import { Image, Text, View } from '@tarojs/components'
import Taro, { useDidShow, usePullDownRefresh, useReachBottom } from '@tarojs/taro'
import { useCallback, useState } from 'react'
import EmptyState from '../../components/EmptyState'
import { fetchFollowFeed, fetchPosts, likePost, unlikePost, type Post } from '../../services/api'
import { useTabStore } from '../../stores/tab'
import { getSafeTop } from '../../utils/safeArea'
import './index.scss'

const SIZE = 10
const CHIPS = ['关注', '推荐', '#今日晚餐', '#减脂餐', '#一人食', '#跟做打卡']

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

export default function Discover() {
  const setTab = useTabStore((s) => s.setIndex)
  const [posts, setPosts] = useState<Post[]>([])
  const [active, setActive] = useState('推荐')
  const [page, setPage] = useState(1)
  const [hasMore, setHasMore] = useState(false)
  const [loading, setLoading] = useState(false)
  const [loaded, setLoaded] = useState(false)

  const load = useCallback(
    async (target: string, p: number, append: boolean) => {
      if (loading) return
      setLoading(true)
      try {
        let data
        if (target === '关注') {
          data = await fetchFollowFeed(p, SIZE)
        } else {
          const topic = target === '推荐' ? undefined : target
          data = await fetchPosts(p, SIZE, topic)
        }
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
    [loading],
  )

  useDidShow(() => {
    setTab(2)
    load(active, 1, false)
  })

  usePullDownRefresh(async () => {
    await load(active, 1, false)
    Taro.stopPullDownRefresh()
  })

  useReachBottom(() => {
    if (hasMore && !loading) load(active, page + 1, true)
  })

  const switchChip = (t: string) => {
    if (t === active) return
    setActive(t)
    setLoaded(false)
    load(t, 1, false)
  }

  const toggleLike = async (p: Post) => {
    try {
      if (p.is_liked) {
        await unlikePost(p.id)
      } else {
        await likePost(p.id)
      }
      setPosts((prev) =>
        prev.map((x) =>
          x.id === p.id
            ? { ...x, is_liked: !x.is_liked, like_count: x.like_count + (x.is_liked ? -1 : 1) }
            : x,
        ),
      )
    } catch (e: any) {
      Taro.showToast({ title: e.message || '操作失败', icon: 'none' })
    }
  }

  const goDetail = (p: Post) => Taro.navigateTo({ url: `/pages/post-detail/index?id=${p.id}` })
  const goAuthor = (p: Post) =>
    Taro.navigateTo({ url: `/pages/user-profile/index?id=${p.author.id}` })
  const goTopicSquare = () => Taro.navigateTo({ url: '/pages/topic-square/index' })

  return (
    <View className='page-content discover'>
      <View className='nav' style={{ paddingTop: `${getSafeTop()}px` }}>
        <View className='nav-title'><Text className='pop'>发现</Text> · 大家的厨房</View>
      </View>

      <View className='section chips-row'>
        <View className='chips'>
          {CHIPS.map((t) => (
            <View key={t} className={`chip ${active === t ? 'chip--on' : ''}`} onClick={() => switchChip(t)}>
              <Text>{t}</Text>
            </View>
          ))}
          <View className='chip chip--hot' onClick={goTopicSquare}>
            <Text>更多话题 →</Text>
          </View>
        </View>
      </View>

      {loaded && posts.length === 0 ? (
        <EmptyState
          icon={active === '关注' ? '👋' : '🍳'}
          title={
            active === '关注'
              ? '还没有关注的人'
              : active === '推荐'
                ? '还没有人发作品'
                : '这个话题下还没有作品'
          }
          desc={
            active === '关注'
              ? '去广场逛逛，关注感兴趣的创作者，追更 TA 的动态'
              : '第一个分享你的下厨成果吧，点右下角 ＋ 发布'
          }
        />
      ) : (
        <View className='wf'>
          {posts.map((p) => (
            <View key={p.id} className='p-card' onClick={() => goDetail(p)}>
              {p.topic && <View className='p-tag'><Text>{p.topic}</Text></View>}
              {p.images.length > 0 ? (
                <Image className='p-img' src={p.images[0]} mode='aspectFill' lazyLoad />
              ) : (
                <View className='p-img p-img--text'><Text>🍳</Text></View>
              )}
              <View className='p-body'>
                <View className='p-name'>{p.content || '分享了下厨心得'}</View>
                <View className='p-foot'>
                  <View
                    className='p-av'
                    onClick={(e) => {
                      e.stopPropagation()
                      goAuthor(p)
                    }}
                  >
                    {p.author.avatar_url?.startsWith('data:') ? (
                      <Image className='p-av-img' src={p.author.avatar_url} mode='aspectFill' />
                    ) : (
                      <Text>{p.author.nickname.slice(0, 1)}</Text>
                    )}
                  </View>
                  <Text className='p-who'>{p.author.nickname}</Text>
                  {p.author.is_following && <View className='mini-chip green'><Text>已关注</Text></View>}
                  <View className={`p-like ${p.is_liked ? 'on' : ''}`} onClick={(e) => { e.stopPropagation(); toggleLike(p) }}>
                    <View className='ic ic-heart ic-xs' />
                    <Text>{p.like_count}</Text>
                  </View>
                </View>
                <View className='p-time'><Text>{timeText(p.created_at)}</Text></View>
              </View>
            </View>
          ))}
        </View>
      )}

      {loading && <View className='load-more'><Text>加载中…</Text></View>}
      {loaded && !hasMore && posts.length > 0 && (
        <View className='load-more'><Text>到底啦，去看看大家的下厨成果吧</Text></View>
      )}

      <View className='fab' onClick={() => Taro.navigateTo({ url: '/pages/post-create/index' })}>
        <View className='ic ic-plus ic-lg' />
      </View>
    </View>
  )
}
