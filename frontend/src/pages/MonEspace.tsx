import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarDays, FileText, KeyRound, UserRound } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { ApiError, api } from "../api/client";
import { Badge, DataTable, EmptyState, ErrorState, Kpi, KpiGridSkeleton, PageHeader, SectionCard } from "../components/ui";
import type { Column } from "../components/ui";
import { formatDate, formatDateTime, formatMoney } from "../lib/format";
import type { MonBulletin, MonConge } from "../types";

type Conge = MonConge;
type LigneBulletin = MonBulletin["lignes"][number];

/** Période de paie « 2026-09-01 » → « septembre 2026 » (suit la langue de l'interface). */
function moisPaie(periode: string, lang: string): string {
  const d = new Date(`${periode.slice(0, 7)}-01T00:00:00`);
  if (Number.isNaN(d.getTime())) return periode;
  const txt = d.toLocaleDateString(lang, { month: "long", year: "numeric" });
  return txt.charAt(0).toUpperCase() + txt.slice(1);
}

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
        <PageHeader
          title={t("monEspace.title")}
          subtitle={t("revueR1.monEspace.sub")}
          actions={
            <Link className="btn ghost" to="/mon-mot-de-passe">
              <KeyRound size={15} aria-hidden="true" /> {t("ecarts_tr.mdp.menu")}
            </Link>
          }
        />
        <SectionCard>
          <EmptyState icon={UserRound} label={t("monEspace.pasDeFiche")} hint={t("revueR1.monEspace.sansFicheAide")} />
        </SectionCard>
      </>
    ) : (
      <ErrorState message={t("common.error")} onRetry={() => void profil.refetch()} retryLabel={t("common.retry")} />
    );
  }

  const p = profil.data!;
  const colsBulletins: Column<MonBulletin>[] = [
    { key: "periode", header: t("monEspace.periode"), render: (b) => moisPaie(b.periode, lang), sortValue: (b) => b.periode },
    { key: "brut", header: t("monEspace.brut"), num: true, render: (b) => formatMoney(b.brut) },
    { key: "net", header: t("monEspace.net"), num: true, render: (b) => <strong>{formatMoney(b.net)}</strong> },
    { key: "depose", header: t("monEspace.deposeLe"), render: (b) => (b.disponible_le ? formatDateTime(b.disponible_le, lang) : "—"), sortValue: (b) => b.disponible_le },
    {
      key: "consulte",
      header: t("monEspace.consulteLe"),
      render: (b) => (b.consulte_le ? formatDateTime(b.consulte_le, lang) : <Badge tone="warn">{t("monEspace.nonConsulte")}</Badge>),
    },
    {
      key: "actions",
      header: <span className="sr-only">{t("ui.actions")}</span>,
      render: (b) => (
        <button type="button" className="btn ghost sm" onClick={() => ouvrir.mutate(b.id)}>
          {t("monEspace.ouvrir")}
        </button>
      ),
    },
  ];
  const colsLignes: Column<LigneBulletin>[] = [
    { key: "libelle", header: t("tableaux.pages.monEspace.libelle"), render: (l) => l.libelle },
    {
      key: "montant",
      header: t("tableaux.pages.monEspace.montant"),
      num: true,
      render: (l) => `${l.nature === "retenue" ? "−" : ""}${formatMoney(l.montant)}`,
    },
  ];
  const colsConges: Column<Conge>[] = [
    { key: "type", header: t("monEspace.type"), render: (c) => t(`monEspace.types.${c.type}`, c.type_label) },
    {
      key: "periode",
      header: t("monEspace.periode"),
      sortValue: (c) => c.date_debut,
      render: (c) => `${formatDate(c.date_debut, lang)} → ${formatDate(c.date_fin, lang)}`,
    },
    { key: "jours", header: t("monEspace.jours"), num: true, render: (c) => c.nb_jours },
    {
      key: "statut",
      header: t("tableaux.pages.monEspace.statut"),
      render: (c) => (
        <Badge tone={c.statut === "valide" ? "ok" : c.statut === "refuse" || c.statut === "annule" ? "err" : "warn"}>{c.statut_label}</Badge>
      ),
    },
    {
      key: "actions",
      header: <span className="sr-only">{t("ui.actions")}</span>,
      render: (c) =>
        c.statut === "demande" ? (
          <button type="button" className="btn ghost sm" onClick={() => annuler.mutate(c.id)}>
            {t("monEspace.annuler")}
          </button>
        ) : null,
    },
  ];
  const setDates = (patch: Partial<typeof form>) =>
    setForm((f) => {
      const next = { ...f, ...patch };
      return { ...next, nb_jours: joursEntre(next.date_debut, next.date_fin) };
    });

  return (
    <>
      <PageHeader
        title={t("monEspace.title")}
        subtitle={`${p.nom_complet} · ${t("monEspace.subtitle")}`}
        actions={
          <Link className="btn ghost" to="/mon-mot-de-passe">
            <KeyRound size={15} aria-hidden="true" /> {t("ecarts_tr.mdp.menu")}
          </Link>
        }
      />

      <div className="kpis">
        <Kpi
          label={t("monEspace.solde")}
          value={p.solde_conges}
          hint={`${t("monEspace.soldeHint")} · ${t("tableaux.pages.monEspace.acquis", { n: p.acquis_annuel })}`}
          icon={CalendarDays}
          tone={p.solde_conges <= 5 ? "warn" : "brand"}
        />
        <Kpi label={t("monEspace.bulletins")} value={bulletins.data?.length ?? 0} icon={FileText} tone="accent" delay={0.05} />
      </div>

      <SectionCard title={t("monEspace.bulletins")}>
        {(bulletins.data ?? []).length === 0 ? (
          <p className="muted">{t("monEspace.noBulletin")}</p>
        ) : (
          <DataTable columns={colsBulletins} rows={bulletins.data!} caption={t("monEspace.bulletins")} />
        )}
        {ouvert && (
          <div className="card" style={{ marginTop: "1rem" }}>
            <strong>
              {ouvert.code} · {moisPaie(ouvert.periode, lang)}
            </strong>
            <DataTable columns={colsLignes} rows={ouvert.lignes} caption={`${ouvert.code} · ${moisPaie(ouvert.periode, lang)}`} />
            <p style={{ display: "flex", justifyContent: "space-between", gap: "var(--space-3)", margin: "var(--space-3) 0 0", padding: "0 var(--space-3)" }}>
              <strong>{t("monEspace.net")}</strong> <strong className="num">{formatMoney(ouvert.net)}</strong>
            </p>
          </div>
        )}
      </SectionCard>

      <SectionCard title={t("monEspace.conges")}>
        {(conges.data ?? []).length === 0 ? (
          <p className="muted">{t("monEspace.noConge")}</p>
        ) : (
          <DataTable columns={colsConges} rows={conges.data!} caption={t("monEspace.conges")} />
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
          <button className="btn primary" type="submit" disabled={deposer.isPending}>
            {t("monEspace.envoyer")}
          </button>
        </form>
      </SectionCard>
    </>
  );
}
