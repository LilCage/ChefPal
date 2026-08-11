/**
 * 屏2 · 作品详情（原型 03）
 * 作者/大图/心得(#话题)/关联菜谱卡 + 点赞 + 分享
 */
import { Button, Image, Text, View } from '@tarojs/components'
import Taro, { useLoad, useShareAppMessage } from '@tarojs/taro'
import { useState } from 'react'
import NavBar from '../../components/NavBar'
import { fetchPost, followUser, likePost, unfollowUser, unlikePost, type Post } from '../../services/api'
import { useAuthStore } from '../../stores/auth'
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

function renderContent(content: string, topic: string | null): (string | { text: string })[] {
  const parts: (string | { text: string })[] = [content]
  if (topic) {
    const idx = content.indexOf(topic)
    if (idx >= 0) {
      return [
        content.slice(0, idx),
        { text: topic },
        content.slice(idx + topic.length),
      ]
    }
  }
  return parts
}

export default function PostDetail() {
  const me = useAuthStore((s) => s.user)
  const [post, setPost] = useState<Post | null>(null)
  const [loaded, setLoaded] = useState(false)
  const [liking, setLiking] = useState(false)
  const [isFollowing, setIsFollowing] = useState(false)

  useLoad((params) => {
    const id = (params as any).id as string
    if (id) loadPost(id)
  })

  useShareAppMessage(() => ({
    title: `ChefPal · ${post?.author.nickname || '大家的厨房'} 的跟做作品`,
    path: post ? `/pages/post-detail/index?id=${post.id}` : '/pages/index/index',
  }))

  const loadPost = async (id: string) => {
    try {
      const p = await fetchPost(id)
      setPost(p)
      setIsFollowing(!!p.author.is_following)
    } catch (e: any) {
      Taro.showToast({ title: e.message || '加载失败', icon: 'none' })
    } finally {
      setLoaded(true)
    }
  }

  const toggleFollow = async () => {
    if (!post || post.author.id === me?.id) return
    try {
      if (isFollowing) {
        await unfollowUser(post.author.id)
        setIsFollowing(false)
      } else {
        await followUser(post.author.id)
        setIsFollowing(true)
      }
    } catch (e: any) {
      Taro.showToast({ title: e.message || '操作失败', icon: 'none' })
    }
  }

  const goAuthor = () => {
    if (!post) return
    Taro.navigateTo({ url: `/pages/user-profile/index?id=${post.author.id}` })
  }

  const toggleLike = async () => {
    if (!post || liking) return
    setLiking(true)
    try {
      if (post.is_liked) await unlikePost(post.id)
      else await likePost(post.id)
      setPost({ ...post, is_liked: !post.is_liked, like_count: post.like_count + (post.is_liked ? -1 : 1) })
    } catch (e: any) {
      Taro.showToast({ title: e.message || '操作失败', icon: 'none' })
    } finally {
      setLiking(false)
    }
  }

  const goShareCard = () => {
    if (!post) return
    Taro.navigateTo({ url: `/pages/post-share-card/index?id=${post.id}` })
  }

  const goComments = () => {
    if (!post) return
    Taro.navigateTo({ url: `/pages/comments/index?id=${post.id}` })
  }

  if (!loaded) {
    return (
      <View className='page-content post-detail'>
        <NavBar title='作品详情' showBack />
        <View className='loading'><Text>加载中…</Text></View>
      </View>
    )
  }

  if (!post) {
    return (
      <View className='page-content post-detail'>
        <NavBar title='作品详情' showBack />
        <View className='loading'><Text>作品不存在或已删除</Text></View>
      </View>
    )
  }

  const segments = renderContent(post.content, post.topic)

  return (
    <View className='page-content post-detail'>
      <NavBar title='作品详情' showBack />

      <View className='post-head'>
        <View className='p-av' onClick={goAuthor}>
          {post.author.avatar_url?.startsWith('data:') ? (
            <Image className='p-av-img' src={post.author.avatar_url} mode='aspectFill' />
          ) : (
            <Text className='p-av-ph'>{post.author.nickname.slice(0, 1)}</Text>
          )}
        </View>
        <View className='ph-body' onClick={goAuthor}>
          <Text className='ph-name'>{post.author.nickname}</Text>
          <Text className='ph-time'>{timeText(post.created_at)} · 跟做打卡</Text>
        </View>
        {post.author.id !== me?.id && (
          <View
            className={`follow-btn ${isFollowing ? 'on' : ''}`}
            onClick={toggleFollow}
          >
            <Text>{isFollowing ? '已关注' : '关注'}</Text>
          </View>
        )}
      </View>

      {post.images.length > 0 && (
        <View className='post-img'>
          <Image src={post.images[0]} mode='widthFix' />
        </View>
      )}

      <View className='post-body'>
        <Text className='ptext'>
          {segments.map((seg, i) =>
            typeof seg === 'string' ? (
              <Text key={i}>{seg}</Text>
            ) : (
              <Text key={i} className='hash'>{seg.text}</Text>
            ),
          )}
        </Text>

        {(post.recipe_id || post.my_recipe_id) && (
          <View
            className='link-card'
            onClick={() => Taro.navigateTo({
              url: post.my_recipe_id
                ? `/pages/my-recipe-create/index?id=${post.my_recipe_id}`
                : `/pages/recipe-detail/index?id=${post.recipe_id}`,
            })}
          >
            <View className='lc-ic'><Text>🍽</Text></View>
            <View className='lc-body'>
              <Text className='lc-title'>{post.my_recipe_id ? '查看完整自建菜谱' : '查看完整 AI 菜谱'}</Text>
              <Text className='lc-sub'>点此查看做法步骤</Text>
            </View>
            <View className='ic ic-chev-r ic-sm lc-go' />
          </View>
        )}
      </View>

      <View className='act-row'>
        <View className={`like-btn ${post.is_liked ? 'on' : ''}`} onClick={toggleLike}>
          <View className='ic ic-heart ic-sm' />
          <Text>{post.like_count}</Text>
        </View>
        <View className='share-chip' onClick={goComments}>
          <View className='ic ic-comment ic-sm' />
          <Text>评论 {post.comment_count}</Text>
        </View>
        <View className='share-chip' onClick={goShareCard}>
          <View className='ic ic-share ic-sm' />
          <Text>分享</Text>
        </View>
      </View>

      <View className='actbar'>
        <View className='cmt-input' onClick={goComments}>
          <View className='ic ic-comment ic-sm' />
          <Text className='cmt-input-ph'>说点什么…</Text>
        </View>
        <Button className={`btn btn--red actbar-like ${post.is_liked ? 'liked' : ''}`} onClick={toggleLike}>
          <View className='ic ic-heart ic-sm' />
          <Text>{post.is_liked ? '已点赞' : '点赞'}</Text>
        </Button>
      </View>
    </View>
  )
}
