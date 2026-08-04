import React, { useEffect, useState } from 'react'
import { Navigate } from 'react-router-dom'
import { useAuthStore } from '../stores/authStore'

interface ProtectedRouteProps {
  children: React.ReactNode
}

const ProtectedRoute: React.FC<ProtectedRouteProps> = ({ children }) => {
  const { token, isAuthenticated, isLoading, loadUser } = useAuthStore()
  const [hasValidatedToken, setHasValidatedToken] = useState(!token)

  useEffect(() => {
    if (!token) {
      setHasValidatedToken(true)
      return
    }

    setHasValidatedToken(false)
    void loadUser().finally(() => setHasValidatedToken(true))
  }, [token, loadUser])

  if (!hasValidatedToken || isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center text-gray-600">
        正在验证登录状态...
      </div>
    )
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />
  }

  return <>{children}</>
}

export default ProtectedRoute
