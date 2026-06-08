import { Routes, Route, Navigate } from 'react-router-dom';
import { AppLayout } from './components/layout/AppLayout';
import { ProtectedRoute } from './components/auth/ProtectedRoute';
import { LoginPage } from './pages/LoginPage';
import { MagicLinkVerifyPage } from './pages/MagicLinkVerifyPage';
import { QueryPage } from './pages/QueryPage';
import { ConnectionsPage } from './pages/ConnectionsPage';
import { GlossaryPage } from './pages/GlossaryPage';
import { MetricsPage } from './pages/MetricsPage';
import { SavedQueriesPage } from './pages/SavedQueriesPage';
import { DashboardsPage } from './pages/DashboardsPage';
import { DashboardDetailPage } from './pages/DashboardDetailPage';
import { DictionaryPage } from './pages/DictionaryPage';
import { KnowledgePage } from './pages/KnowledgePage';
import { CatalogPage } from './pages/CatalogPage';
import { HistoryPage } from './pages/HistoryPage';
import { AuditPage } from './pages/AuditPage';
import { SchedulesPage } from './pages/SchedulesPage';
import { PoliciesPage } from './pages/PoliciesPage';
import { AnalyticsPage } from './pages/AnalyticsPage';

export default function App() {
  return (
    <Routes>
      {/* Public */}
      <Route path="/login" element={<LoginPage />} />
      <Route path="/login/verify" element={<MagicLinkVerifyPage />} />

      {/* Authenticated */}
      <Route element={<ProtectedRoute />}>
        <Route element={<AppLayout />}>
          <Route path="/" element={<Navigate to="/query" replace />} />
          <Route path="/query" element={<QueryPage />} />
          <Route path="/saved-queries" element={<SavedQueriesPage />} />
          <Route path="/dashboards" element={<DashboardsPage />} />
          <Route path="/dashboards/:id" element={<DashboardDetailPage />} />
          <Route path="/connections" element={<ConnectionsPage />} />
          <Route path="/glossary" element={<GlossaryPage />} />
          <Route path="/metrics" element={<MetricsPage />} />
          <Route path="/dictionary" element={<DictionaryPage />} />
          <Route path="/knowledge" element={<KnowledgePage />} />
          <Route path="/catalog" element={<CatalogPage />} />
          <Route path="/history" element={<HistoryPage />} />
          <Route path="/schedules" element={<SchedulesPage />} />
          <Route path="/policies" element={<PoliciesPage />} />
          <Route path="/analytics" element={<AnalyticsPage />} />
          <Route path="/audit" element={<AuditPage />} />
        </Route>
      </Route>
    </Routes>
  );
}
