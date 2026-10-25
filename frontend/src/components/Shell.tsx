import {
  Bell,
  Boxes,
  Calculator,
  ChevronDown,
  FileSignature,
  FileUp,
  Filter,
  FolderOpen,
  GitBranch,
  HardHat,
  KeyRound,
  Languages,
  LayoutDashboard,
  LineChart,
  LogOut,
  Menu as MenuIcon,
  Moon,
  PanelLeftClose,
  PanelLeftOpen,
  PieChart,
  Scale,
  Search,
  ShieldAlert,
  ShieldCheck,
  ShoppingCart,
  SlidersHorizontal,
  Smartphone,
  SquareKanban,
  Sun,
  Truck,
  UserCog,
  UserRound,
  Users,
  Wrench,
} from "lucide-react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useState } from "react";
import type { LucideIcon } from "lucide-react";

import { api } from "../api/client";
import { useAuth } from "../store/auth";
import { searchEntities, type EntityRow } from "../lib/entitySearch";
import { canSeeApp, ROUTE_APP, sansCode, type ErpApp } from "../lib/modules";
import { initiales, roleLabel } from "../lib/roles";
import { MotionProvider } from "./Pilot";
import { BrandLogo } from "./BrandLogo";
import { NotificationBell } from "./NotificationBell";
import { CommandPalette, Menu, Tooltip } from "./ui";
import type { CommandGroupDef, CommandItemDef, MenuEntry } from "./ui";

interface NavItem {
  to: string;
  key: string;
  Icon: LucideIcon;
}

/** Entrée de menu rattachée à une application ERP filtrable (RF-59). */
interface ModuleNavItem extends NavItem {
  app: ErpApp;
}

/** Pilotage : écrans de suivi transverses (non filtrés par module). */
const PILOT_NAV: NavItem[] = [
  { to: "/", key: "nav.dashboard", Icon: LayoutDashboard },
  { to: "/direction", key: "nav.direction", Icon: LineChart },
  { to: "/kanban", key: "nav.kanban", Icon: SquareKanban },
  { to: "/circuits", key: "nav.circuits", Icon: GitBranch },
  { to: "/notifications", key: "nav.notifications", Icon: Bell },
  { to: "/signatures", key: "nav.signatures", Icon: FileSignature },
  { to: "/documents", key: "ecarts_tr.nav.ged", Icon: FolderOpen },
];

/** Espace & administration : outils personnels et paramétrage (groupe repliable). */
const OUTILS_NAV: NavItem[] = [
  { to: "/terrain", key: "nav.terrain", Icon: Smartphone },
  { to: "/mon-espace", key: "nav.monEspace", Icon: UserRound },
  { to: "/securite", key: "nav.securite", Icon: KeyRound },
  { to: "/parametres", key: "ecarts_tr.nav.parametres", Icon: SlidersHorizontal },
  { to: "/reprise", key: "ecarts_import.nav", Icon: FileUp },
  /** Administration (EX-G-01) : comptes, matrice des droits, référentiels, piste d'audit — rôle admin seulement. */
  { to: "/administration", key: "ecarts_tr.nav.administration", Icon: UserCog },
];
/** Reprise de données (CDC §10) : cercle de l'API d'import + RH (salariés, paie) + QA/QC (qualité) + cercle paie. */
const REPRISE_ROLES = new Set(["admin", "comptable", "finance", "direction", "rh", "qaqc", "pdg", "dga", "hse", "logistique", "maintenance"]);

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

/** Préférences d'affichage du menu (par poste) : lecture / écriture tolérantes (navigation privée, stockage bloqué). */
function lirePref(cle: string): string | null {
  try {
    return localStorage.getItem(cle);
  } catch {
    return null;
  }
}
function ecrirePref(cle: string, valeur: string) {
  try {
    localStorage.setItem(cle, valeur);
  } catch {
    /* stockage indisponible : préférence non mémorisée */
  }
}
const PREF_RAIL = "etls.nav.rail";
const PREF_OUTILS = "etls.nav.outils";

export function Shell() {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const user = useAuth((s) => s.user);
  const clear = useAuth((s) => s.clear);

  const [theme, setTheme] = useState(() => document.documentElement.getAttribute("data-theme") ?? "light");
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [navOpen, setNavOpen] = useState(false);
  const [rail, setRail] = useState(() => lirePref(PREF_RAIL) === "1");
  const [outilsPref, setOutilsPref] = useState(() => lirePref(PREF_OUTILS) === "1");
  const isDark = theme === "dark";
  const ThemeIcon = isDark ? Sun : Moon;

  const toggleTheme = useCallback(() => {
    const root = document.documentElement;
    const next = root.getAttribute("data-theme") === "dark" ? "light" : "dark";
    root.setAttribute("data-theme", next);
    ecrirePref("etls.theme", next);
    setTheme(next);
  }, []);

  const toggleLang = useCallback(() => {
    const next = i18n.language === "fr" ? "en" : "fr";
    void i18n.changeLanguage(next);
    ecrirePref("etls.lang", next);
  }, [i18n]);

  const logout = useCallback(() => {
    clear();
    navigate("/login", { replace: true });
  }, [clear, navigate]);

  const toggleRail = () => {
    setRail((r) => {
      ecrirePref(PREF_RAIL, r ? "0" : "1");
      return !r;
    });
  };

  const outilsNav = useMemo(
    () =>
      OUTILS_NAV.filter(({ to }) => {
        if (to === "/reprise") return REPRISE_ROLES.has(user?.role ?? "");
        if (to === "/administration") return user?.role === "admin";
        return true;
      }),
    [user?.role],
  );

  const visibleModules = useMemo(
    () => MODULE_NAV.filter(({ app }) => canSeeApp(user?.modules, app)),
    [user?.modules],
  );

  // Le groupe « Espace & administration » s'ouvre de lui-même si l'écran courant en fait partie.
  const outilsActif = outilsNav.some(({ to }) => pathname === to || pathname.startsWith(`${to}/`));
  const outilsOpen = outilsPref || outilsActif;
  const toggleOutils = () => {
    setOutilsPref((o) => {
      ecrirePref(PREF_OUTILS, o ? "0" : "1");
      return !o;
    });
  };

  // Compteur discret : notifications non lues (même cache que l'écran Notifications).
  const notifications = useQuery({
    queryKey: ["notifications"],
    queryFn: api.notifications,
    staleTime: 60_000,
    refetchInterval: 120_000,
    retry: 0,
  });
  const nonLues = (notifications.data ?? []).filter((n) => !n.is_read).length;

  const displayName = [user?.first_name, user?.last_name].filter(Boolean).join(" ") || user?.email || "";
  const role = roleLabel(t, user?.role);

  // Palette : écrans visibles par le rôle, actions rapides (routes existantes), recherche d'entités via l'API.
  const paletteGroups = useMemo<CommandGroupDef[]>(() => {
    const versPage = (items: NavItem[]): CommandItemDef[] =>
      items.map(({ to, key, Icon }) => ({
        id: `nav-${to}`,
        label: sansCode(t(key)),
        icon: Icon,
        keywords: [to.replace(/[/-]/g, " "), t(key)],
        onSelect: () => navigate(to),
      }));
    const aller = (id: string, label: string, icon: LucideIcon, to: string): CommandItemDef => ({ id, label, icon, onSelect: () => navigate(to) });
    return [
      { id: "pilotage", heading: t("nav.groupPilotage"), items: versPage(PILOT_NAV) },
      { id: "modules", heading: t("nav.groupModules"), items: versPage(visibleModules) },
      { id: "outils", heading: t("shell.groupOutils"), items: versPage(outilsNav) },
      {
        id: "actions",
        heading: t("shell.groupes.actions"),
        items: [
          aller("act-delegation", t("shell.actions.delegation"), ShieldCheck, "/securite"),
          aller("act-documents", t("shell.actions.documents"), FolderOpen, "/documents"),
          aller("act-terrain", t("shell.actions.terrain"), Smartphone, "/terrain"),
          aller("act-conges", t("shell.actions.conges"), UserRound, "/mon-espace"),
          aller("act-mdp", t("shell.actions.motDePasse"), KeyRound, "/mon-mot-de-passe"),
          { id: "act-theme", label: t(isDark ? "shell.actions.themeClair" : "shell.actions.themeSombre"), icon: isDark ? Sun : Moon, onSelect: toggleTheme },
          { id: "act-lang", label: t("shell.actions.langue"), icon: Languages, onSelect: toggleLang },
          { id: "act-logout", label: t("shell.actions.deconnexion"), icon: LogOut, onSelect: logout },
        ],
      },
    ];
  }, [t, navigate, visibleModules, outilsNav, isDark, toggleTheme, toggleLang, logout]);

  const rechercher = useCallback(
    async (q: string, signal: AbortSignal): Promise<CommandGroupDef[]> => {
      const groupes = await searchEntities(q, signal, user?.modules, (path, query, s) => api.rechercher<EntityRow>(path, query, s));
      return groupes.map((g) => ({
        id: `ent-${g.key}`,
        heading: t(`shell.search.${g.key}`),
        items: g.hits.map((h) => ({ id: h.id, label: h.label, hint: h.hint, icon: h.icon, onSelect: () => navigate(h.route) })),
      }));
    },
    [user?.modules, t, navigate],
  );

  useEffect(() => {
    // Tiroir de navigation mobile : Échap le referme (comportement attendu au clavier).
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setNavOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const renderNav = (items: NavItem[]) =>
    items.map(({ to, key, Icon }) => {
      const label = sansCode(t(key));
      const badge = to === "/notifications" && nonLues > 0 ? nonLues : 0;
      const link = (
        <NavLink
          key={to}
          to={to}
          end={to === "/"}
          onClick={() => setNavOpen(false)}
          aria-label={rail ? label : undefined}
          // Classe texte (pas de fonction) : NavLink ajoute `active` lui-même, et le Slot Radix de l'infobulle
          // (mode rail) ne sait fusionner que des chaînes.
          className="nav-link"
        >
          <Icon size={16} strokeWidth={1.85} aria-hidden="true" />
          <span className="nav-label">{label}</span>
          {badge ? (
            <>
              <span className="nav-badge" aria-hidden="true">
                {badge > 99 ? "99+" : badge}
              </span>
              <span className="sr-only">{t("shell.nonLues", { count: badge })}</span>
            </>
          ) : null}
        </NavLink>
      );
      return rail ? (
        <Tooltip key={to} content={badge ? `${label} · ${t("shell.nonLues", { count: badge })}` : label} side="right" delay={150}>
          {link}
        </Tooltip>
      ) : (
        link
      );
    });

  const profilItems: MenuEntry[] = [
    {
      type: "label",
      label: (
        <span className="profile-head">
          <span className="profile-head-name">{displayName}</span>
          {user?.email && user.email !== displayName ? <span className="profile-head-mail">{user.email}</span> : null}
          <span className="profile-head-role">{role}</span>
        </span>
      ),
    },
    "separator",
    { id: "espace", label: t("shell.profil.monEspace"), icon: UserRound, onSelect: () => navigate("/mon-espace") },
    { id: "mdp", label: t("shell.profil.motDePasse"), icon: KeyRound, onSelect: () => navigate("/mon-mot-de-passe") },
    { id: "secu", label: t("shell.profil.securite"), icon: ShieldCheck, onSelect: () => navigate("/securite") },
    "separator",
    { id: "theme", label: t(isDark ? "shell.profil.themeClair" : "shell.profil.themeSombre"), icon: isDark ? Sun : Moon, onSelect: toggleTheme },
    { id: "langue", label: t("shell.profil.langue"), icon: Languages, onSelect: toggleLang },
    "separator",
    { id: "logout", label: t("shell.profil.deconnexion"), icon: LogOut, onSelect: logout, danger: true },
  ];

  return (
    <MotionProvider>
      <a className="skip-link" href="#main-content">
        {t("common.skipToContent")}
      </a>
      <div className={rail ? "app-shell shell-v2 is-rail" : "app-shell shell-v2"}>
        <aside className={navOpen ? "sidebar open" : "sidebar"} id="app-sidebar">
          <div className="sidebar-brand">
            <BrandLogo />
          </div>
          <nav className="sidebar-scroll" aria-label={t("common.mainNav")}>
            <div className="nav-group">
              <span className="nav-group-label">{t("nav.groupPilotage")}</span>
              {renderNav(PILOT_NAV)}
            </div>
            {visibleModules.length > 0 ? (
              <div className="nav-group">
                <span className="nav-group-label">{t("nav.groupModules")}</span>
                {renderNav(visibleModules)}
              </div>
            ) : null}
            <div className="nav-group">
              <button
                type="button"
                className="nav-group-label nav-group-toggle"
                aria-expanded={outilsOpen || rail}
                aria-controls="nav-outils"
                onClick={toggleOutils}
                disabled={outilsActif}
                title={outilsOpen ? t("shell.masquerOutils") : t("shell.afficherOutils")}
              >
                <span>{t("shell.groupOutils")}</span>
                <ChevronDown size={14} aria-hidden="true" className="nav-group-chevron" />
              </button>
              <div id="nav-outils" className="nav-group-items" hidden={!(outilsOpen || rail)}>
                {renderNav(outilsNav)}
              </div>
            </div>
          </nav>
          <div className="sidebar-foot">
            <button type="button" className="btn ghost sidebar-logout" onClick={logout} aria-label={t("common.logout")}>
              <LogOut size={15} aria-hidden="true" />
              <span className="nav-label">{t("common.logout")}</span>
            </button>
            <Tooltip content={rail ? t("shell.deplier") : t("shell.reduire")} side="right">
              <button
                type="button"
                className="icon-btn sidebar-rail-toggle"
                aria-label={rail ? t("shell.deplier") : t("shell.reduire")}
                aria-pressed={rail}
                onClick={toggleRail}
              >
                {rail ? <PanelLeftOpen size={16} aria-hidden="true" /> : <PanelLeftClose size={16} aria-hidden="true" />}
              </button>
            </Tooltip>
          </div>
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
              <MenuIcon size={18} aria-hidden="true" />
            </button>
            <div className="topbar-brand">
              <BrandLogo showTag={false} />
            </div>
            <div className="topbar-search">
              <button
                type="button"
                className="search-trigger"
                aria-label={t("common.search")}
                aria-haspopup="dialog"
                aria-keyshortcuts="Control+K Meta+K"
                onClick={() => setPaletteOpen(true)}
              >
                <Search size={15} aria-hidden="true" />
                <span className="search-trigger-text">{t("shell.rechercher")}</span>
                <kbd>Ctrl K</kbd>
              </button>
            </div>

            <div className="actions">
              <Tooltip content={t("shell.tipTheme")} side="bottom">
                <button type="button" className="icon-btn topbar-pref" onClick={toggleTheme} aria-label={t("common.theme")}>
                  <ThemeIcon size={16} aria-hidden="true" />
                </button>
              </Tooltip>
              <Tooltip content={t("shell.tipLangue")} side="bottom">
                <button type="button" className="icon-btn topbar-pref" onClick={toggleLang} aria-label={t("common.language")}>
                  <Languages size={16} aria-hidden="true" />
                </button>
              </Tooltip>
              <NotificationBell items={notifications.data ?? []} />
              <span className="topbar-sep" aria-hidden="true" />
              <Menu
                align="end"
                items={profilItems}
                trigger={
                  <button type="button" className="profile-trigger" aria-label={`${t("shell.profil.ouvrir")} — ${displayName}, ${role}`}>
                    <span className="avatar" aria-hidden="true">
                      {initiales(displayName)}
                    </span>
                    <span className="profile-meta" aria-hidden="true">
                      <span className="profile-name">{displayName}</span>
                      <span className="profile-role">{role}</span>
                    </span>
                    <ChevronDown size={14} className="profile-chevron" aria-hidden="true" />
                  </button>
                }
              />
            </div>
          </header>

          <main className="main" id="main-content" tabIndex={0}>
            <Outlet />
          </main>
        </div>
      </div>
      <CommandPalette
        open={paletteOpen}
        onOpenChange={setPaletteOpen}
        groups={paletteGroups}
        search={rechercher}
        debounce={300}
        label={t("shell.paletteLabel")}
        placeholder={t("shell.palettePlaceholder")}
        emptyLabel={t("shell.paletteVide")}
      />
    </MotionProvider>
  );
}
