import React, { useEffect, useState } from 'react'
import {
  RadarChart,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  Radar,
  ResponsiveContainer,
} from 'recharts'
import { BarChart3, Trophy, Target, TrendingUp, Calendar, AlertCircle, Loader2 } from 'lucide-react'
import { progressApi, DEV_USER_ID } from '../utils/api'
import type { Progress } from '../types'

/**
 * 格式化通过率：后端返回 0-1 浮点数，前端展示时 *100 并保留 1 位小数。
 * 例如 0.5 → "50.0%"，0.333 → "33.3%"。
 */
const formatAcceptanceRate = (rate: number): string => `${(rate * 100).toFixed(1)}%`

const ProgressPage: React.FC = () => {
  const [progress, setProgress] = useState<Progress | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    progressApi
      .getOverview(DEV_USER_ID)
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

  const radarData =
    progress?.mastery_by_category?.map((c) => ({
      subject: c.name,
      A: c.value,
      fullMark: 100,
    })) || []

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

  // 薄弱知识点：严格使用后端 weak_knowledge_ids，不再前端推断。
  // 通过 knowledge_id 映射名称与 mastery 百分比。
  const weakIdSet = new Set(progress?.weak_knowledge_ids ?? [])
  const weakPoints =
    progress?.mastery_by_category
      ?.filter((c) => weakIdSet.has(c.knowledge_id))
      .map((c) => ({
        name: c.name,
        rate: c.value,
        suggestion: `建议复习 ${c.name} 相关知识点与练习题`,
      })) || []

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

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-white rounded-xl p-6 shadow-sm border border-gray-100">
          <h2 className="text-lg font-semibold mb-4">知识点掌握度</h2>
          {radarData.length > 0 ? (
            <div className="h-80">
              <ResponsiveContainer width="100%" height="100%">
                <RadarChart data={radarData}>
                  <PolarGrid />
                  <PolarAngleAxis dataKey="subject" />
                  <PolarRadiusAxis angle={30} domain={[0, 100]} />
                  <Radar
                    name="掌握度"
                    dataKey="A"
                    stroke="#3b82f6"
                    fill="#3b82f6"
                    fillOpacity={0.3}
                  />
                </RadarChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <div className="h-80 flex items-center justify-center text-gray-400 text-sm">
              暂无掌握度数据
            </div>
          )}
        </div>

        <div className="bg-white rounded-xl p-6 shadow-sm border border-gray-100">
          <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
            <BarChart3 className="text-red-500" size={20} />
            薄弱知识点
          </h2>
          {weakPoints.length > 0 ? (
            <div className="space-y-4">
              {weakPoints.map((point) => (
                <div key={point.name}>
                  <div className="flex items-center justify-between mb-1">
                    <span className="font-medium text-gray-900">{point.name}</span>
                    <span className="text-sm text-gray-500">{point.rate}%</span>
                  </div>
                  <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-red-500 rounded-full"
                      style={{ width: `${point.rate}%` }}
                    />
                  </div>
                  <p className="text-sm text-gray-500 mt-1">{point.suggestion}</p>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-gray-400 text-sm py-8 text-center">暂无薄弱知识点</div>
          )}
        </div>
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
    </div>
  )
}

export default ProgressPage
