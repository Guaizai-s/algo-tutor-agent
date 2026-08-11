import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { AlertCircle, BookX, CheckCircle2, ChevronRight, Loader2, RotateCcw } from 'lucide-react'
import type { WrongBookItem, WrongBookRecommendation } from '../types'
import { wrongbookApi } from '../utils/api'

type Filter = 'all' | 'unresolved' | 'resolved'

const verdictLabel: Record<string, string> = {
  WRONG_ANSWER: '答案错误',
  TIME_LIMIT_EXCEEDED: '超时',
  RUNTIME_ERROR: '运行错误',
}

const verdictStyle: Record<string, string> = {
  WRONG_ANSWER: 'bg-red-100 text-red-700',
  TIME_LIMIT_EXCEEDED: 'bg-orange-100 text-orange-700',
  RUNTIME_ERROR: 'bg-yellow-100 text-yellow-700',
}

const getErrorMessage = (error: unknown): string => {
  const detail = (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail
  return detail || (error instanceof Error ? error.message : '加载错题本失败')
}

const WrongAnswers = () => {
  const [items, setItems] = useState<WrongBookItem[]>([])
  const [total, setTotal] = useState(0)
  const [filter, setFilter] = useState<Filter>('unresolved')
  const [recommendations, setRecommendations] = useState<Record<string, WrongBookRecommendation[]>>(
    {}
  )
  const [loading, setLoading] = useState(true)
  const [busyId, setBusyId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const loadItems = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const resolved = filter === 'all' ? undefined : filter === 'resolved'
      const response = await wrongbookApi.list({ resolved, page_size: 100 })
      setItems(response.data.items)
      setTotal(response.data.total)
    } catch (err: unknown) {
      setError(getErrorMessage(err))
    } finally {
      setLoading(false)
    }
  }, [filter])

  useEffect(() => {
    void loadItems()
  }, [loadItems])

  const retry = async (submissionId: string) => {
    setBusyId(submissionId)
    setError(null)
    try {
      await wrongbookApi.retry(submissionId)
      await loadItems()
    } catch (err: unknown) {
      setError(getErrorMessage(err))
    } finally {
      setBusyId(null)
    }
  }

  const toggleRecommendations = async (submissionId: string) => {
    if (recommendations[submissionId]) {
      setRecommendations((current) => {
        const next = { ...current }
        delete next[submissionId]
        return next
      })
      return
    }
    setBusyId(submissionId)
    try {
      const response = await wrongbookApi.recommendations(submissionId)
      setRecommendations((current) => ({ ...current, [submissionId]: response.data }))
    } catch (err: unknown) {
      setError(getErrorMessage(err))
    } finally {
      setBusyId(null)
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold text-gray-900">错题本</h1>
        <p className="mt-2 text-gray-600">自动同步 CF 非 AC 提交，并在后续 AC 后标记为已订正。</p>
      </div>

      {error ? (
        <div
          role="alert"
          className="flex items-start gap-3 rounded-xl border border-red-200 bg-red-50 p-4 text-red-700"
        >
          <AlertCircle className="mt-0.5 flex-shrink-0" size={20} />
          <span>{error}</span>
        </div>
      ) : null}

      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        <div className="rounded-xl border border-gray-100 bg-white p-6 shadow-sm">
          <BookX className="mb-2 text-red-600" />
          <p className="text-2xl font-bold">{total}</p>
          <p className="text-sm text-gray-500">当前筛选数量</p>
        </div>
        <button
          type="button"
          onClick={() => setFilter('unresolved')}
          className={`rounded-xl border p-6 text-left shadow-sm ${filter === 'unresolved' ? 'border-orange-300 bg-orange-50' : 'border-gray-100 bg-white'}`}
        >
          <RotateCcw className="mb-2 text-orange-600" />
          <p className="font-medium">待订正</p>
        </button>
        <button
          type="button"
          onClick={() => setFilter('resolved')}
          className={`rounded-xl border p-6 text-left shadow-sm ${filter === 'resolved' ? 'border-green-300 bg-green-50' : 'border-gray-100 bg-white'}`}
        >
          <CheckCircle2 className="mb-2 text-green-600" />
          <p className="font-medium">已订正</p>
        </button>
      </div>

      <div className="flex gap-2" aria-label="错题筛选">
        {(['all', 'unresolved', 'resolved'] as const).map((value) => (
          <button
            key={value}
            type="button"
            onClick={() => setFilter(value)}
            className={`rounded-full px-4 py-1.5 text-sm ${filter === value ? 'bg-blue-600 text-white' : 'bg-white text-gray-600'}`}
          >
            {value === 'all' ? '全部' : value === 'unresolved' ? '待订正' : '已订正'}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="flex h-48 items-center justify-center text-gray-500">
          <Loader2 className="mr-2 animate-spin" size={20} /> 加载中...
        </div>
      ) : items.length === 0 ? (
        <div className="rounded-xl border border-gray-100 bg-white p-12 text-center text-gray-500 shadow-sm">
          当前筛选下没有错题记录。
        </div>
      ) : (
        <div className="divide-y divide-gray-100 overflow-hidden rounded-xl border border-gray-100 bg-white shadow-sm">
          {items.map((item) => {
            const title =
              item.problem_title || `Codeforces ${item.cf_contest_id ?? ''}${item.cf_index ?? ''}`
            const recs = recommendations[item.submission_id]
            return (
              <article key={item.submission_id} className="p-6">
                <div className="flex flex-col justify-between gap-4 md:flex-row md:items-start">
                  <div>
                    <div className="flex flex-wrap items-center gap-2">
                      {item.problem_id ? (
                        <Link
                          to={`/problems/${item.problem_id}`}
                          className="text-lg font-medium text-gray-900 hover:text-blue-600"
                        >
                          {title}
                        </Link>
                      ) : (
                        <span className="text-lg font-medium text-gray-900">{title}</span>
                      )}
                      <span
                        className={`rounded px-2 py-0.5 text-xs ${verdictStyle[item.verdict] ?? 'bg-gray-100 text-gray-700'}`}
                      >
                        {verdictLabel[item.verdict] ?? item.verdict}
                      </span>
                      {item.resolved ? (
                        <span className="rounded bg-green-100 px-2 py-0.5 text-xs text-green-700">
                          已订正
                        </span>
                      ) : null}
                    </div>
                    <p className="mt-2 text-sm text-gray-500">
                      {new Date(item.submitted_at).toLocaleString()} · 已重试 {item.retry_count} 次
                    </p>
                    {item.knowledge_point_names.length ? (
                      <p className="mt-1 text-sm text-gray-500">
                        知识点：{item.knowledge_point_names.join('、')}
                      </p>
                    ) : null}
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {!item.resolved ? (
                      <button
                        type="button"
                        onClick={() => retry(item.submission_id)}
                        disabled={busyId === item.submission_id}
                        className="rounded-lg bg-blue-600 px-3 py-2 text-sm text-white hover:bg-blue-700 disabled:opacity-50"
                      >
                        记录一次重试
                      </button>
                    ) : null}
                    <button
                      type="button"
                      onClick={() => toggleRecommendations(item.submission_id)}
                      disabled={busyId === item.submission_id}
                      className="rounded-lg border border-gray-200 px-3 py-2 text-sm text-gray-700 hover:bg-gray-50 disabled:opacity-50"
                    >
                      {recs ? '收起推荐' : '同类题推荐'}
                    </button>
                  </div>
                </div>

                {recs ? (
                  <div className="mt-4 border-t border-gray-100 pt-4">
                    {recs.length ? (
                      <div className="flex flex-wrap gap-2">
                        {recs.map((problem) => (
                          <Link
                            key={problem.problem_id}
                            to={`/problems/${problem.problem_id}`}
                            className="flex items-center gap-1 rounded-lg bg-gray-50 px-3 py-2 text-sm text-gray-700 hover:bg-gray-100"
                          >
                            {problem.title}
                            {problem.cf_rating ? (
                              <span className="text-gray-400">CF {problem.cf_rating}</span>
                            ) : null}
                            <ChevronRight size={14} />
                          </Link>
                        ))}
                      </div>
                    ) : (
                      <p className="text-sm text-gray-500">暂未找到未 AC 的同类题。</p>
                    )}
                  </div>
                ) : null}
              </article>
            )
          })}
        </div>
      )}
    </div>
  )
}

export default WrongAnswers
