import {
  Bell,
  Boxes,
  Calculator,
  Filter,
  GitBranch,
  HardHat,
  Languages,
  LayoutDashboard,
  LineChart,
  LogOut,
  Moon,
  PieChart,
  Scale,
  ShieldAlert,
  ShieldCheck,
  ShoppingCart,
  SquareKanban,
  Sun,
  Truck,
  Users,
  Wrench,
} from "lucide-react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useState } from "react";
import type { LucideIcon } from "lucide-react";

import { useAuth } from "../store/auth";
import { MotionProvider } from "./Pilot";

const NAV_KEYS: { to: string; key: string; Icon: LucideIcon }[] = [
  { to: "/", key: "nav.dashboard", Icon: LayoutDashboard },
  { to: "/pipeline", key: "nav.pipeline", Icon: Filter },
  { to: "/purchases", key: "nav.purchases", Icon: ShoppingCart },
  { to: "/operations", key: "nav.operations", Icon: HardHat },
  { to: "/logistique", key: "nav.logistique", Icon: Truck },
  { to: "/stocks", key: "nav.stocks", Icon: Boxes },
  { to: "/qualite", key: "nav.qualite", Icon: ShieldCheck },
  { to: "/hse", key: "nav.hse", Icon: ShieldAlert },
  { to: "/maintenance", key: "nav.maintenance", Icon: Wrench },
  { to: "/rh-paie", key: "nav.rhPaie", Icon: Users },
  { to: "/comptabilite", key: "nav.comptabilite", Icon: Calculator },
  { to: "/controle-gestion", key: "nav.controleGestion", Icon: PieChart },
  { to: "/juridique", key: "nav.juridique", Icon: Scale },
  { to: "/direction", key: "nav.direction", Icon: LineChart },
  { to: "/kanban", key: "nav.kanban", Icon: SquareKanban },
  { to: "/circuits", key: "nav.circuits", Icon: GitBranch },
  { to: "/notifications", key: "nav.notifications", Icon: Bell },
];

export function Shell() {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const user = useAuth((s) => s.user);
  const clear = useAuth((s) => s.clear);

  const [theme, setTheme] = useState(() => document.documentElement.getAttribute("data-theme") ?? "light");
  const isDark = theme === "dark";
  const ThemeIcon = isDark ? Sun : Moon;

  const toggleTheme = () => {
    const root = document.documentElement;
    const next = root.getAttribute("data-theme") === "dark" ? "light" : "dark";
    root.setAttribute("data-theme", next);
    localStorage.setItem("etls.theme", next);
    setTheme(next);
  };

  const toggleLang = () => {
    const next = i18n.language === "fr" ? "en" : "fr";
    void i18n.changeLanguage(next);
    localStorage.setItem("etls.lang", next);
  };

  const logout = () => {
    clear();
    navigate("/login", { replace: true });
  };

  const displayName = [user?.first_name, user?.last_name].filter(Boolean).join(" ") || user?.email || "";

  return (
    <MotionProvider>
      <div className="app-shell">
        <aside className="sidebar">
          <div className="sidebar-brand">
            <span className="brand-mark">ET</span>
            <span>{t("app.brand")}</span>
          </div>
          <nav style={{ display: "flex", flexDirection: "column", gap: "0.25rem" }}>
            {NAV_KEYS.map(({ to, key, Icon }) => (
              <NavLink
                key={to}
                to={to}
                end={to === "/"}
                className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")}
              >
                <Icon size={16} />
                {t(key)}
              </NavLink>
            ))}
          </nav>
        </aside>

        <main className="main">
          <div className="topbar">
            <div className="actions">
              <button className="icon-btn" title={t("common.theme")} onClick={toggleTheme} aria-label={t("common.theme")}>
                <ThemeIcon size={16} />
              </button>
              <button className="icon-btn" title={t("common.language")} onClick={toggleLang} aria-label={t("common.language")}>
                <Languages size={16} />
              </button>
            </div>
            <div className="user-chip">
              <span>{displayName}</span>
              <button className="btn ghost" onClick={logout}>
                <LogOut size={15} />
                {t("common.logout")}
              </button>
            </div>
          </div>
          <Outlet />
        </main>
      </div>
    </MotionProvider>
  );
}