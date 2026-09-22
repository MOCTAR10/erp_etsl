import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { useAuth } from "../store/auth";
import { MotionProvider } from "./Pilot";

const NAV_KEYS = [
  ["/", "nav.dashboard"],
  ["/pipeline", "nav.pipeline"],
  ["/purchases", "nav.purchases"],
  ["/operations", "nav.operations"],
  ["/logistique", "nav.logistique"],
  ["/stocks", "nav.stocks"],
  ["/qualite", "nav.qualite"],
  ["/hse", "nav.hse"],
  ["/maintenance", "nav.maintenance"],
  ["/rh-paie", "nav.rhPaie"],
  ["/comptabilite", "nav.comptabilite"],
  ["/kanban", "nav.kanban"],
  ["/circuits", "nav.circuits"],
  ["/notifications", "nav.notifications"],
] as const;

export function Shell() {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const user = useAuth((s) => s.user);
  const clear = useAuth((s) => s.clear);

  const toggleTheme = () => {
    const root = document.documentElement;
    const next = root.getAttribute("data-theme") === "dark" ? "light" : "dark";
    root.setAttribute("data-theme", next);
    localStorage.setItem("etls.theme", next);
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
            {NAV_KEYS.map(([to, key]) => (
              <NavLink key={to} to={to} end={to === "/"} className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")}>
                {t(key)}
              </NavLink>
            ))}
          </nav>
        </aside>

        <main className="main">
          <div className="topbar">
            <div className="actions">
              <button className="icon-btn" title={t("common.theme")} onClick={toggleTheme} aria-label={t("common.theme")}>
                ◐
              </button>
              <button className="icon-btn" title={t("common.language")} onClick={toggleLang} aria-label={t("common.language")}>
                {i18n.language === "fr" ? "EN" : "FR"}
              </button>
            </div>
            <div className="user-chip">
              <span>{displayName}</span>
              <button className="btn ghost" onClick={logout}>
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