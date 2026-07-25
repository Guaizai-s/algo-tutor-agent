import axios from 'axios'
import type { AgentChatRequest, AgentChatResponse } from '../types'

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
  getProfile: () => api.get('/auth/me'),
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
  submit: (id: string, code: string, language: string) =>
    api.post(`/problems/${id}/submit`, { code, language }),
  getHints: (id: string, level: number) => api.get(`/problems/${id}/hints`, { params: { level } }),
  getSubmissions: (id: string) => api.get(`/problems/${id}/submissions`),
}

export const agentApi = {
  chat: (req: AgentChatRequest) => api.post<AgentChatResponse>('/agent/chat', req),
}

export const progressApi = {
  getOverview: () => api.get('/progress/overview'),
  getWrongAnswers: () => api.get('/progress/wrong-answers'),
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
