import React, { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  ArrowLeft,
  Loader2,
  AlertCircle,
  CheckCircle,
  XCircle,
  ChevronRight,
  Trophy,
} from 'lucide-react'
import Editor from '@monaco-editor/react'
import { coldstartApi, problemsApi } from '../utils/api'
import type { ColdStartResult, CodeExecutionResult, Problem } from '../types'

interface Answer {
  problemId: string
  title: string
  verdict: string
  passed: number
  total: number
}

const Assess: React.FC = () => {
  const [result, setResult] = useState<ColdStartResult | null>(null)
  const [problems, setProblems] = useState<Problem[]>([])
  const [current, setCurrent] = useState(0)
  const [code, setCode] = useState('')
  const [execResult, setExecResult] = useState<CodeExecutionResult | null>(null)
  const [answers, setAnswers] = useState<Answer[]>([])
  const [loading, setLoading] = useState(true)
  const [running, setRunning] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [finished, setFinished] = useState(false)

  // 进入页面即开始摸底测试：获取诊断题并初始化画像
  useEffect(() => {
    let cancelled = false
    setLoading(true)
    coldstartApi
      .diagnostic()
      .then((resp) => {
        if (cancelled) return
        const r = resp.data as ColdStartResult
        setResult(r)
        const ids = r.diagnostic_problems || []
        if (ids.length === 0) {
          setError('未找到可用的摸底测试题，请先补充平台自建题目。')
          setLoading(false)
          return
        }
        return Promise.all(
          ids.map((pid) => problemsApi.getById(pid).then((p) => p.data as Problem))
        )
      })
      .then((list) => {
        if (cancelled) return
        if (list) {
          setProblems(list)
          const tpl =
            (list[0]?.solution_template as Record<string, string> | null)?.['python'] || ''
          setCode(tpl || '# 在这里写你的代码\n')
        }
      })
      .catch((err: unknown) => {
        if (cancelled) return
        setError(err instanceof Error ? err.message : '摸底测试加载失败')
      })
      .finally(() => !cancelled && setLoading(false))
    return () => {
      cancelled = true
    }
  }, [])

  const currentProblem = problems[current]
  const doneCount = answers.length

  const handleRun = async () => {
    if (!currentProblem || running) return
    setRunning(true)
    setExecResult(null)
    try {
      const resp = await problemsApi.execute(currentProblem.id, code, 'python')
      const r = resp.data as CodeExecutionResult
      setExecResult(r)
      // 记录本次作答（判题结果已由后端自动回传画像）
      setAnswers((prev) => {
        const exists = prev.find((a) => a.problemId === currentProblem.id)
        const answer: Answer = {
          problemId: currentProblem.id,
          title: currentProblem.title,
          verdict: r.verdict,
          passed: r.passed_cases,
          total: r.total_cases,
        }
        return exists
          ? prev.map((a) => (a.problemId === currentProblem.id ? answer : a))
          : [...prev, answer]
      })
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : '运行失败，请重试'
      setExecResult({
        status: 'internal_error',
        verdict: 'N/A',
        message: msg,
      } as CodeExecutionResult)
    } finally {
      setRunning(false)
    }
  }

  const handleNext = () => {
    if (current + 1 < problems.length) {
      setCurrent(current + 1)
      setExecResult(null)
      const tpl =
        (problems[current + 1]?.solution_template as Record<string, string> | null)?.['python'] ||
        ''
      setCode(tpl || '# 在这里写你的代码\n')
    } else {
      setFinished(true)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-[calc(100vh-4rem)] text-gray-500">
        <Loader2 className="animate-spin mr-2" size={20} />
        正在生成摸底测试...
      </div>
    )
  }

  if (error || !currentProblem) {
    return (
      <div className="flex flex-col items-center justify-center h-[calc(100vh-4rem)] gap-4">
        <AlertCircle size={40} className="text-red-500" />
        <p className="text-gray-700">{error || '摸底测试暂不可用'}</p>
        <Link to="/" className="text-blue-600 hover:underline">
          返回首页
        </Link>
      </div>
    )
  }

  return (
    <div className="min-h-[calc(100vh-4rem)] -m-8">
      {/* 顶部：进度条 */}
      <div className="bg-white border-b border-gray-200 px-8 py-4 flex items-center gap-4">
        <Link to="/" className="p-2 hover:bg-gray-100 rounded-lg">
          <ArrowLeft size={20} />
        </Link>
        <div className="flex-1">
          <div className="flex items-center justify-between mb-1">
            <span className="text-sm font-semibold text-gray-900">
              摸底测试 · 第 {Math.min(current + 1, problems.length)} / {problems.length} 题
            </span>
            <span className="text-xs text-gray-500">
              已完成 {doneCount} 题 · 作答后自动分析掌握情况
            </span>
          </div>
          <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
            <div
              className="h-full bg-blue-600 transition-all"
              style={{ width: `${(doneCount / problems.length) * 100}%` }}
            />
          </div>
        </div>
      </div>

      <div className="flex" style={{ height: 'calc(100vh - 8.5rem)' }}>
        {/* 左侧：题目列表 */}
        <div className="w-56 border-r border-gray-200 bg-white overflow-y-auto py-3">
          {problems.map((p, i) => {
            const ans = answers.find((a) => a.problemId === p.id)
            return (
              <button
                key={p.id}
                onClick={() => {
                  setCurrent(i)
                  setExecResult(null)
                }}
                className={`w-full text-left px-4 py-2.5 text-sm flex items-center gap-2 transition-colors ${
                  i === current ? 'bg-blue-50 text-blue-700' : 'text-gray-700 hover:bg-gray-50'
                }`}
              >
                <span className="w-6 h-6 rounded-full flex items-center justify-center text-xs shrink-0 border border-gray-200 bg-gray-50">
                  {ans ? (
                    ans.verdict === 'AC' ? (
                      <CheckCircle size={14} className="text-green-500" />
                    ) : (
                      <XCircle size={14} className="text-red-500" />
                    )
                  ) : (
                    i + 1
                  )}
                </span>
                <span className="truncate">{p.title}</span>
              </button>
            )
          })}
        </div>

        {/* 右侧：题目 + 编辑器 */}
        <div className="flex-1 flex">
          <div className="w-1/2 border-r border-gray-200 overflow-y-auto p-6 bg-white">
            <h2 className="text-lg font-semibold text-gray-900">{currentProblem.title}</h2>
            <p className="text-gray-700 mt-3 whitespace-pre-wrap">{currentProblem.description}</p>
            {currentProblem.sample_input && (
              <div className="mt-4">
                <p className="text-sm font-semibold text-gray-600">样例输入：</p>
                <pre className="bg-gray-50 p-3 rounded-lg text-sm text-gray-800 mt-1">
                  {currentProblem.sample_input}
                </pre>
              </div>
            )}
            {currentProblem.sample_output && (
              <div className="mt-4">
                <p className="text-sm font-semibold text-gray-600">样例输出：</p>
                <pre className="bg-gray-50 p-3 rounded-lg text-sm text-gray-800 mt-1">
                  {currentProblem.sample_output}
                </pre>
              </div>
            )}
          </div>

          <div className="flex-1 flex flex-col bg-gray-900">
            <div className="px-4 py-3 flex items-center justify-between border-b border-gray-700">
              <span className="text-sm text-gray-300 font-medium">Python 3</span>
              <div className="flex gap-2">
                <button
                  onClick={handleRun}
                  disabled={running}
                  className="px-4 py-1.5 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white text-sm rounded-lg transition-colors flex items-center gap-1"
                >
                  {running && <Loader2 className="animate-spin" size={14} />}
                  提交作答
                </button>
                {current + 1 < problems.length ? (
                  <button
                    onClick={handleNext}
                    className="px-4 py-1.5 bg-gray-700 hover:bg-gray-600 text-white text-sm rounded-lg transition-colors flex items-center gap-1"
                  >
                    下一题 <ChevronRight size={14} />
                  </button>
                ) : (
                  <button
                    onClick={handleNext}
                    className="px-4 py-1.5 bg-green-600 hover:bg-green-700 text-white text-sm rounded-lg transition-colors flex items-center gap-1"
                  >
                    完成测试 <Trophy size={14} />
                  </button>
                )}
              </div>
            </div>
            <div className="flex-1">
              <Editor
                language="python"
                value={code}
                onChange={(v) => setCode(v || '')}
                theme="vs-dark"
                options={{
                  fontSize: 14,
                  minimap: { enabled: false },
                  scrollBeyondLastLine: false,
                  automaticLayout: true,
                }}
              />
            </div>
            {execResult && (
              <div className="border-t border-gray-700 bg-gray-800 p-4 max-h-48 overflow-y-auto">
                <div className="flex items-center gap-3 mb-2">
                  {execResult.verdict === 'AC' ? (
                    <span className="flex items-center gap-1 px-3 py-1 rounded bg-green-600 text-white text-sm font-bold">
                      <CheckCircle size={14} /> AC · {execResult.passed_cases}/
                      {execResult.total_cases}
                    </span>
                  ) : (
                    <span className="flex items-center gap-1 px-3 py-1 rounded bg-red-500 text-white text-sm font-bold">
                      <XCircle size={14} />
                      {execResult.verdict || 'N/A'}
                    </span>
                  )}
                  <span className="text-xs text-gray-400">结果已计入掌握情况分析</span>
                </div>
                <p className="text-sm text-yellow-300">{execResult.message}</p>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* 完成弹层 */}
      {finished && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-white rounded-2xl p-8 max-w-md w-full shadow-xl">
            <div className="flex items-center gap-3 mb-4">
              <Trophy size={28} className="text-yellow-500" />
              <h2 className="text-xl font-bold text-gray-900">摸底测试完成！</h2>
            </div>
            <p className="text-gray-600 mb-4">
              你的测试结果已同步到学习画像：
              <span className="font-medium text-gray-900">
                目标难度 {result?.target_rating_min} ~ {result?.target_rating_max}
              </span>
              ，系统已根据作答情况生成个性化学习路径。
            </p>
            <p className="text-sm text-gray-500 mb-6">
              建议前往「算法路线图」生成专属学习路径，开始今日学习。
            </p>
            <div className="flex gap-3">
              <Link
                to="/knowledge"
                className="flex-1 text-center px-4 py-2.5 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm font-medium transition-colors"
              >
                去生成学习路径
              </Link>
              <Link
                to="/today"
                className="flex-1 text-center px-4 py-2.5 border border-gray-300 hover:bg-gray-50 text-gray-700 rounded-lg text-sm font-medium transition-colors"
              >
                去看今日学习
              </Link>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default Assess
