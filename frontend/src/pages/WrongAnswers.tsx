import React, { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { BookX, RotateCcw, ChevronRight, AlertCircle, Loader2 } from 'lucide-react'
import { progressApi } from '../utils/api'
import type { WrongAnswer } from '../types'

const getErrorStyle = (type: string) => {
  switch (type) {
    case 'WA':
      return 'bg-red-100 text-red-700'
    case 'TLE':
      return 'bg-orange-100 text-orange-700'
    case 'RE':
      return 'bg-yellow-100 text-yellow-700'
    default:
      return 'bg-gray-100 text-gray-700'
  }
}

const getErrorText = (type: string) => {
  switch (type) {
    case 'WA':
      return '答案错误'
    case 'TLE':
      return '超时'
    case 'RE':
      return '运行错误'
    default:
      return type
  }
}

const WrongAnswers: React.FC = () => {
  const [items, setItems] = useState<WrongAnswer[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    progressApi
      .getWrongAnswers()
      .then((resp) => {
        if (!cancelled) setItems((resp.data as { items: WrongAnswer[] }).items || [])
      })
      .catch((err: unknown) => {
        if (cancelled) return
        setError(err instanceof Error ? err.message : '加载错题本失败')
      })
      .finally(() => !cancelled && setLoading(false))
    return () => {
      cancelled = true
    }
  }, [])

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64 text-gray-500">
        <Loader2 className="animate-spin mr-2" size={20} />
        加载中...
      </div>
    )
  }

  if (error) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">错题本</h1>
          <p className="text-gray-600 mt-2">回顾错题，查漏补缺，避免重复犯错</p>
        </div>
        <div className="bg-yellow-50 border border-yellow-200 rounded-xl p-6 flex items-start gap-3 text-yellow-800">
          <AlertCircle size={20} className="flex-shrink-0 mt-0.5" />
          <div className="text-sm">
            <p className="font-medium">错题本数据暂不可用</p>
            <p className="mt-1 text-yellow-700">
              后端错题 API（Task 11）尚未实现。待 Role B 完成{' '}
              <code>/api/v1/progress/wrong-answers</code> 后此页面将自动展示真实数据。
            </p>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold text-gray-900">错题本</h1>
        <p className="text-gray-600 mt-2">回顾错题，查漏补缺，避免重复犯错</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="bg-white rounded-xl p-6 shadow-sm border border-gray-100">
          <div className="flex items-center gap-3">
            <div className="w-12 h-12 bg-red-100 rounded-xl flex items-center justify-center">
              <BookX className="text-red-600" size={24} />
            </div>
            <div>
              <p className="text-2xl font-bold text-gray-900">{items.length}</p>
              <p className="text-sm text-gray-500">错题总数</p>
            </div>
          </div>
        </div>
        <div className="bg-white rounded-xl p-6 shadow-sm border border-gray-100">
          <div className="flex items-center gap-3">
            <div className="w-12 h-12 bg-orange-100 rounded-xl flex items-center justify-center">
              <RotateCcw className="text-orange-600" size={24} />
            </div>
            <div>
              <p className="text-2xl font-bold text-gray-900">—</p>
              <p className="text-sm text-gray-500">待复习</p>
            </div>
          </div>
        </div>
        <div className="bg-white rounded-xl p-6 shadow-sm border border-gray-100">
          <div className="flex items-center gap-3">
            <div className="w-12 h-12 bg-green-100 rounded-xl flex items-center justify-center">
              <AlertCircle className="text-green-600" size={24} />
            </div>
            <div>
              <p className="text-2xl font-bold text-gray-900">—</p>
              <p className="text-sm text-gray-500">已订正</p>
            </div>
          </div>
        </div>
      </div>

      {items.length === 0 ? (
        <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-12 text-center text-gray-500">
          暂无错题记录，继续保持！
        </div>
      ) : (
        <div className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden">
          <div className="p-6 border-b border-gray-100">
            <h2 className="text-lg font-semibold">错题列表</h2>
          </div>
          <div className="divide-y divide-gray-100">
            {items.map((item) => (
              <div key={item.id} className="p-6">
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <div className="flex items-center gap-3 mb-2">
                      <Link
                        to={`/problems/${item.problem.id}`}
                        className="text-lg font-medium text-gray-900 hover:text-blue-600"
                      >
                        {item.problem.title}
                      </Link>
                      <span
                        className={`px-2 py-0.5 text-xs rounded ${getErrorStyle(item.error_type)}`}
                      >
                        {getErrorText(item.error_type)}
                      </span>
                    </div>
                    {item.error_message && (
                      <p className="text-sm text-gray-500 mb-2">{item.error_message}</p>
                    )}
                    <p className="text-sm text-gray-500">
                      上次尝试：{new Date(item.created_at).toLocaleString()}
                    </p>
                  </div>
                  <Link
                    to={`/problems/${item.problem.id}`}
                    className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors text-sm"
                  >
                    重新做题
                  </Link>
                </div>

                {item.similar_problems && item.similar_problems.length > 0 && (
                  <div className="mt-4 pt-4 border-t border-gray-100">
                    <p className="text-sm text-gray-600 mb-2">推荐同类题：</p>
                    <div className="flex gap-2 flex-wrap">
                      {item.similar_problems.map((p) => (
                        <Link
                          key={p.id}
                          to={`/problems/${p.id}`}
                          className="flex items-center gap-1 px-3 py-1.5 bg-gray-50 hover:bg-gray-100 rounded-lg text-sm text-gray-700 transition-colors"
                        >
                          {p.title}
                          <ChevronRight size={14} />
                        </Link>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

export default WrongAnswers
