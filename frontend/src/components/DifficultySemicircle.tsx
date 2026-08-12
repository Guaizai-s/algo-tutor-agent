import React from 'react'

/**
 * 双维度难度圆图
 * 对角线斜切为两半：左上 = 理解难度，右下 = 理论深度
 * 配色参考洛谷版：1=灰 2=绿 3=蓝 4=紫/橙 5=红/黑
 */

interface Props {
  comprehension: number
  theory: number
  size?: number
  showLabels?: boolean
}

/** 理解难度（左上）暖色 */
const COMP = ['#bfbfbf', '#52c41a', '#3498db', '#f39c11', '#fe4c61']

/** 理论深度（右下）冷色 */
const THEORY = ['#bfbfbf', '#52c41a', '#3498db', '#9d3dcf', '#0e1d69']

/** 1-5 → 中文 */
const LABEL = ['', '入门', '基础', '提高', '省选', 'NOI']

const DifficultySemicircle: React.FC<Props> = ({
  comprehension,
  theory,
  size = 120,
  showLabels = true,
}) => {
  const clamp = (v: number) => Math.min(Math.max(v || 1, 1), 5)
  const ci = clamp(comprehension) - 1
  const ti = clamp(theory) - 1

  // from 135deg: 分割线从左上到右下
  const grad = `conic-gradient(from 135deg, ${COMP[ci]} 0deg 180deg, ${THEORY[ti]} 180deg 360deg)`

  return (
    <div className="flex flex-col items-center gap-1.5">
      <div
        className="flex items-center justify-center flex-shrink-0"
        style={{
          width: size,
          height: size,
          borderRadius: '50%',
          background: grad,
        }}
      >
        {showLabels && size >= 60 && (
          <div
            className="flex flex-col items-center leading-tight bg-white/85 rounded-full"
            style={{ width: size * 0.45, height: size * 0.45, justifyContent: 'center' }}
          >
            <span className="text-lg font-bold text-gray-800">{comprehension}</span>
            <span className="text-[10px] text-gray-400">理解</span>
            <span className="text-sm font-semibold text-gray-800">{theory}</span>
            <span className="text-[9px] text-gray-400">{LABEL[clamp(theory)]}·理论</span>
          </div>
        )}
      </div>

      {showLabels && (
        <div className="flex items-center gap-3 text-xs text-gray-500">
          <span className="flex items-center gap-1">
            <span className="w-3 h-3 rounded-sm" style={{ background: COMP[ci] }} />
            理解难度
          </span>
          <span className="flex items-center gap-1">
            <span className="w-3 h-3 rounded-sm" style={{ background: THEORY[ti] }} />
            理论深度
          </span>
        </div>
      )}
    </div>
  )
}

export default DifficultySemicircle
