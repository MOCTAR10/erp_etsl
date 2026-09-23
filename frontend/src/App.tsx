import type { ReactNode } from "react";

import { Navigate, Route, Routes, useLocation } from "react-router-dom";

import { useAuth } from "./store/auth";
import { Shell } from "./components/Shell";
import { withPilot } from "./components/Pilot";

import { CircuitsPage } from "./pages/Circuits";
import { DashboardPage } from "./pages/Dashboard";
import { KanbanPage } from "./pages/Kanban";
import { LoginPage } from "./pages/Login";
import { NotificationsPage } from "./pages/Notifications";
import { OperationsPage } from "./pages/Operations";
import { LogistiquePage } from "./pages/Logistique";
import { StocksPage } from "./pages/Stocks";
import { QualitePage } from "./pages/Qualite";
import { HsePage } from "./pages/Hse";
import { MaintenancePage } from "./pages/Maintenance";
import { RhPaiePage } from "./pages/RhPaie";
import { ComptabilitePage } from "./pages/Comptabilite";
import { ControleGestionPage } from "./pages/ControleGestion";
import { PipelinePage } from "./pages/Pipeline";
import { PurchasesPage } from "./pages/Purchases";

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
        <Route index element={withPilot(<DashboardPage />)} />
        <Route path="kanban" element={withPilot(<KanbanPage />)} />
        <Route path="pipeline" element={withPilot(<PipelinePage />)} />
        <Route path="purchases" element={withPilot(<PurchasesPage />)} />
        <Route path="operations" element={withPilot(<OperationsPage />)} />
        <Route path="logistique" element={withPilot(<LogistiquePage />)} />
        <Route path="stocks" element={withPilot(<StocksPage />)} />
        <Route path="qualite" element={withPilot(<QualitePage />)} />
        <Route path="hse" element={withPilot(<HsePage />)} />
        <Route path="maintenance" element={withPilot(<MaintenancePage />)} />
        <Route path="rh-paie" element={withPilot(<RhPaiePage />)} />
        <Route path="comptabilite" element={withPilot(<ComptabilitePage />)} />
        <Route path="controle-gestion" element={withPilot(<ControleGestionPage />)} />
        <Route path="circuits" element={<CircuitsPage />} />
        <Route path="notifications" element={<NotificationsPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}