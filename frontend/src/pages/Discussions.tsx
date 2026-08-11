import React, { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { MessageSquare, ThumbsUp, Star, ChevronRight, AlertCircle, Loader2 } from 'lucide-react'
import { discussionApi } from '../utils/api'
import type { Solution } from '../types'

const Discussions: React.FC = () => {
  const [solutions, setSolutions] = useState<Solution[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [filter, setFilter] = useState<'all' | 'featured' | 'python' | 'cpp' | 'java'>('all')

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    discussionApi
      .getGlobalSolutions()
      .then((resp) => {
        if (!cancelled) setSolutions(resp.data.items as Solution[])
      })
      .catch((err: unknown) => {
        if (cancelled) return
        setError(err instanceof Error ? err.message : '加载题解列表失败')
      })
      .finally(() => !cancelled && setLoading(false))
    return () => {
      cancelled = true
    }
  }, [])

  const filtered = solutions.filter((s) => {
    switch (filter) {
      case 'featured':
        return s.is_featured
      case 'python':
      case 'cpp':
      case 'java':
        return s.language?.toLowerCase() === filter
      default:
        return true
    }
  })

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold text-gray-900">题解广场</h1>
        <p className="text-gray-600 mt-2">分享解题思路，学习优秀题解</p>
      </div>

      <div className="flex gap-2 flex-wrap">
        {(['all', 'featured', 'python', 'cpp', 'java'] as const).map((f) => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={`px-4 py-2 rounded-lg text-sm transition-colors ${
              filter === f
                ? 'bg-blue-600 text-white'
                : 'bg-white text-gray-700 border border-gray-200 hover:bg-gray-50'
            }`}
          >
            {f === 'all' ? '全部' : f === 'featured' ? '精选题解' : f.toUpperCase()}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="flex items-center justify-center h-64 text-gray-500">
          <Loader2 className="animate-spin mr-2" size={20} />
          加载中...
        </div>
      ) : error ? (
        <div className="bg-yellow-50 border border-yellow-200 rounded-xl p-6 flex items-start gap-3 text-yellow-800">
          <AlertCircle size={20} className="flex-shrink-0 mt-0.5" />
          <div className="text-sm">
            <p className="font-medium">题解广场暂不可用</p>
            <p className="mt-1 text-yellow-700">
              后端题解 API（Task 15）尚未实现。待 Role B 完成后此页面将自动展示真实数据。
            </p>
          </div>
        </div>
      ) : filtered.length === 0 ? (
        <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-12 text-center text-gray-500">
          暂无题解，去题库做道题并分享你的思路吧
        </div>
      ) : (
        <div className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden">
          <div className="divide-y divide-gray-100">
            {filtered.map((solution) => (
              <Link
                key={solution.id}
                to={`/solutions/${solution.id}`}
                className="block p-6 hover:bg-gray-50 transition-colors"
              >
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-2">
                      {solution.is_featured && (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 bg-yellow-100 text-yellow-700 rounded text-xs">
                          <Star size={12} />
                          精选
                        </span>
                      )}
                      <Link
                        to={`/problems/${solution.problem_id}`}
                        className="text-sm text-blue-600 hover:underline"
                        onClick={(e) => e.stopPropagation()}
                      >
                        题目 {solution.problem_id.slice(0, 8)}…
                      </Link>
                    </div>
                    <h3 className="text-lg font-medium text-gray-900 hover:text-blue-600 mb-2">
                      {solution.title}
                    </h3>
                    <div className="flex items-center gap-4 text-sm text-gray-500">
                      <div className="flex items-center gap-2">
                        <div className="w-6 h-6 bg-blue-100 rounded-full flex items-center justify-center text-blue-600 text-xs font-medium">
                          {solution.user.username.charAt(0).toUpperCase()}
                        </div>
                        <span>{solution.user.username}</span>
                      </div>
                      {solution.language && (
                        <span className="px-2 py-0.5 bg-gray-100 rounded text-xs">
                          {solution.language}
                        </span>
                      )}
                      <span className="flex items-center gap-1">
                        <ThumbsUp size={14} />
                        {solution.likes}
                      </span>
                      <span className="flex items-center gap-1">
                        <MessageSquare size={14} />
                        {solution.comments_count}
                      </span>
                      <span>{new Date(solution.created_at).toLocaleDateString()}</span>
                    </div>
                  </div>
                  <ChevronRight className="text-gray-400 flex-shrink-0" size={20} />
                </div>
              </Link>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

export default Discussions
