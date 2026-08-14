import {
  BrainCircuit,
  CheckCircle2,
  CircleDashed,
  ListChecks,
  MessageSquareText,
  Wrench,
  XCircle,
} from 'lucide-react'
import type { AgentTraceStep } from '../types'

const KIND_ICONS = {
  understanding: BrainCircuit,
  planning: ListChecks,
  tool: Wrench,
  answer: MessageSquareText,
}

interface AgentTraceProps {
  steps: AgentTraceStep[]
  compact?: boolean
}

const AgentTrace = ({ steps, compact = false }: AgentTraceProps) => {
  if (steps.length === 0) return null

  return (
    <div
      className={`rounded-xl border border-indigo-100 bg-indigo-50/70 ${compact ? 'p-3' : 'p-4'}`}
      aria-label="AI Agent 执行轨迹"
    >
      <div className="flex items-center gap-2 text-sm font-medium text-indigo-900">
        <BrainCircuit size={16} />
        Agent 执行轨迹
      </div>
      <ol className="mt-3 space-y-2">
        {steps.map((step) => {
          const KindIcon = KIND_ICONS[step.kind]
          const StatusIcon =
            step.status === 'success'
              ? CheckCircle2
              : step.status === 'error'
                ? XCircle
                : CircleDashed
          return (
            <li key={step.id} className="flex items-start gap-2.5 text-sm">
              <span className="mt-0.5 rounded-md bg-white p-1 text-indigo-600 shadow-sm">
                <KindIcon size={14} />
              </span>
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="font-medium text-gray-800">{step.title}</span>
                  <StatusIcon
                    size={14}
                    className={
                      step.status === 'success'
                        ? 'text-green-600'
                        : step.status === 'error'
                          ? 'text-red-600'
                          : 'animate-spin text-indigo-500'
                    }
                  />
                </div>
                {step.detail ? <p className="mt-0.5 text-xs text-gray-500">{step.detail}</p> : null}
              </div>
            </li>
          )
        })}
      </ol>
    </div>
  )
}

export default AgentTrace
