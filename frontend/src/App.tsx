import { Routes, Route, Navigate } from 'react-router-dom';
import { AppLayout } from './components/layout/AppLayout';
import { QueryPage } from './pages/QueryPage';
import { ConnectionsPage } from './pages/ConnectionsPage';
import { GlossaryPage } from './pages/GlossaryPage';
import { MetricsPage } from './pages/MetricsPage';
import { DictionaryPage } from './pages/DictionaryPage';
import { KnowledgePage } from './pages/KnowledgePage';
import { HistoryPage } from './pages/HistoryPage';

export default function App() {
  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route path="/" element={<Navigate to="/query" replace />} />
        <Route path="/query" element={<QueryPage />} />
        <Route path="/connections" element={<ConnectionsPage />} />
        <Route path="/glossary" element={<GlossaryPage />} />
        <Route path="/metrics" element={<MetricsPage />} />
        <Route path="/dictionary" element={<DictionaryPage />} />
        <Route path="/knowledge" element={<KnowledgePage />} />
        <Route path="/history" element={<HistoryPage />} />
      </Route>
    </Routes>
  );
}
