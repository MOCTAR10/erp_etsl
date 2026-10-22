import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BadgeCheck, FileSignature, Plus } from "lucide-react";
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
  const [cle, setCle] = useState<{ secret: string; otpauth_uri: string } | null>(null);
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const demarrer = useMutation({
    mutationFn: () => api.post<{ secret: string; otpauth_uri: string }>("/api/documents/signatures/enrolement-totp/"),
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
    <SectionCard title={t("ecarts_correctif.sig.enrolTitle")}>
      <div id="enrolement-totp" className="sign-panel" data-testid="enrolement-totp">
        <p className="muted">{t("ecarts_correctif.sig.enrolIntro")}</p>
        {!cle ? (
          <div className="sign-row">
            <button className="btn" onClick={() => demarrer.mutate()} disabled={demarrer.isPending}>
              {t("ecarts_correctif.sig.enrolStart")}
            </button>
          </div>
        ) : (
          <>
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

function RequestCard({ req }: { req: SignatureRequestItem }) {
  const { t, i18n } = useTranslation();
  const [showCert, setShowCert] = useState(false);
  return (
    <article className="card sign-card">
      <header className="itp-head">
        <strong>
          <FileSignature size={16} aria-hidden="true" /> {req.title || req.document_title}
        </strong>
        <Badge tone={req.expired ? "err" : (TONE[req.status] ?? "warn")}>{req.expired ? t("signatures.expired") : t(`signatures.status.${req.status}`)}</Badge>
      </header>
      <span className="muted">
        {req.document_title} · v{req.version_number} · {t("signatures.until")} {formatDateTime(req.expires_at, i18n.language)}
      </span>
      <ol className="sign-signers">
        {req.signataires.map((s) => (
          <li key={s.id} className={s.status}>
            <span>
              {s.order}. {s.name}
            </span>
            <Badge tone={s.status === "signed" ? "ok" : s.status === "refused" ? "err" : "warn"}>
              {s.status === "signed" && s.signed_at ? formatDateTime(s.signed_at, i18n.language) : t(`signatures.signer.${s.status}`)}
            </Badge>
          </li>
        ))}
      </ol>
      {req.a_mon_tour && <SignPanel req={req} />}
      {req.status === "completed" && (
        <>
          <button className="btn ghost" onClick={() => setShowCert((v) => !v)}>
            {t("signatures.certificate")}
          </button>
          {showCert && <Certificate id={req.id} />}
        </>
      )}
    </article>
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

function NewRequest() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [docId, setDocId] = useState("");
  const [title, setTitle] = useState("");
  const [days, setDays] = useState(7);
  const [signers, setSigners] = useState<number[]>([]);
  const [msg, setMsg] = useState<string | null>(null);
  const docs = useQuery({
    queryKey: ["sig-docs"],
    enabled: open,
    queryFn: () => api.get<Paginated<DocOption>>("/api/documents/documents/").then((p) => p.results),
  });
  const people = useQuery({
    queryKey: ["sig-people"],
    enabled: open,
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
  if (!open)
    return (
      <button className="btn" onClick={() => setOpen(true)}>
        <Plus size={16} aria-hidden="true" /> {t("signatures.new")}
      </button>
    );
  const free = (people.data ?? []).filter((p) => !signers.includes(p.id));
  const nameOf = (id: number) => people.data?.find((p) => p.id === id)?.name ?? String(id);
  const noVersion = !!doc && !doc.current_version;
  return (
    <SectionCard title={t("signatures.new")}>
      <div className="sign-new">
        <select aria-label={t("signatures.document")} value={docId} onChange={(e) => setDocId(e.target.value)}>
          <option value="">{t("signatures.chooseDocument")}</option>
          {(docs.data ?? []).map((d) => (
            <option key={d.id} value={d.id}>
              {d.title}
            </option>
          ))}
        </select>
        {noVersion && <p className="muted">{t("signatures.noVersion")}</p>}
        <input placeholder={t("signatures.titleLabel")} aria-label={t("signatures.titleLabel")} value={title} onChange={(e) => setTitle(e.target.value)} />
        <label className="muted">
          {t("signatures.days")}{" "}
          <input type="number" min={1} max={90} value={days} onChange={(e) => setDays(Number(e.target.value))} />
        </label>
        <strong>{t("signatures.signers")}</strong>
        <ol className="sign-signers">
          {signers.map((id) => (
            <li key={id}>
              <span>{nameOf(id)}</span>
              <button className="btn ghost" onClick={() => setSigners(signers.filter((s) => s !== id))}>
                {t("signatures.remove")}
              </button>
            </li>
          ))}
        </ol>
        <select
          aria-label={t("signatures.addSigner")}
          value=""
          onChange={(e) => e.target.value && setSigners([...signers, Number(e.target.value)])}
        >
          <option value="">{t("signatures.addSigner")}</option>
          {free.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </select>
        <button className="btn" disabled={!doc?.current_version || !signers.length || send.isPending} onClick={() => send.mutate()}>
          {t("signatures.send")}
        </button>
        {msg && (
          <p className="muted" role="status">
            {msg}
          </p>
        )}
      </div>
    </SectionCard>
  );
}

export function SignaturesPage() {
  const { t } = useTranslation();
  const mode = useModeSignature().data;
  const list = useQuery({
    queryKey: ["signatures"],
    queryFn: () => api.get<Paginated<SignatureRequestItem>>("/api/documents/signatures/").then((p) => p.results),
  });

  if (list.isLoading) return <KpiGridSkeleton count={2} />;
  if (list.isError) return <ErrorState message={t("common.error")} onRetry={() => void list.refetch()} retryLabel={t("common.retry")} />;

  const rows = list.data ?? [];
  const toSign = rows.filter((r) => r.a_mon_tour);
  const others = rows.filter((r) => !r.a_mon_tour);

  return (
    <>
      <PageHeader title={t("signatures.title")} subtitle={t("signatures.subtitle")} />
      <NewRequest />
      {mode?.enrolement_requis && <EnrolementTotp />}
      {rows.length === 0 && <EmptyState label={t("signatures.none")} icon={FileSignature} />}
      {toSign.length > 0 && (
        <SectionCard title={`${t("signatures.toSign")} · ${toSign.length}`}>
          <div className="itp-list">
            {toSign.map((r) => (
              <RequestCard key={r.id} req={r} />
            ))}
          </div>
        </SectionCard>
      )}
      {others.length > 0 && (
        <SectionCard title={t("signatures.all")}>
          <div className="itp-list">
            {others.map((r) => (
              <RequestCard key={r.id} req={r} />
            ))}
          </div>
        </SectionCard>
      )}
    </>
  );
}
