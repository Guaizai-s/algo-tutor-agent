export interface User {
  id: string
  email: string
  username: string
  avatar: string | null
  role: 'student' | 'coach' | 'admin'
  school: string | null
  cf_handle: string | null
  atcoder_handle: string | null
  target_medal: 'bronze' | 'silver' | 'gold' | null
  created_at: string
  updated_at: string
}

export type Difficulty = 'easy' | 'medium' | 'hard'

export interface KnowledgePoint {
  id: string
  name: string
  slug: string
  description: string | null
  difficulty: Difficulty
  parent_id: string | null
  order: number
  // 聚合统计（后端 list/get 接口返回）
  lecture_count?: number
  template_count?: number
  children_count?: number
  // Codeforces 关联
  cf_tag?: string | null
  cf_problem_count?: number
}

export interface Problem {
  id: string
  title: string
  slug: string
  description: string
  difficulty: Difficulty
  status: 'draft' | 'published'
  time_limit_ms: number
  memory_limit_kb: number
  sample_input?: string | null
  sample_output?: string | null
  hints?: string[] | null
  solution_template?: Record<string, unknown> | null
  knowledge_point_ids: string[]
  submit_count: number
  accepted_count: number
  created_at: string
  updated_at: string
}

export interface ProblemListResponse {
  items: Problem[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

export interface Lecture {
  id: string
  knowledge_id: string
  level: 'card' | 'standard' | 'deep'
  title: string
  content: string
}

export interface CodeTemplate {
  id: string
  knowledge_id: string
  language: string
  template_code: string
  explanation: string | null
}

export interface Submission {
  id: string
  problem_id: string
  user_id: string
  code: string
  language: 'cpp' | 'java' | 'python'
  status: 'pending' | 'judging' | 'AC' | 'WA' | 'TLE' | 'RE' | 'CE'
  time_used?: number
  memory_used?: number
  complexity_analysis?: string
  code_review?: string
  created_at: string
}

export interface ChatMessage {
  id: string
  conversation_id: string
  user_id: string
  role: 'user' | 'assistant'
  content: string
  references?: AgentReference[]
  tool_calls?: AgentToolCall[]
  created_at: string
}

export interface Conversation {
  id: string
  user_id: string
  title: string
  created_at: string
  updated_at: string
}

export interface WrongAnswer {
  id: string
  problem: Problem
  error_type: 'WA' | 'TLE' | 'RE'
  error_message?: string
  submission_id: string
  created_at: string
  similar_problems?: Problem[]
}

export interface Notification {
  id: string
  type: 'review' | 'push' | 'system'
  title: string
  content: string
  is_read: boolean
  created_at: string
  link?: string
}

export interface ReviewItem {
  id: string
  knowledge_point: KnowledgePoint
  next_review_date: string
  stage: number
  problem?: Problem
}

export interface Solution {
  id: string
  problem_id: string
  user: User
  title: string
  content: string
  language: string
  likes: number
  is_featured: boolean
  comments_count: number
  created_at: string
}

export interface Comment {
  id: string
  solution_id: string
  user: User
  content: string
  likes: number
  created_at: string
}

export interface MasteryByCategory {
  /** 知识点 ID，用于映射 weak_knowledge_ids */
  knowledge_id: string
  name: string
  /** mastery 百分比 0-100 */
  value: number
}

export interface RatingHistoryPoint {
  date: string
  rating: number
}

export interface TargetProgress {
  target_rating_min: number
  target_rating_max: number
  mastered_in_range: number
  total_in_range: number
  progress_percent: number
}

export interface Progress {
  user_id: string
  total_knowledge_points: number
  mastered_knowledge_points: number
  total_problems: number
  solved_problems: number
  /** 通过率，0-1 浮点数。展示时需 *100（如 0.5 → 50.0%） */
  acceptance_rate: number
  /** 连续打卡天数。COMPAT: Task 8 submission 表未实现前返回 0 */
  streak_days: number
  mastery_by_category: MasteryByCategory[]
  /** CF Rating 曲线。COMPAT: Task 8 CF 同步未实现，始终返回空数组 */
  rating_history: RatingHistoryPoint[]
  target_progress: TargetProgress | null
  /** 薄弱知识点 ID 列表（0 < mastery < 0.5；mastery=0 未学不算薄弱） */
  weak_knowledge_ids: string[]
}

export interface AuthResponse {
  access_token: string
  token_type: string
  user: User
}

export interface Hint {
  level: 1 | 2 | 3
  content: string
}

export interface JudgeResult {
  status: 'AC' | 'WA' | 'TLE' | 'RE' | 'CE'
  time_used: number
  memory_used: number
  test_case_results?: {
    status: 'AC' | 'WA' | 'TLE' | 'RE'
    input: string
    expected_output: string
    actual_output?: string
    time_used: number
  }[]
  complexity_analysis: string
  code_review: string
}

export type CodeExecutionStatus =
  'success' | 'compile_error' | 'runtime_error' | 'timeout' | 'internal_error'

export interface CodeExecutionResult {
  status: CodeExecutionStatus
  stdout: string
  stderr: string
  exit_code: number
  time_used_ms: number
  truncated: boolean
  input_source: 'sample' | 'empty'
  message: string
}

// ===== Agent types =====

export interface AgentReference {
  type: 'problem' | 'knowledge'
  id: string
  title: string
  source: string
}

export interface AgentToolCall {
  name: 'execute_code' | 'search_problems' | 'search_knowledge'
  status: 'success' | 'error'
}

export interface AgentChatRequest {
  message: string
  history: { role: 'user' | 'assistant'; content: string }[]
  context?: {
    problem_id?: string
    language?: 'python' | 'cpp' | 'java'
    code?: string
  }
}

export interface AgentChatResponse {
  message: string
  references: AgentReference[]
  tool_calls: AgentToolCall[]
}

// ===== Task 10: Learning path & daily task =====

export type PathItemKind = 'normal' | 'remediation'
export type PathItemStatus = 'pending' | 'active' | 'done' | 'skipped'
export type DailyTaskItemType =
  'lecture_card' | 'template_problem' | 'application_problem' | 'challenge_problem'
export type DailyTaskItemStatus = 'pending' | 'done'

export interface KnowledgePointRef {
  id: string
  name: string
  slug: string
}

export interface ProblemRef {
  id: string
  title: string
  slug: string
  difficulty: string
  cf_rating: number | null
}

export interface LectureRef {
  id: string
  knowledge_id: string
  level: string
  title: string
}

export interface LearningPathItemRead {
  id: string
  knowledge_id: string
  position: number
  kind: PathItemKind
  status: PathItemStatus
  knowledge: KnowledgePointRef
}

export interface LearningPathRead {
  id: string
  user_id: string
  is_active: boolean
  items: LearningPathItemRead[]
}

export interface LearningPathGenerateRequest {
  user_id: string
  preview_count?: number
}

export interface AttemptRequest {
  user_id: string
  knowledge_id: string
  problem_id: string
  verdict: string
  new_mastery?: number
}

export interface AttemptResponse {
  user_id: string
  knowledge_id: string
  consecutive_wa: number
  is_weak: boolean
  mastery: number
  remediation_inserted: boolean
}

export interface DailyTaskItemRead {
  id: string
  item_type: DailyTaskItemType
  position: number
  lecture: LectureRef | null
  problem: ProblemRef | null
  status: DailyTaskItemStatus
  missing_reason: string | null
}

export interface DailyTaskRead {
  id: string
  user_id: string
  task_date: string
  knowledge: KnowledgePointRef
  is_remediation: boolean
  missing_slots: string[]
  items: DailyTaskItemRead[]
}

export interface DailyTaskPathPreviewItem {
  knowledge_id: string
  name: string
  position: number
  kind: PathItemKind
}

export interface DailyTaskTodayResponse {
  task: DailyTaskRead
  path_preview: DailyTaskPathPreviewItem[]
}
