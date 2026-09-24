import { lazy, Suspense, type ReactNode } from "react";

import { Navigate, Route, Routes, useLocation } from "react-router-dom";

import { useAuth } from "./store/auth";
import { Shell } from "./components/Shell";
import { withPilot } from "./components/Pilot";
import { KpiGridSkeleton } from "./components/ui";
import { LoginPage } from "./pages/Login";

const DashboardPage = lazy(() => import("./pages/Dashboard").then((m) => ({ default: m.DashboardPage })));
const KanbanPage = lazy(() => import("./pages/Kanban").then((m) => ({ default: m.KanbanPage })));
const PipelinePage = lazy(() => import("./pages/Pipeline").then((m) => ({ default: m.PipelinePage })));
const PurchasesPage = lazy(() => import("./pages/Purchases").then((m) => ({ default: m.PurchasesPage })));
const OperationsPage = lazy(() => import("./pages/Operations").then((m) => ({ default: m.OperationsPage })));
const LogistiquePage = lazy(() => import("./pages/Logistique").then((m) => ({ default: m.LogistiquePage })));
const StocksPage = lazy(() => import("./pages/Stocks").then((m) => ({ default: m.StocksPage })));
const QualitePage = lazy(() => import("./pages/Qualite").then((m) => ({ default: m.QualitePage })));
const HsePage = lazy(() => import("./pages/Hse").then((m) => ({ default: m.HsePage })));
const MaintenancePage = lazy(() => import("./pages/Maintenance").then((m) => ({ default: m.MaintenancePage })));
const RhPaiePage = lazy(() => import("./pages/RhPaie").then((m) => ({ default: m.RhPaiePage })));
const ComptabilitePage = lazy(() => import("./pages/Comptabilite").then((m) => ({ default: m.ComptabilitePage })));
const ControleGestionPage = lazy(() => import("./pages/ControleGestion").then((m) => ({ default: m.ControleGestionPage })));
const JuridiquePage = lazy(() => import("./pages/Juridique").then((m) => ({ default: m.JuridiquePage })));
const DirectionPage = lazy(() => import("./pages/Direction").then((m) => ({ default: m.DirectionPage })));
const CircuitsPage = lazy(() => import("./pages/Circuits").then((m) => ({ default: m.CircuitsPage })));
const NotificationsPage = lazy(() => import("./pages/Notifications").then((m) => ({ default: m.NotificationsPage })));

function pilotPage(children: ReactNode) {
  return withPilot(<Suspense fallback={<KpiGridSkeleton count={6} />}>{children}</Suspense>);
}

function RequireAuth({ children }: { children: ReactNode }) {
  const access = useAuth((s) => s.access);
  const location = useLocation();
  if (!access) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }
  return <>{children}</>;
}

function GuestOnly({ children }: { children: ReactNode }) {
  const access = useAuth((s) => s.access);
  if (access) return <Navigate to="/" replace />;
  return <>{children}</>;
}

export default function App() {
  return (
    <Routes>
      <Route
        path="/login"
        element={
          <GuestOnly>
            <LoginPage />
          </GuestOnly>
        }
      />
      <Route
        path="/"
        element={
          <RequireAuth>
            <Shell />
          </RequireAuth>
        }
      >
        <Route index element={pilotPage(<DashboardPage />)} />
        <Route path="kanban" element={pilotPage(<KanbanPage />)} />
        <Route path="pipeline" element={pilotPage(<PipelinePage />)} />
        <Route path="purchases" element={pilotPage(<PurchasesPage />)} />
        <Route path="operations" element={pilotPage(<OperationsPage />)} />
        <Route path="logistique" element={pilotPage(<LogistiquePage />)} />
        <Route path="stocks" element={pilotPage(<StocksPage />)} />
        <Route path="qualite" element={pilotPage(<QualitePage />)} />
        <Route path="hse" element={pilotPage(<HsePage />)} />
        <Route path="maintenance" element={pilotPage(<MaintenancePage />)} />
        <Route path="rh-paie" element={pilotPage(<RhPaiePage />)} />
        <Route path="comptabilite" element={pilotPage(<ComptabilitePage />)} />
        <Route path="controle-gestion" element={pilotPage(<ControleGestionPage />)} />
        <Route path="juridique" element={pilotPage(<JuridiquePage />)} />
        <Route path="direction" element={pilotPage(<DirectionPage />)} />
        <Route path="circuits" element={pilotPage(<CircuitsPage />)} />
        <Route path="notifications" element={pilotPage(<NotificationsPage />)} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}