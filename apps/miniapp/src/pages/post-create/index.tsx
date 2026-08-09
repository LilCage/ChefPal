/**
 * 屏1 · 作品发布（原型 03）
 * 图片上传网格(≤3张) + 心得(200字) + 关联收藏菜谱 + 话题选择 → 发布
 */
import { Button, Image, Text, Textarea, View } from '@tarojs/components'
import Taro from '@tarojs/taro'
import { useRef, useState } from 'react'
import NavBar from '../../components/NavBar'
import { createPost, fetchFavorites, TOPICS } from '../../services/api'
import './index.scss'

const MAX_IMAGES = 3
const MAX_CONTENT = 200

function readAsBase64(filePath: string): Promise<string> {
  return new Promise((resolve, reject) => {
    Taro.getFileSystemManager().readFile({
      filePath,
      encoding: 'base64',
      success: (res) => resolve(res.data as string),
      fail: reject,
    })
  })
}

interface LinkedRecipe {
  id: string
  title: string
  match_score: number
}

export default function PostCreate() {
  const [images, setImages] = useState<string[]>([]) // data URL（本地预览 + 上传）
  const [content, setContent] = useState('')
  const [topic, setTopic] = useState<string | null>(null)
  const [recipe, setRecipe] = useState<LinkedRecipe | null>(null)
  const [publishing, setPublishing] = useState(false)
  const favsRef = useRef<LinkedRecipe[]>([])

  const pickImages = async () => {
    const remain = MAX_IMAGES - images.length
    if (remain <= 0) {
      Taro.showToast({ title: `最多上传 ${MAX_IMAGES} 张图片`, icon: 'none' })
      return
    }
    try {
      const res = await Taro.chooseMedia({
        count: remain,
        mediaType: ['image'],
        sourceType: ['album', 'camera'],
        sizeType: ['compressed'],
      })
      const chosen = res.tempFiles as { tempFilePath: string }[]
      const dataUrls: string[] = []
      for (const f of chosen) {
        const b64 = await readAsBase64(f.tempFilePath)
        const ext = (f.tempFilePath.split('.').pop() || 'jpeg').toLowerCase()
        const mime = ext === 'png' ? 'image/png' : ext === 'webp' ? 'image/webp' : 'image/jpeg'
        dataUrls.push(`data:${mime};base64,${b64}`)
      }
      setImages((prev) => [...prev, ...dataUrls].slice(0, MAX_IMAGES))
    } catch {
      /* 用户取消选择 */
    }
  }

  const removeImage = (idx: number) => {
    setImages((prev) => prev.filter((_, i) => i !== idx))
  }

  const pickRecipe = async () => {
    try {
      if (favsRef.current.length === 0) {
        const favs = await fetchFavorites('recipe')
        favsRef.current = favs
          .filter((f) => f.content)
          .map((f) => ({
            id: f.content_id,
            title: f.content.title,
            match_score: f.content.match_score,
          }))
      }
      const list = favsRef.current
      if (list.length === 0) {
        Taro.showToast({ title: '还没有收藏菜谱，先去厨房生成吧', icon: 'none' })
        return
      }
      const itemList = list.slice(0, 6).map((r) => r.title)
      const res = await Taro.showActionSheet({ itemList, itemColor: '#241A12' })
      const picked = list[res.tapIndex]
      if (picked) setRecipe(picked)
    } catch {
      /* 用户取消 */
    }
  }

  const publish = async () => {
    if (publishing) return
    if (!content.trim() && images.length === 0) {
      Taro.showToast({ title: '图文至少填写一项', icon: 'none' })
      return
    }
    setPublishing(true)
    try {
      await createPost({
        content: content.trim(),
        images,
        recipe_id: recipe?.id,
        topic: topic || undefined,
      })
      Taro.showToast({ title: '发布成功！', icon: 'none' })
      setTimeout(() => Taro.navigateBack(), 600)
    } catch (e: any) {
      Taro.showToast({ title: e.message || '发布失败，请重试', icon: 'none' })
    } finally {
      setPublishing(false)
    }
  }

  const cells: (string | null)[] = [...images]
  while (cells.length < MAX_IMAGES) cells.push(null)

  return (
    <View className='page-content post-create'>
      <NavBar title='发布作品' showBack right={<Text className='txtbtn' onClick={publish}>发布</Text>} />

      <View className='upload-grid' style={{ marginTop: '28px' }}>
        {cells.map((img, i) =>
          img ? (
            <View key={i} className='upload-cell'>
              <Image className='cell-img' src={img} mode='aspectFill' />
              <View className='cell-del' onClick={() => removeImage(i)}>×</View>
            </View>
          ) : (
            <View key={i} className={`upload-cell add ${i === 0 && images.length === 0 ? '' : 'empty'}`} onClick={pickImages}>
              <View className='ic ic-plus ic-lg' />
              <Text>{i === 0 ? '添加' : ''}</Text>
            </View>
          ),
        )}
      </View>

      <View className='textarea-wrap'>
        <Textarea
          className='p-input'
          value={content}
          maxlength={MAX_CONTENT}
          placeholder='分享你的下厨心得～（选填）'
          placeholderClass='p-input-ph'
          onInput={(e) => setContent(e.detail.value)}
        />
        <View className='textarea-foot'>
          <Text className='note'>{content.length} / {MAX_CONTENT}</Text>
        </View>
      </View>

      <View className='link-card' onClick={pickRecipe}>
        <View className='lc-ic'><Text>{recipe ? '🍽' : '✨'}</Text></View>
        <View className='lc-body'>
          <Text className='lc-title'>{recipe ? recipe.title : '关联 AI 菜谱（可选）'}</Text>
          <Text className='lc-sub'>
            {recipe ? `关联的 AI 菜谱 · 匹配 ${recipe.match_score}%` : '从我的收藏菜谱中选择'}
          </Text>
        </View>
        <View className='ic ic-chev-r ic-sm lc-go' />
      </View>

      <View className='section topic-sec'>
        <View className='sec-title'>🏷 添加话题</View>
        <View className='chips'>
          {TOPICS.map((t) => (
            <View key={t} className={`chip ${topic === t ? 'chip--on' : ''}`} onClick={() => setTopic(topic === t ? null : t)}>
              <Text>{t}</Text>
            </View>
          ))}
        </View>
      </View>

      <View className='publish-bar'>
        <Button className='btn btn--red btn--block publish-btn' onClick={publish}>
          <Text>{publishing ? '发布中…' : '🛡 安全发布'}</Text>
        </Button>
        <Text className='note publish-note'>发布前将进行内容安全检测</Text>
      </View>
    </View>
  )
}
