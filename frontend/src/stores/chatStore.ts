import { create } from 'zustand'
import { db } from '../db/db'
import type {
  AgentReference,
  AgentToolCall,
  AgentTraceStep,
  ChatMessage,
  Conversation,
} from '../types'

/** 未登录用户使用的占位 user_id。 */
export const LOCAL_USER_ID = 'local'

interface ChatState {
  conversations: Conversation[]
  currentConversationId: string | null
  messages: ChatMessage[]
  isLoading: boolean
  isInitializing: boolean
  error: string | null

  /** 加载该用户所有会话；若无会话则自动创建一个。 */
  init: (userId: string) => Promise<void>
  /** 切换会话并加载其消息。 */
  selectConversation: (id: string) => Promise<void>
  /** 新建会话。 */
  createConversation: (userId: string, title?: string) => Promise<string>
  /** 追加消息并更新会话 updated_at。返回新消息。 */
  addMessage: (params: {
    userId: string
    conversationId: string
    role: 'user' | 'assistant'
    content: string
    references?: AgentReference[]
    toolCalls?: AgentToolCall[]
    trace?: AgentTraceStep[]
  }) => Promise<ChatMessage>
  /** 删除指定消息（用于失败回滚）。 */
  removeMessage: (messageId: string) => Promise<void>
  /** 删除会话及其全部消息（级联）。 */
  deleteConversation: (id: string) => Promise<void>
  /** 清空该用户全部数据。 */
  clearAll: (userId: string) => Promise<void>
  setLoading: (v: boolean) => void
  setError: (e: string | null) => void
}

const genId = () => `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`

const nowIso = () => new Date().toISOString()

export const useChatStore = create<ChatState>((set, get) => ({
  conversations: [],
  currentConversationId: null,
  messages: [],
  isLoading: false,
  isInitializing: false,
  error: null,

  init: async (userId: string) => {
    // 幂等：若已在初始化中或已完成初始化且 user_id 一致，则跳过
    const s = get()
    if (s.isInitializing) return
    if (s.currentConversationId !== null && s.conversations.some((c) => c.user_id === userId)) {
      return
    }
    set({ isInitializing: true, error: null })
    try {
      let convs = await db.conversations
        .where('user_id')
        .equals(userId)
        .reverse()
        .sortBy('updated_at')
      // 重复检查：StrictMode 双调用可能已在两次调用间创建了会话
      if (convs.length === 0) {
        // 再次查询避免竞态（另一个 init 调用可能已经创建）
        await get().createConversation(userId)
        convs = await db.conversations
          .where('user_id')
          .equals(userId)
          .reverse()
          .sortBy('updated_at')
        if (convs.length > 1) {
          // 竞态导致创建了多个默认会话，保留最早一个并删除其余
          const keep = convs[convs.length - 1]
          const dupes = convs.slice(0, -1).filter((c) => c.title === '新对话')
          for (const d of dupes) {
            await get().deleteConversation(d.id)
          }
          convs = [keep]
        }
      }
      set({ conversations: convs, currentConversationId: convs[0]?.id ?? null })
      if (convs[0]) {
        await get().selectConversation(convs[0].id)
      }
    } catch (err) {
      set({ error: err instanceof Error ? err.message : '加载会话失败' })
    } finally {
      set({ isInitializing: false })
    }
  },

  selectConversation: async (id: string) => {
    try {
      const msgs = await db.messages.where('conversation_id').equals(id).sortBy('created_at')
      set({ currentConversationId: id, messages: msgs })
    } catch (err) {
      set({ error: err instanceof Error ? err.message : '加载消息失败' })
    }
  },

  createConversation: async (userId: string, title = '新对话') => {
    const ts = nowIso()
    const conv: Conversation = {
      id: genId(),
      user_id: userId,
      title,
      created_at: ts,
      updated_at: ts,
    }
    await db.conversations.add(conv)
    set((s) => ({
      conversations: [conv, ...s.conversations],
      currentConversationId: conv.id,
      messages: [],
    }))
    return conv.id
  },

  addMessage: async ({ userId, conversationId, role, content, references, toolCalls, trace }) => {
    const msg: ChatMessage = {
      id: genId(),
      conversation_id: conversationId,
      user_id: userId,
      role,
      content,
      references: references?.length ? references : undefined,
      tool_calls: toolCalls?.length ? toolCalls : undefined,
      trace: trace?.length ? trace : undefined,
      created_at: nowIso(),
    }
    await db.messages.add(msg)
    // 更新会话 updated_at 与标题
    const conv = await db.conversations.get(conversationId)
    let newTitle = conv?.title ?? '新对话'
    if (conv) {
      // 第一条用户消息作为会话标题
      if (role === 'user' && (conv.title === '新对话' || !conv.title)) {
        newTitle = content.slice(0, 30)
      }
      await db.conversations.update(conversationId, {
        updated_at: msg.created_at,
        title: newTitle,
      })
    }
    const titleForState = newTitle
    set((s) => ({
      messages: [...s.messages, msg],
      conversations: s.conversations.map((c) =>
        c.id === conversationId ? { ...c, updated_at: msg.created_at, title: titleForState } : c
      ),
    }))
    return msg
  },

  removeMessage: async (messageId: string) => {
    const msg = await db.messages.get(messageId)
    await db.messages.delete(messageId)
    // 回滚标题：如果该用户消息是标题来源（会话标题等于其内容切片），还原为"新对话"
    if (msg && msg.role === 'user' && msg.conversation_id) {
      const conv = await db.conversations.get(msg.conversation_id)
      if (conv && conv.title === msg.content.slice(0, 30)) {
        const remaining = await db.messages
          .where('conversation_id')
          .equals(msg.conversation_id)
          .sortBy('created_at')
        const firstUserMsg = remaining.find((m) => m.role === 'user')
        const restoredTitle = firstUserMsg ? firstUserMsg.content.slice(0, 30) : '新对话'
        await db.conversations.update(msg.conversation_id, { title: restoredTitle })
        set((s) => ({
          messages: s.messages.filter((m) => m.id !== messageId),
          conversations: s.conversations.map((c) =>
            c.id === msg.conversation_id ? { ...c, title: restoredTitle } : c
          ),
        }))
        return
      }
    }
    set((s) => ({ messages: s.messages.filter((m) => m.id !== messageId) }))
  },

  deleteConversation: async (id: string) => {
    await db.transaction('rw', db.conversations, db.messages, async () => {
      await db.messages.where('conversation_id').equals(id).delete()
      await db.conversations.delete(id)
    })
    set((s) => {
      const remaining = s.conversations.filter((c) => c.id !== id)
      return {
        conversations: remaining,
        currentConversationId:
          s.currentConversationId === id ? (remaining[0]?.id ?? null) : s.currentConversationId,
        messages: s.currentConversationId === id ? [] : s.messages,
      }
    })
  },

  clearAll: async (userId: string) => {
    await db.transaction('rw', db.conversations, db.messages, async () => {
      const convIds = await db.conversations.where('user_id').equals(userId).primaryKeys()
      if (convIds.length) {
        await db.messages.where('conversation_id').anyOf(convIds).delete()
        await db.conversations.bulkDelete(convIds)
      }
    })
    set({ conversations: [], currentConversationId: null, messages: [] })
  },

  setLoading: (v) => set({ isLoading: v }),
  setError: (e) => set({ error: e }),
}))
