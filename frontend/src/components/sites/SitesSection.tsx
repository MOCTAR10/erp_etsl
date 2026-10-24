import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../../api/client";
import { ActionBar, type ActionDef, actionsColumn, Badge, type Column, DataTable, QuickForm, SectionCard } from "../ui";
import { describeError } from "../../lib/offlineQueue";
import { formatNumber } from "../../lib/format";
import { SectionActions } from "../sections/SectionActions";
import { type SiteEtsl, useSites } from "./SiteFilter";

const TYPES = ["atelier", "chantier", "depot", "base", "bureau"] as const;
const RESSOURCES = ["depots", "equipements", "actifs", "salaries", "affaires", "ordres", "utilisateurs"] as const;
type Ressource = (typeof RESSOURCES)[number];

interface LigneRepartition extends Record<Ressource, number> {
  site: number | null;
  code: string;
  libelle: string;
  actif: boolean;
}
/** Ligne du tableau : un site, ou la ligne « non rattaché » (`site` nul). */
interface LigneSite {
  id: number | string;
  site: SiteEtsl | null;
  compte: Partial<Record<Ressource, number>>;
}
interface Repartition {
  ressources: Ressource[];
  lignes: LigneRepartition[];
  restriction: { code: string; active: boolean };
}

/** Site de rattachement d'un compte (Administration, EX-G-03) : PATCH du compte, refus serveur affiché. */
export function SiteCompte({ id, email, site }: { id: string; email: string; site: number | null }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const sites = useSites().data ?? [];
  const [erreur, setErreur] = useState<string | null>(null);
  const patch = useMutation({
    mutationFn: (valeur: string) => api.patch(`/api/users/users/${id}/`, { site_etsl: valeur ? Number(valeur) : null }),
    onSuccess: () => {
      setErreur(null);
      void qc.invalidateQueries();
    },
    onError: (e) => setErreur(describeError(e)),
  });
  return (
    <>
      <label className="sr-only" htmlFor={`site-${id}`}>
        {t("ecarts_a5.siteCompte")} — {email}
      </label>
      <select id={`site-${id}`} value={site == null ? "" : String(site)} disabled={patch.isPending} onChange={(e) => patch.mutate(e.target.value)}>
        <option value="">{t("ecarts_a5.aucun")}</option>
        {sites
          .filter((s) => s.actif || s.id === site)
          .map((s) => (
            <option key={s.id} value={String(s.id)}>
              {s.code}
            </option>
          ))}
      </select>
      {erreur && (
        <p className="action-error" role="alert">
          {erreur}
        </p>
      )}
    </>
  );
}

/**
 * Sites ETSL (EX-G-03 multi-sites Port-Gentil / Libreville) : liste provisoire paramétrable (création, mots-clés de
 * rattachement, confirmation, désactivation) et affectation des ressources par site (indicateur de répartition).
 */
export function SitesSection() {
  const { t } = useTranslation();
  const sites = useSites();
  const rep = useQuery({
    queryKey: ["sites-etsl-repartition"],
    queryFn: () => api.get<Repartition>("/api/referentiels/sites/repartition/"),
    retry: 0,
  }).data;
  const parSite = new Map((rep?.lignes ?? []).map((l) => [l.site, l]));
  const nonRattache = parSite.get(null);
  const liste = sites.data ?? [];

  const actions = (s: SiteEtsl): ActionDef[] => [
    ...(s.est_provisoire ? [{ label: t("ecarts_a5.confirmer"), path: `/api/referentiels/sites/${s.id}/confirmer/` }] : []),
    {
      label: t("ecarts_a5.modifierAlias"),
      path: `/api/referentiels/sites/${s.id}/`,
      method: "PATCH" as const,
      tone: "ghost" as const,
      prompt: { name: "alias", label: t("ecarts_a5.alias") },
    },
    {
      label: s.actif ? t("ecarts_a5.desactiver") : t("ecarts_a5.reactiver"),
      path: `/api/referentiels/sites/${s.id}/`,
      method: "PATCH" as const,
      tone: "ghost" as const,
      body: { actif: !s.actif },
    },
  ];

  const lignes: LigneSite[] = [
    ...liste.map((s) => ({ id: s.id, site: s, compte: parSite.get(s.id) ?? {} })),
    ...(nonRattache ? [{ id: "__non-rattache", site: null, compte: nonRattache }] : []),
  ];
  const colonnes: Column<LigneSite>[] = [
    {
      key: "code",
      header: t("ecarts_a5.code"),
      width: 110,
      render: (l) => (l.site ? <strong>{l.site.code}</strong> : <span className="muted">{t("ecarts_a5.nonRattache")}</span>),
    },
    {
      key: "libelle",
      header: t("ecarts_a5.libelle"),
      width: 220,
      render: (l) =>
        l.site ? (
          <>
            {l.site.libelle}
            {l.site.ville ? <div className="cell-sub">{l.site.ville}</div> : null}
          </>
        ) : null,
    },
    { key: "type", header: t("ecarts_a5.type"), width: 110, render: (l) => (l.site ? t(`ecarts_a5.types.${l.site.type_site}`, { defaultValue: l.site.type_site_label }) : null) },
    { key: "alias", header: t("ecarts_a5.alias"), render: (l) => (l.site ? <span className="muted">{l.site.alias || "—"}</span> : null) },
    ...RESSOURCES.map(
      (r): Column<LigneSite> => ({
        key: `res-${r}`,
        header: t(`ecarts_a5.res.${r}`),
        num: true,
        width: 72,
        render: (l) => formatNumber(l.compte[r] ?? 0),
      }),
    ),
    {
      key: "statut",
      header: t("ecarts_a5.statut"),
      width: 120,
      render: (l) =>
        !l.site ? null : !l.site.actif ? (
          <Badge tone="neutral">{t("ecarts_a5.inactif")}</Badge>
        ) : l.site.est_provisoire ? (
          <Badge tone="warn">{t("ecarts_a5.provisoireBadge")}</Badge>
        ) : (
          <Badge tone="ok">{t("ecarts_a5.confirme")}</Badge>
        ),
    },
    // Une action visible (Confirmer tant que le site est provisoire), les autres dans « ⋯ ».
    actionsColumn(t("ecarts_a5.actions"), (l) => (l.site ? actions(l.site) : [])),
  ];

  return (
    <SectionCard
      title={t("ecarts_a5.titre")}
      subtitle={t("ecarts_a5.aide")}
      actions={
        <SectionActions>
          <QuickForm
            title={t("ecarts_a5.nouveau")}
            endpoint="/api/referentiels/sites/"
            fields={[
              { name: "code", label: t("ecarts_a5.code"), required: true },
              { name: "libelle", label: t("ecarts_a5.libelle"), required: true },
              {
                name: "type_site",
                label: t("ecarts_a5.type"),
                type: "select",
                required: true,
                defaultValue: "atelier",
                options: TYPES.map((k) => ({ value: k, label: t(`ecarts_a5.types.${k}`) })),
              },
              { name: "ville", label: t("ecarts_a5.ville") },
              { name: "alias", label: t("ecarts_a5.alias") },
            ]}
          />
          <ActionBar
            actions={[{ label: t("ecarts_a5.rattacher"), path: "/api/referentiels/sites/rattacher/", tone: "ghost", confirm: t("ecarts_a5.rattacherQ") }]}
          />
        </SectionActions>
      }
    >
      {liste.some((s) => s.est_provisoire) ? (
        <div className="banner warn" role="note">
          <AlertTriangle size={18} aria-hidden />
          <div className="banner-body">
            <span className="banner-text">{t("ecarts_a5.provisoire")}</span>
          </div>
        </div>
      ) : null}
      {rep ? <p className="muted">{rep.restriction.active ? t("ecarts_a5.restrictionOn") : t("ecarts_a5.restrictionOff")}</p> : null}
      <div data-testid="sites-etsl">
        <DataTable columns={colonnes} rows={lignes} caption={t("ecarts_a5.titre")} loading={sites.isLoading} />
      </div>
    </SectionCard>
  );
}
