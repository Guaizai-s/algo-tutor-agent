import React, { useEffect, useState } from 'react'
import { useParams, Link, useNavigate } from 'react-router-dom'
import {
  ArrowLeft,
  BookOpen,
  Code2,
  Copy,
  FileText,
  GraduationCap,
  Loader2,
  AlertCircle,
} from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import remarkMath from 'remark-math'
import rehypeKatex from 'rehype-katex'
import { codeToHtml } from 'shiki/bundle/web'
import 'katex/dist/katex.min.css'
import { knowledgeApi } from '../utils/api'
import type { CodeTemplate, KnowledgePoint, Lecture } from '../types'

// OI-wiki / mkdocs-material admonition 类型 → emoji + 标题映射
// 用于把 `??? note "标题"` / `???+ warning` 之类语法转成 blockquote
const ADMONITION_META: Record<string, { emoji: string; defaultTitle: string }> = {
  note: { emoji: '📝', defaultTitle: '笔记' },
  info: { emoji: 'ℹ️', defaultTitle: '信息' },
  tip: { emoji: '💡', defaultTitle: '提示' },
  success: { emoji: '✅', defaultTitle: '成功' },
  warning: { emoji: '⚠️', defaultTitle: '警告' },
  failure: { emoji: '❌', defaultTitle: '失败' },
  danger: { emoji: '🔥', defaultTitle: '危险' },
  bug: { emoji: '🐛', defaultTitle: 'Bug' },
  example: { emoji: '🧪', defaultTitle: '示例' },
  question: { emoji: '❓', defaultTitle: '问题' },
  abstract: { emoji: '📋', defaultTitle: '摘要' },
  quote: { emoji: '💬', defaultTitle: '引用' },
}

// 把 mkdocs admonition 语法转成 Obsidian 风格 callout blockquote
// 输入形如：
//   ???+ warning "注意"
//       作为项目方针的一部分...
//       多行内容...
//   ## 下一个标题
// 输出：
//   > [!WARNING] 注意
//   >
//   > 作为项目方针的一部分...
//   > 多行内容...
//   ## 下一个标题
function preprocessAdmonition(md: string): string {
  const lines = md.split('\n')
  const out: string[] = []
  let i = 0
  while (i < lines.length) {
    const line = lines[i]
    const m = line.match(/^\?\?\?([+-]?)\s+(\w+)(?:\s+"([^"]*)")?\s*$/)
    if (!m) {
      out.push(line)
      i++
      continue
    }
    const type = m[2].toUpperCase()
    const title = m[3] || ADMONITION_META[type.toLowerCase()]?.defaultTitle || type
    // 收集缩进体（4 空格或 tab）
    const body: string[] = []
    i++
    while (i < lines.length) {
      const l = lines[i]
      if (l.startsWith('    ') || l.startsWith('\t')) {
        body.push(l.replace(/^( {4}|\t)/, ''))
        i++
      } else if (l.trim() === '') {
        const next = lines[i + 1]
        if (next && (next.startsWith('    ') || next.startsWith('\t'))) {
          body.push('')
          i++
        } else {
          break
        }
      } else {
        break
      }
    }
    // 先处理 body 内的 content tabs，再加上 > 前缀
    const processedBody = preprocessTabs(body.join('\n'))
    const bodyLines = processedBody.split('\n')
    out.push(`> [!${type}] ${title}`)
    out.push('>')
    bodyLines.forEach((b) => out.push(b ? `> ${b}` : '>'))
    out.push('')
  }
  return out.join('\n')
}

// 把 mkdocs content tabs 语法转成带语言标签的代码块平铺
// 输入形如：
//   === "C++"
//       ```cpp
//       int main() { return 0; }
//       ```
//
//   === "Python"
//       ```python
//       print("hello")
//       ```
// 输出（每个 tab 用加粗语言标签分隔，代码块直接平铺）：
//   **C++**
//
//   ```cpp
//   int main() { return 0; }
//   ```
//
//   **Python**
//
//   ```python
//   print("hello")
//   ```
// 不用 <details> 是因为 react-markdown 默认不渲染原生 HTML（需额外引入 rehype-raw）；
// 多语言并列平铺对学习场景也更友好，便于对比
function preprocessTabs(md: string): string {
  const lines = md.split('\n')
  const out: string[] = []
  let i = 0
  while (i < lines.length) {
    const line = lines[i]
    // 匹配 `=== "标题"` 或 `=== '标题'`
    const m = line.match(/^===\s+["']([^"']+)["']\s*$/)
    if (!m) {
      out.push(line)
      i++
      continue
    }
    const title = m[1]
    // 收集缩进体
    const body: string[] = []
    i++
    while (i < lines.length) {
      const l = lines[i]
      if (l.startsWith('    ') || l.startsWith('\t')) {
        body.push(l.replace(/^( {4}|\t)/, ''))
        i++
      } else if (l.trim() === '') {
        // 空行：若下一行仍是缩进或下一个 ===，归到当前 tab
        const next = lines[i + 1]
        if (
          next &&
          (next.startsWith('    ') || next.startsWith('\t') || /^===\s+["']/.test(next))
        ) {
          body.push('')
          i++
        } else break
      } else break
    }
    // 输出加粗语言标签 + 内容
    out.push(`**${title}**`)
    out.push('')
    body.forEach((b) => out.push(b))
    out.push('')
  }
  return out.join('\n')
}

// Obsidian 风格 callout 颜色映射
const CALLOUT_COLORS: Record<string, { border: string; bg: string; text: string }> = {
  note: { border: '#448aff', bg: '#f0f4ff', text: '#1a3a6b' },
  info: { border: '#00b0ff', bg: '#e1f5fe', text: '#0d3b66' },
  tip: { border: '#00bfa5', bg: '#e0f2f1', text: '#004d40' },
  success: { border: '#00c853', bg: '#e8f5e9', text: '#1b5e20' },
  warning: { border: '#ff9100', bg: '#fff8e1', text: '#5d3f00' },
  danger: { border: '#ff1744', bg: '#ffebee', text: '#7f0000' },
  failure: { border: '#ff5252', bg: '#ffebee', text: '#7f0000' },
  bug: { border: '#d50000', bg: '#fce4ec', text: '#7f0000' },
  example: { border: '#7c4dff', bg: '#ede7f6', text: '#311b92' },
  question: { border: '#64b5f6', bg: '#e3f2fd', text: '#0d3b66' },
  abstract: { border: '#00acc1', bg: '#e0f7fa', text: '#004d40' },
  quote: { border: '#9e9e9e', bg: '#fafafa', text: '#424242' },
}

// 递归提取 React 节点的纯文本内容
function getTextContent(node: unknown): string {
  if (typeof node === 'string') return node
  if (typeof node === 'number') return String(node)
  if (Array.isArray(node)) return (node as unknown[]).map(getTextContent).join('')
  if (node && typeof node === 'object' && 'props' in node) {
    return getTextContent((node as { props: { children?: unknown } }).props.children)
  }
  return ''
}

// Obsidian 风格 callout 渲染组件
const CalloutBlock: React.FC<{
  type: string
  title: string
  children: React.ReactNode
}> = ({ type, title, children }) => {
  const t = type.toLowerCase()
  const colors = CALLOUT_COLORS[t] || CALLOUT_COLORS.note
  const meta = ADMONITION_META[t] || { emoji: '📌' }
  return (
    <div
      className="my-4 rounded-r-lg border-l-4 p-4"
      style={{
        borderLeftColor: colors.border,
        backgroundColor: colors.bg,
      }}
    >
      <div className="flex items-center gap-2 font-semibold mb-2" style={{ color: colors.border }}>
        <span>{meta.emoji}</span>
        <span>{title}</span>
      </div>
      <div className="callout-body text-sm leading-relaxed" style={{ color: colors.text }}>
        {children}
      </div>
    </div>
  )
}

// 异步 Shiki 代码高亮组件（带行号）
const ShikiCodeBlock: React.FC<{ code: string; lang: string }> = ({ code, lang }) => {
  const [html, setHtml] = useState<string>('')

  useEffect(() => {
    let cancelled = false
    codeToHtml(code, {
      lang: lang || 'text',
      theme: 'github-dark',
    }).then((h) => {
      if (!cancelled) setHtml(h)
    })
    return () => {
      cancelled = true
    }
  }, [code, lang])

  if (!html) {
    return (
      <pre className="bg-gray-900 text-gray-100 p-4 rounded-lg overflow-x-auto text-sm">
        <code>{code}</code>
      </pre>
    )
  }

  return <div dangerouslySetInnerHTML={{ __html: html }} />
}

const KnowledgeDetail: React.FC = () => {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [knowledge, setKnowledge] = useState<KnowledgePoint | null>(null)
  const [lectures, setLectures] = useState<Lecture[]>([])
  const [templates, setTemplates] = useState<CodeTemplate[]>([])
  const [prerequisites, setPrerequisites] = useState<KnowledgePoint[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [activeLevel, setActiveLevel] = useState<'card' | 'standard' | 'deep'>('card')
  const [copiedTpl, setCopiedTpl] = useState<string | null>(null)

  // UUID 格式校验
  const isUUID = (s: string) =>
    /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(s)

  useEffect(() => {
    if (!id) return
    let cancelled = false
    setLoading(true)
    setError(null)

    const loadByKpId = (kpId: string) => {
      Promise.all([
        knowledgeApi.getById(kpId),
        knowledgeApi.getLectures(kpId),
        knowledgeApi.getTemplates(kpId),
        knowledgeApi.getPrerequisites(kpId),
      ])
        .then(([kpResp, lecResp, tplResp, preResp]) => {
          if (cancelled) return
          setKnowledge(kpResp.data as KnowledgePoint)
          const lecs = lecResp.data as Lecture[]
          setLectures(lecs)
          setTemplates(tplResp.data as CodeTemplate[])
          setPrerequisites(preResp.data as KnowledgePoint[])
          if (lecs.length > 0) {
            setActiveLevel(lecs[0].level)
          }
        })
        .catch((err: unknown) => {
          if (cancelled) return
          setError(err instanceof Error ? err.message : '加载知识点失败')
        })
        .finally(() => !cancelled && setLoading(false))
    }

    if (isUUID(id)) {
      loadByKpId(id)
    } else {
      // id 不是 UUID，尝试按 slug 查找
      knowledgeApi
        .getTree()
        .then((resp) => {
          if (cancelled) return
          const items = resp.data as KnowledgePoint[]
          const found = items.find((kp) => kp.slug === id)
          if (found) {
            // 重定向到 UUID 版本，避免后续重复查找
            navigate(`/knowledge/${found.id}`, { replace: true })
          } else {
            setError(`知识点 "${id}" 不存在`)
            setLoading(false)
          }
        })
        .catch((err: unknown) => {
          if (cancelled) return
          setError(err instanceof Error ? err.message : '加载知识点失败')
          setLoading(false)
        })
    }

    return () => {
      cancelled = true
    }
  }, [id, navigate])

  const levels: {
    level: 'card' | 'standard' | 'deep'
    label: string
    icon: typeof BookOpen
    desc: string
  }[] = [
    { level: 'card', label: '知识卡片', icon: BookOpen, desc: '快速入门' },
    { level: 'standard', label: '标准讲义', icon: FileText, desc: '系统学习' },
    { level: 'deep', label: '深度专题', icon: GraduationCap, desc: '进阶提升' },
  ]

  const currentLecture = lectures.find((l) => l.level === activeLevel)

  const handleCopy = async (text: string, tplId: string) => {
    try {
      await navigator.clipboard.writeText(text)
      setCopiedTpl(tplId)
      setTimeout(() => setCopiedTpl(null), 1500)
    } catch {
      // ignore clipboard failures
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64 text-gray-500">
        <Loader2 className="animate-spin mr-2" size={20} />
        加载中...
      </div>
    )
  }

  if (error || !knowledge) {
    return (
      <div className="flex flex-col items-center justify-center h-64 gap-4">
        <AlertCircle size={40} className="text-red-500" />
        <p className="text-gray-700">{error || '知识点不存在'}</p>
        <Link to="/knowledge" className="text-blue-600 hover:underline">
          返回算法路线图
        </Link>
      </div>
    )
  }

  const availableLevels = new Set(lectures.map((l) => l.level))

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-4">
        <Link to="/knowledge" className="p-2 hover:bg-gray-100 rounded-lg">
          <ArrowLeft size={20} />
        </Link>
        <div>
          <h1 className="text-2xl font-bold text-gray-900">{knowledge.name}</h1>
          <p className="text-gray-500">难度：{knowledge.difficulty}</p>
        </div>
      </div>

      {/* 学习前置依赖 */}
      {prerequisites.length > 0 && (
        <div className="bg-white rounded-xl border border-gray-100 p-4">
          <p className="text-xs font-medium text-gray-500 mb-2">学习前置（建议先学）</p>
          <div className="flex flex-wrap gap-2">
            {prerequisites.map((pre) => (
              <Link
                key={pre.id}
                to={`/knowledge/${pre.id}`}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-lg border border-gray-200 bg-gray-50 hover:bg-blue-50 hover:border-blue-300 hover:text-blue-600 transition-colors"
                title={pre.description || pre.name}
              >
                <BookOpen size={13} className="text-gray-400" />
                {pre.name}
              </Link>
            ))}
          </div>
        </div>
      )}

      {lectures.length === 0 ? (
        <div className="bg-white rounded-xl border border-gray-100 p-8 text-center text-gray-500">
          该知识点暂无讲义内容
        </div>
      ) : (
        <>
          <div className="flex gap-2 flex-wrap">
            {levels.map((l) => {
              const Icon = l.icon
              const available = availableLevels.has(l.level)
              return (
                <button
                  key={l.level}
                  onClick={() => available && setActiveLevel(l.level)}
                  disabled={!available}
                  className={`flex items-center gap-2 px-4 py-3 rounded-lg transition-colors ${
                    activeLevel === l.level
                      ? 'bg-blue-600 text-white'
                      : available
                        ? 'bg-white text-gray-700 hover:bg-gray-50 border border-gray-200'
                        : 'bg-gray-50 text-gray-400 cursor-not-allowed border border-gray-100'
                  }`}
                >
                  <Icon size={18} />
                  <div className="text-left">
                    <p className="font-medium text-sm">{l.label}</p>
                    <p
                      className={`text-xs ${
                        activeLevel === l.level ? 'text-blue-100' : 'text-gray-500'
                      }`}
                    >
                      {available ? l.desc : '未提供'}
                    </p>
                  </div>
                </button>
              )
            })}
          </div>

          {currentLecture ? (
            <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-8">
              <h2 className="text-xl font-semibold mb-4">{currentLecture.title}</h2>
              <article className="prose prose-slate max-w-none prose-headings:font-semibold prose-code:before:hidden prose-code:after:hidden prose-pre:p-4 prose-pre:rounded-lg">
                <ReactMarkdown
                  remarkPlugins={[remarkGfm, remarkMath]}
                  rehypePlugins={[rehypeKatex]}
                  components={{
                    pre({ children }) {
                      return <>{children}</>
                    },
                    code({ children, className, ...props }) {
                      if (!className) {
                        return (
                          <code className={className} {...props}>
                            {children}
                          </code>
                        )
                      }
                      const lang = className.replace('language-', '')
                      const code = String(children).replace(/\n$/, '')
                      return <ShikiCodeBlock code={code} lang={lang} />
                    },
                    blockquote({ children, ...props }) {
                      const childrenArr = Array.isArray(children) ? children : [children]
                      // 跳过空白文本节点，找到第一个真正的 React 元素
                      const firstIdx = childrenArr.findIndex(
                        (c) => c && typeof c === 'object' && 'props' in c
                      )
                      const firstChild = firstIdx >= 0 ? childrenArr[firstIdx] : undefined
                      if (firstChild) {
                        const text = getTextContent(firstChild)
                        const match = text.match(/^\[!(\w+)\]\s*(.*)/)
                        if (match) {
                          const type = match[1]
                          const title =
                            match[2] || ADMONITION_META[type.toLowerCase()]?.defaultTitle || type
                          return (
                            <CalloutBlock type={type} title={title}>
                              {childrenArr.slice(firstIdx + 1)}
                            </CalloutBlock>
                          )
                        }
                      }
                      return <blockquote {...props}>{children}</blockquote>
                    },
                  }}
                >
                  {preprocessTabs(preprocessAdmonition(currentLecture.content))}
                </ReactMarkdown>
              </article>
            </div>
          ) : (
            <div className="bg-white rounded-xl border border-gray-100 p-8 text-center text-gray-500">
              该级别暂无讲义内容
            </div>
          )}
        </>
      )}

      {knowledge.description && (
        <div className="bg-blue-50 border-l-4 border-blue-500 p-4 rounded-r-lg">
          <p className="font-medium text-blue-900">知识点简介</p>
          <p className="text-blue-700 text-sm mt-1">{knowledge.description}</p>
        </div>
      )}

      {/* 代码模板区 */}
      {templates.length > 0 && (
        <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6">
          <div className="flex items-center gap-2 mb-4">
            <Code2 size={20} className="text-purple-600" />
            <h2 className="text-lg font-semibold text-gray-900">代码模板</h2>
            <span className="text-xs text-gray-500">({templates.length})</span>
          </div>
          <div className="space-y-4">
            {templates.map((tpl) => (
              <div key={tpl.id} className="border border-gray-200 rounded-lg overflow-hidden">
                <div className="flex items-center justify-between bg-gray-50 px-4 py-2 border-b border-gray-200">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-mono px-2 py-0.5 bg-purple-100 text-purple-700 rounded">
                      {tpl.language}
                    </span>
                    {tpl.explanation && (
                      <span className="text-xs text-gray-600">{tpl.explanation}</span>
                    )}
                  </div>
                  <button
                    type="button"
                    onClick={() => handleCopy(tpl.template_code, tpl.id)}
                    className="flex items-center gap-1 text-xs text-gray-500 hover:text-blue-600 transition-colors"
                  >
                    <Copy size={12} />
                    {copiedTpl === tpl.id ? '已复制' : '复制'}
                  </button>
                </div>
                <pre className="bg-gray-900 text-gray-100 text-sm p-4 overflow-x-auto leading-relaxed">
                  <code>{tpl.template_code}</code>
                </pre>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="flex justify-between">
        <Link
          to="/knowledge"
          className="px-6 py-3 border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors"
        >
          返回路线图
        </Link>
        <Link
          to={`/problems?kp=${knowledge.slug}`}
          className="px-6 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
        >
          去做练习题 →
        </Link>
      </div>
    </div>
  )
}

export default KnowledgeDetail
