import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BadgeCheck, FileSignature, KeyRound, Plus } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../api/client";
import { Badge, EmptyState, ErrorState, KpiGridSkeleton, PageHeader, SectionCard } from "../components/ui";
import { formatDateTime } from "../lib/format";
import { describeError } from "../lib/offlineQueue";
import type { Paginated, SignatureCertificate, SignatureRequestItem } from "../types";

const TONE: Record<string, "ok" | "warn" | "err"> = { completed: "ok", pending: "warn", refused: "err" };

/** Second facteur offert au signataire (lot correctif) : code e-mail si la messagerie est active, sinon TOTP. */
interface ModeSignature {
  email_actif: boolean;
  mfa_active: boolean;
  methodes: ("email" | "totp")[];
  methode_defaut: "email" | "totp" | null;
  enrolement_requis: boolean;
  message: string;
}
const MODE_KEY = ["signatures", "mode"];
const useModeSignature = () =>
  useQuery({ queryKey: MODE_KEY, queryFn: () => api.get<ModeSignature>("/api/documents/signatures/mode/"), retry: 0 });

/** Enrôlement de la double authentification depuis l'écran Signatures (sans messagerie, seul second facteur). */
function EnrolementTotp() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [cle, setCle] = useState<{ secret: string; otpauth_uri: string; qr_svg?: string } | null>(null);
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const demarrer = useMutation({
    mutationFn: () => api.post<{ secret: string; otpauth_uri: string; qr_svg?: string }>("/api/documents/signatures/enrolement-totp/"),
    onSuccess: (r) => {
      setCle(r);
      setError(null);
    },
    onError: (e) => setError(describeError(e)),
  });
  const activer = useMutation({
    mutationFn: () => api.post("/api/documents/signatures/activation-totp/", { code }),
    onSuccess: () => {
      setError(null);
      void qc.invalidateQueries({ queryKey: MODE_KEY });
    },
    onError: (e) => setError(describeError(e)),
  });
  return (
    <SectionCard
      className="sig-enrol"
      title={t("ecarts_correctif.sig.enrolTitle")}
      subtitle={t("ecarts_correctif.sig.enrolIntro")}
      actions={
        !cle ? (
          <button className="btn" onClick={() => demarrer.mutate()} disabled={demarrer.isPending}>
            <KeyRound size={15} aria-hidden="true" /> {t("ecarts_correctif.sig.enrolStart")}
          </button>
        ) : null
      }
    >
      <div id="enrolement-totp" className="sig-enrol-body" data-testid="enrolement-totp">
        {!cle ? null : (
          <>
            {cle.qr_svg ? (
              <>
                <p className="muted">{t("ecarts_a1.signatures.scanner")}</p>
                <img className="totp-qr" src={cle.qr_svg} alt={t("ecarts_a1.signatures.qrAlt")} data-testid="totp-qr" />
              </>
            ) : null}
            <p>
              {t("ecarts_correctif.sig.enrolSecret")} : <code>{cle.secret}</code>
            </p>
            <p className="muted">
              <a href={cle.otpauth_uri}>{t("ecarts_correctif.sig.enrolLien")}</a>
            </p>
            <div className="sign-row">
              <input
                inputMode="numeric"
                maxLength={6}
                placeholder={t("ecarts_correctif.sig.codeTotp")}
                aria-label={t("ecarts_correctif.sig.codeTotp")}
                value={code}
                onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
              />
              <button className="btn" onClick={() => activer.mutate()} disabled={activer.isPending || code.length !== 6}>
                {t("ecarts_correctif.sig.enrolActiver")}
              </button>
            </div>
          </>
        )}
        {error && (
          <p className="action-error" role="alert">
            {error}
          </p>
        )}
      </div>
    </SectionCard>
  );
}

function SignPanel({ req }: { req: SignatureRequestItem }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const mode = useModeSignature().data;
  const [choix, setChoix] = useState<"email" | "totp" | null>(null);
  const methode = choix ?? mode?.methode_defaut ?? "email";
  const [otp, setOtp] = useState("");
  const [password, setPassword] = useState("");
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reason, setReason] = useState("");
  const done = () => void qc.invalidateQueries({ queryKey: ["signatures"] });

  const sendOtp = useMutation({
    mutationFn: () => api.post(`/api/documents/signatures/${req.id}/otp/`),
    onSuccess: () => {
      setSent(true);
      setError(null);
    },
    onError: (e) => setError(describeError(e)),
  });
  const sign = useMutation({
    mutationFn: () => api.post(`/api/documents/signatures/${req.id}/sign/`, { otp, password, methode }),
    onSuccess: () => {
      setError(null);
      setOtp("");
      setPassword("");
      done();
    },
    onError: (e) => setError(describeError(e)),
  });
  const refuse = useMutation({
    mutationFn: () => api.post(`/api/documents/signatures/${req.id}/refuse/`, { reason }),
    onSuccess: done,
    onError: (e) => setError(describeError(e)),
  });

  return (
    <div className="sign-panel">
      {mode?.enrolement_requis ? (
        <p className="action-error" role="alert">
          {mode.message || t("ecarts_correctif.sig.sansFacteur")} <a href="#enrolement-totp">{t("ecarts_correctif.sig.lienEnrol")}</a>
        </p>
      ) : (
        <p className="muted">{methode === "totp" ? t("ecarts_correctif.sig.explainTotp") : t("signatures.explain")}</p>
      )}
      {(mode?.methodes.length ?? 0) > 1 && (
        <div className="sign-row" role="radiogroup" aria-label={t("ecarts_correctif.sig.methode")}>
          {mode!.methodes.map((m) => (
            <label key={m}>
              <input type="radio" name={`methode-${req.id}`} checked={methode === m} onChange={() => setChoix(m)} />{" "}
              {t(`ecarts_correctif.sig.methodes.${m}`)}
            </label>
          ))}
        </div>
      )}
      <div className="sign-row">
        {methode === "email" && (
          <button className="btn ghost" onClick={() => sendOtp.mutate()} disabled={sendOtp.isPending}>
            {sent ? t("signatures.resend") : t("signatures.sendCode")}
          </button>
        )}
        <input
          inputMode="numeric"
          maxLength={6}
          placeholder={methode === "totp" ? t("ecarts_correctif.sig.codeTotp") : t("signatures.code")}
          aria-label={methode === "totp" ? t("ecarts_correctif.sig.codeTotp") : t("signatures.code")}
          value={otp}
          onChange={(e) => setOtp(e.target.value.replace(/\D/g, ""))}
        />
        <input
          type="password"
          autoComplete="current-password"
          placeholder={t("signatures.password")}
          aria-label={t("signatures.password")}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        <button className="btn" onClick={() => sign.mutate()} disabled={sign.isPending || otp.length !== 6 || !password}>
          {t("signatures.sign")}
        </button>
      </div>
      <div className="sign-row">
        <input placeholder={t("signatures.reason")} aria-label={t("signatures.reason")} value={reason} onChange={(e) => setReason(e.target.value)} />
        <button className="btn danger" onClick={() => refuse.mutate()} disabled={refuse.isPending || !reason.trim()}>
          {t("signatures.refuse")}
        </button>
      </div>
      {error && (
        <p className="action-error" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}

function Certificate({ id }: { id: string }) {
  const { t, i18n } = useTranslation();
  const cert = useQuery({
    queryKey: ["signature-cert", id],
    queryFn: () => api.get<SignatureCertificate>(`/api/documents/signatures/${id}/certificate/`),
  });
  if (!cert.data) return null;
  const c = cert.data;
  return (
    <div className="cert">
      <div className="cert-head">
        <BadgeCheck size={18} aria-hidden="true" />
        <strong>{t("signatures.certificate")}</strong>
        <Badge tone={c.valid ? "ok" : "err"}>{c.valid ? t("signatures.chainOk") : t("signatures.chainKo")}</Badge>
        <Badge tone={c.document_intact ? "ok" : "err"}>{c.document_intact ? t("signatures.docOk") : t("signatures.docKo")}</Badge>
      </div>
      <code className="cert-hash">SHA-256 {c.document_sha256}</code>
      <ol>
        {c.signatures.map((s) => (
          <li key={s.order}>
            {s.order}. {s.signer} — {formatDateTime(s.signed_at, i18n.language)} · {s.ip ?? "—"} ·{" "}
            {t(`ecarts_correctif.sig.methodes.${(s as { methode?: string }).methode ?? "email"}`)} ·{" "}
            <Badge tone={s.seal_valid ? "ok" : "err"}>{s.seal_valid ? t("signatures.sealOk") : t("signatures.sealKo")}</Badge>
          </li>
        ))}
      </ol>
      <p className="muted">{c.method}</p>
    </div>
  );
}

/** Déblocage d'un signataire bloqué après trop d'essais : émetteur ou administration (`peut_debloquer`). */
function Deblocage({ id }: { id: string }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const debloquer = useMutation({
    mutationFn: () => api.post<{ detail: string }>(`/api/documents/signatures/${id}/unlock/`),
    onSuccess: (r) => {
      setMsg({ ok: true, text: r.detail });
      void qc.invalidateQueries({ queryKey: ["signatures"] });
    },
    onError: (e) => setMsg({ ok: false, text: describeError(e) }),
  });
  return (
    <div className="sign-row">
      <span className="action-error">{t("ecarts_a1.signatures.bloque")}</span>
      <button className="btn ghost" onClick={() => debloquer.mutate()} disabled={debloquer.isPending}>
        {t("ecarts_a1.signatures.debloquer")}
      </button>
      {msg && (
        <span className={msg.ok ? "quick-form-ok" : "action-error"} role={msg.ok ? "status" : "alert"}>
          {msg.text}
        </span>
      )}
    </div>
  );
}

function RequestCard({ req }: { req: SignatureRequestItem }) {
  const { t, i18n } = useTranslation();
  const [showCert, setShowCert] = useState(false);
  const peutDebloquer = (req as SignatureRequestItem & { peut_debloquer?: boolean }).peut_debloquer;
  const titre = req.title || req.document_title;
  const meta: string[] = [];
  if (req.document_title && req.document_title !== titre) meta.push(req.document_title);
  meta.push(t("revueR1.sig.version", { n: req.version_number }));
  if (req.status === "completed" && req.completed_at) meta.push(t("revueR1.sig.signeeLe", { date: formatDateTime(req.completed_at, i18n.language) }));
  else if (req.status === "pending") meta.push(t("revueR1.sig.echeance", { date: formatDateTime(req.expires_at, i18n.language) }));
  if (req.signataires.length) meta.push(t("revueR1.sig.signataires", { count: req.signataires.length }));
  return (
    <li className={`sign-card sig-item${req.a_mon_tour ? " is-mine" : ""}`}>
      <div className="sig-main">
        <span className="sig-icon" aria-hidden="true">
          <FileSignature size={16} />
        </span>
        <div className="sig-text">
          <strong className="sig-title">{titre}</strong>
          <span className="sig-meta">{meta.join(" · ")}</span>
        </div>
        <div className="sig-side">
          <Badge tone={req.expired ? "err" : (TONE[req.status] ?? "warn")}>{req.expired ? t("signatures.expired") : t(`signatures.status.${req.status}`)}</Badge>
          {req.status === "completed" ? (
            <button type="button" className="btn ghost sm sig-cert-btn" aria-expanded={showCert} onClick={() => setShowCert((v) => !v)}>
              <BadgeCheck size={14} aria-hidden="true" /> {t("revueR1.sig.certificat")}
            </button>
          ) : null}
        </div>
      </div>
      {req.signataires.length > 0 && req.status !== "completed" ? (
        <ol className="sign-signers sig-signers">
          {req.signataires.map((s) => (
            <li key={s.id} className={s.status}>
              <span>
                {s.order}. {s.name}
              </span>
              <Badge tone={s.status === "signed" ? "ok" : s.status === "refused" ? "err" : "neutral"}>
                {s.status === "signed" && s.signed_at ? formatDateTime(s.signed_at, i18n.language) : t(`signatures.signer.${s.status}`)}
              </Badge>
            </li>
          ))}
        </ol>
      ) : null}
      {peutDebloquer && <Deblocage id={req.id} />}
      {req.a_mon_tour && <SignPanel req={req} />}
      {showCert && <Certificate id={req.id} />}
    </li>
  );
}

interface DocOption {
  id: string;
  title: string;
  current_version: { id: string } | null;
}
interface SignerOption {
  id: number;
  name: string;
  role: string;
}

function NewRequest({ onClose }: { onClose: () => void }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [docId, setDocId] = useState("");
  const [title, setTitle] = useState("");
  const [days, setDays] = useState(7);
  const [signers, setSigners] = useState<number[]>([]);
  const [msg, setMsg] = useState<string | null>(null);
  const docs = useQuery({
    queryKey: ["sig-docs"],
    queryFn: () => api.get<Paginated<DocOption>>("/api/documents/documents/").then((p) => p.results),
  });
  const people = useQuery({
    queryKey: ["sig-people"],
    queryFn: () => api.get<SignerOption[]>("/api/documents/signatures/signataires/"),
  });
  const doc = docs.data?.find((d) => d.id === docId);
  const send = useMutation({
    mutationFn: () =>
      api.post("/api/documents/signatures/", {
        version: doc?.current_version?.id,
        title,
        signers,
        expires_in_days: days,
      }),
    onSuccess: () => {
      setMsg(t("signatures.created"));
      setDocId("");
      setTitle("");
      setSigners([]);
      void qc.invalidateQueries({ queryKey: ["signatures"] });
    },
    onError: (e) => setMsg(describeError(e)),
  });
  const free = (people.data ?? []).filter((p) => !signers.includes(p.id));
  const nameOf = (id: number) => people.data?.find((p) => p.id === id)?.name ?? String(id);
  const noVersion = !!doc && !doc.current_version;
  return (
    <SectionCard
      title={t("signatures.new")}
      actions={
        <button type="button" className="btn ghost sm" onClick={onClose}>
          {t("actionBar.annuler")}
        </button>
      }
    >
      <div className="sig-form">
        <div className="field">
          <label htmlFor="sig-doc">{t("signatures.document")}</label>
          <select id="sig-doc" value={docId} onChange={(e) => setDocId(e.target.value)}>
            <option value="">{t("signatures.chooseDocument")}</option>
            {(docs.data ?? []).map((d) => (
              <option key={d.id} value={d.id}>
                {d.title}
              </option>
            ))}
          </select>
          {noVersion && <span className="hint">{t("signatures.noVersion")}</span>}
        </div>
        <div className="field">
          <label htmlFor="sig-title">{t("signatures.titleLabel")}</label>
          <input id="sig-title" value={title} onChange={(e) => setTitle(e.target.value)} />
        </div>
        <div className="field">
          <label htmlFor="sig-days">{t("signatures.days")}</label>
          <input id="sig-days" type="number" min={1} max={90} value={days} onChange={(e) => setDays(Number(e.target.value))} />
        </div>
        <div className="field sig-form-wide">
          <label htmlFor="sig-add">{t("signatures.signers")}</label>
          {signers.length ? (
            <ol className="sign-signers sig-signers">
              {signers.map((id, i) => (
                <li key={id}>
                  <span>
                    {i + 1}. {nameOf(id)}
                  </span>
                  <button type="button" className="btn ghost sm" onClick={() => setSigners(signers.filter((s) => s !== id))}>
                    {t("signatures.remove")}
                  </button>
                </li>
              ))}
            </ol>
          ) : null}
          <select id="sig-add" value="" onChange={(e) => e.target.value && setSigners([...signers, Number(e.target.value)])}>
            <option value="">{t("signatures.addSigner")}</option>
            {free.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        </div>
        <div className="sig-form-wide sig-form-foot">
          {msg && (
            <span className="muted" role="status">
              {msg}
            </span>
          )}
          <button className="btn primary" disabled={!doc?.current_version || !signers.length || send.isPending} onClick={() => send.mutate()}>
            {t("signatures.send")}
          </button>
        </div>
      </div>
    </SectionCard>
  );
}

export function SignaturesPage() {
  const { t } = useTranslation();
  const mode = useModeSignature().data;
  const [nouvelle, setNouvelle] = useState(false);
  const list = useQuery({
    queryKey: ["signatures"],
    queryFn: () => api.get<Paginated<SignatureRequestItem>>("/api/documents/signatures/").then((p) => p.results),
  });

  const header = (
    <PageHeader
      title={t("signatures.title")}
      subtitle={t("signatures.subtitle")}
      actions={
        <button type="button" className="btn primary" onClick={() => setNouvelle(true)} disabled={nouvelle}>
          <Plus size={16} aria-hidden="true" /> {t("signatures.new")}
        </button>
      }
    />
  );
  if (list.isLoading)
    return (
      <>
        {header}
        <KpiGridSkeleton count={2} />
      </>
    );
  if (list.isError)
    return (
      <>
        {header}
        <ErrorState message={t("common.error")} onRetry={() => void list.refetch()} retryLabel={t("common.retry")} />
      </>
    );

  const rows = list.data ?? [];
  const toSign = rows.filter((r) => r.a_mon_tour);
  const others = rows.filter((r) => !r.a_mon_tour);

  return (
    <div className="sig-page">
      {header}
      {nouvelle && <NewRequest onClose={() => setNouvelle(false)} />}
      {/* Application d'authentification toujours proposée tant qu'elle n'est pas activée (même avec la messagerie). */}
      {mode && !mode.mfa_active && <EnrolementTotp />}
      {rows.length === 0 && (
        <SectionCard>
          <EmptyState label={t("signatures.none")} hint={t("revueR1.sig.videAide")} icon={FileSignature} />
        </SectionCard>
      )}
      {toSign.length > 0 && (
        <SectionCard title={t("signatures.toSign")} subtitle={t("revueR1.sig.aSignerSub", { count: toSign.length })}>
          <ul className="sig-list">
            {toSign.map((r) => (
              <RequestCard key={r.id} req={r} />
            ))}
          </ul>
        </SectionCard>
      )}
      {others.length > 0 && (
        <SectionCard title={t("signatures.all")} subtitle={t("revueR1.sig.demandesSub", { count: others.length })}>
          <ul className="sig-list">
            {others.map((r) => (
              <RequestCard key={r.id} req={r} />
            ))}
          </ul>
        </SectionCard>
      )}
    </div>
  );
}
