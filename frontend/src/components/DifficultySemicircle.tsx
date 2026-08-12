import React from 'react'

/**
 * 双维度难度半圆图表
 *
 * 两个半圆拼接为整圆：
 * - 上半：理解难度（comprehension_difficulty 1-5）
 * - 下半：理论深度（theory_depth 1-5）
 *
 * 每个半圆一种纯色，配色参考洛谷灰/绿/蓝/紫/红/黑。
 */

interface DifficultySemicircleProps {
  comprehension: number
  theory: number
  size?: number
  showLabels?: boolean
}

// ---- 洛谷配色：1-5 → 颜色 ----

/** 理解难度（上半）暖色系 */
const COMP_COLORS = ['#bfbfbf', '#52c41a', '#3498db', '#f39c11', '#fe4c61']

/** 理论深度（下半）冷色系 */
const THEORY_COLORS = ['#bfbfbf', '#52c41a', '#3498db', '#9d3dcf', '#0e1d69']

/** 1-5 → 中文 */
const LEVEL_LABELS = ['', '入门', '基础', '提高', '省选', 'NOI']

/**
 * 上半圆 path：圆心(cx,cy)，半径 r，从 0°=12点方向，顺时针画 180°
 * SVG arc: A rx ry x-rotation large-arc sweep x y
 *   - 180° 弧: large-arc=0, sweep=1 (顺时针)
 *   起点: (cx, cy-r), 终点: (cx, cy+r)
 */
const upperHalfPath = (cx: number, cy: number, r: number) => {
  // 180° clockwise from top to bottom
  return `M ${cx} ${cy - r} A ${r} ${r} 0 0 1 ${cx} ${cy + r}`
}

const lowerHalfPath = (cx: number, cy: number, r: number) => {
  // 180° clockwise from bottom to top
  return `M ${cx} ${cy + r} A ${r} ${r} 0 0 1 ${cx} ${cy - r}`
}

const DifficultySemicircle: React.FC<DifficultySemicircleProps> = ({
  comprehension,
  theory,
  size = 120,
  showLabels = true,
}) => {
  const cx = size / 2
  const cy = size / 2
  // 圆环内外径
  const outerR = size / 2 - 4
  const innerR = outerR - 16

  const compColor = COMP_COLORS[Math.min(Math.max(comprehension, 1), 5) - 1]
  const theoryColor = THEORY_COLORS[Math.min(Math.max(theory, 1), 5) - 1]

  // 上半填充：上半圆 + 内环+闭合
  const upperFill = `${upperHalfPath(cx, cy, outerR)} L ${cx} ${cy - innerR} A ${innerR} ${innerR} 0 0 0 ${cx} ${cy + innerR} Z`
  // 下半填充
  const lowerFill = `${lowerHalfPath(cx, cy, outerR)} L ${cx} ${cy + innerR} A ${innerR} ${innerR} 0 0 0 ${cx} ${cy - innerR} Z`

  // 水平分割线端点
  return (
    <div className="flex flex-col items-center gap-1.5">
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        {/* 上半：理解难度 */}
        <path d={upperFill} fill={compColor} opacity={0.85} />
        {/* 下半：理论深度 */}
        <path d={lowerFill} fill={theoryColor} opacity={0.85} />
        {/* 水平分割线 */}
        <line x1={cx - outerR} y1={cy} x2={cx - innerR} y2={cy} stroke="white" strokeWidth={2} />
        <line x1={cx + innerR} y1={cy} x2={cx + outerR} y2={cy} stroke="white" strokeWidth={2} />

        {/* 中心文字 */}
        {showLabels && (
          <>
            <text x={cx} y={cy - 7} textAnchor="middle" className="fill-gray-800"
              style={{ fontSize: '18px', fontWeight: 700 }}>
              {comprehension}
            </text>
            <text x={cx} y={cy + 4} textAnchor="middle" className="fill-gray-400"
              style={{ fontSize: '10px' }}>
              理解
            </text>
            <text x={cx} y={cy + 15} textAnchor="middle" className="fill-gray-800"
              style={{ fontSize: '14px', fontWeight: 600 }}>
              {theory}
            </text>
            <text x={cx} y={cy + 24} textAnchor="middle" className="fill-gray-400"
              style={{ fontSize: '9px' }}>
              {LEVEL_LABELS[theory]}·理论
            </text>
          </>
        )}
      </svg>

      {/* 图例 */}
      {showLabels && (
        <div className="flex items-center gap-3 text-xs text-gray-500">
          <span className="flex items-center gap-1">
            <span className="w-3 h-3 rounded-sm" style={{ backgroundColor: compColor }} />
            理解难度
          </span>
          <span className="flex items-center gap-1">
            <span className="w-3 h-3 rounded-sm" style={{ backgroundColor: theoryColor }} />
            理论深度
          </span>
        </div>
      )}
    </div>
  )
}

export default DifficultySemicircle
