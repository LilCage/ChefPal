/**
 * 分享卡片（原型 02 屏4）：canvas 2d 绘制 → 保存相册 / 转发
 * 入口：菜谱详情「分享」(带 id) 或 我的-我的分享卡片（取第一个收藏菜谱）
 */
import { Button, Canvas, Image, Text, View } from '@tarojs/components'
import Taro, { useLoad, useShareAppMessage } from '@tarojs/taro'
import { useEffect, useState } from 'react'
import EmptyState from '../../components/EmptyState'
import NavBar from '../../components/NavBar'
import {
  fetchFavorites,
  fetchRecipe,
  fetchShareCard,
  type Recipe,
  type ShareCardData,
} from '../../services/api'
import './index.scss'

const CANVAS_W = 620
const CANVAS_H = 980
const INK = '#241A12'
const BROWN = '#4A2E1D'
const CREAM = '#FFF7EC'
const SOFT = '#F6E3C3'
const RED = '#E8482A'

export default function ShareCard() {
  const [recipe, setRecipe] = useState<Recipe | null>(null)
  const [shareData, setShareData] = useState<ShareCardData | null>(null)
  const [cardImg, setCardImg] = useState('')
  const [empty, setEmpty] = useState(false)

  useShareAppMessage(() => ({
    title: `ChefPal · ${recipe?.title || '口袋 AI 厨师'}`,
    path: recipe ? `/pages/recipe-detail/index?id=${recipe.id}` : '/pages/index/index',
    imageUrl: cardImg || undefined,
  }))

  useLoad((params) => {
    const id = (params as any).id as string | undefined
    if (id) initRecipe(id)
    else pickFavorite()
  })

  const pickFavorite = async () => {
    try {
      const favs = await fetchFavorites('recipe')
      if (favs.length === 0) {
        setEmpty(true)
        return
      }
      initRecipe(favs[0].content_id)
    } catch {
      setEmpty(true)
    }
  }

  const initRecipe = async (id: string) => {
    try {
      const [rec, share] = await Promise.all([fetchRecipe(id), fetchShareCard(id)])
      setRecipe(rec)
      setShareData(share)
    } catch (e: any) {
      Taro.showToast({ title: e.message || '加载失败', icon: 'none' })
      setEmpty(true)
    }
  }

  useEffect(() => {
    if (recipe && shareData) draw()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [recipe, shareData])

  const draw = async () => {
    const res = await new Promise<any>((resolve) => {
      Taro.createSelectorQuery()
        .select('#shareCanvas')
        .fields({ node: true, size: true })
        .exec((r) => resolve(r && r[0] ? r[0] : null))
    })
    if (!res || !res.node) return
    const canvas = res.node as any
    const dpr = (Taro.getSystemInfoSync().pixelRatio as number) || 2
    const W = CANVAS_W
    const H = CANVAS_H
    canvas.width = W * dpr
    canvas.height = H * dpr
    const ctx = canvas.getContext('2d') as any
    ctx.scale(dpr, dpr)
    ctx.clearRect(0, 0, W, H)

    const roundRect = (x: number, y: number, w: number, h: number, r: number, fill?: string) => {
      ctx.beginPath()
      ctx.moveTo(x + r, y)
      ctx.arcTo(x + w, y, x + w, y + h, r)
      ctx.arcTo(x + w, y + h, x, y + h, r)
      ctx.arcTo(x, y + h, x, y, r)
      ctx.arcTo(x, y, x + w, y, r)
      ctx.closePath()
      if (fill) {
        ctx.fillStyle = fill
        ctx.fill()
      }
      ctx.strokeStyle = INK
      ctx.lineWidth = 5
      ctx.stroke()
    }

    const wrapText = (text: string, x: number, y: number, maxWidth: number, lineHeight: number, maxLines = 6) => {
      const chars = String(text).split('')
      let line = ''
      let n = 0
      for (const ch of chars) {
        const test = line + ch
        if (ctx.measureText(test).width > maxWidth && line) {
          ctx.fillText(line, x, y)
          y += lineHeight
          n += 1
          line = ch
          if (n >= maxLines) return y
        } else {
          line = test
        }
      }
      if (line) ctx.fillText(line, x, y)
      return y
    }

    const loadImage = (dataUrl: string) =>
      new Promise<any>((resolve) => {
        const img = canvas.createImage()
        img.onload = () => resolve(img)
        img.onerror = () => resolve(img)
        img.src = dataUrl
      })

    // 背景 + 外描边
    roundRect(0, 0, W, H, 36, CREAM)

    // 顶部 Hero（渐变 + 品牌角标 + emoji）
    const grad = ctx.createLinearGradient(0, 20, 0, 280)
    grad.addColorStop(0, '#FFD9B0')
    grad.addColorStop(1, '#FF9D6B')
    roundRect(20, 20, W - 40, 260, 28)
    ctx.fillStyle = grad
    ctx.fill()
    // 品牌角标
    roundRect(40, 42, 150, 46, 12, RED)
    ctx.fillStyle = '#FFFFFF'
    ctx.font = '900 26px sans-serif'
    ctx.fillText('ChefPal 生成', 66, 73)
    // 居中 emoji
    ctx.font = '150px sans-serif'
    ctx.fillText('🍳', W / 2 - 75, 200)

    // 标题
    ctx.fillStyle = INK
    ctx.font = '900 52px sans-serif'
    wrapText(recipe!.title, 48, 380, W - 96, 66, 1)

    // 元信息
    ctx.fillStyle = BROWN
    ctx.font = '800 28px sans-serif'
    ctx.fillText(
      `匹配 ${shareData!.match_score}%  ·  ${shareData!.time_minutes}分钟  ·  难度 ${shareData!.difficulty}`,
      48,
      448,
    )

    // 核心秘诀
    let y = 512
    roundRect(48, y - 36, W - 96, 150, 20, SOFT)
    ctx.fillStyle = INK
    ctx.font = '900 28px sans-serif'
    ctx.fillText('✨ 核心秘诀', 72, y - 6)
    ctx.fillStyle = BROWN
    ctx.font = '700 28px sans-serif'
    const secret = shareData!.core_secret || '按步骤操作，注意火候是关键'
    y = wrapText(secret, 72, y + 34, W - 144, 40, 2)

    // 步骤行
    y += 36
    ctx.fillStyle = BROWN
    ctx.font = '700 28px sans-serif'
    ctx.fillText(`🍳 ${shareData!.steps_count} 步搞定，新手零翻车`, 48, y + 20)

    // 底部：品牌 + 小程序码
    const qrSize = 150
    const qrX = W - 48 - qrSize
    const qrY = H - 60 - qrSize
    roundRect(qrX, qrY, qrSize, qrSize, 16, '#FFFFFF')
    if (shareData!.qrcode_base64) {
      const img = await loadImage(shareData!.qrcode_base64)
      if (img.width || img.height) ctx.drawImage(img, qrX + 6, qrY + 6, qrSize - 12, qrSize - 12)
    } else {
      ctx.fillStyle = BROWN
      ctx.font = '800 22px sans-serif'
      ctx.fillText('ChefPal', qrX + 30, qrY + 70)
      ctx.fillText('小程序码', qrX + 22, qrY + 104)
    }

    // 品牌文字（左侧）
    ctx.fillStyle = INK
    ctx.font = '900 32px sans-serif'
    ctx.fillText('ChefPal', 48, H - 90)
    ctx.fillStyle = BROWN
    ctx.font = '600 24px sans-serif'
    ctx.fillText('口袋 AI 厨师 · 从食材到餐桌', 48, H - 52)

    // 导出临时文件
    const tmp = await new Promise<string | null>((resolve) => {
      Taro.canvasToTempFilePath({
        canvas,
        x: 0,
        y: 0,
        width: W * dpr,
        height: H * dpr,
        destWidth: W * dpr,
        destHeight: H * dpr,
        fileType: 'png',
        success: (r) => resolve(r.tempFilePath),
        fail: () => resolve(null),
      })
    })
    if (tmp) setCardImg(tmp)
  }

  const saveToAlbum = () => {
    if (!cardImg) return
    Taro.saveImageToPhotosAlbum({
      filePath: cardImg,
      success: () => Taro.showToast({ title: '已保存到相册', icon: 'none' }),
      fail: (e: any) => {
        if (String(e.errMsg).includes('auth')) {
          Taro.showModal({
            title: '需要相册权限',
            content: '请授权保存到相册后重试',
            confirmText: '去授权',
            success: (r) => {
              if (r.confirm) Taro.openSetting()
            },
          })
        } else {
          Taro.showToast({ title: '保存失败，请重试', icon: 'none' })
        }
      },
    })
  }

  if (empty) {
    return (
      <View className='page-content share-card-page'>
        <NavBar title='生成分享卡片' showBack />
        <EmptyState
          icon='🍜'
          title='还没有可分享的菜谱'
          desc='去「厨房」生成菜谱，或在菜谱详情页点「分享」进入本页'
          btnText='去厨房生成'
          onBtn={() => Taro.switchTab({ url: '/pages/kitchen/index' })}
        />
      </View>
    )
  }

  return (
    <View className='page-content share-card-page'>
      <NavBar title='生成分享卡片' showBack />
      <Canvas type='2d' id='shareCanvas' className='share-canvas' style={{ position: 'absolute', left: '-9999px' }} />

      {cardImg ? (
        <Image className='share-preview' src={cardImg} mode='widthFix' />
      ) : (
        <View className='share-loading'><Text>卡片生成中…</Text></View>
      )}

      <Text className='share-hint'>🎴 长按卡片保存，分享给好友或朋友圈</Text>

      <View className='actbar'>
        <View className='btn btn--white btn--sm' onClick={saveToAlbum}><Text>保存到相册</Text></View>
        <Button className='share-btn' openType='share'><Text>分享给好友</Text></Button>
      </View>
    </View>
  )
}
