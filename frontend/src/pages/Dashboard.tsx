import React, { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  BookOpen,
  Code2,
  RefreshCw,
  BookX,
  MessageSquare,
  TrendingUp,
  CheckCircle2,
  AlertCircle,
} from 'lucide-react'
import { progressApi } from '../utils/api'
import type { Progress } from '../types'

const Dashboard: React.FC = () => {
  const [progress, setProgress] = useState<Progress | null>(null)
  const [progressError, setProgressError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    progressApi
      .getOverview()
      .then((resp) => {
        if (!cancelled) setProgress(resp.data as Progress)
      })
      .catch((err: unknown) => {
        if (cancelled) return
        // 进度 API 尚未由后端实现（Task 11）。降级为空状态而不是崩溃。
        const msg = err instanceof Error ? err.message : '进度数据暂不可用'
        setProgressError(msg)
      })
    return () => {
      cancelled = true
    }
  }, [])

  const quickActions = [
    { path: '/problems', label: '开始刷题', icon: Code2, color: 'bg-blue-500' },
    { path: '/knowledge', label: '学习知识点', icon: BookOpen, color: 'bg-green-500' },
    { path: '/review', label: '今日复习', icon: RefreshCw, color: 'bg-orange-500' },
    { path: '/ai-chat', label: 'AI 问答', icon: MessageSquare, color: 'bg-purple-500' },
  ]

  const stats = progress
    ? [
        {
          label: '已掌握知识点',
          value: `${progress.mastered_knowledge_points}`,
          total: `/${progress.total_knowledge_points}`,
          icon: CheckCircle2,
          color: 'bg-green-100 text-green-600',
          progress:
            progress.total_knowledge_points > 0
              ? (progress.mastered_knowledge_points / progress.total_knowledge_points) * 100
              : 0,
        },
        {
          label: '通过题目',
          value: `${progress.solved_problems}`,
          total: `/${progress.total_problems}`,
          icon: Code2,
          color: 'bg-blue-100 text-blue-600',
        },
        {
          label: '错题本',
          value: `${progress.unresolved_wrong_answers}`,
          icon: BookX,
          color: 'bg-red-100 text-red-600',
          link: '/wrong-answers',
        },
        {
          label: '待复习',
          value: '—',
          icon: RefreshCw,
          color: 'bg-orange-100 text-orange-600',
          link: '/review',
        },
      ]
    : []

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-3xl font-bold text-gray-900">欢迎回来！</h1>
        <p className="text-gray-600 mt-2">今天也要加油练习算法哦</p>
      </div>

      {progressError && (
        <div className="bg-yellow-50 border border-yellow-200 rounded-xl p-4 flex items-start gap-3 text-yellow-800">
          <AlertCircle size={20} className="flex-shrink-0 mt-0.5" />
          <div className="text-sm">
            <p className="font-medium">学习进度数据暂不可用</p>
            <p className="mt-1 text-yellow-700">
              后端进度 API（Task 11）尚未实现，下面快捷入口仍可使用。
            </p>
          </div>
        </div>
      )}

      {progress ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
          {stats.map((stat) => {
            const Icon = stat.icon
            const content = (
              <>
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-gray-500 text-sm">{stat.label}</p>
                    <p className="text-3xl font-bold text-gray-900 mt-1">
                      {stat.value}
                      {stat.total && (
                        <span className="text-base font-normal text-gray-500">{stat.total}</span>
                      )}
                    </p>
                  </div>
                  <div
                    className={`w-12 h-12 ${stat.color} rounded-xl flex items-center justify-center`}
                  >
                    <Icon size={24} />
                  </div>
                </div>
                {typeof stat.progress === 'number' && (
                  <div className="mt-4 h-2 bg-gray-100 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-green-500 rounded-full"
                      style={{ width: `${stat.progress}%` }}
                    />
                  </div>
                )}
                {stat.link && (
                  <p className="text-sm text-blue-600 hover:underline mt-4">查看详情 →</p>
                )}
              </>
            )
            return stat.link ? (
              <Link
                key={stat.label}
                to={stat.link}
                className="bg-white rounded-xl p-6 shadow-sm border border-gray-100 hover:shadow-md transition-shadow"
              >
                {content}
              </Link>
            ) : (
              <div
                key={stat.label}
                className="bg-white rounded-xl p-6 shadow-sm border border-gray-100"
              >
                {content}
              </div>
            )
          })}
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
          {quickActions.map((action) => {
            const Icon = action.icon
            return (
              <Link
                key={action.path}
                to={action.path}
                className="bg-white rounded-xl p-6 shadow-sm border border-gray-100 hover:shadow-md transition-shadow"
              >
                <div
                  className={`w-12 h-12 ${action.color} rounded-xl flex items-center justify-center mb-4`}
                >
                  <Icon className="text-white" size={24} />
                </div>
                <p className="font-medium text-gray-900">{action.label}</p>
              </Link>
            )
          })}
        </div>
      )}

      <div>
        <h2 className="text-xl font-semibold text-gray-900 mb-4">快捷入口</h2>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {quickActions.map((action) => {
            const Icon = action.icon
            return (
              <Link
                key={action.path}
                to={action.path}
                className="bg-white rounded-xl p-6 shadow-sm border border-gray-100 hover:shadow-md transition-shadow group"
              >
                <div
                  className={`w-12 h-12 ${action.color} rounded-xl flex items-center justify-center mb-4 group-hover:scale-110 transition-transform`}
                >
                  <Icon className="text-white" size={24} />
                </div>
                <p className="font-medium text-gray-900">{action.label}</p>
              </Link>
            )
          })}
        </div>
      </div>

      <div>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-xl font-semibold text-gray-900">推荐题目</h2>
          <Link to="/problems" className="text-blue-600 hover:underline text-sm">
            查看全部 →
          </Link>
        </div>
        <div className="bg-white rounded-xl p-6 shadow-sm border border-gray-100 text-center text-gray-500">
          <TrendingUp size={24} className="mx-auto mb-2 text-gray-400" />
          推荐功能由智能推送引擎（Task 12）提供，暂未启用
        </div>
      </div>
    </div>
  )
}

export default Dashboard
