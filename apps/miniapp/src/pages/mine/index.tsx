/**
 * 屏6 · 我的 个人中心（原型 01）
 * 档案/收藏/设置 + 编辑资料入口 + 协议/注销
 */
import { Image, Text, View } from '@tarojs/components'
import Taro, { useDidShow } from '@tarojs/taro'
import { useState } from 'react'
import { deleteAccount, fetchFavorites, fetchMyPosts, fetchTasteMemory, fetchUserProfile } from '../../services/api'
import { useAuthStore } from '../../stores/auth'
import { useTabStore } from '../../stores/tab'
import { getSafeTop } from '../../utils/safeArea'
import './index.scss'

const MENU = [
  { key: 'my-recipes', icon: 'ic-edit', title: '我的菜谱', sub: '自建图文菜谱 · 发布社区', url: '/pages/my-recipes/index' },
  { key: 'preferences', icon: 'ic-sliders', title: '口味设置', sub: '忌口 · 辣度 · 咸淡 · 技能', url: '/pages/preferences/index' },
  { key: 'meal-plan', icon: 'ic-cal', title: '膳食规划', sub: '3 天 / 7 天 · 营养分析', url: '/pages/meal-plan/index' },
  { key: 'follow', icon: 'ic-heart', title: '我的关注 · 粉丝', sub: '关注的人 · 粉丝列表' },
  { key: 'history', icon: 'ic-comment', title: '我的问答历史', sub: '最近 20 条', url: '/pages/qa-history/index' },
  { key: 'share', icon: 'ic-share', title: '我的分享卡片', sub: '生成精美卡片' },
  { key: 'agreement', icon: 'ic-lock', title: '用户协议与隐私政策', sub: '服务条款 · 隐私说明', url: '/pages/agreement/index' },
  { key: 'disclaimer', icon: 'ic-info', title: '免责声明与帮助', sub: 'AI 结果仅供参考' },
]

/* 趣味探索（原型 05）入口：右上角约束 → 全部放内容区 */
const FUN_MENU = [
  { key: 'seasonal', icon: 'ic-cal', title: '时令食材日历', sub: '吃当季 · 最新鲜', url: '/pages/seasonal-calendar/index' },
  { key: 'rescue', icon: 'ic-camera', title: '黑暗料理拯救', sub: '翻车现场 AI 诊断', url: '/pages/dark-rescue/index' },
  { key: 'vote', icon: 'ic-heart', title: '家庭口味投票', sub: '全家决定吃什么', url: '/pages/family-vote/index' },
  { key: 'challenge', icon: 'ic-award', title: '烹饪挑战', sub: '一周只花 50 元', url: '/pages/cooking-challenge/index' },
  { key: 'agents', icon: 'ic-spark', title: 'AI 主厨团', sub: '营养师+大厨+采购', url: '/pages/multi-agent/index' },
  { key: 'fridge', icon: 'ic-bell', title: '冰箱管家', sub: '食材过期预警', url: '/pages/fridge/index' },
]

export default function Mine() {
  const setTab = useTabStore((s) => s.setIndex)
  const user = useAuthStore((s) => s.user)
  const logout = useAuthStore((s) => s.logout)
  const [qaCount, setQaCount] = useState(0)
  const [recipeCount, setRecipeCount] = useState(0)
  const [postCount, setPostCount] = useState(0)
  const [followerCount, setFollowerCount] = useState(0)
  const [followingCount, setFollowingCount] = useState(0)

  /* 漫画风称呼：技能定身份 + 取匹配度最高的 2 个口味修饰（口味记忆风格 > 辣度 > 咸淡），忌口不展示 */
  const prefs = user?.preferences || {}
  const [tasteStyle, setTasteStyle] = useState<string>('')
  const skillTitles: Record<string, string> = {
    '厨房小白': '灶台萌新',
    '进阶达人': '料理猎人',
    '实力大厨': '食之大师',
  }
  const spicinessAdj: Record<number, string> = {
    0: '不食人间烟火辣',
    1: '微辣微风',
    2: '中辣热火',
    3: '特辣爆炎',
  }
  const saltinessAdj: Record<string, string> = {
    '偏淡': '清淡派',
    '适中': '咸淡派',
    '偏咸': '重口派',
  }
  /* 口味记忆风格 → 漫画修饰语 */
  const styleAdj: Record<string, string> = {
    '浓香下饭': '浓香', '清爽快手': '清爽', '蒸煮清淡': '鲜蒸', '香辣过瘾': '火辣',
    '甜口绵绵': '甜蜜', '甜口绵密': '甜蜜', '汤羹温润': '温润',
  }
  const identity = skillTitles[prefs.skill] || '美食猎人'
  const styleMod = tasteStyle && styleAdj[tasteStyle] ? styleAdj[tasteStyle] : ''
  const spicyMod = typeof prefs.spiciness === 'number' ? spicinessAdj[prefs.spiciness] : ''
  const saltMod = saltinessAdj[prefs.saltiness] || ''
  /* 按匹配度排序取前 2 个 */
  const mods = [styleMod, spicyMod, saltMod].filter(Boolean).slice(0, 2)
  const modText = mods.length ? mods.join(' · ') : ''
  const prefsTag = modText ? `${modText} · ${identity}` : identity

  useDidShow(() => {
    setTab(3)
    loadCounts()
  })

  const loadCounts = async () => {
    try {
      const [qa, recipe, posts, profile, taste] = await Promise.all([
        fetchFavorites('qa'),
        fetchFavorites('recipe'),
        fetchMyPosts(),
        fetchUserProfile(user?.id || ''),
        fetchTasteMemory(),
      ])
      setQaCount(qa.length)
      setRecipeCount(recipe.length)
      setPostCount(posts.length)
      setFollowerCount(profile.follower_count)
      setFollowingCount(profile.following_count)
      setTasteStyle(taste.preferred_styles?.[0] || '')
    } catch {
      /* 未登录忽略 */
    }
  }

  const goEditProfile = () => Taro.navigateTo({ url: '/pages/profile-edit/index' })

  const onMenu = (item: (typeof MENU)[number]) => {
    if (item.key === 'share') {
      Taro.navigateTo({ url: '/pages/share-card/index' })
      return
    }
    if (item.key === 'follow') {
      if (!user) return
      Taro.navigateTo({ url: `/pages/follow-list/index?id=${user.id}&tab=following` })
      return
    }
    if (item.key === 'disclaimer') {
      Taro.showModal({
        title: '免责声明',
        content: 'ChefPal 输出的菜谱与问答由 AI 生成，仅供参考，不构成医疗/营养处方；对过敏原请保持谨慎，实际烹饪请以食材新鲜与安全为准。',
        showCancel: false,
        confirmText: '知道了',
      })
      return
    }
    if (!item.url) return
    Taro.navigateTo({ url: item.url })
  }

  const confirmDelete = () => {
    Taro.showModal({
      title: '注销账号',
      content: '注销后将永久删除你的收藏、问答历史与生成的菜谱，且无法恢复。确定注销吗？',
      confirmText: '确认注销',
      confirmColor: '#E8482A',
      success: async (r) => {
        if (!r.confirm) return
        try {
          await deleteAccount()
          logout()
          Taro.reLaunch({ url: '/pages/login/index' })
          Taro.showToast({ title: '账号已注销', icon: 'none' })
        } catch (e: any) {
          Taro.showToast({ title: e.message || '注销失败，请重试', icon: 'none' })
        }
      },
    })
  }

  if (!user) {
    return (
      <View className='page-content mine'>
        <View className='nav' style={{ paddingTop: `${getSafeTop()}px` }}><View className='nav-title pop'>我的厨房</View></View>
        <View className='empty'>
          <View className='empty-art'>🍳</View>
          <Text className='empty-title'>还没有登录</Text>
          <Text className='empty-desc'>登录后同步你的收藏、历史与口味偏好</Text>
          <View className='btn btn--red btn--block' onClick={() => Taro.navigateTo({ url: '/pages/login/index' })}>
            <Text>微信一键登录</Text>
          </View>
        </View>
      </View>
    )
  }

  return (
    <View className='page-content mine'>
      <View className='nav' style={{ paddingTop: `${getSafeTop()}px` }}>
        <View className='nav-title pop'>我的厨房</View>
      </View>

      <View className='profile' onClick={goEditProfile}>
        <View className='avatar'>
          {user.avatar_url?.startsWith('data:') ? (
            <Image className='avatar-img' src={user.avatar_url} mode='aspectFill' />
          ) : (
            <Text>🍳</Text>
          )}
        </View>
        <View className='profile-info'>
          <View className='pname'>
            <Text>{user.nickname || '美食猎人'}</Text>
            <View className='lv-badge'><Text>🏆 Lv.1</Text></View>
          </View>
          <Text className='ptag'>{prefsTag}</Text>
        </View>
        <View className='edit-badge'>
          <View className='ic ic-edit ic-sm' />
        </View>
      </View>

      <View className='stats'>
        <View className='stat'><Text className='stat-num'>{qaCount}</Text><Text className='stat-label'>收藏问答</Text></View>
        <View className='stat'><Text className='stat-num'>{recipeCount}</Text><Text className='stat-label'>收藏菜谱</Text></View>
        <View className='stat'><Text className='stat-num'>{postCount}</Text><Text className='stat-label'>我的作品</Text></View>
      </View>

      <View className='menu'>
        {MENU.map((m) => (
          <View key={m.key} className='menu-item' onClick={() => onMenu(m)}>
            <View className='mi-ic'><View className={`ic ${m.icon} ic-sm`} /></View>
            <View className='mi-body'>
              <Text className='mi-title'>{m.title}</Text>
              <Text className='mi-sub'>
                {m.key === 'follow' ? `关注 ${followingCount} · 粉丝 ${followerCount}` : m.sub}
              </Text>
            </View>
            <View className='ic ic-chev-r ic-sm' />
          </View>
        ))}
      </View>

      <View className='fun-title'>
        <Text className='fun-title-label pop'>趣味探索</Text>
      </View>
      <View className='menu'>
        {FUN_MENU.map((m) => (
          <View key={m.key} className='menu-item' onClick={() => onMenu(m)}>
            <View className='mi-ic'><View className={`ic ${m.icon} ic-sm`} /></View>
            <View className='mi-body'>
              <Text className='mi-title'>{m.title}</Text>
              <Text className='mi-sub'>{m.sub}</Text>
            </View>
            <View className='ic ic-chev-r ic-sm' />
          </View>
        ))}
      </View>

      <View className='danger-zone'>
        <View className='btn btn--white btn--block btn--sm danger-btn' onClick={confirmDelete}>
          <View className='ic ic-trash ic-sm' />
          <Text>注销账号</Text>
        </View>
      </View>

      <View className='logout' onClick={() => {
        Taro.showModal({
          title: '退出登录',
          content: '确定退出当前账号吗？',
          confirmColor: '#E8482A',
          success: (r) => { if (r.confirm) { logout(); Taro.reLaunch({ url: '/pages/login/index' }) } },
        })
      }}>
        <Text>退出登录</Text>
      </View>
    </View>
  )
}
