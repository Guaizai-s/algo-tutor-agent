import axios from 'axios'
import type {
  AgentChatRequest,
  AgentChatResponse,
  AttemptRequest,
  AttemptResponse,
  CodeExecutionResult,
  CodeforcesAccount,
  ColdStartResponse,
  DailyTaskTodayResponse,
  DiagnosticProblem,
  LearningPathGenerateRequest,
  LearningPathRead,
  ProfileUpdateRequest,
  Progress,
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
  updateProfile: (payload: ProfileUpdateRequest) => api.patch<User>('/auth/profile', payload),
  getCodeforces: () => api.get<CodeforcesAccount | null>('/auth/codeforces'),
  bindCodeforces: (handle: string) =>
    api.post<{ user: User; account: CodeforcesAccount }>('/auth/codeforces/bind', { handle }),
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
  getOverview: () => api.get<Progress>('/progress/overview'),
  recomputeMastery: (knowledgeId?: string) =>
    api.post('/progress/recompute', { knowledge_id: knowledgeId ?? null }),
}

export const wrongbookApi = {
  list: (params?: { resolved?: boolean; page?: number; page_size?: number }) =>
    api.get<WrongBookListResponse>('/wrongbook', { params }),
  retry: (submissionId: string) => api.post(`/wrongbook/${submissionId}/retry`),
  recommendations: (submissionId: string) =>
    api.get<WrongBookRecommendation[]>(`/wrongbook/${submissionId}/recommendations`),
}

export const onboardingApi = {
  getStatus: () => api.get<ColdStartResponse>('/onboarding/status'),
  start: () => api.post<ColdStartResponse>('/onboarding/start'),
  submitDiagnostic: (results: { problem_id: string; correct: boolean }[]) =>
    api.post<ColdStartResponse>('/onboarding/diagnostic', { results }),
  diagnosticProblems: (response: ColdStartResponse): DiagnosticProblem[] =>
    response.diagnostic_problems,
}

export const reviewApi = {
  getList: () => api.get('/review/list'),
  submitReview: (id: string, correct: boolean) => api.post(`/review/${id}/submit`, { correct }),
}

export const notificationApi = {
  list: () => api.get('/notifications'),
  markAsRead: (id: string) => api.post(`/notifications/${id}/read`),
  markAllAsRead: () => api.post('/notifications/read-all'),
}

export const discussionApi = {
  getSolutions: (problemId: string) => api.get(`/problems/${problemId}/solutions`),
  getSolutionById: (id: string) => api.get(`/solutions/${id}`),
  createSolution: (problemId: string, data: { title: string; content: string; language: string }) =>
    api.post(`/problems/${problemId}/solutions`, data),
  likeSolution: (id: string) => api.post(`/solutions/${id}/like`),
  getComments: (solutionId: string) => api.get(`/solutions/${solutionId}/comments`),
  createComment: (solutionId: string, content: string) =>
    api.post(`/solutions/${solutionId}/comments`, { content }),
}

// ===== Task 10: Learning path & daily task =====

export const learningApi = {
  /** 生成（或重新生成）学习路径。 */
  generatePath: (req: LearningPathGenerateRequest) =>
    api.post<LearningPathRead>('/learning-paths/generate', req),
  /** 获取当前 active 学习路径。 */
  getCurrentPath: () => api.get<LearningPathRead>('/learning-paths/current'),
  /** 记录一次做题结果，触发路径动态调整。 */
  recordAttempt: (req: AttemptRequest) =>
    api.post<AttemptResponse>('/learning-paths/attempts', req),
}

export const dailyTaskApi = {
  /** 获取今日任务（幂等）。 */
  getToday: () => api.get<DailyTaskTodayResponse>('/daily-tasks/today'),
}
