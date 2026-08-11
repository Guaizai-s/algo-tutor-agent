import React, { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  Calendar,
  BookOpen,
  Code2,
  Target,
  AlertTriangle,
  RefreshCw,
  CheckCircle2,
  Circle,
  ChevronRight,
  Sparkles,
} from 'lucide-react'
import { dailyTaskApi, learningApi, DEV_USER_ID } from '../utils/api'
import type {
  DailyTaskItemRead,
  DailyTaskItemUpdateResponse,
  DailyTaskTodayResponse,
} from '../types'

const TodayTask: React.FC = () => {
  const [data, setData] = useState<DailyTaskTodayResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [regenerating, setRegenerating] = useState(false)
  const [progress, setProgress] = useState({ done: 0, total: 0 })

  const loadAll = async () => {
    setLoading(true)
    setError(null)
    try {
      try {
        await learningApi.getCurrentPath(DEV_USER_ID)
      } catch (err: unknown) {
        const status = (err as { response?: { status?: number } })?.response?.status
        if (status !== 404) {
          throw err
        }
        await learningApi.generatePath({
          user_id: DEV_USER_ID,
          preview_count: 8,
        })
      }
      const todayResp = await dailyTaskApi.getToday(DEV_USER_ID)
      setData(todayResp.data)
      // 从服务器数据初始化进度
      const items = todayResp.data.task.items
      const done = items.filter((i) => i.status === 'done').length
      setProgress({ done, total: items.length })
    } catch (err: unknown) {
      const msg =
        err instanceof Error && err.message
          ? err.message
          : '获取今日任务失败，请确认后端已启动并完成 Task 10 迁移'
      setError(msg)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadAll()
  }, [])

  const handleToggleItem = async (item: DailyTaskItemRead) => {
    if (!data) return
    const newStatus = item.status === 'done' ? 'skipped' : 'done'
    try {
      const resp = await dailyTaskApi.updateItem(data.task.id, item.id, newStatus)
      const result = resp.data as DailyTaskItemUpdateResponse
      // 更新本地 item 状态
      setData((prev) => {
        if (!prev) return prev
        return {
          ...prev,
          task: {
            ...prev.task,
            items: prev.task.items.map((i) => (i.id === item.id ? result.item : i)),
          },
        }
      })
      setProgress({ done: result.task_done, total: result.task_total })
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : '更新任务状态失败'
      setError(msg)
    }
  }

  const handleRegenerate = async () => {
    setRegenerating(true)
    setError(null)
    try {
      await learningApi.generatePath({
        user_id: DEV_USER_ID,
        preview_count: 8,
      })
      const todayResp = await dailyTaskApi.getToday(DEV_USER_ID)
      setData(todayResp.data)
      const items = todayResp.data.task.items
      const done = items.filter((i) => i.status === 'done').length
      setProgress({ done, total: items.length })
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : '重新生成学习路径失败'
      setError(msg)
    } finally {
      setRegenerating(false)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20 text-gray-500">
        <RefreshCw size={20} className="animate-spin mr-2" />
        正在生成今日学习任务...
      </div>
    )
  }

  if (error) {
    return (
      <div className="bg-red-50 border border-red-200 rounded-xl p-6 flex items-start gap-3 text-red-800">
        <AlertTriangle size={20} className="flex-shrink-0 mt-0.5" />
        <div className="flex-1">
          <p className="font-medium">加载失败</p>
          <p className="mt-1 text-sm text-red-700 break-all">{error}</p>
          <button
            onClick={loadAll}
            className="mt-3 px-3 py-1.5 text-sm bg-red-600 text-white rounded-lg hover:bg-red-700"
          >
            重试
          </button>
        </div>
      </div>
    )
  }

  if (!data || !data.task) {
    return (
      <div className="bg-white rounded-xl p-10 shadow-sm border border-gray-100 text-center text-gray-500">
        <Calendar size={32} className="mx-auto mb-3 text-gray-400" />
        <p className="font-medium text-gray-700">今日暂无学习任务</p>
        <p className="mt-1 text-sm">请先生成学习路径，或等待系统为你规划。</p>
        <button
          onClick={handleRegenerate}
          disabled={regenerating}
          className="mt-4 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
        >
          {regenerating ? '生成中...' : '生成学习路径'}
        </button>
      </div>
    )
  }

  const { task, path_preview } = data

  return (
    <div className="space-y-6">
      {/* 头部 */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">今日学习</h1>
          <p className="text-gray-600 mt-2 flex items-center gap-2">
            <Calendar size={16} />
            {task.task_date}
          </p>
        </div>
        <button
          onClick={handleRegenerate}
          disabled={regenerating}
          className="flex items-center gap-2 px-3 py-2 text-sm bg-white border border-gray-200 rounded-lg hover:bg-gray-50 disabled:opacity-50"
        >
          <RefreshCw size={16} className={regenerating ? 'animate-spin' : ''} />
          重新生成路径
        </button>
      </div>

      {/* 进度条 */}
      <div className="bg-white rounded-xl p-4 shadow-sm border border-gray-100">
        <div className="flex items-center justify-between mb-2">
          <span className="text-sm text-gray-600">
            已完成 {progress.done} / {progress.total} 项
          </span>
          <span className="text-sm font-semibold text-gray-900">
            {progress.total > 0 ? Math.round((progress.done / progress.total) * 100) : 0}%
          </span>
        </div>
        <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
          <div
            className="h-full bg-green-500 rounded-full transition-all duration-500"
            style={{ width: `${progress.total > 0 ? (progress.done / progress.total) * 100 : 0}%` }}
          />
        </div>
      </div>

      {/* 全部完成庆祝 */}
      {progress.done === progress.total && progress.total > 0 && (
        <div className="bg-green-50 border border-green-200 rounded-xl p-6 flex items-center gap-4">
          <CheckCircle2 className="text-green-500 flex-shrink-0" size={28} />
          <div>
            <p className="font-semibold text-green-800">今日任务全部完成!</p>
            <p className="text-sm text-green-600 mt-1">已自动打卡，明天继续加油</p>
          </div>
        </div>
      )}

      {/* 当前知识点 */}
      <div
        className={`rounded-xl p-6 shadow-sm border ${
          task.is_remediation ? 'bg-orange-50 border-orange-200' : 'bg-white border-gray-100'
        }`}
      >
        <div className="flex items-center gap-3">
          {task.is_remediation ? (
            <Sparkles className="text-orange-500" size={24} />
          ) : (
            <Target className="text-blue-500" size={24} />
          )}
          <div>
            <p className="text-sm text-gray-500">
              {task.is_remediation ? '补漏任务' : '当前知识点'}
            </p>
            <p className="text-xl font-semibold text-gray-900">{task.knowledge.name}</p>
          </div>
        </div>
      </div>

      {/* 路径预览 */}
      {path_preview.length > 0 && (
        <div className="bg-white rounded-xl p-6 shadow-sm border border-gray-100">
          <h2 className="text-lg font-semibold text-gray-900 mb-3 flex items-center gap-2">
            <ChevronRight size={18} className="text-gray-400" />
            学习路径预览
          </h2>
          <div className="flex flex-wrap gap-2">
            {path_preview.map((p, idx) => (
              <div
                key={p.knowledge_id}
                className={`flex items-center gap-2 px-3 py-1.5 rounded-full text-sm border ${
                  p.kind === 'remediation'
                    ? 'bg-orange-50 border-orange-200 text-orange-700'
                    : 'bg-gray-50 border-gray-200 text-gray-700'
                }`}
              >
                <span className="text-gray-400">{idx + 1}.</span>
                <span>{p.name}</span>
                {p.kind === 'remediation' && (
                  <span className="text-xs px-1.5 py-0.5 bg-orange-200 text-orange-800 rounded">
                    补漏
                  </span>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 任务项列表 */}
      <div className="space-y-3">
        <h2 className="text-lg font-semibold text-gray-900">今日任务清单</h2>
        {task.items.map((item) => (
          <TaskItemCard key={item.id} item={item} onToggle={() => handleToggleItem(item)} />
        ))}
      </div>

      {/* 候选不足提示 */}
      {task.missing_slots.length > 0 && (
        <div className="bg-yellow-50 border border-yellow-200 rounded-xl p-4 flex items-start gap-3 text-yellow-800">
          <AlertTriangle size={20} className="flex-shrink-0 mt-0.5" />
          <div className="text-sm">
            <p className="font-medium">部分任务候选不足</p>
            <p className="mt-1 text-yellow-700">
              以下槽位未能匹配到合适内容：{task.missing_slots.join(', ')}
            </p>
            <p className="mt-1 text-yellow-600">已展示可用部分，缺失槽位后续可补全。</p>
          </div>
        </div>
      )}
    </div>
  )
}

const TaskItemCard: React.FC<{ item: DailyTaskItemRead; onToggle: () => void }> = ({
  item,
  onToggle,
}) => {
  const isLecture = item.item_type === 'lecture_card'
  const isDone = item.status === 'done'
  const isMissing = !item.lecture && !item.problem

  const icon = isLecture ? BookOpen : Code2
  const Icon = icon
  const title = item.lecture?.title || item.problem?.title || slotLabel(item.item_type)

  return (
    <div
      className={`bg-white rounded-xl p-5 shadow-sm border flex items-center justify-between ${
        isMissing ? 'border-yellow-200 bg-yellow-50/50' : 'border-gray-100'
      } ${isDone ? 'opacity-70' : ''}`}
    >
      <div className="flex items-center gap-4 flex-1 min-w-0">
        <div
          className={`w-10 h-10 rounded-lg flex items-center justify-center flex-shrink-0 ${
            isLecture ? 'bg-green-100 text-green-600' : 'bg-blue-100 text-blue-600'
          }`}
        >
          <Icon size={20} />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-xs px-2 py-0.5 bg-gray-100 text-gray-600 rounded">
              {slotLabel(item.item_type)}
            </span>
            {item.problem?.cf_rating != null && (
              <span className="text-xs px-2 py-0.5 bg-purple-100 text-purple-600 rounded">
                CF {item.problem.cf_rating}
              </span>
            )}
            {isMissing && (
              <span className="text-xs px-2 py-0.5 bg-yellow-100 text-yellow-700 rounded">
                缺失
              </span>
            )}
            {isDone && (
              <span className="text-xs px-2 py-0.5 bg-green-100 text-green-700 rounded">
                已完成
              </span>
            )}
          </div>
          <p
            className={`font-medium mt-1 truncate ${isDone ? 'text-gray-400 line-through' : 'text-gray-900'}`}
          >
            {title}
          </p>
          {item.missing_reason && (
            <p className="text-xs text-yellow-700 mt-0.5">{item.missing_reason}</p>
          )}
        </div>
      </div>
      <div className="flex items-center gap-3 flex-shrink-0">
        <button
          type="button"
          onClick={onToggle}
          className="focus:outline-none"
          disabled={isMissing}
          title={isDone ? '标记为未完成' : '标记为已完成'}
        >
          {isDone ? (
            <CheckCircle2
              className="text-green-500 hover:text-green-600 transition-colors"
              size={22}
            />
          ) : (
            <Circle className="text-gray-300 hover:text-gray-400 transition-colors" size={22} />
          )}
        </button>
        {item.problem && (
          <Link
            to={`/problems/${item.problem.id}`}
            className="text-blue-600 hover:underline text-sm whitespace-nowrap"
          >
            去做题 →
          </Link>
        )}
        {item.lecture && (
          <Link
            to={`/knowledge/${item.lecture.knowledge_id}`}
            className="text-blue-600 hover:underline text-sm whitespace-nowrap"
          >
            查看讲义 →
          </Link>
        )}
      </div>
    </div>
  )
}

function slotLabel(type: string): string {
  switch (type) {
    case 'lecture_card':
      return 'CARD 讲义'
    case 'template_problem':
      return '模板题'
    case 'application_problem':
      return '应用题'
    case 'challenge_problem':
      return '挑战题'
    default:
      return type
  }
}

export default TodayTask
