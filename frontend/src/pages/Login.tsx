import { useState } from "react";
import type { FormEvent } from "react";

import {
  ArrowLeftRight,
  BadgeCheck,
  Boxes,
  Calculator,
  ChartNoAxesColumn,
  CircleAlert,
  Eye,
  EyeOff,
  Factory,
  FolderTree,
  GitBranch,
  Layers,
  LoaderCircle,
  Lock,
  LogIn,
  Mail,
  Scale,
  ScrollText,
  ShieldAlert,
  ShieldCheck,
  ShoppingCart,
  TrendingUp,
  Truck,
  Users,
  Workflow,
  Wrench,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { motion } from "motion/react";
import { useTranslation } from "react-i18next";
import { useLocation, useNavigate } from "react-router-dom";

import { login, mfaEnrolement, mfaVerification, type MfaChallenge } from "../api/client";
import { landingForRole } from "../lib/landing";
import { useAuth } from "../store/auth";
import { motionTokens } from "../theme/tokens";

type LoginModule = { code: string; labelKey: string; icon: LucideIcon };
type LoginLayer = { labelKey: string; icon: LucideIcon };
type DemoAccount = { email: string; roleKey: string; icon: LucideIcon };

/** Mot de passe commun aux 6 comptes de démonstration (cf. `seed_all_demo`). */
const DEMO_PASSWORD = "Etls#Demo2026";

const MODULES: LoginModule[] = [
  { code: "M01", labelKey: "login.modules.m01", icon: GitBranch },
  { code: "M02", labelKey: "login.modules.m02", icon: ShoppingCart },
  { code: "M03", labelKey: "login.modules.m03", icon: Factory },
  { code: "M04", labelKey: "login.modules.m04", icon: Truck },
  { code: "M05", labelKey: "login.modules.m05", icon: Boxes },
  { code: "M06", labelKey: "login.modules.m06", icon: BadgeCheck },
  { code: "M07", labelKey: "login.modules.m07", icon: ShieldAlert },
  { code: "M08", labelKey: "login.modules.m08", icon: Wrench },
  { code: "M09", labelKey: "login.modules.m09", icon: Users },
  { code: "M10", labelKey: "login.modules.m10", icon: Calculator },
  { code: "M11", labelKey: "login.modules.m11", icon: TrendingUp },
  { code: "M12", labelKey: "login.modules.m12", icon: Scale },
];

const LAYERS: LoginLayer[] = [
  { labelKey: "login.modules.ged", icon: FolderTree },
  { labelKey: "login.modules.workflows", icon: Workflow },
  { labelKey: "login.modules.registres", icon: ScrollText },
  { labelKey: "login.modules.bi", icon: ChartNoAxesColumn },
  { labelKey: "login.modules.audit", icon: ShieldCheck },
  { labelKey: "login.modules.integrations", icon: ArrowLeftRight },
];

const DEMO_ACCOUNTS: DemoAccount[] = [
  { email: "admin@etls.local", roleKey: "login.demo.admin", icon: ShieldCheck },
  { email: "finance@etls.local", roleKey: "login.demo.finance", icon: Calculator },
  { email: "logistique@etls.local", roleKey: "login.demo.logistique", icon: Truck },
  { email: "rh@etls.local", roleKey: "login.demo.rh", icon: Users },
  { email: "atelier@etls.local", roleKey: "login.demo.atelier", icon: Factory },
  { email: "qaqc@etls.local", roleKey: "login.demo.qaqc", icon: BadgeCheck },
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
  const [revealed, setRevealed] = useState(false);
  const [mfa, setMfa] = useState<MfaChallenge | null>(null);
  const [secret, setSecret] = useState<string | null>(null);
  const [code, setCode] = useState("");

  const from = (location.state as { from?: { pathname?: string } } | null)?.from?.pathname;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const result = await login(email, password);
      if (result.mfa) {
        // Rôle sensible : second facteur exigé avant toute session (lot 15b).
        setMfa(result.mfa);
        if (result.mfa.mfa_enrolement) setSecret((await mfaEnrolement(result.mfa.mfa_jeton)).secret);
        return;
      }
      setSession(result.tokens, result.user);
      // Une URL profonde demandée avant connexion reste prioritaire ; sinon on
      // arrive sur la page qui porte le métier du rôle (pas toujours le dashboard).
      navigate(from || landingForRole(result.user.role), { replace: true });
    } catch {
      setError(t("login.invalid"));
    } finally {
      setBusy(false);
    }
  };

  const submitMfa = async (e: FormEvent) => {
    e.preventDefault();
    if (!mfa) return;
    setBusy(true);
    setError(null);
    try {
      const { user, tokens } = await mfaVerification(mfa.mfa_jeton, code);
      setSession(tokens, user);
      navigate(from || landingForRole(user.role), { replace: true });
    } catch {
      setError(t("login.mfaInvalid"));
      setCode("");
    } finally {
      setBusy(false);
    }
  };

  /** Remplit les identifiants d'un profil de démonstration (pas de soumission). */
  const prefill = (account: DemoAccount) => {
    setEmail(account.email);
    setPassword(DEMO_PASSWORD);
    setError(null);
    setRevealed(false);
  };

  return (
    <div className="login">
      <motion.aside
        className="login-panel"
        initial={{ opacity: 0, y: motionTokens.distance.md }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: motionTokens.duration.base, ease: motionTokens.ease.out }}
      >
        <header className="login-hero">
          <h1>{t("login.welcome")}</h1>
          <p>{t("login.heroSub")}</p>
        </header>

        <section className="login-layers">
          <span className="login-modules-title">
            <Layers size={13} aria-hidden />
            {t("login.transverseTitle")}
          </span>
          <div className="login-layers-grid">
            {LAYERS.map((l) => (
              <div key={l.labelKey} className="login-layer">
                <l.icon size={13} aria-hidden />
                <span>{t(l.labelKey)}</span>
              </div>
            ))}
          </div>
        </section>

        <section className="login-modules">
          <span className="login-modules-title">{t("login.modulesTitle")}</span>
          <div className="login-modules-grid">
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
                <span className="login-module-icon">
                  <m.icon size={15} aria-hidden />
                </span>
                <b>{m.code}</b>
                <span className="login-module-name">{t(m.labelKey)}</span>
              </motion.div>
            ))}
          </div>
        </section>

        <div className="login-foot">{t("login.footer")}</div>
      </motion.aside>

      <main className="login-form">
        <motion.div
          className="login-auth"
          initial={{ opacity: 0, y: motionTokens.distance.md, scale: 0.985 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          transition={{
            duration: motionTokens.duration.base,
            ease: motionTokens.ease.out,
            delay: motionTokens.stagger.quick,
          }}
        >
          <header className="login-auth-head">
            <span className="login-auth-mark">
              <img src={`${import.meta.env.BASE_URL}etsl-logo.jpg`} alt={t("app.logoAlt")} />
            </span>
            <span className="login-auth-id">
              <b>{t("app.brand")}</b>
              <em>{t("login.brandTagline")}</em>
            </span>
          </header>

          <h1 className="login-auth-title">{t("login.title")}</h1>
          <p className="login-auth-sub">{t("login.formSubtitle")}</p>

          {error && (
            <p className="login-alert" role="alert">
              <CircleAlert size={15} aria-hidden />
              <span>{error}</span>
            </p>
          )}

          {mfa ? (
            <form onSubmit={submitMfa} aria-label={t("login.mfaTitle")}>
              <h3 className="login-mfa-title">{t("login.mfaTitle")}</h3>
              {secret ? (
                <div className="login-mfa-enrol">
                  <p className="muted">{t("login.mfaEnrolIntro")}</p>
                  <code className="login-mfa-secret" aria-label={t("login.mfaSecret")}>
                    {secret.match(/.{1,4}/g)?.join(" ")}
                  </code>
                </div>
              ) : (
                <p className="muted">{t("login.mfaIntro")}</p>
              )}
              <div className="login-field">
                <label htmlFor="mfa-code">{t("login.mfaCode")}</label>
                <div className="login-input">
                  <Lock size={16} aria-hidden />
                  <input
                    id="mfa-code"
                    inputMode="numeric"
                    autoComplete="one-time-code"
                    pattern="[0-9]{6}"
                    maxLength={6}
                    required
                    value={code}
                    onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
                  />
                </div>
              </div>
              <button type="submit" className="login-submit" disabled={busy || code.length !== 6}>
                {busy ? t("common.loading") : t("login.mfaSubmit")}
              </button>
              <button
                type="button"
                className="btn ghost"
                onClick={() => {
                  setMfa(null);
                  setSecret(null);
                  setCode("");
                  setError(null);
                }}
              >
                {t("login.mfaBack")}
              </button>
            </form>
          ) : (
          <form onSubmit={submit}>
            <div className="login-field">
              <label htmlFor="email">{t("login.email")}</label>
              <div className="login-input">
                <Mail size={16} aria-hidden />
                <input
                  id="email"
                  type="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  autoComplete="email"
                  placeholder={t("login.emailPlaceholder")}
                  spellCheck={false}
                />
              </div>
            </div>

            <div className="login-field">
              <label htmlFor="password">{t("login.password")}</label>
              <div className="login-input">
                <Lock size={16} aria-hidden />
                <input
                  id="password"
                  type={revealed ? "text" : "password"}
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  autoComplete="current-password"
                />
                <button
                  type="button"
                  className="login-reveal"
                  onClick={() => setRevealed((v) => !v)}
                  aria-label={revealed ? t("login.hidePassword") : t("login.showPassword")}
                  aria-pressed={revealed}
                >
                  {revealed ? <EyeOff size={15} aria-hidden /> : <Eye size={15} aria-hidden />}
                </button>
              </div>
            </div>

            <motion.button
              className="login-submit"
              type="submit"
              disabled={busy}
              whileTap={{ scale: 0.99 }}
              transition={{ duration: motionTokens.duration.fast }}
            >
              {busy ? (
                <LoaderCircle size={16} className="login-spin" aria-hidden />
              ) : (
                <LogIn size={16} aria-hidden />
              )}
              {busy ? t("common.loading") : t("login.submit")}
            </motion.button>
          </form>
          )}

          <section className="login-demo">
            <div className="login-demo-head">
              <b>{t("login.demoTitle")}</b>
              <span>{t("login.demoHint")}</span>
            </div>
            <div className="login-demo-grid">
              {DEMO_ACCOUNTS.map((a) => (
                <div key={a.email} className="login-demo-chip">
                  <a.icon size={13} aria-hidden />
                  <button
                    type="button"
                    className="login-demo-role"
                    onClick={() => prefill(a)}
                    aria-label={`${t(a.roleKey)} - ${a.email}`}
                  >
                    {t(a.roleKey)}
                  </button>
                  <span className="login-demo-mail">{a.email}</span>
                </div>
              ))}
            </div>
            <p className="login-demo-pwd">
              {t("login.demoPassword")} <code>{DEMO_PASSWORD}</code>
            </p>
          </section>
        </motion.div>
      </main>
    </div>
  );
}
