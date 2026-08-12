import React from 'react'

/**
 * 双维度难度圆图
 * 对角线斜切：左上=理解难度，右下=理论深度
 * 洛谷五色：红橙黄绿青
 */

interface Props {
  comprehension: number
  theory: number
  size?: number
  showLabels?: boolean
}

const COLORS = ['#fe4c61', '#f39c11', '#ffc116', '#52c41a', '#3498db']
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

  const grad = `conic-gradient(from 135deg, ${COLORS[ci]} 0deg 180deg, ${COLORS[ti]} 180deg 360deg)`

  return (
    <div className="flex flex-col items-center gap-1.5">
      <div
        className="flex items-center justify-center flex-shrink-0"
        style={{ width: size, height: size, borderRadius: '50%', background: grad }}
      >
        {showLabels && size >= 60 && (
          <div
            className="flex flex-col items-center leading-tight bg-white/85 rounded-full"
            style={{ width: size * 0.4, height: size * 0.4, justifyContent: 'center' }}
          >
            <span className="text-lg font-bold text-gray-800">{comprehension}</span>
            <span className="text-[10px] text-gray-400">理解</span>
            <span className="text-sm font-semibold text-gray-800">{theory}</span>
            <span className="text-[9px] text-gray-400">{LABEL[clamp(theory)]}·理论</span>
          </div>
        )}
      </div>

      {showLabels && (
        <div className="flex flex-col gap-0.5 text-xs text-gray-500">
          {(
            [
              ['理解难度', ci, clamp(comprehension)],
              ['理论深度', ti, clamp(theory)],
            ] as const
          ).map(([label, idx, val]) => (
            <div key={label} className="flex items-center gap-1.5">
              <span className="w-11 text-right">{label}</span>
              {COLORS.map((c, i) => (
                <span
                  key={i}
                  className="w-3 h-3 rounded-sm transition-all"
                  style={{
                    background: c,
                    opacity: i === idx ? 1 : 0.3,
                    outline: i === idx ? `2px solid ${c}` : 'none',
                    outlineOffset: 1,
                  }}
                />
              ))}
              <span className="font-medium text-gray-700">
                {val} {LABEL[val]}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export default DifficultySemicircle
