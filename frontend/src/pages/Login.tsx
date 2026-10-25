import { useState } from "react";
import type { FormEvent } from "react";

import {
  ArrowRight,
  BadgeCheck,
  Calculator,
  CircleAlert,
  Clock,
  Eye,
  EyeOff,
  Factory,
  Landmark,
  LayoutGrid,
  LoaderCircle,
  Lock,
  Mail,
  Moon,
  ShieldCheck,
  Sun,
  Truck,
  Users,
  WifiOff,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { motion } from "motion/react";
import type { Variants } from "motion/react";
import { useTranslation } from "react-i18next";
import { Link, useLocation, useNavigate } from "react-router-dom";

import { login, mfaEnrolement, mfaVerification, type MfaChallenge } from "../api/client";
import { MotionProvider } from "../components/Pilot";
import { landingForRole } from "../lib/landing";
import { useThemeMode } from "../lib/useThemeMode";
import { useAuth } from "../store/auth";
import { motionTokens } from "../theme/tokens";

type DemoAccount = { email: string; roleKey: string; icon: LucideIcon };
type Proof = { titleKey: string; textKey: string; icon: LucideIcon };

/** Mot de passe commun aux 6 comptes de démonstration (cf. `seed_all_demo`). */
const DEMO_PASSWORD = "Etls#Demo2026";

/** Encadré des comptes de démonstration : masqué au build par `VITE_DEMO_COMPTES=false` (instance remise à un client,
 *  dont les mots de passe ont été changés). Affiché par défaut (développement, e2e). */
const SHOW_DEMO_ACCOUNTS = import.meta.env.VITE_DEMO_COMPTES !== "false";

/** Trois preuves de valeur sobres (remplacent l'ancienne grille de 12 tuiles). */
const PROOFS: Proof[] = [
  { titleKey: "login.proofs.modulesTitle", textKey: "login.proofs.modulesText", icon: LayoutGrid },
  { titleKey: "login.proofs.localTitle", textKey: "login.proofs.localText", icon: Landmark },
  { titleKey: "login.proofs.offlineTitle", textKey: "login.proofs.offlineText", icon: WifiOff },
];

const DEMO_ACCOUNTS: DemoAccount[] = [
  { email: "admin@etls.local", roleKey: "login.demo.admin", icon: ShieldCheck },
  { email: "finance@etls.local", roleKey: "login.demo.finance", icon: Calculator },
  { email: "logistique@etls.local", roleKey: "login.demo.logistique", icon: Truck },
  { email: "rh@etls.local", roleKey: "login.demo.rh", icon: Users },
  { email: "atelier@etls.local", roleKey: "login.demo.atelier", icon: Factory },
  { email: "qaqc@etls.local", roleKey: "login.demo.qaqc", icon: BadgeCheck },
];

/* Entrée sobre : le contenu du panneau monte en cascade, la carte suit. */
const rise: Variants = {
  hidden: { opacity: 0, y: motionTokens.distance.md },
  show: { opacity: 1, y: 0, transition: { duration: motionTokens.duration.slow, ease: motionTokens.ease.out } },
};
const cascade: Variants = {
  hidden: {},
  show: { transition: { staggerChildren: motionTokens.stagger.base, delayChildren: 0.12 } },
};

export function LoginPage() {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const location = useLocation();
  const setSession = useAuth((s) => s.setSession);
  const sessionExpiree = useAuth((s) => s.expiree);
  const isDark = useThemeMode() === "dark";

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [revealed, setRevealed] = useState(false);
  const [mfa, setMfa] = useState<MfaChallenge | null>(null);
  const [secret, setSecret] = useState<string | null>(null);
  const [code, setCode] = useState("");

  const from = (location.state as { from?: { pathname?: string } } | null)?.from?.pathname;

  const toggleTheme = () => {
    const next = isDark ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    localStorage.setItem("etls.theme", next);
  };

  const toggleLang = () => {
    const next = i18n.language === "fr" ? "en" : "fr";
    void i18n.changeLanguage(next);
    localStorage.setItem("etls.lang", next);
  };

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
    <MotionProvider>
      <div className="login">
        {/* ══════ Panneau visuel : photo industrielle + accroche + 3 preuves ══════ */}
        <aside className="login-panel">
          <motion.div
            className="login-photo"
            aria-hidden
            initial={{ scale: 1.08, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            transition={{ duration: 1.6, ease: motionTokens.ease.out }}
          />
          <div className="login-veil" aria-hidden />
          <div className="login-grain" aria-hidden />

          <motion.div className="login-panel-inner" variants={cascade} initial="hidden" animate="show">
            <motion.p className="login-eyebrow" variants={rise}>
              {t("login.eyebrow")}
            </motion.p>

            <div className="login-hero">
              <motion.h2 className="login-hero-title" variants={rise}>
                {t("login.heroTitle")}
              </motion.h2>
              <motion.p className="login-hero-sub" variants={rise}>
                {t("login.heroSub")}
              </motion.p>
            </div>

            <motion.ul className="login-proofs" aria-label={t("login.proofsLabel")} variants={rise}>
              {PROOFS.map((p) => (
                <li key={p.titleKey} className="login-proof">
                  <p.icon size={18} strokeWidth={1.75} aria-hidden />
                  <b>{t(p.titleKey)}</b>
                  <span>{t(p.textKey)}</span>
                </li>
              ))}
            </motion.ul>
          </motion.div>
        </aside>

        {/* ══════ Colonne d'authentification ══════ */}
        <main className="login-stage">
          <div className="login-tools">
            <button type="button" className="login-tool" onClick={toggleLang} aria-label={t("login.switchLang")} title={t("login.switchLang")}>
              <span className="login-tool-code">{t("login.langCode")}</span>
            </button>
            <button
              type="button"
              className="login-tool"
              onClick={toggleTheme}
              aria-label={isDark ? t("login.themeLight") : t("login.themeDark")}
              title={isDark ? t("login.themeLight") : t("login.themeDark")}
            >
              {isDark ? <Sun size={16} aria-hidden /> : <Moon size={16} aria-hidden />}
            </button>
          </div>

          <motion.div
            className="login-auth"
            initial={{ opacity: 0, y: motionTokens.distance.md }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: motionTokens.duration.slow, ease: motionTokens.ease.out, delay: 0.08 }}
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

            <h1 className="login-auth-title">{mfa ? t("login.mfaTitle") : t("login.title")}</h1>
            <p className="login-auth-sub">{mfa ? (secret ? t("login.mfaEnrolIntro") : t("login.mfaIntro")) : t("login.formSubtitle")}</p>

            {error && (
              <p className="login-alert" role="alert">
                <CircleAlert size={16} aria-hidden />
                <span>{error}</span>
              </p>
            )}
            {!error && sessionExpiree && (
              <p className="login-alert is-info" role="status">
                <Clock size={16} aria-hidden />
                <span>{t("login.sessionExpiree")}</span>
              </p>
            )}

            {mfa ? (
              <form className="login-fields" onSubmit={submitMfa} aria-label={t("login.mfaTitle")}>
                {secret && (
                  <code className="login-mfa-secret" aria-label={t("login.mfaSecret")}>
                    {secret.match(/.{1,4}/g)?.join(" ")}
                  </code>
                )}
                <div className="login-field">
                  <label htmlFor="mfa-code">{t("login.mfaCode")}</label>
                  <div className="login-input">
                    <Lock size={16} aria-hidden />
                    <input
                      id="mfa-code"
                      className="login-otp"
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
                  {busy && <LoaderCircle size={16} className="login-spin" aria-hidden />}
                  {busy ? t("common.loading") : t("login.mfaSubmit")}
                </button>
                <button
                  type="button"
                  className="login-back"
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
              <form className="login-fields" onSubmit={submit}>
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
                  <div className="login-label-row">
                    <label htmlFor="password">{t("login.password")}</label>
                    <Link className="login-forgot" to="/mot-de-passe-oublie">
                      {t("ecarts_tr.mdp.oublieLien")}
                    </Link>
                  </div>
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
                      {revealed ? <EyeOff size={16} aria-hidden /> : <Eye size={16} aria-hidden />}
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
                  {busy && <LoaderCircle size={16} className="login-spin" aria-hidden />}
                  {busy ? t("common.loading") : t("login.submit")}
                  {!busy && <ArrowRight size={16} className="login-submit-arrow" aria-hidden />}
                </motion.button>

                <p className="login-secure">
                  <ShieldCheck size={13} aria-hidden />
                  {t("login.secureNote")}
                </p>
              </form>
            )}

            {SHOW_DEMO_ACCOUNTS && !mfa && (
              <section className="login-demo" aria-labelledby="login-demo-title">
                <div className="login-demo-head">
                  <b id="login-demo-title">{t("login.demoTitle")}</b>
                  <span className="login-demo-pwd">
                    {t("login.demoPassword")} <code>{DEMO_PASSWORD}</code>
                  </span>
                </div>
                <div className="login-demo-grid">
                  {DEMO_ACCOUNTS.map((a) => (
                    <button
                      key={a.email}
                      type="button"
                      className="login-demo-role"
                      onClick={() => prefill(a)}
                      aria-label={`${t(a.roleKey)} - ${a.email}`}
                      title={`${a.email} — ${t("login.demoHint")}`}
                    >
                      <a.icon size={14} aria-hidden />
                      <span>{t(a.roleKey)}</span>
                    </button>
                  ))}
                </div>
              </section>
            )}
          </motion.div>

          <footer className="login-foot">{t("login.footer")}</footer>
        </main>
      </div>
    </MotionProvider>
  );
}
