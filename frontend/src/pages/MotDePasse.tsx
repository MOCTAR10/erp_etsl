import { useMutation } from "@tanstack/react-query";
import { KeyRound } from "lucide-react";
import { useState, type FormEvent, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import { api } from "../api/client";
import { PageHeader, SectionCard } from "../components/ui";
import { describeError } from "../lib/offlineQueue";
import { useAuth } from "../store/auth";
import type { Me } from "../types";

type MeMdp = Me & { doit_changer_mdp?: boolean };

function Champ({ id, label, value, onChange, autoComplete }: { id: string; label: string; value: string; onChange: (v: string) => void; autoComplete: string }) {
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <input id={id} type="password" required value={value} autoComplete={autoComplete} onChange={(e) => onChange(e.target.value)} />
    </div>
  );
}

function Message({ ok, children }: { ok: boolean; children: ReactNode }) {
  return (
    <p className={ok ? "quick-form-ok" : "action-error"} role={ok ? "status" : "alert"}>
      {children}
    </p>
  );
}

/** « Changer mon mot de passe » (menu utilisateur, Mon espace) ; imposé après une réinitialisation par l'admin. */
export function MonMotDePassePage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const user = useAuth((s) => s.user) as MeMdp | null;
  const setSession = useAuth((s) => s.setSession);
  const [ancien, setAncien] = useState("");
  const [nouveau, setNouveau] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);
  const envoi = useMutation({
    mutationFn: () => api.post<{ access: string; refresh: string; detail: string }>("/api/users/me/mot-de-passe/", { ancien, nouveau, confirmation }),
    onSuccess: (r) => {
      // La session courante reçoit de nouveaux jetons ; les autres sont révoquées par le serveur.
      if (user) setSession({ access: r.access, refresh: r.refresh }, { ...user, doit_changer_mdp: false } as Me);
      setAncien("");
      setNouveau("");
      setConfirmation("");
      setMessage({ ok: true, text: r.detail });
      if (user?.doit_changer_mdp) navigate("/", { replace: true });
    },
    onError: (e) => setMessage({ ok: false, text: describeError(e) }),
  });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    setMessage(null);
    if (nouveau !== confirmation) {
      setMessage({ ok: false, text: t("ecarts_tr.mdp.differents") });
      return;
    }
    envoi.mutate();
  };
  return (
    <>
      <PageHeader title={t("ecarts_tr.mdp.title")} subtitle={t("ecarts_tr.mdp.subtitle")} />
      {user?.doit_changer_mdp ? (
        <p className="action-error" role="note" data-testid="mdp-obligatoire">
          {t("ecarts_tr.mdp.obligatoire")}
        </p>
      ) : null}
      <SectionCard title={t("ecarts_tr.mdp.title")}>
        <form className="quick-form" onSubmit={submit} aria-label={t("ecarts_tr.mdp.title")}>
          <div className="quick-form-grid">
            <Champ id="mdp-ancien" label={t("ecarts_tr.mdp.ancien")} value={ancien} onChange={setAncien} autoComplete="current-password" />
            <Champ id="mdp-nouveau" label={t("ecarts_tr.mdp.nouveau")} value={nouveau} onChange={setNouveau} autoComplete="new-password" />
            <Champ id="mdp-confirmation" label={t("ecarts_tr.mdp.confirmation")} value={confirmation} onChange={setConfirmation} autoComplete="new-password" />
          </div>
          <p className="muted" style={{ fontSize: 13 }}>
            {t("ecarts_tr.mdp.regles")}
          </p>
          <div className="quick-form-actions">
            <button type="submit" className="btn primary" disabled={envoi.isPending}>
              <KeyRound size={15} aria-hidden="true" /> {envoi.isPending ? t("common.loading") : t("ecarts_tr.mdp.valider")}
            </button>
            {message && <Message ok={message.ok}>{message.text}</Message>}
          </div>
        </form>
      </SectionCard>
    </>
  );
}

function CartePublique({ titre, children }: { titre: string; children: ReactNode }) {
  return (
    <main className="main" id="main-content" style={{ maxWidth: 520, margin: "3rem auto", padding: "0 16px" }}>
      <div className="card">
        <h2 style={{ marginTop: 0 }}>{titre}</h2>
        {children}
        <p>
          <Link to="/login">{useTranslation().t("ecarts_tr.mdp.retourConnexion")}</Link>
        </p>
      </div>
    </main>
  );
}

/** « Mot de passe oublié » : envoi d'un lien à usage unique (réponse identique, que le compte existe ou non). */
export function MotDePasseOubliePage() {
  const { t } = useTranslation();
  const [email, setEmail] = useState("");
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);
  const envoi = useMutation({
    mutationFn: () => api.post<{ detail: string }>("/api/users/mot-de-passe/oubli/", { email }),
    onSuccess: (r) => setMessage({ ok: true, text: r.detail }),
    onError: (e) => setMessage({ ok: false, text: describeError(e) }),
  });
  return (
    <CartePublique titre={t("ecarts_tr.mdp.oublieTitre")}>
      <p className="muted">{t("ecarts_tr.mdp.oublieAide")}</p>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          setMessage(null);
          envoi.mutate();
        }}
      >
        <div className="field">
          <label htmlFor="oubli-email">{t("ecarts_tr.mdp.email")}</label>
          <input id="oubli-email" type="email" required value={email} autoComplete="email" onChange={(e) => setEmail(e.target.value)} />
        </div>
        <div className="quick-form-actions">
          <button type="submit" className="btn primary" disabled={envoi.isPending}>
            {envoi.isPending ? t("common.loading") : t("ecarts_tr.mdp.envoyerLien")}
          </button>
          {message && <Message ok={message.ok}>{message.text}</Message>}
        </div>
      </form>
    </CartePublique>
  );
}

/** Lien du courriel : nouveau mot de passe (jeton à usage unique, expirant). */
export function ReinitialiserMotDePassePage() {
  const { t } = useTranslation();
  const [params] = useSearchParams();
  const jeton = params.get("jeton") ?? "";
  const [nouveau, setNouveau] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);
  const envoi = useMutation({
    mutationFn: () => api.post<{ detail: string }>("/api/users/mot-de-passe/reinitialiser/", { jeton, nouveau, confirmation }),
    onSuccess: (r) => setMessage({ ok: true, text: r.detail }),
    onError: (e) => setMessage({ ok: false, text: describeError(e) }),
  });
  return (
    <CartePublique titre={t("ecarts_tr.mdp.reinitTitre")}>
      {!jeton ? (
        <Message ok={false}>{t("ecarts_tr.mdp.lienInvalide")}</Message>
      ) : (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            setMessage(null);
            if (nouveau !== confirmation) {
              setMessage({ ok: false, text: t("ecarts_tr.mdp.differents") });
              return;
            }
            envoi.mutate();
          }}
        >
          <Champ id="reinit-nouveau" label={t("ecarts_tr.mdp.nouveau")} value={nouveau} onChange={setNouveau} autoComplete="new-password" />
          <Champ id="reinit-confirmation" label={t("ecarts_tr.mdp.confirmation")} value={confirmation} onChange={setConfirmation} autoComplete="new-password" />
          <p className="muted" style={{ fontSize: 13 }}>
            {t("ecarts_tr.mdp.regles")}
          </p>
          <div className="quick-form-actions">
            <button type="submit" className="btn primary" disabled={envoi.isPending || message?.ok === true}>
              {envoi.isPending ? t("common.loading") : t("ecarts_tr.mdp.valider")}
            </button>
            {message && <Message ok={message.ok}>{message.text}</Message>}
          </div>
        </form>
      )}
    </CartePublique>
  );
}
