import { NavLink, Navigate, Route, Routes, useNavigate } from "react-router-dom";
import { api } from "./api/client";
import { useApp } from "./state";
import LoginPage from "./pages/LoginPage";
import HomePage from "./pages/HomePage";
import BmiPage from "./pages/BmiPage";
import FaceAnalysisPage from "./pages/FaceAnalysisPage";
import RecognitionPage from "./pages/RecognitionPage";
import DashboardPage from "./pages/DashboardPage";
import HistoryPage from "./pages/HistoryPage";
import ReportsPage from "./pages/ReportsPage";
import PrivacyPage from "./pages/PrivacyPage";
import SettingsPage from "./pages/SettingsPage";
import ConsentPage from "./pages/ConsentPage";

const NAV = [
  ["/", "Home"], ["/bmi", "BMI Analysis"], ["/face", "Face Analysis"], ["/recognition", "Face Recognition"],
  ["/dashboard", "Dashboard"], ["/history", "History"], ["/reports", "Reports"], ["/privacy", "Privacy"], ["/settings", "Settings"],
] as const;

export default function App() {
  const { user, loading, needsSetup, refreshAuth, setSessionId } = useApp();
  const nav = useNavigate();

  if (loading) return <div className="center muted">Loading…</div>;
  if (!user) return <LoginPage setup={needsSetup} />;

  const logout = async () => {
    await api.post("/auth/logout").catch(() => undefined);
    setSessionId(null);
    await refreshAuth();
    nav("/");
  };

  return (
    <div className="shell">
      <header className="topbar">
        <div className="brand">
          <span className="logo" aria-hidden>
            <svg viewBox="0 0 32 32" width="26" height="26"><rect width="32" height="32" rx="8" fill="currentColor" /><circle cx="16" cy="14" r="6" fill="none" stroke="#fff" strokeWidth="2.5" /><path d="M8 26c2-4 5-6 8-6s6 2 8 6" fill="none" stroke="#fff" strokeWidth="2.5" strokeLinecap="round" /></svg>
          </span>
          <span>HEALTHVISION AI</span>
          <span className="tag">V1 prototype</span>
        </div>
        <div className="userbox">
          <span className="muted">{user.display_name} · {user.role === "ADMINISTRATOR" ? "Admin" : "User"}</span>
          <button className="btn ghost sm" onClick={logout}>Sign out</button>
        </div>
      </header>
      <nav className="nav" aria-label="Main">
        {NAV.map(([to, label]) => (
          <NavLink key={to} to={to} end={to === "/"} className={({ isActive }) => (isActive ? "active" : "")}>{label}</NavLink>
        ))}
      </nav>
      <main className="content">
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/consent" element={<ConsentPage />} />
          <Route path="/bmi" element={<BmiPage />} />
          <Route path="/face" element={<FaceAnalysisPage />} />
          <Route path="/recognition" element={<RecognitionPage />} />
          <Route path="/dashboard" element={<DashboardPage />} />
          <Route path="/dashboard/:id" element={<DashboardPage />} />
          <Route path="/history" element={<HistoryPage />} />
          <Route path="/reports" element={<ReportsPage />} />
          <Route path="/privacy" element={<PrivacyPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="*" element={<Navigate to="/" />} />
        </Routes>
      </main>
      <footer className="footer muted">
        These outputs are separate measurements and should not be interpreted as a medical diagnosis or definitive emotional state.
      </footer>
    </div>
  );
}
