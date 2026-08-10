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
  style: string
  steps: RecipeStep[]
  tips: string[]
  missing_seasonings: string[]
  created_at: string | null
}

export const generateRecipes = (ingredients: string[], prefs?: Record<string, any>) =>
  http.post<Recipe[]>('/recipes/generate', { ingredients, prefs })
export const fetchRecipe = (id: string) => http.get<Recipe>(`/recipes/${id}`)

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
