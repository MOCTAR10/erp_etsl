import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../../api/client";
import { formatNumber } from "../../lib/format";
import { describeError } from "../../lib/offlineQueue";
import type { ControleQualite, MesureControle, TypeControleQualite } from "../../types";
import { ActionBar, Badge, DataTable, EmptyState, QuickForm, SectionCard } from "../ui";
import type { Column } from "../ui";

interface Critere {
  id: string;
  type_controle: TypeControleQualite;
  type_label: string;
  code: string;
  libelle: string;
  unite: string;
  mini: string | null;
  maxi: string | null;
  norme: string;
  actif: boolean;
  est_provisoire: boolean;
}
interface Equipement {
  id: string;
  code: string;
  designation: string;
  type_equipement: string;
  utilisable: boolean;
}

/** Types de contrôle à mesures structurées (seuils paramétrables, résultat calculé). */
const TYPES_MESURES: TypeControleQualite[] = ["peinture", "genie_civil", "electrique", "essai", "tth"];

/** Valeur mesurée ou seuil : décimales conservées (« 0,5 »), entiers sans virgule. */
const nombre = (v: string | null) => (v === null ? "—" : formatNumber(v, { decimals: Number.isInteger(Number(v)) ? 0 : 2 }));
const seuil = (c: { mini: string | null; maxi: string | null }) => `[${nombre(c.mini)} ; ${nombre(c.maxi)}]`;

/** Enveloppe sans boîte : porte le data-testid d'une section (création + tableau) sans changer la mise en page. */
const CONTENTS = { display: "contents" } as const;

/** Écarts M6-B : contrôles peinture / génie civil / électricité / essais / TTH mesurés contre des seuils paramétrables. */
export function EcartsM6bSection() {
  const { t } = useTranslation();
  const ofs = useQuery({ queryKey: ["m6e", "ofs"], queryFn: () => api.listAll<{ id: string; code: string; label: string }>("/api/operations/ordres/"), retry: 0 }).data ?? [];
  const equipements = useQuery({ queryKey: ["m6b", "equipements"], queryFn: () => api.listAll<Equipement>("/api/qualite/instruments/"), retry: 0 }).data ?? [];
  const criteres = useQuery({ queryKey: ["m6b", "criteres"], queryFn: () => api.listAll<Critere>("/api/qualite/criteres/"), retry: 0 });
  const controles = useQuery({
    queryKey: ["m6b", "controles"],
    queryFn: () => api.listAll<ControleQualite>("/api/qualite/controles/"),
    select: (rows: ControleQualite[]) => rows.filter((c) => TYPES_MESURES.includes(c.type_controle)),
    retry: 0,
  });
  const crit = criteres.data ?? [];
  const rows = controles.data ?? [];

  return (
    <>
      <div data-testid="controles-mesures" style={CONTENTS}>
        <SectionCard
          title={`${t("m6b.ctrl.title")} · ${rows.length}`}
          subtitle={t("m6b.ctrl.aide")}
          actions={
            <QuickForm
              title={t("m6b.ctrl.nouveau")}
              endpoint="/api/qualite/controles/"
              fields={[
                { name: "type_controle", label: t("qualite.col.type"), type: "select", required: true, defaultValue: "peinture", options: TYPES_MESURES.map((v) => ({ value: v, label: t(`qualite.ctrl_types.${v}`) })) },
                { name: "ordre", label: t("qualite.m6.of"), type: "select", options: ofs.map((o) => ({ value: o.id, label: `${o.code} · ${o.label}` })) },
                { name: "point_controle", label: t("qualite.col.point") },
                {
                  name: "instrument",
                  label: t("m6b.ctrl.equipement"),
                  type: "select",
                  options: equipements.filter((e) => e.utilisable).map((e) => ({ value: e.id, label: `${e.code} · ${e.designation}` })),
                },
              ]}
            />
          }
        >
          {/* Tableau de saisie inline (mesures) : conservé en `<table>` (sélecteur e2e `tr`). */}
          {rows.length > 0 ? (
            <div className="table-wrap">
              <table className="table">
                <caption className="sr-only">{t("m6b.ctrl.title")}</caption>
                <thead>
                  <tr>
                    <th scope="col">{t("qualite.col.code")}</th>
                    <th scope="col">{t("qualite.col.type")}</th>
                    <th scope="col">{t("qualite.m6.of")}</th>
                    <th scope="col">{t("m6b.ctrl.mesures")}</th>
                    <th scope="col">{t("qualite.col.resultat")}</th>
                    <th scope="col">
                      <span className="sr-only">{t("ui.actions")}</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((c) => (
                    <ControleRow key={c.id} controle={c} criteres={crit.filter((k) => k.actif && k.type_controle === c.type_controle)} />
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <EmptyState label={t("tableaux.qualite.aucunControleMesure")} compact />
          )}
        </SectionCard>
      </div>
      <CriteresSection criteres={crit} />
    </>
  );
}

function ControleRow({ controle: c, criteres }: { controle: ControleQualite; criteres: Critere[] }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [critere, setCritere] = useState("");
  const [valeur, setValeur] = useState("");
  const [repere, setRepere] = useState("");
  const [error, setError] = useState<string | null>(null);
  const mesures: MesureControle[] = c.mesures ?? [];
  const clos = c.statut === "valide" || c.statut === "annule";
  const saisir = useMutation({
    mutationFn: () => api.post(`/api/qualite/controles/${c.id}/mesure/`, { critere, valeur, repere }),
    onSuccess: () => {
      setError(null);
      setValeur("");
      setRepere("");
      void qc.invalidateQueries({ queryKey: ["m6b", "controles"] });
    },
    onError: (e) => setError(describeError(e)),
  });
  const hors = mesures.filter((m) => !m.conforme).length;

  return (
    <tr>
      <td>{c.code}</td>
      <td>
        {t(`qualite.ctrl_types.${c.type_controle}`)}
        {c.point_controle && <span className="muted"> · {c.point_controle}</span>}
      </td>
      <td>{c.ordre_code ?? "—"}</td>
      <td>
        {mesures.map((m) => (
          <div key={m.id} className="meta">
            {m.critere_libelle} = <span className="num">{nombre(m.valeur)}</span> {m.unite} <span className="muted">{seuil(m)}</span>{" "}
            <Badge tone={m.conforme ? "ok" : "err"}>{m.conforme ? t("qualite.ctrl_result.conforme") : t("qualite.ctrl_result.non_conforme")}</Badge>
            {m.repere && <span className="muted"> · {m.repere}</span>}
          </div>
        ))}
        {!clos && (
          <form
            style={{ display: "flex", flexWrap: "wrap", gap: "var(--space-2)", alignItems: "center", marginTop: "var(--space-2)" }}
            aria-label={`${t("m6b.ctrl.saisir")} ${c.code}`}
            onSubmit={(e) => {
              e.preventDefault();
              saisir.mutate();
            }}
          >
            <select className="control" aria-label={t("m6b.ctrl.critere")} value={critere} onChange={(e) => setCritere(e.target.value)} required>
              <option value="">{t("m6b.ctrl.critere")}…</option>
              {criteres.map((k) => (
                <option key={k.id} value={k.id}>
                  {k.libelle} ({k.unite}) {seuil(k)}
                </option>
              ))}
            </select>
            <input className="control" aria-label={t("m6b.ctrl.valeur")} placeholder={t("m6b.ctrl.valeur")} inputMode="decimal" value={valeur} onChange={(e) => setValeur(e.target.value)} required size={8} />
            <input className="control" aria-label={t("m6b.ctrl.repere")} placeholder={t("m6b.ctrl.repere")} value={repere} onChange={(e) => setRepere(e.target.value)} size={10} />
            <button type="submit" className="btn ghost sm" disabled={saisir.isPending}>
              {t("m6b.ctrl.saisir")}
            </button>
            {error && <span className="action-error" role="alert"> {error}</span>}
          </form>
        )}
      </td>
      <td>
        {clos ? (
          <Badge tone={c.resultat === "conforme" ? "ok" : "err"}>{t(`qualite.ctrl_result.${c.resultat}`)}</Badge>
        ) : (
          <Badge tone={hors > 0 ? "err" : "warn"}>{hors > 0 ? t("m6b.ctrl.hors", { count: hors }) : t(`qualite.ctrl_status.${c.statut}`)}</Badge>
        )}
      </td>
      <td>
        {!clos && mesures.length > 0 && (
          <ActionBar
            actions={[
              { label: t("m6b.ctrl.conclure"), path: `/api/qualite/controles/${c.id}/conclure/`, confirm: t("m6b.ctrl.confirmConclure") },
              { label: t("m6b.ctrl.partiel"), path: `/api/qualite/controles/${c.id}/conclure/`, body: { partiel: true }, tone: "ghost", confirm: t("m6b.ctrl.confirmPartiel") },
            ]}
          />
        )}
      </td>
    </tr>
  );
}

/** Seuils d'acceptation : provisoires jusqu'à confirmation ETSL ; une modification remet le critère en provisoire. */
function CriteresSection({ criteres }: { criteres: Critere[] }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const modifier = useMutation({
    mutationFn: (v: { id: string; mini: string | null; maxi: string | null }) => api.patch(`/api/qualite/criteres/${v.id}/`, { mini: v.mini, maxi: v.maxi }),
    onSuccess: () => {
      setError(null);
      void qc.invalidateQueries({ queryKey: ["m6b", "criteres"] });
    },
    onError: (e) => setError(describeError(e)),
  });
  const provisoires = criteres.filter((c) => c.est_provisoire).length;
  const lire = (label: string, v: string | null) => {
    const s = window.prompt(label, v ?? "");
    return s === null ? undefined : s.trim() === "" ? null : s.trim().replace(",", ".");
  };
  const cols: Column<Critere>[] = [
    { key: "type", header: t("qualite.col.type"), render: (c) => t(`qualite.ctrl_types.${c.type_controle}`), sortValue: (c) => c.type_controle },
    { key: "critere", header: t("m6b.crit.critere"), render: (c) => c.libelle, sortValue: (c) => c.libelle },
    { key: "seuils", header: t("m6b.crit.seuils"), num: true, render: (c) => `${seuil(c)} ${c.unite}` },
    { key: "norme", header: t("m6b.crit.norme"), render: (c) => c.norme || "—" },
    {
      key: "statut",
      header: t("qualite.col.statut"),
      render: (c) => <Badge tone={c.est_provisoire ? "warn" : "ok"}>{c.est_provisoire ? t("m5e.params.provisoire") : t("m5e.params.confirme")}</Badge>,
      sortValue: (c) => c.est_provisoire,
    },
    {
      key: "actions",
      header: <span className="sr-only">{t("ui.actions")}</span>,
      render: (c) => (
        <div className="action-bar-buttons">
          <button
            type="button"
            className="btn ghost sm"
            onClick={() => {
              const mini = lire(`${c.libelle} : ${t("m6b.crit.mini")} (${c.unite})`, c.mini);
              if (mini === undefined) return;
              const maxi = lire(`${c.libelle} : ${t("m6b.crit.maxi")} (${c.unite})`, c.maxi);
              if (maxi === undefined) return;
              modifier.mutate({ id: c.id, mini, maxi });
            }}
          >
            {t("m5e.params.modifier")}
          </button>
          {c.est_provisoire && (
            <ActionBar actions={[{ label: t("m5e.params.confirmer"), path: `/api/qualite/criteres/${c.id}/confirmer/`, confirm: t("m5e.params.confirmConfirmer") }]} />
          )}
        </div>
      ),
    },
  ];

  return (
    <SectionCard title={`${t("m6b.crit.title")} · ${criteres.length}`}>
      {provisoires > 0 && <p className="muted" role="note">{t("m6b.crit.bandeau", { count: provisoires })}</p>}
      {error && <p className="action-error" role="alert">{error}</p>}
      <div data-testid="criteres-controle">
        <DataTable columns={cols} rows={criteres} caption={t("m6b.crit.title")} />
      </div>
    </SectionCard>
  );
}
