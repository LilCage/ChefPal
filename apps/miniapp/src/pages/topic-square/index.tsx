/**
 * 话题广场（原型 03 屏4）：真实聚合计数话题 chip + 点选后瀑布流
 * 数据源 GET /posts/topics（count）+ GET /posts?topic=
 */
import { Image, Text, View } from '@tarojs/components'
import Taro, { useDidShow, usePullDownRefresh, useReachBottom } from '@tarojs/taro'
import { useCallback, useState } from 'react'
import EmptyState from '../../components/EmptyState'
import NavBar from '../../components/NavBar'
import { fetchPosts, fetchTopics, likePost, unlikePost, type Post, type TopicItem } from '../../services/api'
import './index.scss'

const SIZE = 10

function formatCount(n: number): string {
  return n >= 1000 ? `${(n / 1000).toFixed(1).replace(/\.0$/, '')}k` : String(n)
}

export default function TopicSquare() {
  const [topics, setTopics] = useState<TopicItem[]>([])
  const [active, setActive] = useState<string | null>(null)
  const [posts, setPosts] = useState<Post[]>([])
  const [page, setPage] = useState(1)
  const [hasMore, setHasMore] = useState(false)
  const [loading, setLoading] = useState(false)
  const [loaded, setLoaded] = useState(false)

  const loadTopics = async () => {
    try {
      const list = await fetchTopics()
      setTopics(list)
      if (list.length > 0 && active === null) {
        setActive(list[0].topic)
      }
    } catch (e: any) {
      Taro.showToast({ title: e.message || '加载失败', icon: 'none' })
    }
  }

  const loadPosts = useCallback(
    async (topic: string | null, p: number, append: boolean) => {
      if (loading) return
      setLoading(true)
      try {
        const data = await fetchPosts(p, SIZE, topic || undefined)
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
    loadTopics()
    if (active) loadPosts(active, 1, false)
  })

  usePullDownRefresh(async () => {
    await loadTopics()
    if (active) await loadPosts(active, 1, false)
    Taro.stopPullDownRefresh()
  })

  useReachBottom(() => {
    if (hasMore && !loading) loadPosts(active, page + 1, true)
  })

  const switchTopic = (t: string) => {
    if (t === active) return
    setActive(t)
    setLoaded(false)
    loadPosts(t, 1, false)
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

  return (
    <View className='page-content topic-square'>
      <NavBar title={<Text className='pop'>话题广场</Text>} showBack />

      <View className='section chips-row'>
        <View className='chips'>
          {topics.map((t) => (
            <View
              key={t.topic}
              className={`chip ${active === t.topic ? 'chip--on' : ''}`}
              onClick={() => switchTopic(t.topic)}
            >
              <Text>{t.topic}</Text>
              <Text className='chip-count'>{formatCount(t.count)}</Text>
            </View>
          ))}
        </View>
      </View>

      {loaded && posts.length === 0 ? (
        <EmptyState icon='🏷️' title='这个话题下还没有作品' desc='来发第一篇，带上这个话题吧' />
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
                  <View className='p-av'>
                    {p.author.avatar_url?.startsWith('data:') ? (
                      <Image className='p-av-img' src={p.author.avatar_url} mode='aspectFill' />
                    ) : (
                      <Text>{p.author.nickname.slice(0, 1)}</Text>
                    )}
                  </View>
                  <Text className='p-who'>{p.author.nickname}</Text>
                  <View className={`p-like ${p.is_liked ? 'on' : ''}`} onClick={(e) => { e.stopPropagation(); toggleLike(p) }}>
                    <View className='ic ic-heart ic-xs' />
                    <Text>{p.like_count}</Text>
                  </View>
                </View>
              </View>
            </View>
          ))}
        </View>
      )}

      {loading && <View className='load-more'><Text>加载中…</Text></View>}
      {loaded && !hasMore && posts.length > 0 && (
        <View className='load-more'><Text>到底啦</Text></View>
      )}
    </View>
  )
}
