import { useState } from "react";
import type { FormEvent } from "react";

import {
  BadgeCheck,
  Boxes,
  Calculator,
  Factory,
  GitBranch,
  LayoutGrid,
  Layers,
  LogIn,
  Scale,
  ShieldAlert,
  ShieldCheck,
  ShoppingCart,
  TrendingUp,
  Truck,
  Users,
  Wrench,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { motion } from "motion/react";
import { useTranslation } from "react-i18next";
import { useLocation, useNavigate } from "react-router-dom";

import { login } from "../api/client";
import { useAuth } from "../store/auth";
import { motionTokens } from "../theme/tokens";
import { BrandLogo } from "../components/BrandLogo";

type LoginModule = {
  code: string;
  labelKey: string;
  icon: LucideIcon;
};

const MODULES: LoginModule[] = [
  { code: "M01", labelKey: "sidebar.commercial", icon: GitBranch },
  { code: "M02", labelKey: "sidebar.commandes", icon: ShoppingCart },
  { code: "M03", labelKey: "sidebar.operations", icon: Factory },
  { code: "M04", labelKey: "sidebar.logistique", icon: Truck },
  { code: "M05", labelKey: "sidebar.stocks", icon: Boxes },
  { code: "M06", labelKey: "sidebar.qualite", icon: BadgeCheck },
  { code: "M07", labelKey: "sidebar.hse", icon: ShieldAlert },
  { code: "M08", labelKey: "sidebar.maintenance", icon: Wrench },
  { code: "M09", labelKey: "sidebar.rhPaie", icon: Users },
  { code: "M10", labelKey: "sidebar.comptabilite", icon: Calculator },
  { code: "M11", labelKey: "sidebar.controleGestion", icon: TrendingUp },
  { code: "M12", labelKey: "sidebar.juridique", icon: Scale },
];

const TRANSVERSE_KEYS = [
  "sidebar.bi",
  "sidebar.ged",
  "sidebar.workflows",
  "sidebar.registres",
  "sidebar.audit",
];

export function LoginPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const location = useLocation();
  const setSession = useAuth((s) => s.setSession);

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const from = (location.state as { from?: { pathname: string } } | null)?.from?.pathname ?? "/";

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const { user, tokens } = await login(email, password);
      setSession(tokens, user);
      navigate(from, { replace: true });
    } catch {
      setError(t("login.invalid"));
    } finally {
      setBusy(false);
    }
  };

  const enter = {
    initial: { opacity: 0, y: motionTokens.distance.md },
    animate: { opacity: 1, y: 0 },
    transition: { duration: motionTokens.duration.base, ease: motionTokens.ease.out },
  };

  return (
    <div className="login">
      <motion.aside className="login-panel" {...enter}>
        <BrandLogo size="lg" />

        <div className="login-hero">
          <h1>{t("login.welcome")}</h1>
          <p className="login-sub">{t("login.panelSub")}</p>
          <ul className="login-features">
            <li>
              <GitBranch size={18} />
              {t("login.featureWorkflow")}
            </li>
            <li>
              <LayoutGrid size={18} />
              {t("login.featureModules")}
            </li>
            <li>
              <ShieldCheck size={18} />
              {t("login.featureSecurity")}
            </li>
          </ul>
        </div>

        <div className="login-modules">
          <span className="login-modules-title">{t("login.modulesTitle")}</span>
          <div className="login-module-grid">
            {MODULES.map((m, i) => (
              <motion.div
                key={m.code}
                className="login-module"
                initial={{ opacity: 0, y: motionTokens.distance.sm }}
                animate={{ opacity: 1, y: 0 }}
                transition={{
                  delay: i * motionTokens.stagger.quick,
                  duration: motionTokens.duration.base,
                  ease: motionTokens.ease.out,
                }}
              >
                <m.icon size={15} />
                <span>
                  <b>{m.code}</b>
                  {t(m.labelKey)}
                </span>
              </motion.div>
            ))}
          </div>

          <div className="login-transverse">
            <Layers size={15} />
            <span>
              <b>{t("login.modulesSub")}</b>
              <em>{TRANSVERSE_KEYS.map((k) => t(k)).join(" · ")}</em>
            </span>
          </div>
        </div>

        <div className="login-foot">{t("login.footer")}</div>
      </motion.aside>

      <div className="login-form">
        <motion.div
          initial={{ opacity: 0, y: motionTokens.distance.md, scale: 0.98 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          transition={{
            duration: motionTokens.duration.base,
            ease: motionTokens.ease.out,
            delay: motionTokens.stagger.quick,
          }}
          className="card login-card"
        >
          <div className="login-brand">
            <BrandLogo size="lg" />
          </div>
          <h1>{t("login.title")}</h1>
          <form onSubmit={submit}>
            <div className="field">
              <label htmlFor="email">{t("login.email")}</label>
              <input
                id="email"
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                autoComplete="email"
              />
            </div>
            <div className="field">
              <label htmlFor="password">{t("login.password")}</label>
              <input
                id="password"
                type="password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
              />
            </div>
            {error && (
              <p className="badge err" style={{ width: "100%", justifyContent: "center" }}>
                {error}
              </p>
            )}
            <motion.button
              className="btn primary"
              style={{ width: "100%" }}
              type="submit"
              disabled={busy}
              whileTap={{ scale: 0.98 }}
            >
              <LogIn size={15} />
              {busy ? t("common.loading") : t("login.submit")}
            </motion.button>
          </form>
        </motion.div>
      </div>
    </div>
  );
}
