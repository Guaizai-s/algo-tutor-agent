import React from 'react'

/**
 * 双维度难度半圆图表
 *
 * 整圆被水平分割为两半：
 * - 上半（左半弧）：理解难度 comprehension_difficulty（1-5）
 * - 下半（右半弧）：理论深度 theory_depth（1-5）
 *
 * 每半部分是一个半圆弧，弧度 = (value / 5) * 180°
 * 颜色从冷色到暖色渐变，值越高越深。
 */

interface DifficultySemicircleProps {
  /** 理解难度 1-5 */
  comprehension: number
  /** 理论深度 1-5 */
  theory: number
  /** 整体尺寸，默认 120 */
  size?: number
  /** 是否显示标签，默认 true */
  showLabels?: boolean
}

/** 理解难度 1-5 → 颜色 */
const comprehensionColor = (v: number): string => {
  const colors = ['#22c55e', '#84cc16', '#eab308', '#f97316', '#ef4444']
  return colors[Math.min(Math.max(v, 1), 5) - 1] || colors[0]
}

/** 理论深度 1-5 → 颜色 */
const theoryColor = (v: number): string => {
  const colors = ['#06b6d4', '#3b82f6', '#6366f1', '#8b5cf6', '#a855f7']
  return colors[Math.min(Math.max(v, 1), 5) - 1] || colors[0]
}

/** 1-5 → 中文描述 */
const levelLabel = (v: number): string => {
  const labels = ['', '入门', '基础', '中等', '较难', '困难']
  return labels[Math.min(Math.max(v, 1), 5)] || ''
}

const DifficultySemicircle: React.FC<DifficultySemicircleProps> = ({
  comprehension,
  theory,
  size = 120,
  showLabels = true,
}) => {
  const cx = size / 2
  const cy = size / 2
  const outerR = size / 2 - 4
  const innerR = outerR - 10
  const strokeW = outerR - innerR // 环宽度

  // 上半弧：从左(180°) 顺时针画到右(0°)，实际从180°画到(180 - angle)度
  const compAngle = (comprehension / 5) * 180

  // 下半弧：从右(0°) 顺时针画到左(180°)，实际从0°画到(0 + angle)度
  const theoryAngle = (theory / 5) * 180

  /** 极坐标转笛卡尔坐标，角度从正上方(12点)顺时针 */
  const polarToCartesian = (r: number, angleDeg: number) => {
    const rad = ((angleDeg - 90) * Math.PI) / 180
    return {
      x: cx + r * Math.cos(rad),
      y: cy + r * Math.sin(rad),
    }
  }

  /** 画弧线 path（从 startAngle 顺时针到 endAngle） */
  const arcPath = (r: number, startAngle: number, endAngle: number) => {
    const s = polarToCartesian(r, startAngle)
    const e = polarToCartesian(r, endAngle)
    const sweep = endAngle - startAngle <= 180 ? 0 : 1
    return `M ${s.x} ${s.y} A ${r} ${r} 0 ${sweep} 1 ${e.x} ${e.y}`
  }

  // 上半弧（理解难度）：左侧(180°) → 右侧(0°)，从180倒着到180-compAngle
  const compOuterPath = arcPath(outerR, 180, 180 - compAngle)
  const compInnerPath = arcPath(innerR, 180 - compAngle, 180)

  // 下半弧（理论深度）：右侧(0°) → 左侧(180°)，顺时针
  const theoryOuterPath = arcPath(outerR, 0, theoryAngle)
  const theoryInnerPath = arcPath(innerR, theoryAngle, 0)

  const compColor = comprehensionColor(comprehension)
  const theoryCol = theoryColor(theory)

  return (
    <div className="flex flex-col items-center gap-1">
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        {/* 背景圆环 */}
        <circle
          cx={cx}
          cy={cy}
          r={(outerR + innerR) / 2}
          fill="none"
          stroke="#e5e7eb"
          strokeWidth={strokeW}
          strokeDasharray={`${((outerR + innerR) / 2) * Math.PI} ${((outerR + innerR) / 2) * Math.PI}`}
          strokeDashoffset={0}
        />

        {/* 上半弧 - 理解难度（填充扇形区域） */}
        <path
          d={`${compOuterPath} L ${polarToCartesian(innerR, 180 - compAngle).x} ${
            polarToCartesian(innerR, 180 - compAngle).y
          } ${compInnerPath} Z`}
          fill={compColor}
          opacity={0.85}
        />

        {/* 下半弧 - 理论深度（填充扇形区域） */}
        <path
          d={`${theoryOuterPath} L ${polarToCartesian(innerR, theoryAngle).x} ${
            polarToCartesian(innerR, theoryAngle).y
          } ${theoryInnerPath} Z`}
          fill={theoryCol}
          opacity={0.85}
        />

        {/* 水平分割线 */}
        <line x1={cx - outerR} y1={cy} x2={cx - innerR} y2={cy} stroke="#d1d5db" strokeWidth={1} />
        <line x1={cx + innerR} y1={cy} x2={cx + outerR} y2={cy} stroke="#d1d5db" strokeWidth={1} />

        {/* 中心刻度线（12点钟和6点钟） */}
        <line x1={cx} y1={cy - outerR} x2={cx} y2={cy - outerR + 6} stroke="#9ca3af" strokeWidth={1} />
        <line x1={cx} y1={cy + outerR - 6} x2={cx} y2={cy + outerR} stroke="#9ca3af" strokeWidth={1} />

        {/* 中心文字 - 理解难度值 */}
        {showLabels && (
          <>
            <text
              x={cx}
              y={cy - 6}
              textAnchor="middle"
              className="fill-gray-700"
              style={{ fontSize: `${size * 0.18}px`, fontWeight: 600 }}
            >
              {comprehension}
            </text>
            <text
              x={cx}
              y={cy + size * 0.1}
              textAnchor="middle"
              className="fill-gray-500"
              style={{ fontSize: `${size * 0.085}px` }}
            >
              理解
            </text>
            <text
              x={cx}
              y={cy + size * 0.18}
              textAnchor="middle"
              className="fill-gray-500"
              style={{ fontSize: `${size * 0.085}px` }}
            >
              {levelLabel(theory)}·理论
            </text>
          </>
        )}
      </svg>

      {/* 图例 */}
      {showLabels && (
        <div className="flex items-center gap-3 text-xs text-gray-500">
          <span className="flex items-center gap-1">
            <span className="w-2.5 h-2.5 rounded-sm" style={{ backgroundColor: compColor }} />
            理解难度
          </span>
          <span className="flex items-center gap-1">
            <span className="w-2.5 h-2.5 rounded-sm" style={{ backgroundColor: theoryCol }} />
            理论深度
          </span>
        </div>
      )}
    </div>
  )
}

export default DifficultySemicircle
