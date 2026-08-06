import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { CheckCircle2, ExternalLink, Loader2, Save, UserRound } from 'lucide-react'
import { useAuthStore } from '../stores/authStore'
import type { CodeforcesAccount, ColdStartResponse, ProfileUpdateRequest } from '../types'
import { authApi, onboardingApi } from '../utils/api'

const getErrorMessage = (error: unknown, fallback: string): string => {
  const detail = (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail
  return detail || (error instanceof Error ? error.message : fallback)
}

const Profile = () => {
  const { user, updateProfile, setUser } = useAuthStore()
  const [form, setForm] = useState<ProfileUpdateRequest>({
    username: user?.username ?? '',
    school: user?.school ?? '',
    atcoder_handle: user?.atcoder_handle ?? '',
    target_medal: user?.target_medal ?? 'silver',
  })
  const [cfHandle, setCfHandle] = useState(user?.cf_handle ?? '')
  const [account, setAccount] = useState<CodeforcesAccount | null>(null)
  const [onboarding, setOnboarding] = useState<ColdStartResponse | null>(null)
  const [diagnosticResults, setDiagnosticResults] = useState<Record<string, boolean>>({})
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const loadProfileData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [profileResponse, cfResponse, onboardingResponse] = await Promise.all([
        authApi.getProfile(),
        authApi.getCodeforces(),
        onboardingApi.getStatus(),
      ])
      setUser(profileResponse.data)
      setForm({
        username: profileResponse.data.username,
        school: profileResponse.data.school ?? '',
        atcoder_handle: profileResponse.data.atcoder_handle ?? '',
        target_medal: profileResponse.data.target_medal ?? 'silver',
      })
      setCfHandle(profileResponse.data.cf_handle ?? '')
      setAccount(cfResponse.data)
      setOnboarding(onboardingResponse.data)
    } catch (err: unknown) {
      setError(getErrorMessage(err, '加载个人档案失败'))
    } finally {
      setLoading(false)
    }
  }, [setUser])

  useEffect(() => {
    void loadProfileData()
  }, [loadProfileData])

  const saveProfile = async (event: React.FormEvent) => {
    event.preventDefault()
    setBusy('profile')
    setError(null)
    setMessage(null)
    try {
      await updateProfile(form)
      setMessage('个人档案已保存')
    } catch (err: unknown) {
      setError(getErrorMessage(err, '保存个人档案失败'))
    } finally {
      setBusy(null)
    }
  }

  const bindCodeforces = async (event: React.FormEvent) => {
    event.preventDefault()
    setBusy('bind')
    setError(null)
    setMessage(null)
    try {
      const response = await authApi.bindCodeforces(cfHandle)
      setUser(response.data.user)
      setAccount(response.data.account)
      setCfHandle(response.data.account.handle)
      setMessage('Codeforces 账号验证并绑定成功，可以开始冷启动同步')
    } catch (err: unknown) {
      setError(getErrorMessage(err, '绑定 Codeforces 失败'))
    } finally {
      setBusy(null)
    }
  }

  const startOnboarding = async () => {
    setBusy('onboarding')
    setError(null)
    setMessage(null)
    try {
      const response = await onboardingApi.start()
      setOnboarding(response.data)
      setDiagnosticResults(
        Object.fromEntries(response.data.diagnostic_problems.map((problem) => [problem.id, false]))
      )
      setMessage(response.data.message)
      const cfResponse = await authApi.getCodeforces()
      setAccount(cfResponse.data)
    } catch (err: unknown) {
      setError(getErrorMessage(err, '启动冷启动失败'))
    } finally {
      setBusy(null)
    }
  }

  const submitDiagnostic = async () => {
    if (!onboarding?.diagnostic_problems.length) return
    setBusy('diagnostic')
    setError(null)
    setMessage(null)
    try {
      const results = onboarding.diagnostic_problems.map((problem) => ({
        problem_id: problem.id,
        correct: diagnosticResults[problem.id] ?? false,
      }))
      const response = await onboardingApi.submitDiagnostic(results)
      setOnboarding(response.data)
      setMessage(response.data.message)
    } catch (err: unknown) {
      setError(getErrorMessage(err, '提交诊断结果失败'))
    } finally {
      setBusy(null)
    }
  }

  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center text-gray-500">
        <Loader2 className="mr-2 animate-spin" size={20} />
        加载个人档案...
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <div>
        <h1 className="flex items-center gap-2 text-3xl font-bold text-gray-900">
          <UserRound className="text-blue-600" /> 个人档案与冷启动
        </h1>
        <p className="mt-2 text-gray-600">完善 ACM 档案，绑定 Codeforces 后生成初始学习路径。</p>
      </div>

      {error ? (
        <div role="alert" className="rounded-xl border border-red-200 bg-red-50 p-4 text-red-700">
          {error}
        </div>
      ) : null}
      {message ? (
        <div
          role="status"
          className="rounded-xl border border-green-200 bg-green-50 p-4 text-green-700"
        >
          {message}
        </div>
      ) : null}

      <div className="grid gap-6 lg:grid-cols-2">
        <form
          onSubmit={saveProfile}
          className="space-y-4 rounded-xl border border-gray-100 bg-white p-6 shadow-sm"
        >
          <h2 className="text-lg font-semibold">ACM 档案</h2>
          <label className="block text-sm font-medium text-gray-700">
            用户名
            <input
              value={form.username ?? ''}
              onChange={(event) =>
                setForm((current) => ({ ...current, username: event.target.value }))
              }
              className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2"
              required
              minLength={2}
            />
          </label>
          <label className="block text-sm font-medium text-gray-700">
            学校
            <input
              value={form.school ?? ''}
              onChange={(event) =>
                setForm((current) => ({ ...current, school: event.target.value }))
              }
              className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2"
              required
              placeholder="请输入学校名称"
            />
          </label>
          <label className="block text-sm font-medium text-gray-700">
            AtCoder handle（可选）
            <input
              value={form.atcoder_handle ?? ''}
              onChange={(event) =>
                setForm((current) => ({ ...current, atcoder_handle: event.target.value }))
              }
              className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2"
            />
          </label>
          <label className="block text-sm font-medium text-gray-700">
            目标奖牌
            <select
              value={form.target_medal ?? 'silver'}
              onChange={(event) =>
                setForm((current) => ({
                  ...current,
                  target_medal: event.target.value as 'bronze' | 'silver' | 'gold',
                }))
              }
              className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2"
            >
              <option value="bronze">铜牌</option>
              <option value="silver">银牌</option>
              <option value="gold">金牌</option>
            </select>
          </label>
          <button
            type="submit"
            disabled={busy !== null}
            className="flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-white hover:bg-blue-700 disabled:opacity-50"
          >
            {busy === 'profile' ? (
              <Loader2 className="animate-spin" size={16} />
            ) : (
              <Save size={16} />
            )}
            保存档案
          </button>
        </form>

        <div className="space-y-4 rounded-xl border border-gray-100 bg-white p-6 shadow-sm">
          <h2 className="text-lg font-semibold">Codeforces 绑定</h2>
          {account ? (
            <div className="rounded-lg bg-blue-50 p-4 text-sm text-blue-800">
              <p className="font-medium">已绑定：{account.handle}</p>
              <p className="mt-1">当前 Rating：{account.current_rating ?? '未定级'}</p>
              <a
                href={`https://codeforces.com/profile/${account.handle}`}
                target="_blank"
                rel="noreferrer"
                className="mt-2 inline-flex items-center gap-1 text-blue-600 hover:underline"
              >
                查看 CF 主页 <ExternalLink size={14} />
              </a>
            </div>
          ) : (
            <form onSubmit={bindCodeforces} className="space-y-3">
              <label className="block text-sm font-medium text-gray-700">
                CF handle
                <input
                  value={cfHandle}
                  onChange={(event) => setCfHandle(event.target.value)}
                  className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2"
                  required
                  minLength={3}
                />
              </label>
              <button
                type="submit"
                disabled={busy !== null}
                className="rounded-lg bg-indigo-600 px-4 py-2 text-white hover:bg-indigo-700 disabled:opacity-50"
              >
                {busy === 'bind' ? '验证中...' : '验证并绑定'}
              </button>
            </form>
          )}

          <div className="border-t border-gray-100 pt-4">
            <div className="flex items-center justify-between gap-3">
              <div>
                <p className="font-medium">冷启动状态</p>
                <p className="text-sm text-gray-500">{onboarding?.message ?? '尚未开始'}</p>
              </div>
              {onboarding?.completed ? (
                <CheckCircle2 className="text-green-500" />
              ) : (
                <button
                  type="button"
                  onClick={startOnboarding}
                  disabled={busy !== null}
                  className="rounded-lg bg-green-600 px-4 py-2 text-sm text-white hover:bg-green-700 disabled:opacity-50"
                >
                  {busy === 'onboarding' ? '同步中...' : '开始冷启动'}
                </button>
              )}
            </div>
            {onboarding?.completed ? (
              <div className="mt-3 flex gap-4 text-sm">
                <Link to="/today" className="text-blue-600 hover:underline">
                  查看今日任务
                </Link>
                <Link to="/progress" className="text-blue-600 hover:underline">
                  查看学习进度
                </Link>
              </div>
            ) : null}
          </div>
        </div>
      </div>

      {onboarding?.mode === 'diagnostic_required' ? (
        <section className="rounded-xl border border-gray-100 bg-white p-6 shadow-sm">
          <h2 className="text-lg font-semibold">诊断题结果</h2>
          <p className="mt-1 text-sm text-gray-500">
            完成题目后勾选已通过项；未勾选项将作为薄弱点。
          </p>
          <p
            className={`mt-2 text-sm ${onboarding.diagnostic_ready ? 'text-green-700' : 'text-amber-700'}`}
            role="status"
          >
            当前题单：{onboarding.diagnostic_problem_count} 道题，覆盖{' '}
            {onboarding.diagnostic_knowledge_count} 个知识点
            {onboarding.diagnostic_ready
              ? '，已达到正式诊断标准。'
              : '，内容不足时将按可用题目降级。'}
          </p>
          {onboarding.diagnostic_problems.length ? (
            <div className="mt-4 space-y-2">
              {onboarding.diagnostic_problems.map((problem) => (
                <label
                  key={problem.id}
                  className="flex items-center gap-3 rounded-lg border border-gray-100 p-3"
                >
                  <input
                    type="checkbox"
                    checked={diagnosticResults[problem.id] ?? false}
                    onChange={(event) =>
                      setDiagnosticResults((current) => ({
                        ...current,
                        [problem.id]: event.target.checked,
                      }))
                    }
                    className="h-4 w-4"
                  />
                  <Link
                    to={`/problems/${problem.id}`}
                    className="flex-1 text-gray-800 hover:text-blue-600"
                  >
                    {problem.title}
                  </Link>
                  <span className="text-xs uppercase text-gray-500">{problem.difficulty}</span>
                </label>
              ))}
              <button
                type="button"
                onClick={submitDiagnostic}
                disabled={busy !== null}
                className="mt-3 rounded-lg bg-blue-600 px-4 py-2 text-white hover:bg-blue-700 disabled:opacity-50"
              >
                {busy === 'diagnostic' ? '生成路径中...' : '提交诊断并生成路径'}
              </button>
            </div>
          ) : (
            <p className="mt-4 rounded-lg bg-yellow-50 p-4 text-sm text-yellow-800">
              当前没有可用的平台诊断题，请先执行种子数据脚本。
            </p>
          )}
        </section>
      ) : null}
    </div>
  )
}

export default Profile
