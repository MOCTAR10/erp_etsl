import { useState } from "react";
import type { FormEvent } from "react";

import { GitBranch, LayoutGrid, LogIn, ShieldCheck } from "lucide-react";
import { motion } from "motion/react";
import { useTranslation } from "react-i18next";
import { useLocation, useNavigate } from "react-router-dom";

import { login } from "../api/client";
import { useAuth } from "../store/auth";
import { motionTokens } from "../theme/tokens";
import { BrandLogo } from "../components/BrandLogo";

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
        <span className="brand-chip">
          <img src="/etsl-logo.jpg" alt={t("app.logoAlt")} />
        </span>

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