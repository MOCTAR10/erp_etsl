import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../../api/client";
import { ActionBar, type ActionDef, Badge, QuickForm, SectionCard } from "../ui";
import { describeError } from "../../lib/offlineQueue";
import { useSites } from "./SiteFilter";

const TYPES = ["atelier", "chantier", "depot", "base", "bureau"] as const;
const RESSOURCES = ["depots", "equipements", "actifs", "salaries", "affaires", "ordres", "utilisateurs"] as const;
type Ressource = (typeof RESSOURCES)[number];

interface LigneRepartition extends Record<Ressource, number> {
  site: number | null;
  code: string;
  libelle: string;
  actif: boolean;
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

  const actions = (s: (typeof liste)[number]): ActionDef[] => [
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

  return (
    <SectionCard
      title={t("ecarts_a5.titre")}
      subtitle={t("ecarts_a5.aide")}
      actions={
        <div className="action-bar-buttons">
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
        </div>
      }
    >
      {liste.some((s) => s.est_provisoire) ? (
        <p className="action-error" role="note">
          {t("ecarts_a5.provisoire")}
        </p>
      ) : null}
      {rep ? <p className="muted">{rep.restriction.active ? t("ecarts_a5.restrictionOn") : t("ecarts_a5.restrictionOff")}</p> : null}
      <div className="table-wrap">
        <table className="table" data-testid="sites-etsl">
          <caption className="sr-only">{t("ecarts_a5.titre")}</caption>
          <thead>
            <tr>
              <th scope="col">{t("ecarts_a5.code")}</th>
              <th scope="col">{t("ecarts_a5.libelle")}</th>
              <th scope="col">{t("ecarts_a5.type")}</th>
              <th scope="col">{t("ecarts_a5.alias")}</th>
              {RESSOURCES.map((r) => (
                <th scope="col" key={r} style={{ textAlign: "right" }}>
                  {t(`ecarts_a5.res.${r}`)}
                </th>
              ))}
              <th scope="col">{t("ecarts_a5.statut")}</th>
              <th scope="col">{t("ecarts_a5.actions")}</th>
            </tr>
          </thead>
          <tbody>
            {liste.map((s) => (
              <tr key={s.id}>
                <td>
                  <strong>{s.code}</strong>
                </td>
                <td>
                  {s.libelle}
                  {s.ville ? <div className="muted" style={{ fontSize: 12 }}>{s.ville}</div> : null}
                </td>
                <td>{t(`ecarts_a5.types.${s.type_site}`, { defaultValue: s.type_site_label })}</td>
                <td className="muted" style={{ fontSize: 12 }}>
                  {s.alias || "—"}
                </td>
                {RESSOURCES.map((r) => (
                  <td key={r} style={{ textAlign: "right" }}>
                    {parSite.get(s.id)?.[r] ?? 0}
                  </td>
                ))}
                <td>
                  {!s.actif ? (
                    <Badge tone="neutral">{t("ecarts_a5.inactif")}</Badge>
                  ) : s.est_provisoire ? (
                    <Badge tone="warn">{t("ecarts_a5.provisoireBadge")}</Badge>
                  ) : (
                    <Badge tone="ok">{t("ecarts_a5.confirme")}</Badge>
                  )}
                </td>
                <td>
                  <ActionBar actions={actions(s)} />
                </td>
              </tr>
            ))}
            {nonRattache ? (
              <tr>
                <td colSpan={4} className="muted">
                  {t("ecarts_a5.nonRattache")}
                </td>
                {RESSOURCES.map((r) => (
                  <td key={r} style={{ textAlign: "right" }}>
                    {nonRattache[r]}
                  </td>
                ))}
                <td colSpan={2} />
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </SectionCard>
  );
}
