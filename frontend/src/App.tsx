import { lazy, Suspense, type ReactNode } from "react";

import { Navigate, Route, Routes, useLocation } from "react-router-dom";

import { useAuth } from "./store/auth";
import { landingForRole } from "./lib/landing";
import { Shell } from "./components/Shell";
import { withPilot } from "./components/Pilot";
import { AppToaster, KpiGridSkeleton } from "./components/ui";
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
const SignaturesPage = lazy(() => import("./pages/Signatures").then((m) => ({ default: m.SignaturesPage })));
const TerrainPage = lazy(() => import("./pages/Terrain").then((m) => ({ default: m.TerrainPage })));
const MonEspacePage = lazy(() => import("./pages/MonEspace").then((m) => ({ default: m.MonEspacePage })));
const RhPaiePage = lazy(() => import("./pages/RhPaie").then((m) => ({ default: m.RhPaiePage })));
const ComptabilitePage = lazy(() => import("./pages/Comptabilite").then((m) => ({ default: m.ComptabilitePage })));
const ControleGestionPage = lazy(() => import("./pages/ControleGestion").then((m) => ({ default: m.ControleGestionPage })));
const JuridiquePage = lazy(() => import("./pages/Juridique").then((m) => ({ default: m.JuridiquePage })));
const DirectionPage = lazy(() => import("./pages/Direction").then((m) => ({ default: m.DirectionPage })));
const CircuitsPage = lazy(() => import("./pages/Circuits").then((m) => ({ default: m.CircuitsPage })));
const NotificationsPage = lazy(() => import("./pages/Notifications").then((m) => ({ default: m.NotificationsPage })));
const SecuritePage = lazy(() => import("./pages/Securite").then((m) => ({ default: m.SecuritePage })));
const DocumentsPage = lazy(() => import("./pages/Documents").then((m) => ({ default: m.DocumentsPage })));
const ParametresPage = lazy(() => import("./pages/Parametres").then((m) => ({ default: m.ParametresPage })));
const MonMotDePassePage = lazy(() => import("./pages/MotDePasse").then((m) => ({ default: m.MonMotDePassePage })));
const MotDePasseOubliePage = lazy(() => import("./pages/MotDePasse").then((m) => ({ default: m.MotDePasseOubliePage })));
const ReinitialiserMotDePassePage = lazy(() =>
  import("./pages/MotDePasse").then((m) => ({ default: m.ReinitialiserMotDePassePage })),
);
const AdministrationPage = lazy(() => import("./pages/Administration").then((m) => ({ default: m.AdministrationPage })));
const DemoUiPage = lazy(() => import("./pages/DemoUi").then((m) => ({ default: m.DemoUiPage })));
const ReprisePage = lazy(() => import("./pages/Reprise").then((m) => ({ default: m.ReprisePage })));

function pilotPage(children: ReactNode) {
  return withPilot(<Suspense fallback={<KpiGridSkeleton count={6} />}>{children}</Suspense>);
}

function RequireAuth({ children }: { children: ReactNode }) {
  const access = useAuth((s) => s.access);
  const doitChanger = useAuth((s) => Boolean((s.user as { doit_changer_mdp?: boolean } | null)?.doit_changer_mdp));
  const location = useLocation();
  if (!access) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }
  // Mot de passe réinitialisé par l'admin : changement imposé avant tout autre écran (le serveur bloque aussi).
  if (doitChanger && location.pathname !== "/mon-mot-de-passe") {
    return <Navigate to="/mon-mot-de-passe" replace />;
  }
  return <>{children}</>;
}

function GuestOnly({ children }: { children: ReactNode }) {
  const access = useAuth((s) => s.access);
  const role = useAuth((s) => s.user?.role);
  if (access) return <Navigate to={landingForRole(role)} replace />;
  return <>{children}</>;
}

export default function App() {
  return (
    <>
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
        path="/mot-de-passe-oublie"
        element={
          <Suspense fallback={null}>
            <MotDePasseOubliePage />
          </Suspense>
        }
      />
      <Route
        path="/reinitialiser-mot-de-passe"
        element={
          <Suspense fallback={null}>
            <ReinitialiserMotDePassePage />
          </Suspense>
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
        <Route path="signatures" element={pilotPage(<SignaturesPage />)} />
        <Route path="terrain" element={pilotPage(<TerrainPage />)} />
        <Route path="mon-espace" element={pilotPage(<MonEspacePage />)} />
        <Route path="rh-paie" element={pilotPage(<RhPaiePage />)} />
        <Route path="comptabilite" element={pilotPage(<ComptabilitePage />)} />
        <Route path="controle-gestion" element={pilotPage(<ControleGestionPage />)} />
        <Route path="juridique" element={pilotPage(<JuridiquePage />)} />
        <Route path="direction" element={pilotPage(<DirectionPage />)} />
        <Route path="circuits" element={pilotPage(<CircuitsPage />)} />
        <Route path="notifications" element={pilotPage(<NotificationsPage />)} />
        <Route path="securite" element={pilotPage(<SecuritePage />)} />
        <Route path="documents" element={pilotPage(<DocumentsPage />)} />
        <Route path="parametres" element={pilotPage(<ParametresPage />)} />
        <Route path="administration" element={pilotPage(<AdministrationPage />)} />
        <Route path="mon-mot-de-passe" element={pilotPage(<MonMotDePassePage />)} />
        <Route path="reprise" element={pilotPage(<ReprisePage />)} />
        <Route path="demo-ui" element={pilotPage(<DemoUiPage />)} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
    <AppToaster />
    </>
  );
}