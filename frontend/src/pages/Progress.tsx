import React, { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Trophy,
  Target,
  TrendingUp,
  Calendar,
  AlertCircle,
  Loader2,
  ChevronDown,
  ChevronRight,
  LayoutList,
  BarChart3,
  RefreshCw,
  Map,
  ArrowRight,
  Zap,
  ExternalLink,
} from 'lucide-react'
import { progressApi, learningApi, notificationApi } from '../utils/api'
import type {
  MasteryByCategory,
  Progress,
  LearningPathRead,
  ActivityResponse,
  RecommendationResponse,
} from '../types'

type ViewMode = 'chart' | 'list'

/**
 * 格式化通过率：后端返回 0-1 浮点数，前端展示时 *100 并保留 1 位小数。
 * 例如 0.5 → "50.0%"，0.333 → "33.3%"。
 */
const formatAcceptanceRate = (rate: number): string => `${(rate * 100).toFixed(1)}%`

/** 按 mastery 值返回颜色类名 */
const masteryColor = (value: number): string => {
  if (value >= 80) return 'bg-green-500'
  if (value >= 50) return 'bg-amber-500'
  if (value > 0) return 'bg-red-500'
  return 'bg-gray-300'
}

/** 按 mastery 值返回文字颜色 */
const masteryTextColor = (value: number): string => {
  if (value >= 80) return 'text-green-600'
  if (value >= 50) return 'text-amber-600'
  if (value > 0) return 'text-red-500'
  return 'text-gray-400'
}

const ProgressPage: React.FC = () => {
  const navigate = useNavigate()
  const [progress, setProgress] = useState<Progress | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [viewMode, setViewMode] = useState<ViewMode>('chart')
  const [learningPath, setLearningPath] = useState<LearningPathRead | null>(null)

  useEffect(() => {
    let cancelled = false
    progressApi
      .getOverview()
      .then((resp) => {
        if (!cancelled) setProgress(resp.data as Progress)
      })
      .catch((err: unknown) => {
        if (cancelled) return
        setError(err instanceof Error ? err.message : '加载进度数据失败')
      })
      .finally(() => !cancelled && setLoading(false))
    return () => {
      cancelled = true
    }
  }, [])

  // 获取学习路径（独立加载，失败不影响主面板）
  useEffect(() => {
    let cancelled = false
    learningApi
      .getCurrentPath()
      .then((resp) => {
        if (!cancelled) setLearningPath(resp.data as LearningPathRead)
      })
      .catch(() => {
        // 路径数据加载失败静默处理，不阻塞主面板
      })
    return () => {
      cancelled = true
    }
  }, [])

  const [activity, setActivity] = useState<ActivityResponse | null>(null)

  // 获取学习活动数据（独立加载）
  useEffect(() => {
    let cancelled = false
    progressApi
      .getActivity(7)
      .then((resp) => {
        if (!cancelled) setActivity(resp.data as ActivityResponse)
      })
      .catch(() => {
        // 活动数据加载失败静默处理
      })
    return () => {
      cancelled = true
    }
  }, [])

  const [recommendations, setRecommendations] = useState<RecommendationResponse | null>(null)

  // 获取推荐题目（独立加载，失败静默处理）
  useEffect(() => {
    let cancelled = false
    notificationApi
      .getRecommendations()
      .then((resp) => {
        if (!cancelled) setRecommendations(resp.data as RecommendationResponse)
      })
      .catch(() => {
        // 推荐数据加载失败静默处理，不阻塞主面板
      })
    return () => {
      cancelled = true
    }
  }, [])

  /** 将知识点按 parent_name 分组，组内按 mastery 升序 */
  const groupedMastery = useMemo(() => {
    const groups: Record<string, MasteryByCategory[]> = {}
    for (const item of progress?.mastery_by_category ?? []) {
      const key = item.parent_name || '未分类'
      if (!groups[key]) groups[key] = []
      groups[key].push(item)
    }
    for (const key of Object.keys(groups)) {
      groups[key].sort((a, b) => a.value - b.value)
    }
    return groups
  }, [progress?.mastery_by_category])

  const groupNames = Object.keys(groupedMastery).sort()

  /** 薄弱知识点 ID 集合，用于快速判断 */
  const weakSet = useMemo(
    () => new Set(progress?.weak_knowledge_ids ?? []),
    [progress?.weak_knowledge_ids]
  )

  /** 柱状图数据：按一级分类聚合平均 mastery，按 mastery 升序（薄弱优先） */
  const chartData = useMemo(() => {
    const data = groupNames.map((name) => {
      const items = groupedMastery[name]
      const avg = items.length > 0 ? items.reduce((s, i) => s + i.value, 0) / items.length : 0
      return { name, value: Math.round(avg), count: items.length }
    })
    data.sort((a, b) => a.value - b.value)
    return data
  }, [groupedMastery, groupNames])

  const [collapsedGroups, setCollapsedGroups] = useState<Record<string, boolean>>({})

  const toggleGroup = (groupName: string) => {
    setCollapsedGroups((prev) => ({ ...prev, [groupName]: !prev[groupName] }))
  }

  /** 学习路径进度信息 */
  const pathProgress = useMemo(() => {
    if (!learningPath || learningPath.items.length === 0) return null
    const total = learningPath.items.length
    const done = learningPath.items.filter(
      (item) => item.status === 'done' || item.status === 'skipped'
    ).length
    const activeItem = learningPath.items.find((item) => item.status === 'active')
    return {
      total,
      done,
      percent: total > 0 ? Math.round((done / total) * 100) : 0,
      currentName: activeItem?.knowledge.name ?? null,
      currentIndex: activeItem?.position ?? null,
    }
  }, [learningPath])

  const stats = progress
    ? [
        {
          label: '已掌握知识点',
          value: `${progress.mastered_knowledge_points}`,
          total: `/${progress.total_knowledge_points}`,
          icon: Target,
          color: 'text-green-600 bg-green-100',
        },
        {
          label: '通过题目',
          value: `${progress.solved_problems}`,
          total: `/${progress.total_problems}`,
          icon: Trophy,
          color: 'text-blue-600 bg-blue-100',
        },
        {
          label: '通过率',
          value: formatAcceptanceRate(progress.acceptance_rate),
          icon: TrendingUp,
          color: 'text-purple-600 bg-purple-100',
        },
        {
          label: '连续打卡',
          value: `${progress.streak_days}`,
          total: '天',
          icon: Calendar,
          color: 'text-orange-600 bg-orange-100',
        },
      ]
    : []

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64 text-gray-500">
        <Loader2 className="animate-spin mr-2" size={20} />
        加载中...
      </div>
    )
  }

  if (error || !progress) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">学习进度</h1>
          <p className="text-gray-600 mt-2">查看你的学习数据和薄弱点</p>
        </div>
        <div className="bg-yellow-50 border border-yellow-200 rounded-xl p-6 flex items-start gap-3 text-yellow-800">
          <AlertCircle size={20} className="flex-shrink-0 mt-0.5" />
          <div className="text-sm">
            <p className="font-medium">进度数据暂不可用</p>
            <p className="mt-1 text-yellow-700">
              无法加载 <code>/api/v1/progress/overview</code> 的数据。请确认后端服务已启动、 user_id
              参数合法后重试。
            </p>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold text-gray-900">学习进度</h1>
        <p className="text-gray-600 mt-2">查看你的学习数据和薄弱点</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {stats.map((stat) => {
          const Icon = stat.icon
          return (
            <div
              key={stat.label}
              className="bg-white rounded-xl p-6 shadow-sm border border-gray-100"
            >
              <div
                className={`w-12 h-12 ${stat.color} rounded-xl flex items-center justify-center mb-4`}
              >
                <Icon size={24} />
              </div>
              <p className="text-gray-500 text-sm">{stat.label}</p>
              <p className="text-2xl font-bold text-gray-900 mt-1">
                {stat.value}
                {stat.total && (
                  <span className="text-base font-normal text-gray-500">{stat.total}</span>
                )}
              </p>
            </div>
          )
        })}
      </div>

      {/* 导航卡片：下一步行动 */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* 推荐练习 */}
        <div className="bg-white rounded-xl p-5 shadow-sm border border-gray-100">
          <div className="flex items-center gap-2 mb-3">
            <Zap size={18} className="text-amber-500" />
            <h3 className="font-semibold text-sm text-gray-800">推荐练习</h3>
            <span className="text-[10px] text-gray-400 ml-auto">beta</span>
          </div>
          {!recommendations || recommendations.items.length === 0 ? (
            <>
              <p className="text-sm text-gray-400">
                {recommendations === null ? '加载中...' : '暂无推荐，薄弱知识点已全部掌握'}
              </p>
            </>
          ) : (
            <div className="space-y-2 mb-3">
              {recommendations.items.slice(0, 2).map((item) => (
                <div key={item.knowledge_id}>
                  <div className="flex items-center gap-1.5 mb-1">
                    <span className="w-1.5 h-1.5 rounded-full bg-red-400 flex-shrink-0" />
                    <span
                      className="text-xs text-gray-700 truncate flex-1"
                      title={item.knowledge_name}
                    >
                      {item.knowledge_name}
                    </span>
                    <span className="text-[10px] font-medium text-red-500">{item.mastery}%</span>
                  </div>
                  <div className="ml-4 space-y-0.5">
                    {item.problems.slice(0, 2).map((p) => (
                      <button
                        key={p.problem_id}
                        type="button"
                        onClick={() => navigate(`/problems/${p.problem_id}`)}
                        className="flex items-center gap-1 text-xs text-blue-600 hover:text-blue-700 hover:underline w-full text-left"
                      >
                        <ExternalLink size={10} className="flex-shrink-0" />
                        <span className="truncate">{p.title}</span>
                        {p.cf_rating !== null && (
                          <span className="text-[10px] text-gray-400 flex-shrink-0">
                            *{p.cf_rating}
                          </span>
                        )}
                      </button>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}
          <button
            type="button"
            onClick={() => navigate('/today')}
            className="flex items-center gap-1 text-xs text-blue-600 hover:text-blue-700 font-medium"
          >
            查看今日学习 <ArrowRight size={12} />
          </button>
        </div>

        {/* 待复习提醒 */}
        <div className="bg-white rounded-xl p-5 shadow-sm border border-gray-100">
          <div className="flex items-center gap-2 mb-3">
            <RefreshCw size={18} className="text-purple-500" />
            <h3 className="font-semibold text-sm text-gray-800">待复习提醒</h3>
          </div>
          {progress.review_status === null ? (
            <p className="text-sm text-gray-400">暂无复习记录</p>
          ) : (
            <div className="mb-3">
              <p className="text-2xl font-bold text-purple-600">
                {progress.review_status.due_count}
                <span className="text-sm font-normal text-gray-400">
                  {' '}
                  / {progress.review_status.total_records}
                </span>
              </p>
              <p className="text-xs text-gray-500 mt-1">
                已完成 {progress.review_status.completed} 个知识点复习
              </p>
            </div>
          )}
          <button
            type="button"
            onClick={() => navigate('/review')}
            className="flex items-center gap-1 text-xs text-blue-600 hover:text-blue-700 font-medium"
          >
            去复习 <ArrowRight size={12} />
          </button>
        </div>

        {/* 学习路径进度 */}
        <div className="bg-white rounded-xl p-5 shadow-sm border border-gray-100">
          <div className="flex items-center gap-2 mb-3">
            <Map size={18} className="text-blue-500" />
            <h3 className="font-semibold text-sm text-gray-800">学习路径进度</h3>
          </div>
          {pathProgress === null ? (
            <p className="text-sm text-gray-400">暂无学习路径</p>
          ) : (
            <div className="mb-3">
              <p className="text-2xl font-bold text-blue-600">{pathProgress.percent}%</p>
              <p className="text-xs text-gray-500 mt-1">
                {pathProgress.currentName
                  ? `当前：${pathProgress.currentName}`
                  : `第 ${pathProgress.done}/${pathProgress.total} 步`}
              </p>
            </div>
          )}
          <button
            type="button"
            onClick={() => navigate('/knowledge')}
            className="flex items-center gap-1 text-xs text-blue-600 hover:text-blue-700 font-medium"
          >
            查看路线图 <ArrowRight size={12} />
          </button>
        </div>
      </div>

      {/* 知识点掌握度 */}
      <div className="bg-white rounded-xl p-6 shadow-sm border border-gray-100">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold">知识点掌握度</h2>
          {/* 视图切换 */}
          <div className="flex bg-gray-100 rounded-lg p-0.5">
            <button
              type="button"
              onClick={() => setViewMode('chart')}
              className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${
                viewMode === 'chart'
                  ? 'bg-white text-gray-900 shadow-sm'
                  : 'text-gray-500 hover:text-gray-700'
              }`}
            >
              <BarChart3 size={14} />
              分类
            </button>
            <button
              type="button"
              onClick={() => setViewMode('list')}
              className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${
                viewMode === 'list'
                  ? 'bg-white text-gray-900 shadow-sm'
                  : 'text-gray-500 hover:text-gray-700'
              }`}
            >
              <LayoutList size={14} />
              明细
            </button>
          </div>
        </div>

        {groupNames.length === 0 ? (
          <div className="h-40 flex items-center justify-center text-gray-400 text-sm">
            暂无掌握度数据
          </div>
        ) : viewMode === 'chart' ? (
          /* ---- 分类柱状图 ---- */
          <div className="space-y-2">
            {chartData.map((item) => (
              <div key={item.name} className="flex items-center gap-3">
                <span
                  className="text-sm text-gray-700 w-20 flex-shrink-0 truncate"
                  title={item.name}
                >
                  {item.name}
                </span>
                <div className="flex-1 h-4 bg-gray-100 rounded-full overflow-hidden">
                  <div
                    className={`h-full rounded-full transition-all ${masteryColor(item.value)}`}
                    style={{ width: `${Math.max(item.value, 3)}%` }}
                  />
                </div>
                <span
                  className={`text-sm font-medium w-10 text-right tabular-nums ${masteryTextColor(item.value)}`}
                >
                  {item.value}%
                </span>
              </div>
            ))}
            {/* 图例 */}
            <div className="flex items-center gap-4 text-xs text-gray-400 pt-2 border-t border-gray-100 mt-3">
              <span className="flex items-center gap-1">
                <span className="w-2.5 h-2.5 rounded-full bg-green-500" /> 已掌握
              </span>
              <span className="flex items-center gap-1">
                <span className="w-2.5 h-2.5 rounded-full bg-amber-500" /> 基本
              </span>
              <span className="flex items-center gap-1">
                <span className="w-2.5 h-2.5 rounded-full bg-red-500" /> 薄弱
              </span>
              <span className="flex items-center gap-1">
                <span className="w-2.5 h-2.5 rounded-full bg-gray-300" /> 未学
              </span>
            </div>
          </div>
        ) : (
          /* ---- 列表视图 ---- */
          <div className="space-y-2">
            {groupNames.map((groupName) => {
              const items = groupedMastery[groupName]
              const isCollapsed = collapsedGroups[groupName] ?? false
              const groupMastered = items.filter((i) => i.value >= 80).length
              return (
                <div key={groupName} className="border border-gray-100 rounded-lg">
                  <button
                    type="button"
                    onClick={() => toggleGroup(groupName)}
                    className="w-full flex items-center justify-between px-3 py-2 hover:bg-gray-50 rounded-lg transition-colors"
                  >
                    <div className="flex items-center gap-1.5">
                      {isCollapsed ? (
                        <ChevronRight size={14} className="text-gray-400" />
                      ) : (
                        <ChevronDown size={14} className="text-gray-400" />
                      )}
                      <span className="font-medium text-gray-800 text-xs">{groupName}</span>
                      <span className="text-xs text-gray-400">
                        {groupMastered}/{items.length}
                      </span>
                    </div>
                  </button>
                  {!isCollapsed && (
                    <div className="px-3 pb-2 space-y-1.5">
                      {items.map((item) => {
                        const isWeak = weakSet.has(item.knowledge_id)
                        return (
                          <div key={item.knowledge_id} className="flex items-center gap-2">
                            <span
                              className="flex items-center gap-1 text-xs text-gray-600 w-24 flex-shrink-0 truncate"
                              title={item.name}
                            >
                              {isWeak && (
                                <span className="text-red-400 text-[8px] leading-none">●</span>
                              )}
                              {item.name}
                            </span>
                            <div
                              className={`flex-1 h-1.5 rounded-full overflow-hidden ${isWeak ? 'ring-1 ring-red-200 bg-red-50' : 'bg-gray-100'}`}
                            >
                              <div
                                className={`h-full rounded-full transition-all ${masteryColor(item.value)}`}
                                style={{ width: `${Math.max(item.value, 3)}%` }}
                              />
                            </div>
                            <span
                              className={`text-xs font-medium w-10 text-right tabular-nums ${masteryTextColor(item.value)}`}
                            >
                              {item.value}%
                            </span>
                          </div>
                        )
                      })}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        )}
      </div>

      {progress.target_progress && (
        <div className="bg-white rounded-xl p-6 shadow-sm border border-gray-100">
          <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
            <Target className="text-blue-500" size={20} />
            训练目标完成进度
          </h2>
          <div className="flex items-center justify-between mb-2">
            <span className="text-gray-600">
              目标 Rating 区间：{progress.target_progress.target_rating_min} -{' '}
              {progress.target_progress.target_rating_max}
            </span>
            <span className="text-2xl font-bold text-gray-900">
              {progress.target_progress.progress_percent}%
            </span>
          </div>
          <div className="h-3 bg-gray-100 rounded-full overflow-hidden">
            <div
              className="h-full bg-blue-500 rounded-full transition-all"
              style={{ width: `${progress.target_progress.progress_percent}%` }}
            />
          </div>
          <p className="text-sm text-gray-500 mt-2">
            已掌握 {progress.target_progress.mastered_in_range} /{' '}
            {progress.target_progress.total_in_range} 个知识点
          </p>
        </div>
      )}

      {/* 学习活动日历 */}
      {activity && activity.days.length > 0 && (
        <div className="bg-white rounded-xl p-6 shadow-sm border border-gray-100">
          <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
            <Calendar className="text-green-500" size={20} />
            学习活动
            <span className="text-sm font-normal text-gray-400 ml-auto">
              本周 {activity.total_week} 题
              {activity.total_last_week > 0 && ` · 上周 ${activity.total_last_week} 题`}
            </span>
          </h2>
          <div className="flex items-end gap-1.5 h-24">
            {activity.days.map((day) => {
              const maxCount = Math.max(...activity.days.map((d) => d.count), 1)
              const height = Math.max((day.count / maxCount) * 100, 4)
              const isToday = day.date === activity.days[activity.days.length - 1]?.date
              return (
                <div key={day.date} className="flex-1 flex flex-col items-center gap-1">
                  <span className="text-xs text-gray-500 tabular-nums">{day.count}</span>
                  <div
                    className={`w-full rounded-t transition-all ${
                      day.count > 0 ? (isToday ? 'bg-green-500' : 'bg-green-300') : 'bg-gray-100'
                    }`}
                    style={{ height: `${height}%` }}
                    title={`${day.date}: ${day.count} 题`}
                  />
                  <span
                    className={`text-[10px] ${isToday ? 'text-green-600 font-medium' : 'text-gray-400'}`}
                  >
                    {new Date(day.date)
                      .toLocaleDateString('zh-CN', { weekday: 'short' })
                      .replace('周', '')}
                  </span>
                </div>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}

export default ProgressPage
