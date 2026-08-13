import React, { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import {
  ArrowLeft,
  Lightbulb,
  RotateCcw,
  Send,
  CheckCircle,
  XCircle,
  Clock,
  Cpu,
  AlertCircle,
  ExternalLink,
  Link2,
  Trophy,
  History,
} from 'lucide-react'
import Editor from '@monaco-editor/react'
import { problemsApi, submissionsApi } from '../utils/api'
import { useAuthStore } from '../stores/authStore'
import type { CodeExecutionResult, Problem, SubmissionRead, SubmissionListResponse } from '../types'

type Lang = 'python' | 'cpp' | 'java'

const DIFFICULTY_LABEL: Record<string, string> = {
  easy: '简单',
  medium: '中等',
  hard: '困难',
}
const DIFFICULTY_STYLE: Record<string, string> = {
  easy: 'bg-green-100 text-green-700',
  medium: 'bg-yellow-100 text-yellow-700',
  hard: 'bg-red-100 text-red-700',
}

const ProblemDetail: React.FC = () => {
  const { id } = useParams<{ id: string }>()
  const [problem, setProblem] = useState<Problem | null>(null)
  const [problemLoading, setProblemLoading] = useState(true)
  const [problemError, setProblemError] = useState<string | null>(null)
  const [code, setCode] = useState('')
  const [language, setLanguage] = useState<Lang>('python')
  const [customInput, setCustomInput] = useState('')
  const [useCustomInput, setUseCustomInput] = useState(false)
  const [isJudging, setIsJudging] = useState(false)
  const [result, setResult] = useState<CodeExecutionResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [hintLevel, setHintLevel] = useState(0)
  const [submissions, setSubmissions] = useState<SubmissionRead[]>([])
  const [isAC, setIsAC] = useState(false)
  const { user } = useAuthStore()
  const cfBound = !!user?.cf_handle

  // Load real problem by UUID.
  useEffect(() => {
    if (!id) return
    setProblemLoading(true)
    setProblemError(null)
    problemsApi
      .getById(id)
      .then((resp) => {
        const p = resp.data as Problem
        setProblem(p)
        // Initialize code editor from solution template if available.
        const tpl = (p.solution_template as Record<string, string> | null)?.[language] || ''
        setCode(tpl || '# 在这里写你的代码\n')
      })
      .catch((err: unknown) => {
        const msg = err instanceof Error ? err.message : '题目加载失败'
        setProblemError(msg)
      })
      .finally(() => setProblemLoading(false))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id])

  // Load submissions for this problem.
  useEffect(() => {
    if (!id) return
    submissionsApi
      .list({ user_id: user?.id ?? '', problem_id: id, page_size: 5 })
      .then((resp) => {
        const data = resp.data as SubmissionListResponse
        setSubmissions(data.items)
        setIsAC(data.items.some((s) => s.verdict === 'OK'))
      })
      .catch(() => {})
  }, [id, user?.id])

  if (problemLoading) {
    return (
      <div className="flex items-center justify-center h-[calc(100vh-4rem)] text-gray-500">
        题目加载中...
      </div>
    )
  }

  if (problemError || !problem) {
    return (
      <div className="flex flex-col items-center justify-center h-[calc(100vh-4rem)] gap-4">
        <AlertCircle size={40} className="text-red-500" />
        <p className="text-gray-700">{problemError || '题目不存在'}</p>
        <Link to="/problems" className="text-blue-600 hover:underline">
          返回题目列表
        </Link>
      </div>
    )
  }

  const hints = problem.hints || []
  // CF 外链题：来源是 codeforces，或无样例且有外链 URL
  const isCFProblem =
    problem.source === 'codeforces' || (!!problem.external_url && !problem.sample_input)

  const handleSubmit = async () => {
    if (!id) {
      setError('缺少题目 ID，无法运行代码')
      return
    }
    setIsJudging(true)
    setResult(null)
    setError(null)
    try {
      // 代码执行是确定性后端操作，不经过耗时且可能重复调用工具的 Agent。
      const resp = await problemsApi.execute(
        id,
        code,
        language,
        useCustomInput ? customInput : undefined
      )
      setResult(resp.data)
      // 刷新提交记录（CF 同步可能已写入新提交）
      submissionsApi
        .list({ user_id: user?.id ?? '', problem_id: id, page_size: 5 })
        .then((sResp) => {
          const data = sResp.data as SubmissionListResponse
          setSubmissions(data.items)
          setIsAC(data.items.some((s) => s.verdict === 'OK'))
        })
        .catch(() => {})
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : '提交失败，请重试'
      setError(msg)
    } finally {
      setIsJudging(false)
    }
  }

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'success':
        return 'text-green-600 bg-green-50'
      case 'runtime_error':
        return 'text-red-600 bg-red-50'
      case 'timeout':
        return 'text-orange-600 bg-orange-50'
      case 'compile_error':
        return 'text-red-600 bg-red-50'
      default:
        return 'text-gray-600 bg-gray-50'
    }
  }

  const getStatusText = (status: string) => {
    switch (status) {
      case 'success':
        return '运行成功'
      case 'runtime_error':
        return '运行错误 (Runtime Error)'
      case 'timeout':
        return '超时 (Time Limit Exceeded)'
      case 'compile_error':
        return '编译错误 (Compile Error)'
      case 'internal_error':
        return '执行失败'
      default:
        return status
    }
  }

  const getStatusIcon = (status: string) => {
    return status === 'success' ? <CheckCircle size={18} /> : <XCircle size={18} />
  }

  return (
    <div className="h-[calc(100vh-4rem)] -m-8 flex flex-col">
      <div className="flex items-center gap-4 px-8 py-4 border-b border-gray-200 bg-white">
        <Link to="/problems" className="p-2 hover:bg-gray-100 rounded-lg">
          <ArrowLeft size={20} />
        </Link>
        <h1 className="text-xl font-bold text-gray-900">{problem.title}</h1>
        {isAC && (
          <span className="flex items-center gap-1 px-2 py-0.5 bg-green-100 text-green-700 rounded text-xs font-medium">
            <Trophy size={12} />
            AC
          </span>
        )}
        <span
          className={`px-2 py-1 text-xs rounded ${
            DIFFICULTY_STYLE[problem.difficulty] || 'bg-gray-100 text-gray-700'
          }`}
        >
          {DIFFICULTY_LABEL[problem.difficulty] || problem.difficulty}
        </span>
        <span className="text-xs text-gray-500">
          时间限制 {problem.time_limit_ms}ms / 内存限制 {Math.round(problem.memory_limit_kb / 1024)}
          MB
        </span>
      </div>

      <div className="flex flex-1 overflow-hidden">
        <div className="w-1/2 border-r border-gray-200 overflow-y-auto p-6 bg-white">
          {isCFProblem && (
            <div className="mb-4 p-4 bg-blue-50 border border-blue-200 rounded-lg">
              <div className="flex items-start gap-2">
                <ExternalLink size={18} className="text-blue-600 flex-shrink-0 mt-0.5" />
                <div className="flex-1 text-sm">
                  <p className="font-medium text-blue-900">Codeforces 外链题</p>
                  <p className="text-blue-700 mt-1">
                    本地会按需同步公开题面和样例；你也可以在右侧填写自定义输入进行调试。
                    {cfBound
                      ? '你在 CF 的提交会每 5 分钟自动同步，AC 后自动计入掌握度。'
                      : '绑定 CF 账号后，你在 CF 的提交会自动同步进来。'}
                  </p>
                  <div className="flex gap-2 mt-3">
                    {problem.external_url && (
                      <a
                        href={problem.external_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center gap-1 px-3 py-1.5 bg-blue-600 hover:bg-blue-700 text-white text-xs font-medium rounded transition-colors"
                      >
                        <ExternalLink size={12} />去 Codeforces 读题 / 提交
                      </a>
                    )}
                    {!cfBound && (
                      <Link
                        to="/profile"
                        className="inline-flex items-center gap-1 px-3 py-1.5 bg-white border border-blue-300 text-blue-700 hover:bg-blue-50 text-xs font-medium rounded transition-colors"
                      >
                        <Link2 size={12} />
                        绑定 CF 账号
                      </Link>
                    )}
                  </div>
                </div>
              </div>
            </div>
          )}
          <div className="prose max-w-none">
            <h2 className="text-lg font-semibold">题目描述</h2>
            <p className="text-gray-700 mt-2 whitespace-pre-wrap">{problem.description}</p>

            {problem.sample_input && (
              <>
                <h3 className="text-md font-semibold mt-6">样例输入：</h3>
                <div className="bg-gray-50 p-4 rounded-lg">
                  <pre className="text-sm text-gray-800 whitespace-pre-wrap">
                    {problem.sample_input}
                  </pre>
                </div>
              </>
            )}

            {problem.sample_output && (
              <>
                <h3 className="text-md font-semibold mt-6">样例输出：</h3>
                <div className="bg-gray-50 p-4 rounded-lg">
                  <pre className="text-sm text-gray-800 whitespace-pre-wrap">
                    {problem.sample_output}
                  </pre>
                </div>
              </>
            )}
          </div>

          {hintLevel > 0 && hints.length > 0 && (
            <div className="mt-6">
              <h3 className="text-md font-semibold flex items-center gap-2 text-yellow-600">
                <Lightbulb size={18} />
                提示 (Level {hintLevel})
              </h3>
              <div className="mt-2 p-4 bg-yellow-50 border border-yellow-200 rounded-lg">
                <p className="text-yellow-800">{hints[hintLevel - 1]}</p>
              </div>
            </div>
          )}

          <div className="mt-6 flex gap-2">
            {hintLevel < hints.length && (
              <button
                onClick={() => setHintLevel(hintLevel + 1)}
                className="flex items-center gap-2 px-4 py-2 bg-yellow-100 text-yellow-700 rounded-lg hover:bg-yellow-200 transition-colors"
              >
                <Lightbulb size={18} />
                {hintLevel === 0 ? '获取提示' : '下一层提示'}
              </button>
            )}
          </div>
        </div>

        <div className="w-1/2 flex flex-col bg-gray-900">
          <div className="flex items-center justify-between px-4 py-2 bg-gray-800 border-b border-gray-700">
            <select
              value={language}
              onChange={(e) => setLanguage(e.target.value as Lang)}
              className="bg-gray-700 text-gray-200 px-3 py-1.5 rounded border-none text-sm outline-none"
            >
              <option value="python">Python 3</option>
              <option value="cpp">C++</option>
              <option value="java">Java</option>
            </select>
            <div className="flex gap-2">
              <button
                onClick={() => setCode('')}
                className="p-2 text-gray-400 hover:text-white transition-colors"
                title="重置代码"
              >
                <RotateCcw size={18} />
              </button>
              <button
                onClick={handleSubmit}
                disabled={isJudging || (!problem.sample_input && !useCustomInput)}
                title={
                  !problem.sample_input && !useCustomInput
                    ? '题目样例尚未同步，请先启用自定义输入'
                    : undefined
                }
                className="flex items-center gap-2 px-4 py-1.5 bg-green-600 text-white rounded hover:bg-green-700 disabled:opacity-50 transition-colors text-sm"
              >
                <Send size={16} />
                {isJudging ? '运行中...' : '运行代码'}
              </button>
            </div>
          </div>

          <div className="flex-1 overflow-hidden">
            <Editor
              height="100%"
              language={language === 'cpp' ? 'cpp' : language === 'java' ? 'java' : 'python'}
              value={code}
              onChange={(value) => setCode(value || '')}
              theme="vs-dark"
              options={{
                fontSize: 14,
                minimap: { enabled: false },
                scrollBeyondLastLine: false,
                automaticLayout: true,
              }}
            />
          </div>

          <div className="border-t border-gray-700 bg-gray-800 px-4 py-3">
            <label className="flex items-center gap-2 text-sm text-gray-200 cursor-pointer">
              <input
                type="checkbox"
                checked={useCustomInput}
                onChange={(event) => setUseCustomInput(event.target.checked)}
                className="rounded border-gray-500"
              />
              使用自定义输入
              {!problem.sample_input && (
                <span className="text-yellow-300 text-xs">样例不可用时必须填写</span>
              )}
            </label>
            {useCustomInput && (
              <textarea
                value={customInput}
                onChange={(event) => setCustomInput(event.target.value)}
                placeholder="在这里粘贴程序标准输入；允许空字符串，但需要主动勾选。"
                aria-label="自定义输入"
                className="mt-2 w-full h-24 resize-y rounded bg-gray-900 border border-gray-600 px-3 py-2 text-sm font-mono text-gray-100 placeholder:text-gray-500 focus:outline-none focus:border-blue-500"
              />
            )}
          </div>

          {error && (
            <div className="border-t border-gray-700 bg-red-900/30 p-4 flex items-center gap-2 text-red-300 text-sm">
              <AlertCircle size={16} />
              <span>{error}</span>
            </div>
          )}

          {result && (
            <div className="border-t border-gray-700 bg-gray-800 p-4 max-h-64 overflow-y-auto">
              <div
                className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-lg ${getStatusColor(
                  result.status
                )} mb-4`}
              >
                {getStatusIcon(result.status)}
                <span className="font-medium">{getStatusText(result.status)}</span>
                {result.is_real_judge && (
                  <span
                    className={`px-2 py-0.5 rounded text-xs font-bold ${
                      result.verdict === 'AC' ? 'bg-green-600 text-white' : 'bg-red-500 text-white'
                    }`}
                  >
                    {result.verdict === 'AC'
                      ? `AC · ${result.passed_cases}/${result.total_cases}`
                      : `${result.verdict} · ${result.passed_cases}/${result.total_cases}`}
                  </span>
                )}
              </div>

              <div className="flex gap-6 mb-4">
                <div className="flex items-center gap-2 text-gray-300">
                  <Clock size={16} />
                  <span>{result.time_used_ms} ms</span>
                </div>
                <div className="flex items-center gap-2 text-gray-300">
                  <Cpu size={16} />
                  <span>exit {result.exit_code}</span>
                </div>
              </div>

              <div className="space-y-3">
                <p className="text-sm text-yellow-300">{result.message}</p>
                {result.stdout && (
                  <div>
                    <p className="text-sm text-gray-400 mb-1">标准输出</p>
                    <pre className="text-gray-200 text-sm whitespace-pre-wrap bg-gray-900 p-2 rounded">
                      {result.stdout}
                    </pre>
                  </div>
                )}
                {result.stderr && (
                  <div>
                    <p className="text-sm text-gray-400 mb-1">标准错误 / 说明</p>
                    <pre className="text-red-300 text-sm whitespace-pre-wrap bg-gray-900 p-2 rounded">
                      {result.stderr}
                    </pre>
                  </div>
                )}
              </div>
            </div>
          )}

          {submissions.length > 0 && (
            <div className="border-t border-gray-700 bg-gray-800 p-4 max-h-48 overflow-y-auto">
              <div className="flex items-center gap-2 mb-2">
                <History size={14} className="text-gray-400" />
                <span className="text-xs text-gray-400 font-medium">提交记录</span>
              </div>
              <div className="space-y-1.5">
                {submissions.map((sub) => (
                  <div key={sub.id} className="flex items-center gap-2 text-xs">
                    {sub.verdict === 'OK' ? (
                      <CheckCircle size={12} className="text-green-400 flex-shrink-0" />
                    ) : (
                      <XCircle size={12} className="text-red-400 flex-shrink-0" />
                    )}
                    <span className={sub.verdict === 'OK' ? 'text-green-400' : 'text-red-400'}>
                      {sub.verdict === 'OK' ? 'AC' : sub.verdict}
                    </span>
                    <span className="text-gray-500">{sub.programming_language}</span>
                    <span className="text-gray-500 ml-auto">
                      {new Date(sub.submitted_at).toLocaleString('zh-CN', {
                        month: 'short',
                        day: 'numeric',
                        hour: '2-digit',
                        minute: '2-digit',
                      })}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

export default ProblemDetail
