import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom'
import Layout from './components/Layout'
import ProtectedRoute from './components/ProtectedRoute'
import Login from './pages/Login'
import Register from './pages/Register'
import Dashboard from './pages/Dashboard'
import KnowledgeTree from './pages/KnowledgeTree'
import KnowledgeDetail from './pages/KnowledgeDetail'
import ProblemList from './pages/ProblemList'
import ProblemDetail from './pages/ProblemDetail'
import AIChat from './pages/AIChat'
import Progress from './pages/Progress'
import WrongAnswers from './pages/WrongAnswers'
import Review from './pages/Review'
import Notifications from './pages/Notifications'
import TodayTask from './pages/TodayTask'
import Profile from './pages/Profile'

function App() {
  return (
    <Router>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />
        <Route
          path="/"
          element={
            <ProtectedRoute>
              <Layout />
            </ProtectedRoute>
          }
        >
          <Route index element={<Navigate to="/dashboard" replace />} />
          <Route path="dashboard" element={<Dashboard />} />
          <Route path="today" element={<TodayTask />} />
          <Route path="profile" element={<Profile />} />
          <Route path="knowledge" element={<KnowledgeTree />} />
          <Route path="knowledge/graph" element={<Navigate to="/knowledge" replace />} />
          <Route path="knowledge/:id" element={<KnowledgeDetail />} />
          <Route path="problems" element={<ProblemList />} />
          <Route path="problems/:id" element={<ProblemDetail />} />
          <Route path="ai-chat" element={<AIChat />} />
          <Route path="progress" element={<Progress />} />
          <Route path="wrong-answers" element={<WrongAnswers />} />
          <Route path="review" element={<Review />} />
          <Route path="notifications" element={<Notifications />} />
        </Route>
      </Routes>
    </Router>
  )
}

export default App
