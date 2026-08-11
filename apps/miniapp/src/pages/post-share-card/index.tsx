/**
 * 屏6 · 作品分享卡（原型 03）：canvas 2d 绘制 → 保存相册 / 转发
 * 图片：优先作品首图（网络图经 getImageInfo 转本地临时路径），失败降级 emoji 渐变底
 */
import { Button, Canvas, Image, Text, View } from '@tarojs/components'
import Taro, { useLoad, useShareAppMessage } from '@tarojs/taro'
import { useEffect, useState } from 'react'
import NavBar from '../../components/NavBar'
import { fetchPostShareCard, type PostShareCardData } from '../../services/api'
import './index.scss'

const CANVAS_W = 620
const CANVAS_H = 980
const INK = '#241A12'
const BROWN = '#4A2E1D'
const CREAM = '#FFF7EC'
const SOFT = '#F6E3C3'
const RED = '#E8482A'
const GOLD = '#F0A73E'
const GRAY = '#8A6F5C'

export default function PostShareCard() {
  const [data, setData] = useState<PostShareCardData | null>(null)
  const [cardImg, setCardImg] = useState('')
  const [failed, setFailed] = useState(false)

  useShareAppMessage(() => ({
    title: data ? `ChefPal · ${data.nickname} 的跟做作品` : 'ChefPal 口袋厨师',
    path: data ? `/pages/post-detail/index?id=${data.id}` : '/pages/index/index',
    imageUrl: cardImg || undefined,
  }))

  useLoad((params) => {
    const id = (params as any).id as string
    if (id) init(id)
  })

  const init = async (id: string) => {
    try {
      const d = await fetchPostShareCard(id)
      setData(d)
    } catch (e: any) {
      Taro.showToast({ title: e.message || '加载失败', icon: 'none' })
      setFailed(true)
    }
  }

  useEffect(() => {
    if (data) draw()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data])

  const draw = async () => {
    const res = await new Promise<any>((resolve) => {
      Taro.createSelectorQuery()
        .select('#postShareCanvas')
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
      if (fill) { ctx.fillStyle = fill; ctx.fill() }
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

    const loadImage = (src: string) =>
      new Promise<any>((resolve) => {
        const img = canvas.createImage()
        img.onload = () => resolve(img)
        img.onerror = () => resolve(null)
        img.src = src
      })

    // 作品首图：网络/临时路径先转本地，失败降级
    let heroImg: any = null
    if (data!.image) {
      try {
        const info = await Taro.getImageInfo({ src: data!.image })
        heroImg = await loadImage(info.path)
      } catch {
        heroImg = null
      }
    }

    // 背景 + 外描边
    roundRect(0, 0, W, H, 36, CREAM)

    // 顶部 Hero：作品图 / 渐变 + emoji
    roundRect(20, 20, W - 40, 300, 28)
    if (heroImg && (heroImg.width || heroImg.height)) {
      ctx.save()
      // 裁剪圆角区域后绘制
      const clip = () => {
        ctx.beginPath()
        ctx.moveTo(48, 48)
        ctx.arcTo(W - 48, 48, W - 48, H - 48, 28)
        ctx.arcTo(W - 48, 320, 48, 320, 28)
        ctx.arcTo(48, 320, 48, 48, 28)
        ctx.closePath()
      }
      ctx.save()
      clip()
      ctx.clip()
      const ratio = heroImg.width / heroImg.height
      const iw = W - 40
      const ih = 300
      const sw = ih * ratio
      ctx.drawImage(heroImg, (iw - sw) / 2 + 20, 20, sw, ih)
      ctx.restore()
    } else {
      const grad = ctx.createLinearGradient(0, 20, 0, 320)
      grad.addColorStop(0, '#FFD9B0')
      grad.addColorStop(1, '#FF9D6B')
      roundRect(20, 20, W - 40, 300, 28, grad)
      ctx.font = '150px sans-serif'
      ctx.fillText('🍳', W / 2 - 75, 240)
    }
    // 品牌角标
    roundRect(40, 42, 170, 48, 12, RED)
    ctx.fillStyle = '#FFFFFF'
    ctx.font = '900 26px sans-serif'
    ctx.fillText('来自 ChefPal', 62, 75)

    // 标题（心得）
    ctx.fillStyle = INK
    ctx.font = '900 46px sans-serif'
    let y = 400
    y = wrapText(data!.content || '分享了下厨成果', 48, y, W - 96, 62, 3)

    // 元信息：点赞 + 话题
    y += 36
    const meta = `♥ ${data!.like_count}${data!.topic ? `  ·  ${data!.topic}` : ''}`
    roundRect(48, y - 30, Math.min(ctx.measureText(meta).width + 48, W - 96), 52, 14, SOFT)
    ctx.fillStyle = BROWN
    ctx.font = '800 28px sans-serif'
    ctx.fillText(meta, 72, y + 6)

    // 作者
    y += 70
    ctx.fillStyle = GRAY
    ctx.font = '600 26px sans-serif'
    ctx.fillText(`@ ${data!.nickname} · 今日分享`, 48, y)

    // 底部：品牌 + 小程序码
    const qrSize = 150
    const qrX = W - 48 - qrSize
    const qrY = H - 60 - qrSize
    roundRect(qrX, qrY, qrSize, qrSize, 16, '#FFFFFF')
    if (data!.qrcode_base64) {
      const img = await loadImage(data!.qrcode_base64)
      if (img && (img.width || img.height)) {
        ctx.drawImage(img, qrX + 6, qrY + 6, qrSize - 12, qrSize - 12)
      }
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
    ctx.fillText('口袋厨师 · 从食材到餐桌', 48, H - 52)

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
            success: (r) => { if (r.confirm) Taro.openSetting() },
          })
        } else {
          Taro.showToast({ title: '保存失败，请重试', icon: 'none' })
        }
      },
    })
  }

  if (failed) {
    return (
      <View className='page-content pshare'>
        <NavBar title='生成分享卡片' showBack />
        <View className='share-loading'><Text>作品不存在或已删除</Text></View>
      </View>
    )
  }

  return (
    <View className='page-content pshare'>
      <NavBar title='生成分享卡片' showBack />
      <Canvas type='2d' id='postShareCanvas' className='share-canvas' style={{ position: 'absolute', left: '-9999px' }} />

      {cardImg ? (
        <Image className='share-preview' src={cardImg} mode='widthFix' />
      ) : (
        <View className='share-loading'><Text>卡片生成中…</Text></View>
      )}

      <Text className='share-hint'>🎴 长按卡片保存，分享给好友或朋友圈</Text>

      <View className='actbar'>
        <View className='btn btn--white btn--sm' onClick={saveToAlbum}><Text>保存到相册</Text></View>
        <Button className='share-btn' openType='share'><Text>分享到微信</Text></Button>
      </View>
    </View>
  )
}
