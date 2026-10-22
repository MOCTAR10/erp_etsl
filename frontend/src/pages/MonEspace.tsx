import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarDays, FileText } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { ApiError, api } from "../api/client";
import { Badge, EmptyState, ErrorState, Kpi, KpiGridSkeleton, PageHeader, SectionCard } from "../components/ui";
import { formatDate, formatDateTime, formatMoney } from "../lib/format";
import type { MonBulletin } from "../types";

const TYPES = ["annuel", "rotation", "maladie", "maternite", "sans_solde", "exceptionnel"] as const;

/** Durée inclusive en jours entre deux dates ISO (préremplit « Jours »). */
function joursEntre(debut: string, fin: string): number {
  if (!debut || !fin) return 0;
  const d = (new Date(fin).getTime() - new Date(debut).getTime()) / 86_400_000 + 1;
  return Number.isFinite(d) && d > 0 ? Math.round(d) : 0;
}

function errorMessage(err: unknown): string {
  if (err instanceof ApiError && err.detail && typeof err.detail === "object") {
    const parts = Object.values(err.detail as Record<string, unknown>).flat().map(String);
    if (parts.length) return parts.join(" · ");
  }
  return "Erreur";
}

export function MonEspacePage() {
  const { t, i18n } = useTranslation();
  const qc = useQueryClient();
  const lang = i18n.language;

  const profil = useQuery({ queryKey: ["mon-profil"], queryFn: api.monProfil, retry: false });
  const bulletins = useQuery({ queryKey: ["mes-bulletins"], queryFn: api.mesBulletins, enabled: profil.isSuccess });
  const conges = useQuery({ queryKey: ["mes-conges"], queryFn: api.mesConges, enabled: profil.isSuccess });

  const [ouvert, setOuvert] = useState<MonBulletin | null>(null);
  const [form, setForm] = useState({ type: "annuel", date_debut: "", date_fin: "", nb_jours: 0, motif: "" });
  const [info, setInfo] = useState<string | null>(null);

  const ouvrir = useMutation({
    mutationFn: (id: string) => api.monBulletin(id),
    onSuccess: (b) => {
      setOuvert(b);
      void qc.invalidateQueries({ queryKey: ["mes-bulletins"] });
    },
  });
  const deposer = useMutation({
    mutationFn: () => api.deposerConge({ ...form }),
    onSuccess: () => {
      setInfo(t("monEspace.envoye"));
      setForm({ type: "annuel", date_debut: "", date_fin: "", nb_jours: 0, motif: "" });
      void qc.invalidateQueries({ queryKey: ["mes-conges"] });
      void qc.invalidateQueries({ queryKey: ["mon-profil"] });
    },
  });
  const annuler = useMutation({
    mutationFn: (id: string) => api.annulerConge(id),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["mes-conges"] }),
  });

  if (profil.isLoading) return <KpiGridSkeleton count={2} />;
  if (profil.isError) {
    const sansFiche = profil.error instanceof ApiError && profil.error.status === 403;
    return sansFiche ? (
      <>
        <PageHeader title={t("monEspace.title")} />
      <p>
        <Link className="btn ghost" to="/mon-mot-de-passe">
          {t("ecarts_tr.mdp.menu")}
        </Link>
      </p>
        <EmptyState label={t("monEspace.pasDeFiche")} />
      </>
    ) : (
      <ErrorState message={t("common.error")} onRetry={() => void profil.refetch()} retryLabel={t("common.retry")} />
    );
  }

  const p = profil.data!;
  const setDates = (patch: Partial<typeof form>) =>
    setForm((f) => {
      const next = { ...f, ...patch };
      return { ...next, nb_jours: joursEntre(next.date_debut, next.date_fin) };
    });

  return (
    <>
      <PageHeader title={t("monEspace.title")} subtitle={`${p.nom_complet} · ${t("monEspace.subtitle")}`} />
      <p>
        <Link className="btn ghost" to="/mon-mot-de-passe">
          {t("ecarts_tr.mdp.menu")}
        </Link>
      </p>

      <div className="kpis">
        <Kpi
          label={t("monEspace.solde")}
          value={p.solde_conges}
          hint={`${t("monEspace.soldeHint")} (${p.acquis_annuel} j / an)`}
          icon={CalendarDays}
          tone={p.solde_conges <= 5 ? "warn" : "brand"}
        />
        <Kpi label={t("monEspace.bulletins")} value={bulletins.data?.length ?? 0} icon={FileText} tone="accent" delay={0.05} />
      </div>

      <SectionCard title={t("monEspace.bulletins")}>
        {(bulletins.data ?? []).length === 0 ? (
          <p className="muted">{t("monEspace.noBulletin")}</p>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>{t("monEspace.periode")}</th>
                <th>{t("monEspace.brut")}</th>
                <th>{t("monEspace.net")}</th>
                <th>{t("monEspace.deposeLe")}</th>
                <th>{t("monEspace.consulteLe")}</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {bulletins.data!.map((b) => (
                <tr key={b.id}>
                  <td>{b.periode.slice(0, 7)}</td>
                  <td>{formatMoney(b.brut)}</td>
                  <td>
                    <strong>{formatMoney(b.net)}</strong>
                  </td>
                  <td>{b.disponible_le ? formatDateTime(b.disponible_le, lang) : "—"}</td>
                  <td>
                    {b.consulte_le ? formatDateTime(b.consulte_le, lang) : <Badge tone="warn">{t("monEspace.nonConsulte")}</Badge>}
                  </td>
                  <td>
                    <button className="btn ghost" onClick={() => ouvrir.mutate(b.id)}>
                      {t("monEspace.ouvrir")}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {ouvert && (
          <div className="card" style={{ marginTop: "1rem" }}>
            <strong>
              {ouvert.code} · {ouvert.periode.slice(0, 7)}
            </strong>
            <table className="table mt-1">
              <tbody>
                {ouvert.lignes.map((l) => (
                  <tr key={l.id}>
                    <td>{l.libelle}</td>
                    <td style={{ textAlign: "right" }}>
                      {l.nature === "retenue" ? "−" : ""}
                      {formatMoney(l.montant)}
                    </td>
                  </tr>
                ))}
                <tr>
                  <td>
                    <strong>{t("monEspace.net")}</strong>
                  </td>
                  <td style={{ textAlign: "right" }}>
                    <strong>{formatMoney(ouvert.net)}</strong>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        )}
      </SectionCard>

      <SectionCard title={t("monEspace.conges")}>
        {(conges.data ?? []).length === 0 ? (
          <p className="muted">{t("monEspace.noConge")}</p>
        ) : (
          <table className="table">
            <tbody>
              {conges.data!.map((c) => (
                <tr key={c.id}>
                  <td>{t(`monEspace.types.${c.type}`, c.type_label)}</td>
                  <td>
                    {formatDate(c.date_debut, lang)} → {formatDate(c.date_fin, lang)} · {c.nb_jours} j
                  </td>
                  <td>
                    <Badge tone={c.statut === "valide" ? "ok" : c.statut === "refuse" || c.statut === "annule" ? "err" : "warn"}>
                      {c.statut_label}
                    </Badge>
                  </td>
                  <td>
                    {c.statut === "demande" && (
                      <button className="btn ghost" onClick={() => annuler.mutate(c.id)}>
                        {t("monEspace.annuler")}
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        <h3 style={{ marginTop: "1.2rem" }}>{t("monEspace.nouvelle")}</h3>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            setInfo(null);
            deposer.mutate();
          }}
          style={{ display: "grid", gap: "0.7rem", maxWidth: 520 }}
        >
          <label className="field">
            <span>{t("monEspace.type")}</span>
            <select value={form.type} onChange={(e) => setForm({ ...form, type: e.target.value })}>
              {TYPES.map((k) => (
                <option key={k} value={k}>
                  {t(`monEspace.types.${k}`)}
                </option>
              ))}
            </select>
          </label>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 90px", gap: "0.7rem" }}>
            <label className="field">
              <span>{t("monEspace.debut")}</span>
              <input type="date" required value={form.date_debut} onChange={(e) => setDates({ date_debut: e.target.value })} />
            </label>
            <label className="field">
              <span>{t("monEspace.fin")}</span>
              <input type="date" required value={form.date_fin} onChange={(e) => setDates({ date_fin: e.target.value })} />
            </label>
            <label className="field">
              <span>{t("monEspace.jours")}</span>
              <input
                type="number"
                min={1}
                required
                value={form.nb_jours || ""}
                onChange={(e) => setForm({ ...form, nb_jours: Number(e.target.value) })}
              />
            </label>
          </div>
          <label className="field">
            <span>{t("monEspace.motif")}</span>
            <input value={form.motif} onChange={(e) => setForm({ ...form, motif: e.target.value })} />
          </label>
          {deposer.isError && <p className="error">{errorMessage(deposer.error)}</p>}
          {info && <p className="muted">{info}</p>}
          <button className="btn" type="submit" disabled={deposer.isPending}>
            {t("monEspace.envoyer")}
          </button>
        </form>
      </SectionCard>
    </>
  );
}
