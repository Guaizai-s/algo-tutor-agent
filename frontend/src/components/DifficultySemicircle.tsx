import React from 'react'

/**
 * 双维度难度半圆图表（洛谷配色风格）
 *
 * 整圆被水平分割：
 * - 上半弧：理解难度（comprehension_difficulty 1-5）
 * - 下半弧：理论深度（theory_depth 1-5）
 *
 * 每半圆分为 5 段（36°/段），用洛谷经典色阶填充：
 *   1=灰 2=绿 3=蓝 4=紫 5=红/黑
 * 上半用暖色调（红结尾），下半用冷色调（黑结尾）。
 *
 * 填充区域从起点顺时针覆盖到当前值对应的角度。
 */

interface DifficultySemicircleProps {
  comprehension: number
  theory: number
  size?: number
  showLabels?: boolean
}

// ---- 洛谷配色 ----

/** 理解难度（上半弧）1-5 → 洛谷暖色系 */
const COMP_COLORS = ['#bfbfbf', '#52c41a', '#3498db', '#f39c11', '#fe4c61']

/** 理论深度（下半弧）1-5 → 洛谷冷色系 */
const THEORY_COLORS = ['#bfbfbf', '#52c41a', '#3498db', '#9d3dcf', '#0e1d69']

/** 1-5 → 中文等级名 */
const LEVEL_LABELS = ['', '入门', '基础', '提高', '省选', 'NOI']

const DEG_PER_SEG = 36 // 180° / 5

/** 极坐标 → 笛卡尔坐标，0° = 12点方向，顺时针 */
const polarToCartesian = (cx: number, cy: number, r: number, angleDeg: number) => {
  const rad = ((angleDeg - 90) * Math.PI) / 180
  return { x: cx + r * Math.cos(rad), y: cy + r * Math.sin(rad) }
}

const DifficultySemicircle: React.FC<DifficultySemicircleProps> = ({
  comprehension,
  theory,
  size = 140,
  showLabels = true,
}) => {
  const cx = size / 2
  const cy = size / 2
  const outerR = size / 2 - 8
  const innerR = outerR - 14   // 圆环宽度

  // 上半弧：从 180°(左) 顺时针到 0°(右)
  // 每段 36°，第 i 段覆盖 [180 - (i+1)*36, 180 - i*36]
  const renderUpperSegments = () => {
    const segments: React.ReactNode[] = []
    for (let i = 0; i < 5; i++) {
      const startA = 180 - (i + 1) * DEG_PER_SEG
      const endA = 180 - i * DEG_PER_SEG
      const isFilled = i < comprehension
      const color = COMP_COLORS[i]
      const sOuter = polarToCartesian(cx, cy, outerR, startA)
      const eOuter = polarToCartesian(cx, cy, outerR, endA)
      const sInner = polarToCartesian(cx, cy, innerR, startA)
      const eInner = polarToCartesian(cx, cy, innerR, endA)

      segments.push(
        <path
          key={`comp-${i}`}
          d={`M ${sOuter.x} ${sOuter.y} A ${outerR} ${outerR} 0 0 1 ${eOuter.x} ${eOuter.y} L ${eInner.x} ${eInner.y} A ${innerR} ${innerR} 0 0 0 ${sInner.x} ${sInner.y} Z`}
          fill={isFilled ? color : '#e5e7eb'}
          opacity={isFilled ? 0.9 : 0.5}
        />
      )
    }
    return segments
  }

  // 下半弧：从 0°(右) 顺时针到 180°(左)
  const renderLowerSegments = () => {
    const segments: React.ReactNode[] = []
    for (let i = 0; i < 5; i++) {
      const startA = i * DEG_PER_SEG
      const endA = (i + 1) * DEG_PER_SEG
      const isFilled = i < theory
      const color = THEORY_COLORS[i]
      const sOuter = polarToCartesian(cx, cy, outerR, startA)
      const eOuter = polarToCartesian(cx, cy, outerR, endA)
      const sInner = polarToCartesian(cx, cy, innerR, startA)
      const eInner = polarToCartesian(cx, cy, innerR, endA)

      segments.push(
        <path
          key={`theory-${i}`}
          d={`M ${sOuter.x} ${sOuter.y} A ${outerR} ${outerR} 0 0 1 ${eOuter.x} ${eOuter.y} L ${eInner.x} ${eInner.y} A ${innerR} ${innerR} 0 0 0 ${sInner.x} ${sInner.y} Z`}
          fill={isFilled ? color : '#e5e7eb'}
          opacity={isFilled ? 0.9 : 0.5}
        />
      )
    }
    return segments
  }

  // 刻度线
  const renderTicks = () => {
    const ticks: React.ReactNode[] = []
    // 上半刻度：180°, 144°, 108°, 72°, 36°, 0°
    for (let i = 0; i <= 5; i++) {
      const a = 180 - i * DEG_PER_SEG
      const s = polarToCartesian(cx, cy, innerR - 2, a)
      const e = polarToCartesian(cx, cy, outerR + 2, a)
      ticks.push(<line key={`tick-top-${i}`} x1={s.x} y1={s.y} x2={e.x} y2={e.y} stroke="#9ca3af" strokeWidth={1} />)
    }
    // 下半刻度：0°, 36°, 72°, 108°, 144°, 180°
    for (let i = 0; i <= 5; i++) {
      const a = i * DEG_PER_SEG
      const s = polarToCartesian(cx, cy, innerR - 2, a)
      const e = polarToCartesian(cx, cy, outerR + 2, a)
      ticks.push(<line key={`tick-bot-${i}`} x1={s.x} y1={s.y} x2={e.x} y2={e.y} stroke="#9ca3af" strokeWidth={1} />)
    }
    return ticks
  }

  // 水平分割线
  const leftInner = polarToCartesian(cx, cy, innerR, 180)
  const leftOuter = polarToCartesian(cx, cy, outerR, 180)
  const rightInner = polarToCartesian(cx, cy, innerR, 0)
  const rightOuter = polarToCartesian(cx, cy, outerR, 0)

  return (
    <div className="flex flex-col items-center gap-1.5">
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        {/* 上半段 */}
        {renderUpperSegments()}
        {/* 下半段 */}
        {renderLowerSegments()}
        {/* 刻度 */}
        {renderTicks()}
        {/* 水平分割线 */}
        <line x1={leftOuter.x} y1={leftOuter.y} x2={leftInner.x} y2={leftInner.y} stroke="#9ca3af" strokeWidth={1.5} />
        <line x1={rightInner.x} y1={rightInner.y} x2={rightOuter.x} y2={rightOuter.y} stroke="#9ca3af" strokeWidth={1.5} />

        {/* 中心文字 */}
        {showLabels && (
          <>
            {/* 理解难度值 + 标签 */}
            <text x={cx} y={cy - 8} textAnchor="middle" className="fill-gray-800"
              style={{ fontSize: '18px', fontWeight: 700 }}>
              {comprehension}
            </text>
            <text x={cx} y={cy + 2} textAnchor="middle" className="fill-gray-400"
              style={{ fontSize: '10px' }}>
              理解
            </text>
            {/* 理论深度值 */}
            <text x={cx} y={cy + 14} textAnchor="middle" className="fill-gray-800"
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

      {/* 图例：展示完整色阶 */}
      {showLabels && (
        <div className="flex flex-col gap-1 text-[10px] text-gray-500">
          <div className="flex items-center gap-0.5">
            <span className="w-8">理解</span>
            {COMP_COLORS.map((c, i) => (
              <span key={i} className="w-3 h-2.5 rounded-sm" style={{ backgroundColor: c }}
                title={`${LEVEL_LABELS[i + 1]}(${i + 1})`} />
            ))}
          </div>
          <div className="flex items-center gap-0.5">
            <span className="w-8">理论</span>
            {THEORY_COLORS.map((c, i) => (
              <span key={i} className="w-3 h-2.5 rounded-sm" style={{ backgroundColor: c }}
                title={`${LEVEL_LABELS[i + 1]}(${i + 1})`} />
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

export default DifficultySemicircle
