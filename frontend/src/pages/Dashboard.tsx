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
  Link2,
  ExternalLink,
  Zap,
} from 'lucide-react'
import { progressApi, notificationApi } from '../utils/api'
import { useAuthStore } from '../stores/authStore'
import type { Progress, RecommendationResponse } from '../types'

const Dashboard: React.FC = () => {
  const [progress, setProgress] = useState<Progress | null>(null)
  const [progressError, setProgressError] = useState<string | null>(null)
  const [recommendations, setRecommendations] = useState<RecommendationResponse | null>(null)
  const { user } = useAuthStore()
  const cfBound = !!user?.cf_handle

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

  useEffect(() => {
    let cancelled = false
    notificationApi
      .getRecommendations()
      .then((resp) => {
        if (!cancelled) setRecommendations(resp.data as RecommendationResponse)
      })
      .catch(() => {})
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
          value: '—',
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

      {/* 摸底测试引导卡 */}
      <div className="bg-blue-50 border border-blue-200 rounded-xl p-4 flex items-start gap-3">
        <div className="w-10 h-10 bg-blue-100 rounded-lg flex items-center justify-center text-blue-600 flex-shrink-0">
          <Zap size={20} />
        </div>
        <div className="flex-1">
          <p className="font-medium text-blue-900">还没有做过摸底测试？</p>
          <p className="text-sm text-blue-700 mt-0.5">
            通过 15
            道覆盖核心知识点的诊断题，系统能快速判断你的真实水平，并据此定制每日学习推送，让题目难度与你的能力精准匹配。
          </p>
        </div>
        <Link
          to="/assess"
          className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium rounded-lg transition-colors flex-shrink-0"
        >
          开始摸底
        </Link>
      </div>

      {/* CF 绑定状态卡片 */}
      {cfBound ? (
        <div className="bg-green-50 border border-green-200 rounded-xl p-4 flex items-start gap-3">
          <div className="w-10 h-10 bg-green-100 rounded-lg flex items-center justify-center text-green-600 flex-shrink-0">
            <Link2 size={20} />
          </div>
          <div className="flex-1">
            <p className="font-medium text-green-900">
              Codeforces 已绑定：
              <a
                href={`https://codeforces.com/profile/${user?.cf_handle}`}
                target="_blank"
                rel="noopener noreferrer"
                className="text-green-700 hover:underline inline-flex items-center gap-1 ml-1"
              >
                {user?.cf_handle}
                <ExternalLink size={14} />
              </a>
            </p>
            <p className="text-sm text-green-700 mt-0.5">
              系统每 5 分钟自动同步你的 CF 提交记录，AC 的题目会自动计入掌握度。
            </p>
          </div>
          <Link
            to="/profile"
            className="text-sm text-green-700 hover:text-green-900 hover:underline flex-shrink-0"
          >
            管理 →
          </Link>
        </div>
      ) : (
        <div className="bg-orange-50 border border-orange-200 rounded-xl p-4 flex items-start gap-3">
          <div className="w-10 h-10 bg-orange-100 rounded-lg flex items-center justify-center text-orange-600 flex-shrink-0">
            <AlertCircle size={20} />
          </div>
          <div className="flex-1">
            <p className="font-medium text-orange-900">尚未绑定 Codeforces 账号</p>
            <p className="text-sm text-orange-700 mt-0.5">
              题库里的题目来自 Codeforces。绑定 CF 账号后，系统才能自动同步你的提交结果与 AC
              状态，否则题库无法记录你的练习进度。
            </p>
          </div>
          <Link
            to="/profile"
            className="px-4 py-2 bg-orange-600 hover:bg-orange-700 text-white text-sm font-medium rounded-lg transition-colors flex-shrink-0"
          >
            去绑定
          </Link>
        </div>
      )}

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
        <div className="bg-white rounded-xl p-6 shadow-sm border border-gray-100">
          {!recommendations || recommendations.items.length === 0 ? (
            <div className="text-center text-gray-500 py-2">
              <TrendingUp size={24} className="mx-auto mb-2 text-gray-400" />
              {recommendations === null ? '加载中...' : '暂无推荐，薄弱知识点已全部掌握'}
            </div>
          ) : (
            <div className="space-y-3">
              {recommendations.items.map((item) => (
                <div key={item.knowledge_id}>
                  <div className="flex items-center gap-2 mb-1.5">
                    <Zap size={14} className="text-amber-500 flex-shrink-0" />
                    <span
                      className="text-sm font-medium text-gray-800 truncate flex-1"
                      title={item.knowledge_name}
                    >
                      {item.knowledge_name}
                    </span>
                    <span className="text-xs font-medium text-red-500 bg-red-50 px-1.5 py-0.5 rounded">
                      {item.mastery}%
                    </span>
                  </div>
                  <div className="ml-6 space-y-1">
                    {item.problems.map((p) => (
                      <Link
                        key={p.problem_id}
                        to={`/problems/${p.problem_id}`}
                        className="flex items-center gap-1.5 text-sm text-blue-600 hover:text-blue-700 hover:underline"
                      >
                        <ExternalLink size={12} className="flex-shrink-0" />
                        <span className="truncate">{p.title}</span>
                        {p.cf_rating !== null && (
                          <span className="text-xs text-gray-400 flex-shrink-0 ml-auto">
                            *{p.cf_rating}
                          </span>
                        )}
                      </Link>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

export default Dashboard
