import { useState } from "react";
import type { FormEvent } from "react";

import { LogIn } from "lucide-react";
import { motion } from "motion/react";
import { useTranslation } from "react-i18next";
import { useLocation, useNavigate } from "react-router-dom";

import { login } from "../api/client";
import { useAuth } from "../store/auth";
import { motionTokens } from "../theme/tokens";

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

  return (
    <div className="login">
      <motion.div
        initial={{ opacity: 0, y: motionTokens.distance.md, scale: 0.98 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: motionTokens.duration.base, ease: motionTokens.ease.out }}
        className="card login-card"
      >
        <div className="sidebar-brand" style={{ padding: "0 0 1rem" }}>
          <span className="brand-mark">ET</span>
          <div style={{ lineHeight: 1.2 }}>
            <div>{t("app.brand")}</div>
            <div className="muted" style={{ fontWeight: 400, fontSize: 12 }}>
              {t("app.tagline")}
            </div>
          </div>
        </div>
        <h1 style={{ fontSize: 18 }}>{t("login.title")}</h1>
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
  );
}