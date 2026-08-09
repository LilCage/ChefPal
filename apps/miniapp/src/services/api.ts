/**
 * 后端 API 服务层：对齐 FastAPI OpenAPI 契约。
 * 所有方法返回解析后的 data（统一响应体的 data 字段）。
 */
import { http } from '../utils/request'
import type { User } from '../stores/auth'

/* ---------- 认证 ---------- */
export const login = (code: string) =>
  http.post<{ token: string; user: User }>('/auth/login', { code }, false)

/* ---------- 用户 ---------- */
export const fetchMe = () => http.get<User>('/users/me')
export const updatePreferences = (prefs: Record<string, any>) =>
  http.put<User>('/users/me/preferences', prefs)
export const updateProfile = (data: { nickname?: string; avatar_url?: string }) =>
  http.put<User>('/users/me/profile', data)
export const deleteAccount = () => http.del('/users/me')

/* ---------- 分享卡片 ---------- */
export interface ShareCardData {
  title: string
  match_score: number
  time_minutes: number
  difficulty: string
  core_secret: string | null
  steps_count: number
  qrcode_base64: string | null
}
export const fetchShareCard = (id: string) => http.get<ShareCardData>(`/recipes/${id}/share-card`)

/* ---------- 问答 ---------- */
export interface QARecord {
  id: string
  question: string
  answer: {
    core_secret: string
    ingredients: string[]
    steps: string[]
    avoid_pitfalls: string[]
    sources?: string[]
  }
  sources: string[] | null
  created_at: string | null
}

export const askQA = (question: string) =>
  http.post<QARecord>('/qa/ask', { question })
export const fetchQAHistory = () => http.get<QARecord[]>('/qa/history')
export const deleteQARecord = (id: string) => http.del(`/qa/${id}`)

/* ---------- 菜谱 ---------- */
export interface RecipeStep {
  title: string
  detail: string
}

export interface Recipe {
  id: string
  title: string
  ingredients: { name: string; is_have?: boolean; is_missing?: boolean }[]
  match_score: number
  time_minutes: number
  difficulty: string
  steps: RecipeStep[]
  tips: string[]
  missing_seasonings: string[]
  created_at: string | null
}

export const generateRecipes = (ingredients: string[], prefs?: Record<string, any>) =>
  http.post<Recipe[]>('/recipes/generate', { ingredients, prefs })
export const fetchRecipe = (id: string) => http.get<Recipe>(`/recipes/${id}`)

/* ---------- 收藏 ---------- */
export interface FavoriteItem {
  favorite_id: string
  content_type: 'qa' | 'recipe'
  content_id: string
  content: any
  created_at: string | null
}

export const addFavorite = (content_type: 'qa' | 'recipe', content_id: string) =>
  http.post<FavoriteItem>('/favorites', { content_type, content_id })
export const removeFavorite = (content_type: 'qa' | 'recipe', content_id: string) =>
  http.del<FavoriteItem>(`/favorites?content_type=${content_type}&content_id=${content_id}`)
export const fetchFavorites = (type?: 'qa' | 'recipe') =>
  http.get<FavoriteItem[]>(`/favorites${type ? `?type=${type}` : ''}`)

/* ---------- 社区作品 ---------- */
export interface PostAuthor {
  id: string
  nickname: string
  avatar_url: string | null
}

export interface Post {
  id: string
  content: string
  images: string[]
  topic: string | null
  like_count: number
  is_liked: boolean
  recipe_id: string | null
  created_at: string | null
  author: PostAuthor
}

export interface PostList {
  items: Post[]
  total: number
  page: number
  size: number
  has_more: boolean
}

export interface PostShareCardData {
  id: string
  content: string
  image: string | null
  topic: string | null
  like_count: number
  nickname: string
  avatar_url: string | null
  qrcode_base64: string | null
}

export const TOPICS = ['#今日晚餐', '#减脂餐', '#一人食', '#跟做打卡', '#空气炸锅'] as const

export const createPost = (data: {
  content?: string
  images?: string[]
  recipe_id?: string
  topic?: string
}) => http.post<Post>('/posts', data)
export const fetchPosts = (page = 1, size = 10, topic?: string) =>
  http.get<PostList>(
    `/posts?page=${page}&size=${size}${topic ? `&topic=${encodeURIComponent(topic)}` : ''}`,
  )
export const fetchPost = (id: string) => http.get<Post>(`/posts/${id}`)
export const fetchMyPosts = () => http.get<Post[]>('/posts/mine')
export const likePost = (id: string) =>
  http.post<{ liked: boolean; like_count: number }>(`/posts/${id}/like`)
export const unlikePost = (id: string) =>
  http.del<{ liked: boolean; like_count: number }>(`/posts/${id}/like`)
export const fetchPostShareCard = (id: string) =>
  http.get<PostShareCardData>(`/posts/${id}/share-card`)
