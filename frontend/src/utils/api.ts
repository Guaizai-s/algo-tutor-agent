import axios from 'axios'
import type {
  AgentChatRequest,
  AgentChatResponse,
  AttemptRequest,
  AttemptResponse,
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
  }) => api.get('/problems/', { params }),
  getById: (id: string) => api.get(`/problems/${id}`),
  execute: (id: string, code: string, language: 'python' | 'cpp' | 'java') =>
    api.post<CodeExecutionResult>(`/problems/${id}/execute`, { code, language }),
  submit: (id: string, code: string, language: string) =>
    api.post(`/problems/${id}/submit`, { code, language }),
  getHints: (id: string, level: number) => api.get(`/problems/${id}/hints`, { params: { level } }),
  getSubmissions: (id: string) => api.get(`/problems/${id}/submissions`),
}

export const agentApi = {
  chat: (req: AgentChatRequest) => api.post<AgentChatResponse>('/agent/chat', req),
}

export const progressApi = {
  getOverview: (userId: string) => api.get('/progress/overview', { params: { user_id: userId } }),
  getActivity: (userId: string, days = 30) =>
    api.get('/progress/activity', { params: { user_id: userId, days } }),
  getWrongAnswers: () => api.get('/progress/wrong-answers', { params: { user_id: DEV_USER_ID } }),
  recomputeMastery: (userId: string, knowledgeId?: string) =>
    api.post('/progress/recompute', { user_id: userId, knowledge_id: knowledgeId ?? null }),
}

export const reviewApi = {
  getList: () => api.get('/review/list', { params: { user_id: DEV_USER_ID } }),
  getStatus: () => api.get('/review/status', { params: { user_id: DEV_USER_ID } }),
  submitReview: (id: string, correct: boolean) => api.post(`/review/${id}/submit`, { correct }),
}

export const notificationApi = {
  list: () => api.get('/notifications', { params: { user_id: DEV_USER_ID } }),
  markAsRead: (id: string) =>
    api.post(`/notifications/${id}/read`, null, { params: { user_id: DEV_USER_ID } }),
  markAllAsRead: () =>
    api.post('/notifications/read-all', null, { params: { user_id: DEV_USER_ID } }),
  getRecommendations: (userId: string) =>
    api.get('/notifications/recommendations', { params: { user_id: userId } }),
}

export const discussionApi = {
  getSolutions: (problemId: string) => api.get(`/problems/${problemId}/solutions`),
  /** 全局题解列表（讨论区首页）。 */
  getGlobalSolutions: () => api.get('/solutions'),
  getSolutionById: (id: string) => api.get(`/solutions/${id}`),
  createSolution: (problemId: string, data: { title: string; content: string; language: string }) =>
    api.post(`/problems/${problemId}/solutions`, data),
  likeSolution: (id: string) => api.post(`/solutions/${id}/like`),
  getComments: (solutionId: string) => api.get(`/solutions/${solutionId}/comments`),
  createComment: (solutionId: string, content: string) =>
    api.post(`/solutions/${solutionId}/comments`, { content }),
}

// ===== Task 10: Learning path & daily task =====

/**
 * 开发期固定的 user_id（COMPAT: 认证落地后从 token 解析）。
 * 使用一个稳定 UUID，避免每次刷新生成新用户。
 * 该 UUID 仅用于本地开发调用 Task 10 API，不与真实用户绑定。
 */
export const DEV_USER_ID = '00000000-0000-4000-8000-000000000001'

export const learningApi = {
  /** 生成（或重新生成）学习路径。 */
  generatePath: (req: LearningPathGenerateRequest) =>
    api.post<LearningPathRead>('/learning-paths/generate', req),
  /** 获取当前 active 学习路径。 */
  getCurrentPath: (userId: string) =>
    api.get<LearningPathRead>('/learning-paths/current', { params: { user_id: userId } }),
  /** 获取路线图聚合数据：知识树 + 用户学习状态。 */
  getRoadmap: (userId: string) =>
    api.get<RoadmapResponse>('/learning-paths/roadmap', { params: { user_id: userId } }),
  /** 记录一次做题结果，触发路径动态调整。 */
  recordAttempt: (req: AttemptRequest) =>
    api.post<AttemptResponse>('/learning-paths/attempts', req),
  /** 标记知识点为已掌握（自评），跳过路径中对应项。 */
  markMastered: (req: MarkMasteredRequest) =>
    api.post<MarkMasteredResponse>('/learning-paths/mark-mastered', req),
}

export const coldstartApi = {
  /** CF 冷启动：拉取 CF 提交记录，映射知识点。 */
  cfColdStart: (userId: string) =>
    api.post<ColdStartResultResponse>('/coldstart/cf', null, { params: { user_id: userId } }),
}

export const dailyTaskApi = {
  /** 获取今日任务（幂等）。 */
  getToday: (userId: string) =>
    api.get<DailyTaskTodayResponse>('/daily-tasks/today', { params: { user_id: userId } }),
  /** 更新任务项状态（标记完成/跳过）。 */
  updateItem: (taskId: string, itemId: string, status: 'done' | 'skipped') =>
    api.patch<DailyTaskItemUpdateResponse>(`/daily-tasks/${taskId}/items/${itemId}`, { status }),
}
