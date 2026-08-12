import axios from 'axios'
import type {
  AgentChatRequest,
  AgentChatResponse,
  BindCFRequest,
  BindCFResponse,
  CodeExecutionResult,
  ColdStartResultResponse,
  DailyTaskItemUpdateResponse,
  DailyTaskTodayResponse,
  LearningPathGenerateRequest,
  LearningPathRead,
  MarkMasteredRequest,
  MarkMasteredResponse,
  ProfileUpdateRequest,
  RoadmapResponse,
  User,
  WrongBookListResponse,
  WrongBookRecommendation,
} from '../types'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1',
  headers: {
    'Content-Type': 'application/json',
  },
})

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('token')
      localStorage.removeItem('user')
      window.location.href = '/login'
    }
    return Promise.reject(error)
  }
)

export default api

export const authApi = {
  login: (email: string, password: string) => api.post('/auth/login', { email, password }),
  register: (email: string, username: string, password: string) =>
    api.post('/auth/register', { email, username, password }),
  getProfile: () => api.get<User>('/auth/me'),
  updateProfile: (data: ProfileUpdateRequest) => api.patch<User>('/auth/profile', data),
  bindCF: (data: BindCFRequest) => api.post<BindCFResponse>('/auth/bind-cf', data),
}

export const knowledgeApi = {
  getTree: () => api.get('/knowledge/'),
  getById: (id: string) => api.get(`/knowledge/${id}`),
  getLectures: (id: string) => api.get(`/knowledge/${id}/lectures`),
  getTemplates: (id: string) => api.get(`/knowledge/${id}/templates`),
  getPrerequisites: (id: string) => api.get(`/knowledge/${id}/prerequisites`),
}

export const problemsApi = {
  list: (params?: {
    page?: number
    page_size?: number
    difficulty?: 'easy' | 'medium' | 'hard'
    search?: string
    tag?: string
    source?: string
    sort?: 'newest' | 'oldest' | 'rating_asc' | 'rating_desc' | 'acceptance'
  }) => api.get('/problems/', { params }),
  getById: (id: string) => api.get(`/problems/${id}`),
  execute: (id: string, code: string, language: 'python' | 'cpp' | 'java') =>
    api.post<CodeExecutionResult>(`/problems/${id}/execute`, { code, language }),
}

export const agentApi = {
  chat: (req: AgentChatRequest) => api.post<AgentChatResponse>('/agent/chat', req),
}

export const progressApi = {
  getOverview: () => api.get('/progress/overview'),
  getActivity: (days = 30) => api.get('/progress/activity', { params: { days } }),
}

export const wrongbookApi = {
  list: (params?: { resolved?: boolean; page?: number; page_size?: number }) =>
    api.get<WrongBookListResponse>('/wrongbook', { params }),
  retry: (submissionId: string) => api.post(`/wrongbook/${submissionId}/retry`),
  recommendations: (submissionId: string) =>
    api.get<WrongBookRecommendation[]>(`/wrongbook/${submissionId}/recommendations`),
}

export const reviewApi = {
  getList: () => api.get('/review/list'),
  submitReview: (id: string, correct: boolean) => api.post(`/review/${id}/submit`, { correct }),
}

export const notificationApi = {
  list: () => api.get('/notifications'),
  markAsRead: (id: string) => api.post(`/notifications/${id}/read`),
  markAllAsRead: () => api.post('/notifications/read-all'),
  getRecommendations: () => api.get('/recommendations'),
}

export const submissionsApi = {
  list: (params: {
    user_id: string
    problem_id?: string
    verdict?: string
    page?: number
    page_size?: number
  }) => api.get('/submissions', { params }),
}

// ===== Task 10: Learning path & daily task =====

export const learningApi = {
  /** 生成（或重新生成）学习路径。 */
  generatePath: (req: LearningPathGenerateRequest) =>
    api.post<LearningPathRead>('/learning-paths/generate', req),
  /** 获取当前 active 学习路径。 */
  getCurrentPath: () => api.get<LearningPathRead>('/learning-paths/current'),
  /** 获取路线图聚合数据：知识树 + 用户学习状态。 */
  getRoadmap: () => api.get<RoadmapResponse>('/learning-paths/roadmap'),
  /** 标记知识点为已掌握（自评），跳过路径中对应项。 */
  markMastered: (req: MarkMasteredRequest) =>
    api.post<MarkMasteredResponse>('/learning-paths/mark-mastered', req),
}

export const coldstartApi = {
  /** CF 冷启动：拉取 CF 提交记录，映射知识点。 */
  cfColdStart: () => api.post<ColdStartResultResponse>('/coldstart/cf'),
  /** 诊断题冷启动：返回 15 道摸底测试题，初始化用户画像。 */
  diagnostic: () => api.post<ColdStartResultResponse>('/coldstart/diagnostic'),
}

export const dailyTaskApi = {
  /** 获取今日任务（幂等）。 */
  getToday: () => api.get<DailyTaskTodayResponse>('/daily-tasks/today'),
  /** 更新任务项状态（标记完成/跳过）。 */
  updateItem: (taskId: string, itemId: string, status: 'done' | 'skipped') =>
    api.patch<DailyTaskItemUpdateResponse>(`/daily-tasks/${taskId}/items/${itemId}`, { status }),
}
