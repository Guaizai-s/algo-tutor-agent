import { create } from 'zustand'
import type { ProfileUpdateRequest, User } from '../types'
import { authApi } from '../utils/api'

interface AuthState {
  user: User | null
  token: string | null
  isAuthenticated: boolean
  isLoading: boolean
  login: (email: string, password: string) => Promise<void>
  register: (email: string, username: string, password: string) => Promise<void>
  logout: () => void
  loadUser: () => Promise<void>
  updateProfile: (payload: ProfileUpdateRequest) => Promise<User>
  setUser: (user: User) => void
}

export const useAuthStore = create<AuthState>((set) => ({
  user: JSON.parse(localStorage.getItem('user') || 'null'),
  token: localStorage.getItem('token'),
  isAuthenticated: !!localStorage.getItem('token'),
  isLoading: false,

  login: async (email: string, password: string) => {
    set({ isLoading: true })
    try {
      const response = await authApi.login(email, password)
      const { access_token, user } = response.data
      localStorage.setItem('token', access_token)
      localStorage.setItem('user', JSON.stringify(user))
      set({ user, token: access_token, isAuthenticated: true, isLoading: false })
    } catch (error) {
      set({ isLoading: false })
      throw error
    }
  },

  register: async (email: string, username: string, password: string) => {
    set({ isLoading: true })
    try {
      const response = await authApi.register(email, username, password)
      const { access_token, user } = response.data
      localStorage.setItem('token', access_token)
      localStorage.setItem('user', JSON.stringify(user))
      set({ user, token: access_token, isAuthenticated: true, isLoading: false })
    } catch (error) {
      set({ isLoading: false })
      throw error
    }
  },

  logout: () => {
    localStorage.removeItem('token')
    localStorage.removeItem('user')
    set({ user: null, token: null, isAuthenticated: false })
  },

  loadUser: async () => {
    const token = localStorage.getItem('token')
    if (!token) return
    set({ isLoading: true })
    try {
      const response = await authApi.getProfile()
      const user = response.data
      localStorage.setItem('user', JSON.stringify(user))
      set({ user, isAuthenticated: true, isLoading: false })
    } catch {
      localStorage.removeItem('token')
      localStorage.removeItem('user')
      set({ user: null, token: null, isAuthenticated: false, isLoading: false })
    }
  },

  updateProfile: async (payload: ProfileUpdateRequest) => {
    set({ isLoading: true })
    try {
      const response = await authApi.updateProfile(payload)
      const user = response.data
      localStorage.setItem('user', JSON.stringify(user))
      set({ user, isLoading: false })
      return user
    } catch (error) {
      set({ isLoading: false })
      throw error
    }
  },

  setUser: (user: User) => {
    localStorage.setItem('user', JSON.stringify(user))
    set({ user })
  },
}))
