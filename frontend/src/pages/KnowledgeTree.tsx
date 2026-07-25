import React, { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  AlertCircle,
  BookOpen,
  ChevronDown,
  ChevronRight,
  Code2,
  Loader2,
  type LucideIcon,
} from 'lucide-react'
import { knowledgeApi } from '../utils/api'
import type { KnowledgePoint } from '../types'

interface KnowledgeNode extends KnowledgePoint {
  children: KnowledgeNode[]
}

// 7 个一级分类 → 颜色 + 图标（用于根节点视觉区分）
const CATEGORY_META: Record<string, { color: string; icon: LucideIcon }> = {
  基础: { color: 'text-blue-600', icon: BookOpen },
  数据结构: { color: 'text-violet-600', icon: BookOpen },
  图论: { color: 'text-emerald-600', icon: BookOpen },
  动态规划: { color: 'text-amber-600', icon: BookOpen },
  字符串: { color: 'text-pink-600', icon: BookOpen },
  数学: { color: 'text-orange-600', icon: BookOpen },
  杂项: { color: 'text-slate-600', icon: BookOpen },
}

const KnowledgeTree: React.FC = () => {
  const [tree, setTree] = useState<KnowledgeNode[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [expanded, setExpanded] = useState<Set<string>>(new Set())

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    knowledgeApi
      .getTree()
      .then((resp) => {
        if (cancelled) return
        const items = resp.data as KnowledgePoint[]
        const byId = new Map<string, KnowledgeNode>()
        items.forEach((kp) => byId.set(kp.id, { ...kp, children: [] }))
        const roots: KnowledgeNode[] = []
        byId.forEach((node) => {
          if (node.parent_id && byId.has(node.parent_id)) {
            byId.get(node.parent_id)!.children.push(node)
          } else {
            roots.push(node)
          }
        })
        const sortRec = (nodes: KnowledgeNode[]) => {
          nodes.sort((a, b) => a.order - b.order || a.name.localeCompare(b.name))
          nodes.forEach((n) => sortRec(n.children))
        }
        sortRec(roots)
        setTree(roots)
        // 默认展开所有一级分类根，让用户看到二级结构
        setExpanded(new Set(roots.map((r) => r.id)))
      })
      .catch((err: unknown) => {
        if (cancelled) return
        setError(err instanceof Error ? err.message : '加载失败')
      })
      .finally(() => !cancelled && setLoading(false))
    return () => {
      cancelled = true
    }
  }, [])

  const toggle = (id: string) => {
    setExpanded((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  // 顶层统计：递归累加所有节点
  const stats = useMemo(() => {
    let totalKp = 0
    let totalLec = 0
    let totalTpl = 0
    const sumLec = (n: KnowledgeNode): number =>
      (n.lecture_count || 0) + n.children.reduce((s, c) => s + sumLec(c), 0)
    const sumTpl = (n: KnowledgeNode): number =>
      (n.template_count || 0) + n.children.reduce((s, c) => s + sumTpl(c), 0)
    const sumLeaves = (n: KnowledgeNode): number =>
      n.children.length === 0 ? 1 : n.children.reduce((s, c) => s + sumLeaves(c), 0)
    tree.forEach((r) => {
      totalKp += sumLeaves(r)
      totalLec += sumLec(r)
      totalTpl += sumTpl(r)
    })
    return { totalKp, totalLec, totalTpl, catCount: tree.length }
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

  // 递归渲染缩进树节点
  // depth=0 是分类根，depth>=1 是子节点（subtag 或叶子）
  const renderNode = (node: KnowledgeNode, depth: number): React.ReactNode => {
    const isRoot = depth === 0
    const hasChildren = node.children.length > 0
    const isOpen = expanded.has(node.id)
    const meta = isRoot ? CATEGORY_META[node.name.replace('分类', '')] : null
    const Icon = meta?.icon || BookOpen

    const lecCount = node.lecture_count || 0
    const tplCount = node.template_count || 0

    return (
      <div key={node.id}>
        <div
          className={`group flex items-center gap-2 pr-3 rounded-md transition-colors ${
            isRoot ? 'py-2 hover:bg-blue-50/50' : 'py-1.5 hover:bg-gray-50'
          } ${isRoot ? 'font-semibold' : ''}`}
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
            <span className="flex-shrink-0 w-5" /> // 占位，对齐箭头
          )}

          {/* 难度色点 / 分类图标 */}
          {isRoot ? (
            <Icon size={16} className={`flex-shrink-0 ${meta?.color || 'text-gray-500'}`} />
          ) : (
            <span
              className={`flex-shrink-0 w-2 h-2 rounded-full ${getDifficultyColor(node.difficulty)}`}
            />
          )}

          {/* 名称（叶子节点是链接，非叶子节点是按钮可点击展开） */}
          {hasChildren ? (
            <button
              onClick={() => toggle(node.id)}
              className={`truncate text-left flex-1 ${
                isRoot ? `text-base ${meta?.color || 'text-gray-900'}` : 'text-sm text-gray-700'
              }`}
              title={node.description || node.name}
            >
              {node.name}
            </button>
          ) : (
            <Link
              to={`/knowledge/${node.id}`}
              className="truncate text-sm text-gray-700 hover:text-blue-600 flex-1 text-left"
              title={node.description || node.name}
            >
              {node.name}
            </Link>
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
        </div>

        {/* 子节点：缩进 + 左侧竖线连接 */}
        {hasChildren && isOpen && (
          <div className="relative">
            {/* 竖线：从父节点下方延伸到子节点末尾 */}
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
      <div>
        <h1 className="text-3xl font-bold text-gray-900">算法路线图</h1>
        <p className="text-gray-600 mt-2">
          按 7 大分类组织的算法学习路线，融合 OI-wiki 与左程云讲义两大数据源
        </p>
      </div>

      {/* 顶层统计条 */}
      {!loading && !error && tree.length > 0 && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <div className="bg-white rounded-lg border border-gray-100 p-4">
            <p className="text-xs text-gray-500">分类</p>
            <p className="text-2xl font-bold text-gray-900 mt-1">{stats.catCount}</p>
          </div>
          <div className="bg-white rounded-lg border border-gray-100 p-4">
            <p className="text-xs text-gray-500">知识点</p>
            <p className="text-2xl font-bold text-gray-900 mt-1">{stats.totalKp}</p>
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
        <div className="bg-white rounded-xl border border-gray-100 p-3">
          {tree.map((root) => renderNode(root, 0))}
        </div>
      )}

      {/* 图例 */}
      {!loading && !error && tree.length > 0 && (
        <div className="bg-white rounded-xl border border-gray-100 p-4">
          <p className="text-xs font-medium text-gray-500 mb-2">图例</p>
          <div className="flex flex-wrap items-center gap-4 text-xs text-gray-600">
            <div className="flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-green-500" /> 入门
            </div>
            <div className="flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-yellow-500" /> 中等
            </div>
            <div className="flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-red-500" /> 进阶
            </div>
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
