import { expect, test, type Page } from '@playwright/test'

const demoUser = {
  id: '00000000-0000-4000-8000-000000000001',
  email: 'demo@algo-tutor.local',
  username: '演示学员',
  avatar: null,
  role: 'student',
  school: '未来学习中心',
  cf_handle: 'demo_student',
  atcoder_handle: null,
  target_medal: 'silver',
  created_at: '2026-08-15T00:00:00Z',
  updated_at: '2026-08-15T00:00:00Z',
}

const progress = {
  user_id: demoUser.id,
  total_knowledge_points: 303,
  mastered_knowledge_points: 1,
  total_problems: 11373,
  solved_problems: 1,
  acceptance_rate: 0.5,
  streak_days: 3,
  mastery_by_category: [],
  rating_history: [{ date: '2026-08-08', rating: 1360 }],
  target_progress: null,
  weak_knowledge_ids: [],
  review_status: { due_count: 1, total_records: 1, completed: 0 },
}

const mockApi = async (page: Page) => {
  await page.route('**/api/v1/**', async (route) => {
    const request = route.request()
    const pathname = new URL(request.url()).pathname

    if (pathname.endsWith('/auth/login')) {
      await route.fulfill({
        json: { access_token: 'demo-token', token_type: 'bearer', user: demoUser },
      })
      return
    }
    if (pathname.endsWith('/auth/me')) {
      await route.fulfill({ json: demoUser })
      return
    }
    if (pathname.endsWith('/progress/overview')) {
      await route.fulfill({ json: progress })
      return
    }
    if (pathname.endsWith('/recommendations')) {
      await route.fulfill({ json: { items: [] } })
      return
    }
    if (pathname.endsWith('/agent/chat/stream')) {
      const events = [
        {
          type: 'trace',
          step: {
            id: 'understanding',
            kind: 'understanding',
            title: '理解学习目标',
            detail: '已结合当前问题与个性化学习上下文',
            status: 'success',
          },
        },
        {
          type: 'trace',
          step: {
            id: 'tool-knowledge',
            kind: 'tool',
            title: '检索知识库',
            detail: '找到二分查找讲义',
            status: 'success',
            tool_name: 'search_knowledge',
          },
        },
        { type: 'answer_delta', delta: '建议先补二分查找，' },
        { type: 'answer_delta', delta: '再完成一道边界练习。' },
        {
          type: 'done',
          references: [],
          tool_calls: [{ name: 'search_knowledge', status: 'success' }],
          trace: [
            {
              id: 'understanding',
              kind: 'understanding',
              title: '理解学习目标',
              detail: '已结合当前问题与个性化学习上下文',
              status: 'success',
            },
            {
              id: 'tool-knowledge',
              kind: 'tool',
              title: '检索知识库',
              detail: '找到二分查找讲义',
              status: 'success',
              tool_name: 'search_knowledge',
            },
          ],
        },
      ]
      await route.fulfill({
        status: 200,
        contentType: 'text/event-stream',
        body: events.map((event) => `data: ${JSON.stringify(event)}\n\n`).join(''),
      })
      return
    }
    await route.fulfill({ status: 200, contentType: 'application/json', body: '{}' })
  })
}

test('golden demo login and Agent trace remain usable', async ({ page }) => {
  page.on('pageerror', (error) => console.error(`Browser page error: ${error.message}`))
  await mockApi(page)
  await page.goto('/login')
  await page.getByRole('button', { name: '一键进入黄金演示账号' }).click()

  await expect(page.getByRole('heading', { name: '欢迎回来！' })).toBeVisible()
  await expect(page.getByText('Codeforces 已绑定：')).toBeVisible()

  await page.goto('/ai-chat')
  await page.getByPlaceholder('输入你的问题...').fill('我为什么要先补二分查找？')
  await page.getByRole('button', { name: '发送问题' }).click()

  await expect(page.getByText('Agent 执行轨迹')).toBeVisible()
  await expect(page.getByText('检索知识库')).toBeVisible()
  await expect(page.getByText('建议先补二分查找，再完成一道边界练习。')).toBeVisible()
})
