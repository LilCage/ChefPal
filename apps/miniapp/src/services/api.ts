/**
 * 后端 API 服务层：对齐 FastAPI OpenAPI 契约。
 * 所有方法返回解析后的 data（统一响应体的 data 字段）。
 */
import Taro from '@tarojs/taro'
import { API_BASE_URL } from '../config/env'
import { http } from '../utils/request'
import { useAuthStore, type User } from '../stores/auth'

/* ---------- 认证 ---------- */
export const login = (code: string) =>
  http.post<{ token: string; user: User }>('/auth/login', { code }, false)

/* ---------- 用户 ---------- */
export const fetchMe = () => http.get<User>('/users/me')
/** 标记已看过新用户引导（服务端随账号存储） */
export const markOnboarded = () => http.post<{ onboarded: boolean }>('/users/me/onboarded')
export const updatePreferences = (prefs: Record<string, any>) =>
  http.put<User>('/users/me/preferences', prefs)
export const updateProfile = (data: { nickname?: string; avatar_url?: string }) =>
  http.put<User>('/users/me/profile', data)
export const deleteAccount = () => http.del('/users/me')

/* ---------- 小伴口味记忆（EXT-13.1/13.2） ---------- */
export interface TasteMemory {
  preferred_styles: string[]
  preferred_topics: string[]
  recent_qa_keywords: string[]
  total_signals: number
}
export const fetchTasteMemory = () => http.get<TasteMemory>('/users/me/taste-memory')
export const clearTasteMemory = () => http.del<{ deleted: number }>('/users/me/taste-memory')

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
export interface QARecommendation {
  name: string
  core_secret: string
  time_minutes: number
  ingredients: string[]
  kb_id?: string | null
}
export interface QARecord {
  id: string
  question: string
  answer: {
    core_secret: string
    dish_name?: string
    ingredients: string[]
    steps: string[]
    prep_steps?: string[]
    cook_steps?: string[]
    avoid_pitfalls: string[]
    sources?: string[]
    recommendations?: QARecommendation[]
    /** 追问提示（秘诀/技巧类：如"需要我帮你查找「蒸蛋」的菜谱吗？"） */
    followup?: string
    /** 链接/文档解析标记（前端渲染来源横幅用） */
    parse_type?: 'web' | 'video' | 'doc'
    parse_source?: string
  }
  sources: string[] | null
  kb_hit?: boolean
  kb_id?: string | null
  session_id?: string | null
  created_at: string | null
}

/* ---------- 菜谱知识库（RAG：HowToCook 种子 + AI 沉淀） ---------- */
export interface KBEntry {
  id: string
  kind: 'recipe' | 'tip'
  title: string
  summary: string
  content: string
  ingredients: string[]
  steps: string[]
  prep_steps: string[]
  cook_steps: string[]
  tips: string[]
  images: string[] // HowToCook 成品图相对路径（/kb-data/ 下）
  time_minutes: number
  difficulty: string
  style: string
  category: string
  source_type: string
  source_id: string
  hit_count: number
  similarity: number | null
  created_at: string | null
}
/** 按菜名查知识库菜谱（多菜推荐点详情用）；未收录抛 404 */
export const fetchKBRecipeByTitle = (title: string) =>
  http.get<KBEntry>(`/kb/recipes?q=${encodeURIComponent(title)}`)
export const fetchKBEntry = (id: string) => http.get<KBEntry>(`/kb/${id}`)
/** 菜名未收录时 AI 现生成完整做法并入库；force=true 用于已收录但无完整步骤的条目标签补全 */
export const generateKBRecipe = (title: string, force = false) =>
  http.post<KBEntry & { from_kb: boolean }>('/kb/generate', { title, force })

export const askQA = (question: string, session_id?: string | null) =>
  http.post<QARecord>('/qa/ask', { question, session_id })

/* 流式问答：SSE 打字机。onDelta 逐字回调（过渡语先行），onDone 收到完整结构化数据，onError 出错。 */
export function askQAStream(
  question: string,
  handlers: {
    onDelta: (text: string) => void
    onDone: (data: QARecord) => void
    onError: (msg: string) => void
    /** 服务端重试前清掉已流出的半截回答（避免残字叠加） */
    onReset?: () => void
  },
  session_id?: string | null,
): () => void {
  const token = useAuthStore.getState().token

  // 持久 TextDecoder（stream:true）：跨网络 chunk 保留不完整 UTF-8 字节序列。
  // 此前每次 new TextDecoder 独立解码，中文等多字节字符被分包切开时产生替换符 �，
  // 破坏 SSE data 行导致 done/error 事件 JSON.parse 失败被丢弃 —— 首页问答偶发"不回答/卡死"的根因。
  let utf8Decoder: any = null
  try {
    utf8Decoder = new (globalThis as any).TextDecoder('utf-8', { stream: true })
  } catch {
    utf8Decoder = null
  }

  // 终态守卫：done/error 只触发一次；流结束仍无终态（服务端崩溃/断连）→ 兜底报错，
  // 保证上层 sending 一定复位、输入坞不冻结。
  let finished = false
  const finish = (fn: () => void) => {
    if (finished) return
    finished = true
    fn()
  }

  const requestTask = Taro.request({
    url: `${API_BASE_URL}/qa/stream`,
    method: 'POST',
    data: { question, session_id },
    header: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    enableChunked: true,
    responseType: 'arraybuffer',
    // 请求完成但未收到终态事件（正常流程 done/error 已置 finished，这里是兜底）
    success: () => finish(() => handlers.onError('连接中断，请稍后重试')),
    fail: (err) => finish(() => handlers.onError(err.errMsg || '连接失败')),
  })

  let buffer = ''
  const decode = (buf: ArrayBuffer): string => {
    if (utf8Decoder) {
      try {
        return utf8Decoder.decode(buf)
      } catch {
        /* 落到兜底 */
      }
    }
    // 基础库不支持 TextDecoder 时：base64 + escape/unescape 经典解码（无流状态，尽力而为）
    const b64 = Taro.arrayBufferToBase64(buf)
    try {
      return decodeURIComponent(escape(atob(b64)))
    } catch {
      return ''
    }
  }

  requestTask.onChunkReceived((res: any) => {
    const chunk = decode(res.data)
    buffer += chunk
    // 按 SSE 行（data: ...\n\n）切分完整事件
    let idx: number
    while ((idx = buffer.indexOf('\n\n')) !== -1) {
      const rawEvent = buffer.slice(0, idx)
      buffer = buffer.slice(idx + 2)
      for (const line of rawEvent.split('\n')) {
        const t = line.trim()
        if (!t.startsWith('data:')) continue
        const payload = t.slice(5).trim()
        let ev: any
        try {
          ev = JSON.parse(payload)
        } catch {
          continue
        }
        if (ev.type === 'delta') handlers.onDelta(ev.text || '')
        else if (ev.type === 'reset') handlers.onReset?.()
        else if (ev.type === 'done') {
          finish(() => handlers.onDone(ev.data))
        } else if (ev.type === 'error') {
          finish(() => handlers.onError(ev.message || '生成失败'))
          requestTask.abort()
        }
      }
    }
  })

  return () => requestTask.abort()
}
export const fetchQAHistory = () => http.get<QARecord[]>('/qa/history')
export const deleteQARecord = (id: string) => http.del(`/qa/${id}`)
/** 对话会话：按时间升序返回该会话全部消息（对话页恢复历史用） */
export const fetchQASession = (sessionId: string) => http.get<QARecord[]>(`/qa/session/${sessionId}`)

/** 历史会话摘要（按最后活动时间降序，最多 limit 个） */
export interface QASessionSummary {
  session_id: string
  title: string
  last_question: string
  msg_count: number
  last_at: string | null
}
export const fetchQASessions = (limit = 20) =>
  http.get<QASessionSummary[]>(`/qa/sessions?limit=${limit}`)
/** 删除整个会话（仅限本人） */
export const deleteQASession = (sessionId: string) => http.del(`/qa/session/${sessionId}`)

/* ---------- 链接/文档解析（对话内：粘贴链接自动解析 / 📎 上传文档） ---------- */
export const parseUrl = (url: string, session_id?: string | null) =>
  http.post<QARecord>('/parse/url', { url, session_id })

/** 上传 PDF/Word 文档 → 解析成结构化菜谱 */
export const parseDocument = (filePath: string, session_id?: string | null) =>
  new Promise<QARecord>((resolve, reject) => {
    const token = useAuthStore.getState().token
    Taro.uploadFile({
      url: `${API_BASE_URL}/parse/document`,
      filePath,
      name: 'file',
      formData: session_id ? { session_id } : {},
      header: token ? { Authorization: `Bearer ${token}` } : {},
      success: (res) => {
        try {
          const body = JSON.parse(res.data)
          if (body.code === 0) resolve(body.data)
          else reject(new Error(body.message || '解析失败'))
        } catch {
          reject(new Error('解析结果解析失败'))
        }
      },
      fail: (err) => reject(new Error(err.errMsg || '文档上传失败')),
    })
  })

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
  style: string
  steps: RecipeStep[]
  tips: string[]
  missing_seasonings: string[]
  created_at: string | null
}

export const generateRecipes = (ingredients: string[], prefs?: Record<string, any>) =>
  http.post<Recipe[]>('/recipes/generate', { ingredients, prefs })
export const fetchRecipe = (id: string) => http.get<Recipe>(`/recipes/${id}`)

/* ---------- 个人菜谱创作（EXT-4.1/4.2） ---------- */
export interface MyRecipeIngredient {
  name: string
  note?: string
}
export interface MyRecipeStep {
  title: string
  detail: string
}
export interface MyRecipeSeasoning {
  name: string
  amount?: string
}
export interface MyRecipe {
  id: string
  title: string
  cover_image: string | null
  servings: number
  ingredients: MyRecipeIngredient[]
  prep_steps: MyRecipeStep[]
  cook_steps: MyRecipeStep[]
  seasonings: MyRecipeSeasoning[]
  tips: string[]
  style: string
  time_minutes: number
  difficulty: string
  created_at: string | null
  updated_at: string | null
}
export interface PublishResult {
  post_id: string
  my_recipe_id: string
  title: string
  content: string
  images: string[]
  topic: string | null
}

export const createMyRecipe = (data: Partial<MyRecipe> & { title: string }) =>
  http.post<MyRecipe>('/my-recipes', data)
export const fetchMyRecipes = () => http.get<MyRecipe[]>('/my-recipes')
export const fetchMyRecipe = (id: string) => http.get<MyRecipe>(`/my-recipes/${id}`)
export const updateMyRecipe = (id: string, data: Partial<MyRecipe>) =>
  http.put<MyRecipe>(`/my-recipes/${id}`, data)
export const deleteMyRecipe = (id: string) => http.del(`/my-recipes/${id}`)
export const publishMyRecipe = (
  id: string,
  data: { content?: string; images?: string[]; topic?: string },
) => http.post<PublishResult>(`/my-recipes/${id}/publish`, data)

/* ---------- 菜谱DNA进化树 ---------- */
export interface RecipeVersion {
  id: string | null
  recipe_id: string
  parent_id: string | null
  version_label: string
  title: string
  changes: string
  is_root: boolean
  created_at: string | null
}
export interface RecipeTreeData {
  recipe_id: string
  title: string
  versions: RecipeVersion[]
}
export const fetchRecipeTree = (ref: string) => http.get<RecipeTreeData>(`/recipes/${ref}/tree`)
export const forkRecipe = (ref: string, changes: string) =>
  http.post<RecipeVersion>(`/recipes/${ref}/fork`, { changes })

/* ---------- 收藏（qa=问答 / recipe=自建菜谱 / kb=知识库菜谱） ---------- */
export interface FavoriteItem {
  favorite_id: string
  content_type: 'qa' | 'recipe' | 'kb'
  content_id: string
  content: any
  created_at: string | null
}

export const addFavorite = (content_type: 'qa' | 'recipe' | 'kb', content_id: string) =>
  http.post<FavoriteItem>('/favorites', { content_type, content_id })
export const removeFavorite = (content_type: 'qa' | 'recipe' | 'kb', content_id: string) =>
  http.del<FavoriteItem>(`/favorites?content_type=${content_type}&content_id=${content_id}`)
export const fetchFavorites = (type?: 'qa' | 'recipe' | 'kb') =>
  http.get<FavoriteItem[]>(`/favorites${type ? `?type=${type}` : ''}`)
/** 查询是否已收藏（详情页星标选中态） */
export const fetchFavoriteStatus = (content_type: 'qa' | 'recipe' | 'kb', content_id: string) =>
  http.get<{ favorited: boolean }>(
    `/favorites/status?content_type=${content_type}&content_id=${content_id}`,
  )

/* ---------- 时令食材日历 ---------- */
export interface SeasonalItem {
  name: string
  emoji: string
  level: '应季' | '正当时'
  note: string
}
export interface SeasonalPairing {
  ingredients: string[]
  dish: string
  note: string
}
export interface SeasonalData {
  month: number
  label: string
  items: SeasonalItem[]
  pairing: SeasonalPairing
}
export const fetchSeasonal = (month?: number) =>
  http.get<SeasonalData>(`/seasonal${month ? `?month=${month}` : ''}`)

/* ---------- 家庭口味投票 ---------- */
export interface VoteOption {
  name: string
  count: number
}
export interface VoteDetail {
  id: string
  status: 'active' | 'closed'
  ingredients: string[]
  options: VoteOption[]
  my_choice: number | null
  total_count: number
  created_at: string | null
}
export interface VoteShareCard {
  title: string
  options: string[]
  options_count: number
  qrcode_base64: string | null
}
export const generateVote = (ingredients: string[]) =>
  http.post<VoteDetail>('/votes/generate', { ingredients })
export const fetchVote = (id: string) => http.get<VoteDetail>(`/votes/${id}`)
export const castVote = (id: string, optionIndex: number) =>
  http.post<VoteDetail>(`/votes/${id}/vote`, { option_index: optionIndex })

/* ---------- 烹饪挑战 ---------- */
export interface Challenge {
  id: string
  title: string
  budget: number
  description: string | null
  status: 'active' | 'finished'
  participant_count: number
  created_at: string | null
}
export interface ChallengeList {
  items: Challenge[]
}
export interface JoinResult {
  id: string
  title: string
  budget: number
  status: 'active' | 'finished'
  participant_count: number
  joined: boolean
}
export interface LeaderboardItem {
  user_id: string
  nickname: string
  spend: number
  meal_count: number
  is_me: boolean
}
export const createChallenge = (data: { title: string; budget: number; description?: string }) =>
  http.post<Challenge>('/challenges', data)
export const fetchChallenges = () => http.get<ChallengeList>('/challenges')
export const joinChallenge = (id: string) => http.post<JoinResult>(`/challenges/${id}/join`)
export const updateChallengeProgress = (id: string, spend: number, mealCount = 0) =>
  http.put<{ spend: number; meal_count: number }>(`/challenges/${id}/progress`, { spend, meal_count: mealCount })
export const fetchLeaderboard = (id: string) =>
  http.get<{ items: LeaderboardItem[] }>(`/challenges/${id}/leaderboard`)

/* ---------- 多智能体协作 ---------- */
export interface NutritionistData {
  calories_kcal: number
  protein_g: number
  advice: string
  avoided_allergens: string[]
}
export interface ChefData {
  dish_name: string
  technique: string
  plating: string
}
export interface ShopperItem {
  name: string
  quantity: string
}
export interface ShopperCategory {
  name: string
  items: ShopperItem[]
}
export interface ShopperData {
  categories: ShopperCategory[]
  tips: string
}
export interface CollaborateData {
  nutritionist: NutritionistData
  chef: ChefData
  shopper: ShopperData
}
export const collaborateAgents = (ingredients: string[], prefs?: Record<string, any>) =>
  http.post<CollaborateData>('/agents/collaborate', { ingredients, prefs })

/* ---------- 关注系统 ---------- */
export interface UserProfile {
  id: string
  nickname: string
  avatar_url: string | null
  follower_count: number
  following_count: number
  post_count: number
  is_following: boolean
}

export interface UserListItem {
  id: string
  nickname: string
  avatar_url: string | null
  follower_count: number
  following_count: number
  is_following: boolean
}

export interface FollowResponse {
  following: boolean
  follower_count: number
  following_count: number
}

export interface UserListResult {
  items: UserListItem[]
  total: number
  page: number
  size: number
  has_more: boolean
}

export const fetchUserProfile = (id: string) => http.get<UserProfile>(`/users/${id}`)
export const followUser = (id: string) => http.post<FollowResponse>(`/users/${id}/follow`)
export const unfollowUser = (id: string) => http.del<FollowResponse>(`/users/${id}/follow`)
export const fetchFollowers = (id: string, page = 1, size = 20) =>
  http.get<UserListResult>(`/users/${id}/followers?page=${page}&size=${size}`)
export const fetchFollowing = (id: string, page = 1, size = 20) =>
  http.get<UserListResult>(`/users/${id}/following?page=${page}&size=${size}`)
export const fetchFollowFeed = (page = 1, size = 10) =>
  http.get<PostList>(`/follows/feed?page=${page}&size=${size}`)

/* ---------- 话题广场 ---------- */
export interface TopicItem {
  topic: string
  count: number
}
export const fetchTopics = () => http.get<TopicItem[]>('/posts/topics')

/* ---------- 社区作品 ---------- */
export interface PostAuthor {
  id: string
  nickname: string
  avatar_url: string | null
  is_following?: boolean
}

export interface Post {
  id: string
  content: string
  images: string[]
  topic: string | null
  like_count: number
  comment_count: number
  is_liked: boolean
  recipe_id: string | null
  my_recipe_id: string | null
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
export const fetchPosts = (page = 1, size = 10, topic?: string, userId?: string) =>
  http.get<PostList>(
    `/posts?page=${page}&size=${size}${topic ? `&topic=${encodeURIComponent(topic)}` : ''}${userId ? `&user_id=${userId}` : ''}`,
  )
export const fetchPost = (id: string) => http.get<Post>(`/posts/${id}`)
export const fetchMyPosts = () => http.get<Post[]>('/posts/mine')
export const likePost = (id: string) =>
  http.post<{ liked: boolean; like_count: number }>(`/posts/${id}/like`)
export const unlikePost = (id: string) =>
  http.del<{ liked: boolean; like_count: number }>(`/posts/${id}/like`)
export const fetchPostShareCard = (id: string) =>
  http.get<PostShareCardData>(`/posts/${id}/share-card`)

/* ---------- 评论 ---------- */
export interface CommentAuthor {
  id: string
  nickname: string
  avatar_url: string | null
}

export interface Comment {
  id: string
  content: string
  like_count: number
  is_liked: boolean
  is_owner: boolean
  created_at: string | null
  author: CommentAuthor
}

export interface CommentList {
  items: Comment[]
  total: number
  page: number
  size: number
  has_more: boolean
}

export const fetchComments = (postId: string, page = 1, size = 20) =>
  http.get<CommentList>(`/posts/${postId}/comments?page=${page}&size=${size}`)
export const createComment = (postId: string, content: string) =>
  http.post<Comment>(`/posts/${postId}/comments`, { content })
export const likeComment = (id: string) =>
  http.post<{ liked: boolean; like_count: number }>(`/comments/${id}/like`)
export const unlikeComment = (id: string) =>
  http.del<{ liked: boolean; like_count: number }>(`/comments/${id}/like`)
export const deleteComment = (id: string) => http.del(`/comments/${id}`)

/* ---------- 膳食规划 ---------- */
export interface PlanDish {
  name: string
}
export interface PlanMeal {
  name: string
  total_kcal: number
  dishes: PlanDish[]
}
export interface PlanDay {
  day_label: string
  meals: PlanMeal[]
  total_kcal: number
  protein_g: number
  fat_g: number
  carbs_g: number
}
export interface MealPlanData {
  days: PlanDay[]
}
export interface MealPlan {
  id: string
  data: MealPlanData
  created_at: string | null
}

export const generatePlan = (prefs?: Record<string, any>, days = 3) =>
  http.post<MealPlan>('/plans/generate', { prefs, days })
export const fetchLatestPlan = () => http.get<MealPlan>('/plans/latest')

/* ---------- 拍照识食材 ---------- */
export const recognizeIngredients = (imageBase64: string) =>
  http.post<{ ingredients: string[] }>('/vision/recognize', { image_base64: imageBase64 })

/* ---------- 黑暗料理拯救 ---------- */
export interface RescueIssue {
  title: string
  detail: string
  fix: string
}
export const diagnoseDish = (imageBase64: string) =>
  http.post<{ issues: RescueIssue[] }>('/rescue/diagnose', { image_base64: imageBase64 })

/* ---------- 购物清单 ---------- */
export interface ShopItem {
  item_id: string
  name: string
  quantity: string
  checked: boolean
}
export interface ShopCategory {
  name: string
  items: ShopItem[]
}
export interface ShoppingListData {
  categories: ShopCategory[]
}
export interface ShoppingList {
  id: string
  data: ShoppingListData
  created_at: string | null
}

export const generateShoppingList = (mealPlanId?: string) =>
  http.post<ShoppingList>('/shopping-list/generate', { meal_plan_id: mealPlanId })
export const fetchLatestShoppingList = () => http.get<ShoppingList>('/shopping-list/latest')
export const toggleShopItem = (listId: string, itemId: string, checked: boolean) =>
  http.put<{ item_id: string; checked: boolean }>(
    `/shopping-list/${listId}/items/${itemId}/checked`,
    { checked },
  )

/* ---------- 冰箱管家（食材过期预警） ---------- */
export interface FridgeItem {
  id: string
  name: string
  emoji: string
  added_at: string | null
  best_before_days: number
  days_stored: number
  days_left: number
  status: 'now' | 'warn' | 'ok'
}
export interface FridgeList {
  items: FridgeItem[]
  expiring_count: number
}
export interface FridgeSuggestion {
  ingredients: string[]
  dish: string
  time_minutes: number
  match_score: number
}
export interface FridgeAdvice {
  suggestions: FridgeSuggestion[]
  note: string
}
export const fetchFridge = () => http.get<FridgeList>('/fridge')
export const addFridgeItem = (data: { name: string; emoji?: string; best_before_days?: number }) =>
  http.post<FridgeItem>('/fridge', data)
export const removeFridgeItem = (id: string) =>
  http.del<{ id: string; removed: boolean }>(`/fridge/${id}`)
export const fetchFridgeAdvice = () => http.post<FridgeAdvice>('/fridge/advice')

/* ---------- 语音烹饪助手（EXT-14.1） ---------- */
export interface CookAnswer {
  answer: string
  current_step: number
  title: string
}
export const askCookAssistant = (recipeId: string, question: string) =>
  http.post<CookAnswer>('/cook-assistant/query', { recipe_id: recipeId, question })

/* ---------- 语音输入（后端百炼 ASR） ---------- */
export const transcribeVoice = (filePath: string) =>
  new Promise<string>((resolve, reject) => {
    const token = useAuthStore.getState().token
    Taro.uploadFile({
      url: `${API_BASE_URL}/voice/transcribe`,
      filePath,
      name: 'file',
      header: token ? { Authorization: `Bearer ${token}` } : {},
      success: (res) => {
        try {
          const body = JSON.parse(res.data)
          if (body.code === 0) resolve(body.data.text)
          else reject(new Error(body.message || '识别失败'))
        } catch {
          reject(new Error('识别结果解析失败'))
        }
      },
      fail: (err) => reject(new Error(err.errMsg || '音频上传失败')),
    })
  })
