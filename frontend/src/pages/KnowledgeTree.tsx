import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  AlertCircle,
  BookOpen,
  Brain,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Code2,
  Loader2,
  Search,
  Sparkles,
  Target,
  X,
  type LucideIcon,
} from 'lucide-react'
import { knowledgeApi, learningApi, coldstartApi, dailyTaskApi } from '../utils/api'
import type {
  KnowledgePointRef,
  RoadmapKnowledgeNode,
  RoadmapNodeStatus,
  DailyTaskTodayResponse,
} from '../types'

interface KnowledgeNode extends RoadmapKnowledgeNode {
  children: KnowledgeNode[]
}

// 10 个一级分类 → 颜色 + 图标（用于根节点视觉区分）
const CATEGORY_META: Record<string, { color: string; icon: LucideIcon }> = {
  入门: { color: 'text-green-600', icon: BookOpen },
  基础: { color: 'text-blue-600', icon: BookOpen },
  数据结构: { color: 'text-violet-600', icon: BookOpen },
  图论: { color: 'text-emerald-600', icon: BookOpen },
  动态规划: { color: 'text-amber-600', icon: BookOpen },
  字符串: { color: 'text-pink-600', icon: BookOpen },
  搜索: { color: 'text-cyan-600', icon: BookOpen },
  数学: { color: 'text-orange-600', icon: BookOpen },
  杂项: { color: 'text-slate-600', icon: BookOpen },
  竞赛: { color: 'text-red-600', icon: BookOpen },
}

// 状态 → 视觉配置
const STATUS_STYLE: Record<
  RoadmapNodeStatus,
  { bg: string; border: string; text: string; icon: React.ReactNode }
> = {
  done: {
    bg: 'bg-green-50/60',
    border: 'border-l-green-400',
    text: 'text-green-700',
    icon: <CheckCircle2 size={14} className="text-green-500 flex-shrink-0" />,
  },
  active: {
    bg: 'bg-blue-50',
    border: 'border-l-blue-500',
    text: 'text-blue-700',
    icon: <Target size={14} className="text-blue-500 flex-shrink-0 animate-pulse" />,
  },
  pending: {
    bg: 'bg-white',
    border: 'border-l-transparent',
    text: 'text-gray-600',
    icon: null,
  },
  unlocked: {
    bg: 'bg-white',
    border: 'border-l-transparent',
    text: 'text-gray-700',
    icon: null,
  },
  none: {
    bg: 'bg-white',
    border: 'border-l-transparent',
    text: 'text-gray-600',
    icon: null,
  },
}

const STATUS_LABEL: Record<RoadmapNodeStatus, string> = {
  done: '已掌握',
  active: '学习中',
  pending: '待学习',
  unlocked: '可学习',
  none: '未开始',
}

// "其他"子分类判断
const isOtherCategory = (name: string) => name.startsWith('其他')

// 叶子节点计数
const countLeaves = (n: KnowledgeNode): number =>
  n.children.length === 0 ? 1 : n.children.reduce((s, c) => s + countLeaves(c), 0)
const countDoneLeaves = (n: KnowledgeNode): number =>
  n.children.length === 0
    ? n.status === 'done'
      ? 1
      : 0
    : n.children.reduce((s, c) => s + countDoneLeaves(c), 0)

const KnowledgeTree: React.FC = () => {
  const [tree, setTree] = useState<KnowledgeNode[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [expanded, setExpanded] = useState<Set<string>>(new Set())
  const [hasPath, setHasPath] = useState(false)
  const [pathPreview, setPathPreview] = useState<KnowledgePointRef[]>([])
  const [generatingPath, setGeneratingPath] = useState(false)
  const [markingMastered, setMarkingMastered] = useState<Set<string>>(new Set())
  const [searchQuery, setSearchQuery] = useState('')
  const [statusFilter, setStatusFilter] = useState<RoadmapNodeStatus | 'all'>('all')
  const [todayTask, setTodayTask] = useState<DailyTaskTodayResponse | null>(null)

  const loadData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      // 并行加载知识树、路线图状态和今日任务
      const [treeResp, roadmapResp, todayResp] = await Promise.all([
        knowledgeApi.getTree(),
        learningApi.getRoadmap().catch(() => null),
        dailyTaskApi.getToday().catch(() => null),
      ])

      const kpItems = treeResp.data as Array<{
        id: string
        name: string
        slug: string
        parent_id: string | null
        difficulty: string
        order: number
        lecture_count?: number
        template_count?: number
      }>

      // 构建 roadmap 状态索引
      const roadmapMap = new Map<string, RoadmapKnowledgeNode>()
      if (roadmapResp) {
        const roadmapData = roadmapResp.data
        setHasPath(roadmapData.has_path)
        setPathPreview(roadmapData.path_preview)
        for (const node of roadmapData.tree) {
          roadmapMap.set(node.id, node)
        }
      } else {
        setHasPath(false)
        setPathPreview([])
      }

      // 今日任务
      if (todayResp) {
        setTodayTask(todayResp.data)
      } else {
        setTodayTask(null)
      }

      // 合并：以知识树结构为主，附加 roadmap 状态
      const byId = new Map<string, KnowledgeNode>()
      for (const kp of kpItems) {
        const rm = roadmapMap.get(kp.id)
        byId.set(kp.id, {
          id: kp.id,
          name: kp.name,
          slug: kp.slug,
          parent_id: kp.parent_id,
          difficulty: kp.difficulty,
          order: kp.order,
          lecture_count: rm?.lecture_count ?? kp.lecture_count ?? 0,
          template_count: rm?.template_count ?? kp.template_count ?? 0,
          status: rm?.status ?? 'none',
          mastery: rm?.mastery ?? null,
          is_weak: rm?.is_weak ?? false,
          path_position: rm?.path_position ?? null,
          theory_done: rm?.theory_done ?? false,
          practice_mastery: rm?.practice_mastery ?? null,
          theory_lecture_count: rm?.theory_lecture_count ?? 0,
          children: [],
        })
      }

      const roots: KnowledgeNode[] = []
      byId.forEach((node) => {
        if (node.parent_id && byId.has(node.parent_id)) {
          byId.get(node.parent_id)!.children.push(node)
        } else {
          roots.push(node)
        }
      })
      const sortRec = (nodes: KnowledgeNode[]) => {
        nodes.sort((a, b) => {
          // "其他" 子分类排到最后
          const aOther = isOtherCategory(a.name)
          const bOther = isOtherCategory(b.name)
          if (aOther && !bOther) return 1
          if (!aOther && bOther) return -1
          return a.order - b.order || a.name.localeCompare(b.name)
        })
        nodes.forEach((n) => sortRec(n.children))
      }
      sortRec(roots)
      setTree(roots)
      setExpanded(new Set(roots.map((r) => r.id)))
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : '加载失败')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadData()
  }, [loadData])

  const handleGeneratePath = async () => {
    setGeneratingPath(true)
    setError(null)
    try {
      // 先尝试 CF 冷启动（写入 mastery），再生成路径
      await coldstartApi.cfColdStart().catch(() => null)
      await learningApi.generatePath({ preview_count: 8 })
      await loadData()
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : '生成学习路径失败')
    } finally {
      setGeneratingPath(false)
    }
  }

  const handleMarkMastered = async (knowledgeId: string) => {
    setMarkingMastered((prev) => new Set(prev).add(knowledgeId))
    try {
      await learningApi.markMastered({ knowledge_id: knowledgeId })
      await loadData()
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : '标记失败')
    } finally {
      setMarkingMastered((prev) => {
        const next = new Set(prev)
        next.delete(knowledgeId)
        return next
      })
    }
  }

  const toggle = (id: string) => {
    setExpanded((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  // 搜索 + 状态过滤：过滤树并自动展开匹配节点的父链
  const isFiltering = searchQuery.trim() !== '' || statusFilter !== 'all'

  const filteredTree = useMemo(() => {
    if (!isFiltering) return tree
    const query = searchQuery.trim().toLowerCase()

    const filterNode = (node: KnowledgeNode): KnowledgeNode | null => {
      const matchesQuery = !query || node.name.toLowerCase().includes(query)
      const matchesStatus = statusFilter === 'all' || node.status === statusFilter

      if (node.children.length === 0) {
        // 叶子节点：需同时满足搜索和状态
        return matchesQuery && matchesStatus ? node : null
      }

      // 非叶子：先过滤子节点
      const filteredChildren = node.children
        .map(filterNode)
        .filter((n): n is KnowledgeNode => n !== null)

      if (filteredChildren.length > 0) {
        return { ...node, children: filteredChildren }
      }

      // 无匹配子节点，若自身满足搜索+状态则保留（空 children）
      if (matchesQuery && matchesStatus) {
        return { ...node, children: [] }
      }
      return null
    }

    return tree.map(filterNode).filter((n): n is KnowledgeNode => n !== null)
  }, [tree, searchQuery, statusFilter, isFiltering])

  // 过滤模式下自动展开所有有子节点的节点
  const effectiveExpanded = useMemo(() => {
    if (!isFiltering) return expanded
    const expandSet = new Set<string>()
    const collect = (node: KnowledgeNode) => {
      if (node.children.length > 0) {
        expandSet.add(node.id)
        node.children.forEach(collect)
      }
    }
    filteredTree.forEach(collect)
    return expandSet
  }, [isFiltering, filteredTree, expanded])

  // 顶层统计
  const stats = useMemo(() => {
    let totalKp = 0
    let totalLec = 0
    let totalTpl = 0
    let mastered = 0
    let learning = 0
    const sumLec = (n: KnowledgeNode): number =>
      (n.lecture_count || 0) + n.children.reduce((s, c) => s + sumLec(c), 0)
    const sumTpl = (n: KnowledgeNode): number =>
      (n.template_count || 0) + n.children.reduce((s, c) => s + sumTpl(c), 0)
    const sumLeaves = (n: KnowledgeNode): number =>
      n.children.length === 0 ? 1 : n.children.reduce((s, c) => s + sumLeaves(c), 0)
    const countStatus = (n: KnowledgeNode) => {
      if (n.status === 'done') mastered++
      if (n.status === 'active') learning++
      n.children.forEach(countStatus)
    }
    tree.forEach((r) => {
      totalKp += sumLeaves(r)
      totalLec += sumLec(r)
      totalTpl += sumTpl(r)
      countStatus(r)
    })
    return { totalKp, totalLec, totalTpl, catCount: tree.length, mastered, learning }
  }, [tree])

  const getDifficultyColor = (diff: string) => {
    switch (diff) {
      case 'easy':
        return 'bg-green-500'
      case 'medium':
        return 'bg-yellow-500'
      case 'hard':
        return 'bg-red-500'
      default:
        return 'bg-gray-400'
    }
  }

  const renderNode = (node: KnowledgeNode, depth: number): React.ReactNode => {
    const isRoot = depth === 0
    const hasChildren = node.children.length > 0
    const isOpen = effectiveExpanded.has(node.id)
    const meta = isRoot ? CATEGORY_META[node.name.replace('分类', '')] : null
    const Icon = meta?.icon || BookOpen
    const style = STATUS_STYLE[node.status]
    const isOther = isOtherCategory(node.name)

    const lecCount = node.lecture_count || 0
    const tplCount = node.template_count || 0

    // 根节点进度数据
    const rootTotal = isRoot ? countLeaves(node) : 0
    const rootDone = isRoot ? countDoneLeaves(node) : 0
    const rootPct = rootTotal > 0 ? (rootDone / rootTotal) * 100 : 0

    return (
      <div key={node.id}>
        <div
          className={`group flex items-center gap-2 pr-3 rounded-md transition-colors border-l-2 ${
            style.border
          } ${style.bg} ${
            isRoot ? 'py-2 hover:bg-blue-50/50' : 'py-1.5 hover:bg-gray-50'
          } ${isRoot ? 'font-semibold' : ''} ${isOther && !isRoot ? 'opacity-60' : ''}`}
          style={{ paddingLeft: `${depth * 20 + 8}px` }}
        >
          {/* 展开/折叠箭头 */}
          {hasChildren ? (
            <button
              onClick={() => toggle(node.id)}
              className="flex-shrink-0 p-0.5 rounded hover:bg-gray-200 text-gray-500"
              aria-label={isOpen ? '折叠' : '展开'}
            >
              {isOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
            </button>
          ) : (
            <span className="flex-shrink-0 w-5" />
          )}

          {/* 状态图标 / 分类图标 / 难度圆点 */}
          {isRoot ? (
            <Icon size={16} className={`flex-shrink-0 ${meta?.color || 'text-gray-500'}`} />
          ) : style.icon ? (
            <span className="flex-shrink-0">{style.icon}</span>
          ) : (
            <span
              className={`flex-shrink-0 w-2 h-2 rounded-full ${getDifficultyColor(node.difficulty)}`}
            />
          )}

          {/* 名称 */}
          {hasChildren ? (
            <button
              onClick={() => toggle(node.id)}
              className={`truncate text-left flex-1 ${
                isRoot ? `text-base ${meta?.color || 'text-gray-900'}` : `text-sm ${style.text}`
              } ${isOther ? 'text-gray-400' : ''}`}
              title={node.name}
            >
              {node.name}
            </button>
          ) : (
            <Link
              to={`/knowledge/${node.id}`}
              className={`truncate text-sm flex-1 text-left ${style.text} hover:text-blue-600`}
              title={node.name}
            >
              {node.name}
            </Link>
          )}

          {/* 根节点：分类级进度条 */}
          {isRoot && (
            <div className="flex items-center gap-1.5 flex-shrink-0">
              <div className="w-16 h-2 bg-gray-200 rounded-full overflow-hidden">
                <div
                  className="h-full bg-green-500 rounded-full transition-all"
                  style={{ width: `${rootPct}%` }}
                />
              </div>
              <span className="text-xs text-gray-500 tabular-nums">
                {rootDone}/{rootTotal}
              </span>
            </div>
          )}

          {/* 非根非叶：子节点数 */}
          {!isRoot && hasChildren && (
            <span className="text-xs text-gray-400 flex-shrink-0">({node.children.length})</span>
          )}

          {/* 状态标签 */}
          {node.status !== 'unlocked' && !isRoot && (
            <span
              className={`text-xs px-1.5 py-0.5 rounded flex-shrink-0 ${style.bg} ${style.text}`}
            >
              {STATUS_LABEL[node.status]}
            </span>
          )}

          {/* 统计徽章 */}
          <div className="flex items-center gap-1 flex-shrink-0">
            {lecCount > 0 && (
              <span className="flex items-center gap-0.5 text-xs text-blue-600 bg-blue-50 px-1.5 py-0.5 rounded">
                <BookOpen size={11} />
                {lecCount}
              </span>
            )}
            {tplCount > 0 && (
              <span className="flex items-center gap-0.5 text-xs text-purple-600 bg-purple-50 px-1.5 py-0.5 rounded">
                <Code2 size={11} />
                {tplCount}
              </span>
            )}
          </div>

          {/* 双维度进度（仅叶子节点且非根） */}
          {!hasChildren && !isRoot && (node.theory_done || node.practice_mastery != null) && (
            <div className="flex items-center gap-1.5 flex-shrink-0">
              {node.lecture_count > 0 && (
                <span
                  className={`flex items-center gap-0.5 text-xs px-1.5 py-0.5 rounded ${
                    node.theory_done ? 'bg-green-50 text-green-600' : 'bg-gray-100 text-gray-400'
                  }`}
                  title={node.theory_done ? '讲义已读' : '讲义未读'}
                >
                  <BookOpen size={10} />
                  {node.theory_done ? '已读' : '未读'}
                </span>
              )}
              {node.practice_mastery != null && node.practice_mastery > 0 && (
                <span
                  className={`flex items-center gap-0.5 text-xs px-1.5 py-0.5 rounded ${
                    (node.practice_mastery ?? 0) >= 0.8
                      ? 'bg-green-50 text-green-600'
                      : 'bg-yellow-50 text-yellow-600'
                  }`}
                  title={`实践 mastery: ${Math.round((node.practice_mastery ?? 0) * 100)}%`}
                >
                  <Brain size={10} />
                  {Math.round((node.practice_mastery ?? 0) * 100)}%
                </span>
              )}
            </div>
          )}

          {/* 自评"已掌握"按钮（仅叶子节点，非 done 状态） */}
          {!hasChildren && node.status !== 'done' && (
            <button
              onClick={(e) => {
                e.preventDefault()
                e.stopPropagation()
                handleMarkMastered(node.id)
              }}
              disabled={markingMastered.has(node.id)}
              className="flex-shrink-0 text-xs px-2 py-0.5 rounded border border-green-300 text-green-600 hover:bg-green-50 disabled:opacity-50 transition-colors"
              title="标记为已掌握"
            >
              {markingMastered.has(node.id) ? '...' : '标记为已掌握'}
            </button>
          )}
        </div>

        {/* 子节点 */}
        {hasChildren && isOpen && (
          <div className="relative">
            <div
              className="absolute left-0 top-0 bottom-0 w-px bg-gray-200"
              style={{ marginLeft: `${depth * 20 + 15}px` }}
            />
            {node.children.map((child) => renderNode(child, depth + 1))}
          </div>
        )}
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* 页头 */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">算法路线图</h1>
          <p className="text-gray-600 mt-2">
            按 10 大分类组织的算法学习路线，融合 OI-wiki 与左程云讲义两大数据源
          </p>
        </div>
        {!hasPath && !loading && !error && (
          <button
            onClick={handleGeneratePath}
            disabled={generatingPath}
            className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 text-sm"
          >
            <Sparkles size={16} className={generatingPath ? 'animate-spin' : ''} />
            {generatingPath ? '生成中...' : '生成学习路径'}
          </button>
        )}
      </div>

      {/* 推荐学习路径时间线 */}
      {hasPath && pathPreview.length > 0 && (
        <div className="bg-white rounded-xl p-5 shadow-sm border border-blue-100">
          <h2 className="text-sm font-semibold text-gray-900 mb-3 flex items-center gap-2">
            <Target size={16} className="text-blue-500" />
            推荐学习路径
          </h2>
          <div className="flex items-center gap-2 overflow-x-auto pb-1">
            {pathPreview.map((kp, idx) => (
              <React.Fragment key={kp.id}>
                <Link
                  to={`/knowledge/${kp.id}`}
                  className="flex items-center gap-2 px-3 py-1.5 rounded-full text-sm border border-blue-200 bg-blue-50 text-blue-700 hover:bg-blue-100 whitespace-nowrap flex-shrink-0 transition-colors"
                >
                  <span className="w-5 h-5 rounded-full bg-blue-500 text-white text-xs flex items-center justify-center font-medium">
                    {idx + 1}
                  </span>
                  <span>{kp.name}</span>
                </Link>
                {idx < pathPreview.length - 1 && (
                  <ChevronRight size={14} className="text-gray-300 flex-shrink-0" />
                )}
              </React.Fragment>
            ))}
          </div>
        </div>
      )}

      {/* 今日任务置顶卡片 */}
      {todayTask && !loading && !error && (
        <div className="bg-gradient-to-r from-blue-50 to-indigo-50 rounded-xl p-5 shadow-sm border border-blue-200">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-blue-500 flex items-center justify-center">
                <Target size={20} className="text-white" />
              </div>
              <div>
                <p className="text-xs text-blue-600 font-medium">今日任务</p>
                <Link
                  to={`/knowledge/${todayTask.task.knowledge.id}`}
                  className="text-lg font-semibold text-gray-900 hover:text-blue-600 transition-colors"
                >
                  {todayTask.task.knowledge.name}
                </Link>
                {todayTask.task.is_remediation && (
                  <span className="ml-2 text-xs px-1.5 py-0.5 bg-orange-100 text-orange-700 rounded">
                    补漏
                  </span>
                )}
              </div>
            </div>
            <div className="flex items-center gap-3">
              <div className="text-right">
                <p className="text-xs text-gray-500">任务进度</p>
                <p className="text-sm font-semibold text-gray-700">
                  {todayTask.task.items.filter((i) => i.status === 'done').length}/
                  {todayTask.task.items.length}
                </p>
              </div>
              <Link
                to="/today-task"
                className="px-3 py-2 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
              >
                去完成 →
              </Link>
            </div>
          </div>
        </div>
      )}

      {/* 无路径引导 */}
      {!hasPath && !loading && !error && tree.length > 0 && (
        <div className="bg-yellow-50 border border-yellow-200 rounded-xl p-4 flex items-start gap-3 text-yellow-800">
          <Sparkles size={18} className="flex-shrink-0 mt-0.5" />
          <div className="text-sm">
            <p className="font-medium">尚未生成学习路径</p>
            <p className="mt-1 text-yellow-700">
              点击右上角"生成学习路径"，系统会根据知识点前置依赖为你规划最优学习顺序
            </p>
          </div>
        </div>
      )}

      {/* 顶层统计条 */}
      {!loading && !error && tree.length > 0 && (
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
          <div className="bg-white rounded-lg border border-gray-100 p-4">
            <p className="text-xs text-gray-500">分类</p>
            <p className="text-2xl font-bold text-gray-900 mt-1">{stats.catCount}</p>
          </div>
          <div className="bg-white rounded-lg border border-gray-100 p-4">
            <p className="text-xs text-gray-500">知识点</p>
            <p className="text-2xl font-bold text-gray-900 mt-1">{stats.totalKp}</p>
          </div>
          <div className="bg-white rounded-lg border border-gray-100 p-4">
            <p className="text-xs text-gray-500">已掌握</p>
            <p className="text-2xl font-bold text-green-600 mt-1">{stats.mastered}</p>
          </div>
          <div className="bg-white rounded-lg border border-gray-100 p-4">
            <p className="text-xs text-gray-500">学习中</p>
            <p className="text-2xl font-bold text-blue-600 mt-1">{stats.learning}</p>
          </div>
          <div className="bg-white rounded-lg border border-gray-100 p-4">
            <p className="text-xs text-gray-500">讲义</p>
            <p className="text-2xl font-bold text-blue-600 mt-1">{stats.totalLec}</p>
          </div>
          <div className="bg-white rounded-lg border border-gray-100 p-4">
            <p className="text-xs text-gray-500">代码模板</p>
            <p className="text-2xl font-bold text-purple-600 mt-1">{stats.totalTpl}</p>
          </div>
        </div>
      )}

      {/* 主体：缩进树 */}
      {loading ? (
        <div className="flex items-center justify-center py-12 text-gray-500">
          <Loader2 className="animate-spin mr-2" size={20} />
          加载中...
        </div>
      ) : error ? (
        <div className="bg-red-50 border border-red-200 rounded-xl p-6 flex items-start gap-3 text-red-700">
          <AlertCircle size={20} className="flex-shrink-0 mt-0.5" />
          <div>
            <p className="font-medium">加载失败</p>
            <p className="text-sm mt-1 text-red-600">{error}</p>
            <p className="text-xs mt-2 text-red-500">
              提示：确认后端服务已启动且 <code>/api/v1/knowledge/</code> 路由可用。
            </p>
          </div>
        </div>
      ) : tree.length === 0 ? (
        <div className="bg-white rounded-xl border border-gray-100 p-12 text-center text-gray-500">
          暂无数据
        </div>
      ) : (
        <>
          {/* 搜索栏 + 状态过滤 */}
          <div className="bg-white rounded-xl border border-gray-100 p-3 flex items-center gap-3 flex-wrap">
            <div className="relative flex-1 min-w-[200px]">
              <Search
                size={16}
                className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400"
              />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="搜索知识点名称..."
                className="w-full pl-9 pr-8 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500/30 focus:border-blue-400"
              />
              {searchQuery && (
                <button
                  onClick={() => setSearchQuery('')}
                  className="absolute right-2.5 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
                >
                  <X size={15} />
                </button>
              )}
            </div>
            <div className="flex items-center gap-1 flex-shrink-0">
              {(
                [
                  { key: 'all', label: '全部' },
                  { key: 'active', label: '学习中' },
                  { key: 'unlocked', label: '可学习' },
                  { key: 'done', label: '已掌握' },
                  { key: 'none', label: '未开始' },
                ] as const
              ).map((tab) => (
                <button
                  key={tab.key}
                  onClick={() => setStatusFilter(tab.key)}
                  className={`px-3 py-1.5 text-xs rounded-lg transition-colors ${
                    statusFilter === tab.key
                      ? 'bg-blue-600 text-white'
                      : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                  }`}
                >
                  {tab.label}
                </button>
              ))}
            </div>
          </div>

          {/* 树主体 */}
          {filteredTree.length === 0 ? (
            <div className="bg-white rounded-xl border border-gray-100 p-12 text-center text-gray-500">
              未找到匹配的知识点
            </div>
          ) : (
            <div className="bg-white rounded-xl border border-gray-100 p-3">
              {filteredTree.map((root) => renderNode(root, 0))}
            </div>
          )}
        </>
      )}

      {/* 图例 */}
      {!loading && !error && tree.length > 0 && (
        <div className="bg-white rounded-xl border border-gray-100 p-4">
          <p className="text-xs font-medium text-gray-500 mb-2">图例</p>
          <div className="flex flex-wrap items-center gap-4 text-xs text-gray-600">
            <div className="flex items-center gap-1.5">
              <CheckCircle2 size={14} className="text-green-500" /> 已掌握
            </div>
            <div className="flex items-center gap-1.5">
              <Target size={14} className="text-blue-500" /> 学习中
            </div>
            <span className="text-gray-300">|</span>
            <div className="flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-green-500" /> 入门
            </div>
            <div className="flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-yellow-500" /> 中等
            </div>
            <div className="flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-red-500" /> 进阶
            </div>
            <span className="text-gray-300">|</span>
            <div className="flex items-center gap-1.5">
              <span className="flex items-center gap-0.5 text-blue-600 bg-blue-50 px-1.5 py-0.5 rounded">
                <BookOpen size={11} />N
              </span>
              讲义数
            </div>
            <div className="flex items-center gap-1.5">
              <span className="flex items-center gap-0.5 text-purple-600 bg-purple-50 px-1.5 py-0.5 rounded">
                <Code2 size={11} />N
              </span>
              模板代码数
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default KnowledgeTree
