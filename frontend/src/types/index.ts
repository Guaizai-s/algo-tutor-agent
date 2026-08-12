export type TargetMedal = 'bronze' | 'silver' | 'gold'

export interface User {
  id: string
  email: string
  username: string
  avatar: string | null
  role: 'student' | 'coach' | 'admin'
  school: string | null
  cf_handle: string | null
  atcoder_handle: string | null
  target_medal: TargetMedal | null
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
  // 双维度难度评价（1-5 数值）
  comprehension_difficulty?: number
  theory_depth?: number
}

export interface Problem {
  id: string
  title: string
  slug: string
  description: string
  difficulty: Difficulty
  status: 'draft' | 'published'
  source?: 'platform' | 'codeforces' | 'atcoder' | 'user_reported' | null
  external_url?: string | null
  cf_tags?: string[] | null
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
  source?: string
  rewrite_version?: number
}

export interface CodeTemplate {
  id: string
  knowledge_id: string
  language: string
  template_code: string
  explanation: string | null
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

export interface Notification {
  id: string
  notification_type: 'review_reminder' | 'daily_task' | 'path_update' | 'remediation' | 'system'
  title: string
  body: string
  is_read: boolean
  read_at: string | null
  created_at: string
  related_knowledge_id?: string | null
  related_problem_id?: string | null
}

export interface ReviewItem {
  id: string
  knowledge_point: KnowledgePoint
  next_review_date: string
  stage: number
  problem?: Problem
}

export interface MasteryByCategory {
  /** 知识点 ID，用于映射 weak_knowledge_ids */
  knowledge_id: string
  name: string
  /** 一级父分类名称，用于分组展示 */
  parent_name: string | null
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
  /** 艾宾浩斯复习状态概览 */
  review_status: ReviewStatus | null
}

export interface ReviewStatus {
  due_count: number
  total_records: number
  completed: number
}

export interface ActivityDay {
  date: string
  count: number
}

export interface ActivityResponse {
  user_id: string
  days: ActivityDay[]
  total_week: number
  total_last_week: number
}

export interface WrongBookItem {
  submission_id: string
  problem_id: string | null
  problem_title: string | null
  cf_contest_id: number | null
  cf_index: string | null
  verdict: string
  knowledge_point_names: string[]
  retry_count: number
  resolved: boolean
  submitted_at: string
  last_retry_at: string | null
}

export interface WrongBookListResponse {
  items: WrongBookItem[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

export interface WrongBookRecommendation {
  problem_id: string
  title: string
  difficulty: string
  cf_rating: number | null
  knowledge_point_names: string[]
  ac_count: number
  submit_count: number
}

export interface AuthResponse {
  access_token: string
  token_type: string
  user: User
}

export interface BindCFRequest {
  handle: string
}

export interface BindCFResponse {
  handle: string
  current_rating: number | null
  max_rating: number | null
  rank: string | null
  message: string
}

export interface ProfileUpdateRequest {
  username?: string
  avatar?: string | null
  school?: string | null
  atcoder_handle?: string | null
  target_medal?: TargetMedal | null
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
  preview_count?: number
}

export interface AttemptRequest {
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

export interface MarkMasteredRequest {
  knowledge_id: string
}

export interface MarkMasteredResponse {
  knowledge_id: string
  mastery: number
  items_skipped: number
}

export interface ColdStartResultResponse {
  user_id: string
  method: string
  target_rating_min: number
  target_rating_max: number
  mastered_count: number
  weak_count: number
  next_available_count: number
  diagnostic_problems: string[]
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

export interface DailyTaskItemUpdateResponse {
  item: DailyTaskItemRead
  task_done: number
  task_total: number
  all_done: boolean
  check_in: boolean
  auto_mastered: boolean
}

// ===== Roadmap (路线图视图) =====

export type RoadmapNodeStatus = 'done' | 'active' | 'pending' | 'unlocked' | 'none'

export interface RoadmapKnowledgeNode {
  id: string
  name: string
  slug: string
  parent_id: string | null
  difficulty: string
  order: number
  lecture_count: number
  template_count: number
  status: RoadmapNodeStatus
  mastery: number | null
  is_weak: boolean
  path_position: number | null
  theory_done: boolean
  practice_mastery: number | null
  theory_lecture_count: number
  comprehension_difficulty?: number
  theory_depth?: number
}

export interface RoadmapResponse {
  user_id: string
  has_path: boolean
  tree: RoadmapKnowledgeNode[]
  path_preview: KnowledgePointRef[]
}

// ===== Recommendations =====

export interface RecommendationProblem {
  problem_id: string
  title: string
  slug: string
  difficulty: string
  cf_rating: number | null
}

export interface RecommendationItem {
  knowledge_id: string
  knowledge_name: string
  mastery: number
  problems: RecommendationProblem[]
}

export interface RecommendationResponse {
  user_id: string
  items: RecommendationItem[]
}

// ===== 提交记录 =====

export interface SubmissionRead {
  id: string
  cf_submission_id: number | null
  user_id: string
  problem_id: string | null
  problem_title: string | null
  contest_id: number | null
  problem_index: string | null
  verdict: string
  programming_language: string
  submitted_at: string
  time_consumed_ms: number
  memory_consumed_bytes: number
  passed_test_count: number
}

export interface SubmissionListResponse {
  items: SubmissionRead[]
  total: number
  page: number
  page_size: number
  total_pages: number
}
