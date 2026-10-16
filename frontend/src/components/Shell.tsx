import {
  Bell,
  Boxes,
  Calculator,
  CircleUser,
  Filter,
  GitBranch,
  HardHat,
  Languages,
  LayoutDashboard,
  LineChart,
  LogOut,
  Menu,
  Moon,
  PieChart,
  Scale,
  Search,
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
import { useMemo, useRef, useState } from "react";
import type { LucideIcon } from "lucide-react";

import { useAuth } from "../store/auth";
import { canSeeApp, ROUTE_APP, type ErpApp } from "../lib/modules";
import { MotionProvider } from "./Pilot";
import { BrandLogo } from "./BrandLogo";

interface NavItem {
  to: string;
  key: string;
  Icon: LucideIcon;
}

/** Entrée de menu rattachée à une application ERP filtrable (RF-59). */
interface ModuleNavItem extends NavItem {
  app: ErpApp;
}

const PILOT_NAV: NavItem[] = [
  { to: "/", key: "nav.dashboard", Icon: LayoutDashboard },
  { to: "/direction", key: "nav.direction", Icon: LineChart },
  { to: "/kanban", key: "nav.kanban", Icon: SquareKanban },
  { to: "/circuits", key: "nav.circuits", Icon: GitBranch },
  { to: "/notifications", key: "nav.notifications", Icon: Bell },
];

const MODULE_NAV: ModuleNavItem[] = [
  { to: "/pipeline", key: "nav.pipeline", Icon: Filter, app: ROUTE_APP["/pipeline"] },
  { to: "/purchases", key: "nav.purchases", Icon: ShoppingCart, app: ROUTE_APP["/purchases"] },
  { to: "/operations", key: "nav.operations", Icon: HardHat, app: ROUTE_APP["/operations"] },
  { to: "/logistique", key: "nav.logistique", Icon: Truck, app: ROUTE_APP["/logistique"] },
  { to: "/stocks", key: "nav.stocks", Icon: Boxes, app: ROUTE_APP["/stocks"] },
  { to: "/qualite", key: "nav.qualite", Icon: ShieldCheck, app: ROUTE_APP["/qualite"] },
  { to: "/hse", key: "nav.hse", Icon: ShieldAlert, app: ROUTE_APP["/hse"] },
  { to: "/maintenance", key: "nav.maintenance", Icon: Wrench, app: ROUTE_APP["/maintenance"] },
  { to: "/rh-paie", key: "nav.rhPaie", Icon: Users, app: ROUTE_APP["/rh-paie"] },
  { to: "/comptabilite", key: "nav.comptabilite", Icon: Calculator, app: ROUTE_APP["/comptabilite"] },
  { to: "/controle-gestion", key: "nav.controleGestion", Icon: PieChart, app: ROUTE_APP["/controle-gestion"] },
  { to: "/juridique", key: "nav.juridique", Icon: Scale, app: ROUTE_APP["/juridique"] },
];

export function Shell() {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const user = useAuth((s) => s.user);
  const clear = useAuth((s) => s.clear);

  const [theme, setTheme] = useState(() => document.documentElement.getAttribute("data-theme") ?? "light");
  const [query, setQuery] = useState("");
  const [navOpen, setNavOpen] = useState(false);
  const searchRef = useRef<HTMLInputElement>(null);
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

  const visibleModules = useMemo(
    () => MODULE_NAV.filter(({ app }) => canSeeApp(user?.modules, app)),
    [user?.modules],
  );

  const displayName = [user?.first_name, user?.last_name].filter(Boolean).join(" ") || user?.email || "";
  const initials = (displayName || "?")
    .split(/[\s@._-]+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase() ?? "")
    .join("");

  const matches = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return [];
    return [...PILOT_NAV, ...visibleModules]
      .filter(({ key, to }) => t(key).toLowerCase().includes(q) || to.includes(q))
      .slice(0, 7);
  }, [query, t, visibleModules]);

  const goSearch = (to: string) => {
    setQuery("");
    navigate(to);
  };

  const renderNav = (items: NavItem[]) =>
    items.map(({ to, key, Icon }) => (
      <NavLink
        key={to}
        to={to}
        end={to === "/"}
        onClick={() => setNavOpen(false)}
        className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")}
      >
        <Icon size={16} />
        {t(key)}
      </NavLink>
    ));

  return (
    <MotionProvider>
      <div className="app-shell">
        <aside className={navOpen ? "sidebar open" : "sidebar"} id="app-sidebar">
          <div className="sidebar-brand">
            <BrandLogo />
          </div>
          <div className="sidebar-scroll">
            <div className="nav-group">
              <span className="nav-group-label">{t("nav.groupPilotage")}</span>
              {renderNav(PILOT_NAV)}
            </div>
            <div className="nav-group">
              <span className="nav-group-label">{t("nav.groupModules")}</span>
              {renderNav(visibleModules)}
            </div>
          </div>
          <button type="button" className="btn ghost sidebar-logout" onClick={logout}>
            <LogOut size={15} />
            {t("common.logout")}
          </button>
        </aside>

        {navOpen && <div className="nav-backdrop" onClick={() => setNavOpen(false)} aria-hidden="true" />}

        <div className="main-col">
          <header className="topbar">
            <button
              type="button"
              className="icon-btn nav-toggle"
              aria-label={t("common.menu")}
              aria-controls="app-sidebar"
              aria-expanded={navOpen}
              onClick={() => setNavOpen((o) => !o)}
            >
              <Menu size={18} />
            </button>
            <div className="topbar-search">
              <div className="search-field">
                <Search size={15} />
                <input
                  ref={searchRef}
                  type="search"
                  placeholder={t("common.search")}
                  aria-label={t("common.search")}
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && matches[0]) goSearch(matches[0].to);
                    if (e.key === "Escape") setQuery("");
                  }}
                />
              </div>
              {query.trim() !== "" && (
                <div className="search-pop">
                  {matches.length === 0 ? (
                    <div className="search-empty">{t("common.noResult")}</div>
                  ) : (
                    matches.map(({ to, key, Icon }) => (
                      <button key={to} type="button" className="search-item" onClick={() => goSearch(to)}>
                        <Icon size={15} />
                        {t(key)}
                      </button>
                    ))
                  )}
                </div>
              )}
            </div>

            <div className="actions">
              <button
                className="icon-btn"
                title={t("common.theme")}
                onClick={toggleTheme}
                aria-label={t("common.theme")}
              >
                <ThemeIcon size={16} />
              </button>
              <button
                className="icon-btn"
                title={t("common.language")}
                onClick={toggleLang}
                aria-label={t("common.language")}
              >
                <Languages size={16} />
              </button>

              <div className="user-chip">
                <span className="avatar" aria-hidden="true">
                  {initials || <CircleUser size={16} />}
                </span>
                <span className="user-meta">
                  <span className="user-name">{displayName}</span>
                  <span className="user-role">{user?.role ?? ""}</span>
                </span>
                <button className="btn ghost" onClick={logout}>
                  <LogOut size={15} />
                  {t("common.logout")}
                </button>
              </div>
            </div>
          </header>

          <main className="main">
            <Outlet />
          </main>
        </div>
      </div>
    </MotionProvider>
  );
}