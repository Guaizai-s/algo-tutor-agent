export interface User {
  id: string
  email: string
  username: string
  avatar?: string
  role: 'student' | 'coach' | 'admin'
  created_at: string
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

export interface Progress {
  total_knowledge_points: number
  mastered_knowledge_points: number
  total_problems: number
  solved_problems: number
  acceptance_rate: number
  streak_days: number
  mastery_by_category: { name: string; value: number }[]
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
