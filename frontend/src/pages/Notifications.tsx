import React, { useEffect, useState } from 'react'
import {
  Bell,
  Check,
  CheckCheck,
  BookOpen,
  RefreshCw,
  AlertCircle,
  Loader2,
  Target,
  Zap,
} from 'lucide-react'
import { notificationApi } from '../utils/api'
import type { Notification } from '../types'

const Notifications: React.FC = () => {
  const [notifications, setNotifications] = useState<Notification[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = () => {
    let cancelled = false
    setLoading(true)
    notificationApi
      .list()
      .then((resp) => {
        if (!cancelled) setNotifications(resp.data.items as Notification[])
      })
      .catch((err: unknown) => {
        if (cancelled) return
        setError(err instanceof Error ? err.message : '加载消息失败')
      })
      .finally(() => !cancelled && setLoading(false))
    return () => {
      cancelled = true
    }
  }

  useEffect(() => {
    load()
  }, [])

  const handleMarkAsRead = async (id: string) => {
    setNotifications((prev) => prev.map((n) => (n.id === id ? { ...n, is_read: true } : n)))
    try {
      await notificationApi.markAsRead(id)
    } catch {
      setNotifications((prev) => prev.map((n) => (n.id === id ? { ...n, is_read: false } : n)))
    }
  }

  const handleMarkAllAsRead = async () => {
    const original = notifications
    setNotifications((prev) => prev.map((n) => ({ ...n, is_read: true })))
    try {
      await notificationApi.markAllAsRead()
    } catch {
      setNotifications(original)
    }
  }

  const getIcon = (type: string) => {
    switch (type) {
      case 'review_reminder':
        return <RefreshCw className="text-orange-600" size={20} />
      case 'daily_task':
        return <BookOpen className="text-blue-600" size={20} />
      case 'path_update':
        return <Target className="text-green-600" size={20} />
      case 'remediation':
        return <Zap className="text-yellow-600" size={20} />
      default:
        return <AlertCircle className="text-gray-600" size={20} />
    }
  }

  const getIconBg = (type: string) => {
    switch (type) {
      case 'review_reminder':
        return 'bg-orange-100'
      case 'daily_task':
        return 'bg-blue-100'
      case 'path_update':
        return 'bg-green-100'
      case 'remediation':
        return 'bg-yellow-100'
      default:
        return 'bg-gray-100'
    }
  }

  const unreadCount = notifications.filter((n) => !n.is_read).length

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64 text-gray-500">
        <Loader2 className="animate-spin mr-2" size={20} />
        加载中...
      </div>
    )
  }

  if (error) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">消息中心</h1>
          <p className="text-gray-600 mt-2">查看系统通知和学习提醒</p>
        </div>
        <div className="bg-red-50 border border-red-200 rounded-xl p-6 flex items-start gap-3 text-red-800">
          <AlertCircle size={20} className="flex-shrink-0 mt-0.5" />
          <div className="text-sm">
            <p className="font-medium">加载失败</p>
            <p className="mt-1 text-red-700">{error}</p>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">消息中心</h1>
          <p className="text-gray-600 mt-2">查看系统通知和学习提醒</p>
        </div>
        {unreadCount > 0 && (
          <button
            onClick={handleMarkAllAsRead}
            className="flex items-center gap-2 px-4 py-2 text-blue-600 hover:bg-blue-50 rounded-lg transition-colors"
          >
            <CheckCheck size={18} />
            全部已读
          </button>
        )}
      </div>

      <div className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden">
        <div className="p-4 border-b border-gray-100 bg-gray-50">
          <p className="text-sm text-gray-600">
            共 {notifications.length} 条消息，{unreadCount} 条未读
          </p>
        </div>
        {notifications.length === 0 ? (
          <div className="p-12 text-center text-gray-500">
            <Bell size={32} className="mx-auto mb-2 text-gray-400" />
            暂无消息
          </div>
        ) : (
          <div className="divide-y divide-gray-100">
            {notifications.map((notification) => (
              <div
                key={notification.id}
                className={`p-4 flex gap-4 hover:bg-gray-50 transition-colors ${
                  !notification.is_read ? 'bg-blue-50/30' : ''
                }`}
              >
                <div
                  className={`w-10 h-10 rounded-full flex items-center justify-center flex-shrink-0 ${getIconBg(
                    notification.notification_type
                  )}`}
                >
                  {getIcon(notification.notification_type)}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <p className="font-medium text-gray-900">{notification.title}</p>
                    {!notification.is_read && <span className="w-2 h-2 bg-blue-600 rounded-full" />}
                  </div>
                  <p className="text-gray-600 text-sm">{notification.body}</p>
                  <p className="text-gray-400 text-xs mt-1">
                    {new Date(notification.created_at).toLocaleString()}
                  </p>
                </div>
                {!notification.is_read && (
                  <button
                    onClick={() => handleMarkAsRead(notification.id)}
                    className="p-2 text-gray-400 hover:text-blue-600 hover:bg-blue-50 rounded-lg transition-colors self-start"
                    title="标记为已读"
                  >
                    <Check size={18} />
                  </button>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

export default Notifications
