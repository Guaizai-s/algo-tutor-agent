import React, { useState } from 'react'
import { Outlet, Link, useLocation, useNavigate } from 'react-router-dom'
import {
  BookOpen,
  Code2,
  MessageSquare,
  BarChart3,
  BookX,
  Bell,
  RefreshCw,
  LogOut,
  Menu,
  X,
  CalendarCheck,
  UserCircle,
} from 'lucide-react'
import { useAuthStore } from '../stores/authStore'

const Layout: React.FC = () => {
  const location = useLocation()
  const navigate = useNavigate()
  const { user, logout } = useAuthStore()
  const [sidebarOpen, setSidebarOpen] = useState(true)

  const navItems = [
    { path: '/today', label: '今日学习', icon: CalendarCheck },
    { path: '/knowledge', label: '算法路线图', icon: BookOpen },
    { path: '/problems', label: '题库', icon: Code2 },
    { path: '/ai-chat', label: 'AI 问答', icon: MessageSquare },
    { path: '/progress', label: '学习进度', icon: BarChart3 },
    { path: '/wrong-answers', label: '错题本', icon: BookX },
    { path: '/review', label: '复习提醒', icon: RefreshCw },
    { path: '/notifications', label: '消息中心', icon: Bell },
  ]

  const handleLogout = () => {
    logout()
    navigate('/login')
  }

  return (
    <div className="min-h-screen bg-gray-50 flex">
      <aside
        className={`${
          sidebarOpen ? 'w-64' : 'w-20'
        } bg-white border-r border-gray-200 transition-all duration-300 flex flex-col fixed h-full z-20`}
      >
        <div className="p-4 border-b border-gray-200 flex items-center justify-between">
          {sidebarOpen && (
            <Link
              to="/dashboard"
              className="text-xl font-bold text-blue-600 hover:text-blue-700 transition-colors"
            >
              算法教练
            </Link>
          )}
          <button
            onClick={() => setSidebarOpen(!sidebarOpen)}
            className="p-2 hover:bg-gray-100 rounded-lg"
          >
            {sidebarOpen ? <X size={20} /> : <Menu size={20} />}
          </button>
        </div>

        <nav className="flex-1 p-4 space-y-1 overflow-y-auto">
          {navItems.map((item) => {
            const Icon = item.icon
            const isActive = location.pathname.startsWith(item.path)
            return (
              <Link
                key={item.path}
                to={item.path}
                className={`flex items-center gap-3 px-3 py-3 rounded-lg transition-colors ${
                  isActive ? 'bg-blue-50 text-blue-600' : 'text-gray-700 hover:bg-gray-100'
                }`}
              >
                <Icon size={20} />
                {sidebarOpen && <span>{item.label}</span>}
              </Link>
            )
          })}
        </nav>

        <div className="p-4 border-t border-gray-200">
          <Link
            to="/profile"
            className="flex items-center gap-3 mb-3 rounded-lg hover:bg-gray-100 transition-colors -mx-1 px-1 py-1"
          >
            <div className="w-10 h-10 bg-blue-100 rounded-full flex items-center justify-center text-blue-600 font-semibold flex-shrink-0">
              {user?.username?.charAt(0).toUpperCase() || 'U'}
            </div>
            {sidebarOpen && (
              <div className="flex-1 min-w-0">
                <p className="font-medium text-gray-900 truncate">{user?.username}</p>
                <p className="text-sm text-gray-500 truncate">
                  {user?.cf_handle ? (
                    <span className="text-green-600">CF: {user.cf_handle}</span>
                  ) : (
                    <span className="text-orange-500">未绑定 CF</span>
                  )}
                </p>
              </div>
            )}
          </Link>
          {sidebarOpen && (
            <Link
              to="/profile"
              className={`flex items-center gap-3 w-full px-3 py-2 rounded-lg transition-colors mb-1 ${
                location.pathname === '/profile'
                  ? 'bg-blue-50 text-blue-600'
                  : 'text-gray-700 hover:bg-gray-100'
              }`}
            >
              <UserCircle size={20} />
              <span>个人档案</span>
            </Link>
          )}
          <button
            onClick={handleLogout}
            className="flex items-center gap-3 w-full px-3 py-2 text-gray-700 hover:bg-gray-100 rounded-lg transition-colors"
          >
            <LogOut size={20} />
            {sidebarOpen && <span>退出登录</span>}
          </button>
        </div>
      </aside>

      <main className={`flex-1 ${sidebarOpen ? 'ml-64' : 'ml-20'} transition-all duration-300`}>
        <div className="p-8">
          <Outlet />
        </div>
      </main>
    </div>
  )
}

export default Layout
