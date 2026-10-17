import {
  Bell,
  Boxes,
  Calculator,
  CircleUser,
  FileSignature,
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
  Smartphone,
  SquareKanban,
  Sun,
  Truck,
  UserRound,
  Users,
  Wrench,
} from "lucide-react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useEffect, useMemo, useState } from "react";
import type { LucideIcon } from "lucide-react";

import { useAuth } from "../store/auth";
import { canSeeApp, ROUTE_APP, type ErpApp } from "../lib/modules";
import { MotionProvider } from "./Pilot";
import { BrandLogo } from "./BrandLogo";
import { CommandPalette, type PaletteItem } from "./CommandPalette";

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
  { to: "/signatures", key: "nav.signatures", Icon: FileSignature },
  { to: "/terrain", key: "nav.terrain", Icon: Smartphone },
  { to: "/mon-espace", key: "nav.monEspace", Icon: UserRound },
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
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [navOpen, setNavOpen] = useState(false);
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

  // Palette de commandes : pages (déjà filtrées par rôle) + actions rapides.
  const paletteItems = useMemo<PaletteItem[]>(
    () => [
      ...[...PILOT_NAV, ...visibleModules].map(({ to, key, Icon }) => ({
        id: `go${to === "/" ? "-home" : to.replace(/\//g, "-")}`,
        label: t(key),
        group: t("palette.pages"),
        Icon,
        keywords: to,
        run: () => navigate(to),
      })),
      { id: "act-theme", label: t("common.theme"), group: t("palette.actions"), Icon: isDark ? Sun : Moon, run: toggleTheme },
      { id: "act-lang", label: t("common.language"), group: t("palette.actions"), Icon: Languages, run: toggleLang },
      { id: "act-logout", label: t("common.logout"), group: t("palette.actions"), Icon: LogOut, run: logout },
    ],
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [t, visibleModules, isDark, i18n.language],
  );

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPaletteOpen((o) => !o);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

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
      <a className="skip-link" href="#main-content">
        {t("common.skipToContent")}
      </a>
      <div className="app-shell">
        <aside className={navOpen ? "sidebar open" : "sidebar"} id="app-sidebar">
          <div className="sidebar-brand">
            <BrandLogo />
          </div>
          <nav className="sidebar-scroll" aria-label={t("common.mainNav")}>
            <div className="nav-group">
              <span className="nav-group-label">{t("nav.groupPilotage")}</span>
              {renderNav(PILOT_NAV)}
            </div>
            <div className="nav-group">
              <span className="nav-group-label">{t("nav.groupModules")}</span>
              {renderNav(visibleModules)}
            </div>
          </nav>
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
              <button
                type="button"
                className="search-trigger"
                aria-label={t("common.search")}
                aria-haspopup="dialog"
                onClick={() => setPaletteOpen(true)}
              >
                <Search size={15} />
                <span>{t("common.search")}</span>
                <kbd>Ctrl K</kbd>
              </button>
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

          <main className="main" id="main-content" tabIndex={-1}>
            <Outlet />
          </main>
        </div>
      </div>
      <CommandPalette
        open={paletteOpen}
        onClose={() => setPaletteOpen(false)}
        items={paletteItems}
        placeholder={t("palette.placeholder")}
        emptyLabel={t("common.noResult")}
      />
    </MotionProvider>
  );
}