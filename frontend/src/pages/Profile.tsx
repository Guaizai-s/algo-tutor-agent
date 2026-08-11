import React, { useState } from 'react'
import { ExternalLink, Link2, Save, CheckCircle, AlertCircle, Trophy } from 'lucide-react'
import { useAuthStore } from '../stores/authStore'
import type { BindCFResponse, TargetMedal as MedalType } from '../types'

const MEDAL_OPTIONS: { value: MedalType; label: string; color: string }[] = [
  { value: 'bronze', label: '铜牌', color: 'bg-amber-100 text-amber-700' },
  { value: 'silver', label: '银牌', color: 'bg-gray-100 text-gray-700' },
  { value: 'gold', label: '金牌', color: 'bg-yellow-100 text-yellow-700' },
]

const Profile: React.FC = () => {
  const { user, bindCF, updateProfile } = useAuthStore()

  // ===== CF 绑定 =====
  const [cfHandle, setCfHandle] = useState(user?.cf_handle || '')
  const [cfBinding, setCfBinding] = useState(false)
  const [cfResult, setCfResult] = useState<BindCFResponse | null>(null)
  const [cfError, setCfError] = useState<string | null>(null)

  const handleBindCF = async () => {
    const handle = cfHandle.trim()
    if (!handle) {
      setCfError('请输入 Codeforces handle')
      return
    }
    setCfBinding(true)
    setCfError(null)
    setCfResult(null)
    try {
      const result = await bindCF(handle)
      setCfResult(result)
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setCfError(detail || '绑定失败，请确认 handle 正确后重试')
    } finally {
      setCfBinding(false)
    }
  }

  // ===== 档案编辑 =====
  const [school, setSchool] = useState(user?.school || '')
  const [atcoderHandle, setAtcoderHandle] = useState(user?.atcoder_handle || '')
  const [targetMedal, setTargetMedal] = useState<MedalType | ''>(user?.target_medal || '')
  const [profileSaving, setProfileSaving] = useState(false)
  const [profileSaved, setProfileSaved] = useState(false)
  const [profileError, setProfileError] = useState<string | null>(null)

  const handleSaveProfile = async () => {
    setProfileSaving(true)
    setProfileError(null)
    setProfileSaved(false)
    try {
      await updateProfile({
        school: school || null,
        atcoder_handle: atcoderHandle || null,
        target_medal: (targetMedal || null) as MedalType | null,
      })
      setProfileSaved(true)
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setProfileError(detail || '保存失败，请重试')
    } finally {
      setProfileSaving(false)
    }
  }

  const cfBound = !!user?.cf_handle

  return (
    <div className="max-w-3xl mx-auto space-y-8">
      <div>
        <h1 className="text-3xl font-bold text-gray-900">个人档案</h1>
        <p className="text-gray-600 mt-2">
          绑定 Codeforces 账号后，系统每 5 分钟自动同步你的提交记录与 AC 状态
        </p>
      </div>

      {/* ===== CF 绑定卡片 ===== */}
      <section className="bg-white rounded-xl p-6 shadow-sm border border-gray-100">
        <div className="flex items-center gap-3 mb-4">
          <div className="w-10 h-10 bg-blue-100 rounded-lg flex items-center justify-center text-blue-600">
            <Link2 size={20} />
          </div>
          <div>
            <h2 className="text-lg font-semibold text-gray-900">Codeforces 账号</h2>
            <p className="text-sm text-gray-500">绑定后自动汇集你的 CF 提交结果</p>
          </div>
        </div>

        {cfBound ? (
          <div className="space-y-4">
            <div className="flex items-center gap-4 p-4 bg-green-50 border border-green-200 rounded-lg">
              <CheckCircle size={24} className="text-green-600 flex-shrink-0" />
              <div className="flex-1">
                <p className="font-medium text-gray-900">
                  已绑定：
                  <a
                    href={`https://codeforces.com/profile/${user?.cf_handle}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-blue-600 hover:underline inline-flex items-center gap-1 ml-1"
                  >
                    {user?.cf_handle}
                    <ExternalLink size={14} />
                  </a>
                </p>
                {cfResult && (
                  <p className="text-sm text-gray-600 mt-1">
                    {cfResult.rank ? `段位：${cfResult.rank}，` : ''}
                    {cfResult.current_rating != null
                      ? `当前 Rating：${cfResult.current_rating}`
                      : '暂无 Rating'}
                    {cfResult.max_rating != null ? `（最高 ${cfResult.max_rating}）` : ''}
                  </p>
                )}
                <p className="text-xs text-gray-500 mt-1">
                  系统每 5 分钟自动拉取你的最新提交，AC 的题目会自动标记为已掌握。
                </p>
              </div>
            </div>
            <p className="text-xs text-gray-500">如需更换绑定，请联系管理员确认账号归属后处理。</p>
          </div>
        ) : (
          <div className="space-y-3">
            <div className="p-3 bg-yellow-50 border border-yellow-200 rounded-lg text-sm text-yellow-800 flex items-start gap-2">
              <AlertCircle size={16} className="flex-shrink-0 mt-0.5" />
              <span>
                未绑定 CF 账号。绑定后才能汇集你在 Codeforces 上的提交记录与 AC
                状态，否则题库只能空转。
              </span>
            </div>
            <div className="flex gap-2">
              <input
                type="text"
                value={cfHandle}
                onChange={(e) => setCfHandle(e.target.value)}
                placeholder="输入你的 Codeforces handle"
                className="flex-1 px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none"
                onKeyDown={(e) => {
                  if (e.key === 'Enter') handleBindCF()
                }}
              />
              <button
                onClick={handleBindCF}
                disabled={cfBinding}
                className="px-5 py-2.5 bg-blue-600 hover:bg-blue-700 disabled:bg-blue-400 text-white font-medium rounded-lg transition-colors whitespace-nowrap"
              >
                {cfBinding ? '验证中...' : '绑定'}
              </button>
            </div>
            {cfError && (
              <p className="text-sm text-red-600 flex items-center gap-1">
                <AlertCircle size={14} />
                {cfError}
              </p>
            )}
            <p className="text-xs text-gray-500">
              不知道自己的 handle？登录
              <a
                href="https://codeforces.com"
                target="_blank"
                rel="noopener noreferrer"
                className="text-blue-600 hover:underline inline-flex items-center gap-0.5 mx-1"
              >
                Codeforces
                <ExternalLink size={12} />
              </a>
              后在右上角查看。
            </p>
          </div>
        )}
      </section>

      {/* ===== 档案编辑卡片 ===== */}
      <section className="bg-white rounded-xl p-6 shadow-sm border border-gray-100">
        <div className="flex items-center gap-3 mb-4">
          <div className="w-10 h-10 bg-purple-100 rounded-lg flex items-center justify-center text-purple-600">
            <Trophy size={20} />
          </div>
          <div>
            <h2 className="text-lg font-semibold text-gray-900">学习档案</h2>
            <p className="text-sm text-gray-500">完善信息以获得更精准的推荐</p>
          </div>
        </div>

        <div className="space-y-5">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">学校</label>
            <input
              type="text"
              value={school}
              onChange={(e) => setSchool(e.target.value)}
              placeholder="填写你的学校（选填）"
              className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">AtCoder Handle</label>
            <input
              type="text"
              value={atcoderHandle}
              onChange={(e) => setAtcoderHandle(e.target.value)}
              placeholder="AtCoder 用户名（选填）"
              className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">目标奖牌</label>
            <div className="flex gap-2">
              {MEDAL_OPTIONS.map((opt) => (
                <button
                  key={opt.value}
                  type="button"
                  onClick={() => setTargetMedal(targetMedal === opt.value ? '' : opt.value)}
                  className={`px-4 py-2 rounded-lg text-sm font-medium border transition-colors ${
                    targetMedal === opt.value
                      ? `${opt.color} border-current`
                      : 'bg-white text-gray-600 border-gray-200 hover:border-gray-300'
                  }`}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </div>

          {profileError && (
            <p className="text-sm text-red-600 flex items-center gap-1">
              <AlertCircle size={14} />
              {profileError}
            </p>
          )}
          {profileSaved && (
            <p className="text-sm text-green-600 flex items-center gap-1">
              <CheckCircle size={14} />
              档案已保存
            </p>
          )}

          <button
            onClick={handleSaveProfile}
            disabled={profileSaving}
            className="inline-flex items-center gap-2 px-5 py-2.5 bg-gray-900 hover:bg-gray-800 disabled:bg-gray-400 text-white font-medium rounded-lg transition-colors"
          >
            <Save size={16} />
            {profileSaving ? '保存中...' : '保存档案'}
          </button>
        </div>
      </section>
    </div>
  )
}

export default Profile
