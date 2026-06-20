import { Routes, Route, Navigate } from 'react-router-dom'
import Sidebar from './components/Sidebar'
import Search from './pages/Search'
import PolicyNotice from './pages/PolicyNotice'
import Ranking from './pages/Ranking'
import Onboarding from './pages/Onboarding'

export default function App() {
  return (
    <div className="flex h-full">
      <Sidebar />
      <main className="flex-1 overflow-y-auto">
        <div className="mx-auto max-w-4xl px-8 py-8">
          <Routes>
            <Route path="/" element={<Search />} />
            <Route path="/q/:sessionId" element={<Search />} />
            <Route path="/notice" element={<Navigate to="/notice/regulation" replace />} />
            <Route path="/notice/:category" element={<PolicyNotice />} />
            <Route path="/ranking" element={<Ranking />} />
            <Route path="/onboarding" element={<Onboarding />} />
          </Routes>
        </div>
      </main>
    </div>
  )
}
