import React, { useState, useRef, useEffect } from 'react'
import { Send, Bot, User, BookOpen, AlertCircle, RefreshCw } from 'lucide-react'
import { Link } from 'react-router-dom'
import { agentApi } from '../utils/api'
import { useChatStore, LOCAL_USER_ID } from '../stores/chatStore'
import { useAuthStore } from '../stores/authStore'
import AgentTrace from '../components/AgentTrace'
import type {
  AgentReference,
  AgentStreamEvent,
  AgentToolCall,
  AgentTraceStep,
  ChatMessage,
} from '../types'

const MAX_HISTORY = 20

const AIChat: React.FC = () => {
  const {
    messages,
    currentConversationId,
    isLoading,
    isInitializing,
    error: storeError,
    init,
    addMessage,
    removeMessage,
    setLoading,
    setError,
  } = useChatStore()
  const { user } = useAuthStore()
  const userId = user?.id ?? LOCAL_USER_ID

  const [input, setInput] = useState('')
  const [lastFailedInput, setLastFailedInput] = useState<string>('')
  const [liveTrace, setLiveTrace] = useState<AgentTraceStep[]>([])
  const [streamingAnswer, setStreamingAnswer] = useState('')
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const abortRef = useRef<AbortController | null>(null)

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, liveTrace, streamingAnswer])

  // 挂载时加载该用户的会话
  useEffect(() => {
    init(userId)
  }, [userId, init])

  useEffect(() => () => abortRef.current?.abort(), [])

  const buildHistory = (msgs: ChatMessage[]) => {
    const recent = msgs.slice(-MAX_HISTORY)
    return recent.map((m) => ({ role: m.role, content: m.content }))
  }

  const send = async (text: string) => {
    if (!text.trim() || isLoading || !currentConversationId) return

    setError(null)
    setLoading(true)
    setInput('')
    setLiveTrace([])
    setStreamingAnswer('')

    let userMsgId: string | null = null
    try {
      // 1. 先持久化用户消息
      const userMsg = await addMessage({
        userId,
        conversationId: currentConversationId,
        role: 'user',
        content: text,
      })
      userMsgId = userMsg.id
      // 2. 构建历史（不含刚插入的用户消息，避免重复）
      const history = buildHistory(messages)
      const controller = new AbortController()
      abortRef.current = controller
      let answer = ''
      let references: AgentReference[] = []
      let toolCalls: AgentToolCall[] = []
      let completedTrace: AgentTraceStep[] = []
      const traceById = new Map<string, AgentTraceStep>()

      const onStreamEvent = (event: AgentStreamEvent) => {
        if (event.type === 'trace') {
          traceById.set(event.step.id, event.step)
          setLiveTrace(Array.from(traceById.values()))
        } else if (event.type === 'answer_delta') {
          answer += event.delta
          setStreamingAnswer(answer)
        } else if (event.type === 'done') {
          references = event.references
          toolCalls = event.tool_calls
          completedTrace = event.trace
          setLiveTrace(event.trace)
        }
      }

      await agentApi.streamChat(
        { message: text, history, context: undefined },
        onStreamEvent,
        controller.signal
      )
      if (!answer.trim()) throw new Error('AI 未返回有效内容，请重试')

      // 3. 持久化 AI 回复
      await addMessage({
        userId,
        conversationId: currentConversationId,
        role: 'assistant',
        content: answer,
        references,
        toolCalls,
        trace: completedTrace.length ? completedTrace : Array.from(traceById.values()),
      })
    } catch (err) {
      // 失败回滚：移除刚插入的用户消息（如果已插入）
      if (userMsgId) {
        await removeMessage(userMsgId)
      }
      const message = err instanceof Error ? err.message : '请求失败，请重试'
      setError(message)
      setLastFailedInput(text)
    } finally {
      abortRef.current = null
      setLiveTrace([])
      setStreamingAnswer('')
      setLoading(false)
    }
  }

  const handleSend = () => {
    send(input)
  }

  const handleRetry = async () => {
    if (!currentConversationId) return
    setError(null)
    await send(lastFailedInput)
  }

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const quickQuestions = ['DP 怎么入门？', '二分查找模板', '什么是滑动窗口？', '递归和迭代的区别']

  // 欢迎消息（仅本地展示用，不持久化）
  const displayMessages: (ChatMessage & { isWelcome?: boolean })[] =
    messages.length === 0
      ? [
          {
            id: 'welcome',
            conversation_id: '',
            user_id: '',
            role: 'assistant',
            content:
              '你好！我是你的算法教练 AI，有什么问题可以问我。比如：\n- 动态规划怎么入门？\n- 二分查找有什么注意事项？\n- 这道题的思路是什么？',
            created_at: '',
            isWelcome: true,
          },
        ]
      : messages

  return (
    <div className="h-[calc(100vh-8rem)] flex flex-col">
      <div>
        <h1 className="text-3xl font text-gray-900">AI 问答</h1>
        <p className="text-gray-600 mt-2">有任何算法问题，随时问我</p>
      </div>

      <div className="flex-1 mt-6 bg-white rounded-xl shadow-sm border border-gray-100 flex flex-col overflow-hidden">
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {isInitializing ? (
            <div className="flex items-center justify-center text-gray-400 py-12">
              正在加载历史会话...
            </div>
          ) : (
            displayMessages.map((msg) => (
              <div
                key={msg.id}
                className={`flex gap-3 ${msg.role === 'user' ? 'flex-row-reverse' : ''}`}
              >
                <div
                  className={`w-10 h-10 rounded-full flex items-center justify-center flex-shrink-0 ${
                    msg.role === 'user' ? 'bg-blue-600' : 'bg-purple-600'
                  }`}
                >
                  {msg.role === 'user' ? (
                    <User className="text-white" size={20} />
                  ) : (
                    <Bot className="text-white" size={20} />
                  )}
                </div>
                <div className={`max-w-[78%] ${msg.role === 'user' ? 'items-end' : ''}`}>
                  {msg.role === 'assistant' && msg.trace && msg.trace.length > 0 ? (
                    <div className="mb-2">
                      <AgentTrace steps={msg.trace} compact />
                    </div>
                  ) : null}
                  <div
                    className={`px-4 py-3 rounded-2xl whitespace-pre-wrap ${
                      msg.role === 'user'
                        ? 'bg-blue-600 text-white rounded-tr-md'
                        : 'bg-gray-100 text-gray-900 rounded-tl-md'
                    }`}
                  >
                    {msg.content}
                  </div>
                  {msg.references && msg.references.length > 0 && (
                    <div className="mt-2 space-y-1">
                      <p className="text-xs text-gray-500">引用来源：</p>
                      {msg.references.map((ref: AgentReference) => (
                        <Link
                          key={`${ref.type}-${ref.id}`}
                          to={
                            ref.type === 'problem' ? `/problems/${ref.id}` : `/knowledge/${ref.id}`
                          }
                          className="flex items-center gap-2 text-sm text-blue-600 hover:underline"
                          title={ref.source}
                        >
                          <BookOpen size={14} />
                          <span>{ref.title}</span>
                          <span className="text-xs text-gray-400">({ref.source})</span>
                        </Link>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            ))
          )}
          {isLoading && (
            <div className="flex gap-3">
              <div className="w-10 h-10 rounded-full bg-purple-600 flex items-center justify-center flex-shrink-0">
                <Bot className="text-white" size={20} />
              </div>
              <div className="w-full max-w-[78%] space-y-2">
                {liveTrace.length > 0 ? (
                  <AgentTrace steps={liveTrace} />
                ) : (
                  <div className="rounded-xl border border-indigo-100 bg-indigo-50 p-4 text-sm text-indigo-700">
                    正在启动算法教练...
                  </div>
                )}
                {streamingAnswer ? (
                  <div className="bg-gray-100 px-4 py-3 rounded-2xl rounded-tl-md whitespace-pre-wrap text-gray-900">
                    {streamingAnswer}
                    <span className="ml-1 inline-block h-4 w-0.5 animate-pulse bg-purple-500 align-middle" />
                  </div>
                ) : null}
              </div>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>

        {storeError && (
          <div className="px-6 py-3 bg-red-50 border-t border-red-100 flex items-center justify-between">
            <div className="flex items-center gap-2 text-red-700 text-sm">
              <AlertCircle size={16} />
              <span>请求失败：{storeError}</span>
            </div>
            <button
              onClick={handleRetry}
              disabled={isLoading}
              className="flex items-center gap-1 px-3 py-1.5 bg-red-600 text-white rounded-lg text-sm hover:bg-red-700 disabled:opacity-50"
            >
              <RefreshCw size={14} />
              重试
            </button>
          </div>
        )}

        {messages.length === 0 && !isLoading && !isInitializing && (
          <div className="px-6 pb-4">
            <p className="text-sm text-gray-500 mb-2">常见问题：</p>
            <div className="flex flex-wrap gap-2">
              {quickQuestions.map((q) => (
                <button
                  key={q}
                  onClick={() => setInput(q)}
                  className="px-3 py-1.5 bg-gray-100 hover:bg-gray-200 rounded-lg text-sm text-gray-700 transition-colors"
                >
                  {q}
                </button>
              ))}
            </div>
          </div>
        )}

        <div className="p-4 border-t border-gray-100">
          <div className="flex gap-3">
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyPress}
              placeholder="输入你的问题..."
              rows={1}
              className="flex-1 px-4 py-3 border border-gray-200 rounded-xl resize-none focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none"
            />
            <button
              onClick={handleSend}
              disabled={!input.trim() || isLoading || isInitializing}
              aria-label="发送问题"
              className="px-4 py-3 bg-blue-600 text-white rounded-xl hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              <Send size={20} />
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

export default AIChat
