import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BadgeCheck, FileSignature } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../api/client";
import { Badge, EmptyState, ErrorState, KpiGridSkeleton, PageHeader, SectionCard } from "../components/ui";
import { formatDateTime } from "../lib/format";
import { describeError } from "../lib/offlineQueue";
import type { Paginated, SignatureCertificate, SignatureRequestItem } from "../types";

const TONE: Record<string, "ok" | "warn" | "err"> = { completed: "ok", pending: "warn", refused: "err" };

function SignPanel({ req }: { req: SignatureRequestItem }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
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
    mutationFn: () => api.post(`/api/documents/signatures/${req.id}/sign/`, { otp, password }),
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
      <p className="muted">{t("signatures.explain")}</p>
      <div className="sign-row">
        <button className="btn ghost" onClick={() => sendOtp.mutate()} disabled={sendOtp.isPending}>
          {sent ? t("signatures.resend") : t("signatures.sendCode")}
        </button>
        <input
          inputMode="numeric"
          maxLength={6}
          placeholder={t("signatures.code")}
          aria-label={t("signatures.code")}
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

export function SignaturesPage() {
  const { t } = useTranslation();
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
