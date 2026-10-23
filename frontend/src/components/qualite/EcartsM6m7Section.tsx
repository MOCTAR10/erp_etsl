import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../../api/client";
import { formatDate } from "../../lib/format";
import { SectionActions } from "../sections/SectionActions";
import { Badge, DataTable, QuickForm, SectionCard } from "../ui";
import type { Column } from "../ui";

interface Organisme {
  id: string;
  nom: string;
  numero_agrement: string;
  autorite: string;
  methodes: string;
  date_fin_validite: string;
  actif: boolean;
  valide: boolean;
  nb_controles: number;
}
interface Wps {
  id: string;
  code: string;
  type: string;
  statut: string;
  procede: string;
}
interface WpsRequis {
  id: string;
  contract: string | null;
  contract_code: string | null;
  profile: string;
  wps: string;
  wps_code: string;
  wps_statut: string;
  libelle: string;
}
interface Ordre {
  id: string;
  code: string;
  label: string;
  affaire: string | null;
  affaire_code: string | null;
}
interface Contrat {
  id: string;
  code: string;
}
interface Conformite {
  affaire_code: string;
  conforme: boolean;
  requis: { wps: string; wps_code: string; statut: string; valide: boolean; origine: string; libelle: string }[];
}

const METHODES = ["RT", "UT", "PT", "MT"];
const PROFILS = ["marche_travaux", "maintenance"];

/** Enveloppe sans boîte : porte le data-testid d une section (création + tableau) sans changer la mise en page. */
const CONTENTS = { display: "contents" } as const;

const useListe = <T,>(key: string, path: string) =>
  useQuery({ queryKey: ["ecarts-m6m7", key], queryFn: () => api.listAll<T>(path), retry: 0 }).data ?? [];

/** Écarts M6 : référentiel des organismes agréés et WPS requis par profil contractuel. */
export function EcartsM6m7Section() {
  const { t } = useTranslation();
  const organismes = useListe<Organisme>("organismes", "/api/qualite/organismes-agrees/");
  const wps = useListe<Wps>("wps", "/api/qualite/wps/");
  const requis = useListe<WpsRequis>("wps-requis", "/api/qualite/wps-requis/");
  const ordres = useListe<Ordre>("ordres", "/api/operations/ordres/");
  // Les contrats (module commercial) ne sont lisibles que par certains rôles : liste vide sinon.
  const contrats = useListe<Contrat>("contrats", "/api/commercial/contracts/");
  const [ordre, setOrdre] = useState("");
  const conformite = useQuery({
    queryKey: ["ecarts-m6m7", "conformite", ordre],
    queryFn: () => api.get<Conformite>(`/api/qualite/wps-requis/conformite/?ordre=${ordre}`),
    enabled: ordre !== "",
    retry: 0,
  });

  const wpsValides = wps.filter((w) => w.type === "wps" && w.statut === "valide").map((w) => ({ value: w.id, label: `${w.code} · ${w.procede.toUpperCase()}` }));
  const orgValides = organismes.filter((o) => o.valide).map((o) => ({ value: o.id, label: `${o.nom} · ${o.methodes || METHODES.join(",")}` }));
  const ordresAffaire = ordres.filter((o) => o.affaire);
  const m = "ecarts_m6m7";

  const orgCols: Column<Organisme>[] = [
    {
      key: "nom",
      header: t(`${m}.org.nom`),
      render: (o) => (
        <>
          {o.nom}
          {o.autorite ? <span className="muted"> · {o.autorite}</span> : null}
        </>
      ),
      sortValue: (o) => o.nom,
    },
    { key: "numero", header: t(`${m}.org.numero`), render: (o) => o.numero_agrement },
    { key: "methodes", header: t(`${m}.org.methodes`), render: (o) => o.methodes || METHODES.join(", ") },
    {
      key: "validite",
      header: t(`${m}.org.validite`),
      render: (o) => (
        <>
          {formatDate(o.date_fin_validite)} <Badge tone={o.valide ? "ok" : "err"}>{t(o.valide ? `${m}.org.valide` : `${m}.org.expire`)}</Badge>
        </>
      ),
      sortValue: (o) => o.date_fin_validite,
    },
    { key: "controles", header: t(`${m}.org.controles`), num: true, render: (o) => o.nb_controles, sortValue: (o) => o.nb_controles },
  ];
  const requisCols: Column<WpsRequis>[] = [
    { key: "origine", header: t(`${m}.wps.origine`), render: (r) => r.contract_code ?? t(`${m}.wps.profils.${r.profile}`) },
    { key: "wps", header: "WPS", render: (r) => r.wps_code, sortValue: (r) => r.wps_code },
    {
      key: "statut",
      header: t(`${m}.wps.statut`),
      render: (r) => <Badge tone={r.wps_statut === "valide" ? "ok" : "err"}>{t(`qualite.wps_status.${r.wps_statut}`, { defaultValue: r.wps_statut })}</Badge>,
    },
    { key: "libelle", header: t(`${m}.wps.libelle`), render: (r) => r.libelle || "—" },
  ];

  return (
    <>
      <div data-testid="organismes-agrees" style={CONTENTS}>
        <SectionCard
          title={`${t(`${m}.org.title`)} · ${organismes.length}`}
          subtitle={t(`${m}.org.aide`)}
          actions={
            <SectionActions>
              <QuickForm
                title={t(`${m}.org.ajouter`)}
                endpoint="/api/qualite/organismes-agrees/"
                fields={[
                  { name: "nom", label: t(`${m}.org.nom`), required: true },
                  { name: "numero_agrement", label: t(`${m}.org.numero`), required: true },
                  { name: "autorite", label: t(`${m}.org.autorite`) },
                  { name: "methodes", label: t(`${m}.org.methodes`) },
                  { name: "date_fin_validite", label: t(`${m}.org.validite`), type: "date", required: true },
                ]}
              />
              <QuickForm
                title={t(`${m}.org.cnd`)}
                endpoint="/api/qualite/controles/"
                transform={(v) => ({ ...v, type_controle: "cnd", organisme: "agrege" })}
                fields={[
                  { name: "organisme_agree", label: t(`${m}.org.nom`), type: "select", required: true, options: orgValides },
                  { name: "methode_cnd", label: t(`${m}.org.methode`), type: "select", required: true, defaultValue: "UT", options: METHODES.map((v) => ({ value: v, label: v })) },
                  { name: "ordre", label: t(`${m}.org.of`), type: "select", options: ordres.map((o) => ({ value: o.id, label: `${o.code} · ${o.label}` })) },
                  { name: "wps", label: "WPS", type: "select", options: wpsValides },
                  { name: "point_controle", label: t(`${m}.org.point`) },
                  { name: "date_controle", label: t(`${m}.org.date`), type: "date" },
                ]}
              />
            </SectionActions>
          }
        >
          <DataTable columns={orgCols} rows={organismes} caption={t(`${m}.org.title`)} emptyLabel={t(`${m}.aucun`)} />
        </SectionCard>
      </div>

      <div data-testid="wps-requis" style={CONTENTS}>
        <SectionCard
          title={`${t(`${m}.wps.title`)} · ${requis.length}`}
          subtitle={t(`${m}.wps.aide`)}
          actions={
            <QuickForm
              title={t(`${m}.wps.ajouter`)}
              endpoint="/api/qualite/wps-requis/"
              fields={[
                { name: "profile", label: t(`${m}.wps.profil`), type: "select", options: PROFILS.map((p) => ({ value: p, label: t(`${m}.wps.profils.${p}`) })) },
                ...(contrats.length > 0 ? [{ name: "contract", label: t(`${m}.wps.contrat`), type: "select" as const, options: contrats.map((c) => ({ value: c.id, label: c.code })) }] : []),
                { name: "wps", label: "WPS", type: "select", required: true, options: wpsValides },
                { name: "libelle", label: t(`${m}.wps.libelle`) },
              ]}
            />
          }
        >
          <DataTable columns={requisCols} rows={requis} caption={t(`${m}.wps.title`)} />
          <div className="field" style={{ marginTop: "var(--space-4)", maxWidth: 420 }}>
            <label htmlFor="m6m7-conformite">{t(`${m}.wps.conformite`)}</label>
            <select id="m6m7-conformite" className="control" value={ordre} onChange={(e) => setOrdre(e.target.value)}>
              <option value="">—</option>
              {ordresAffaire.map((o) => (
                <option key={o.id} value={o.id}>{`${o.code} · ${o.affaire_code ?? ""}`}</option>
              ))}
            </select>
          </div>
          {conformite.data && (
            <div role="status">
              {conformite.data.requis.length === 0 ? (
                <p className="muted">{t(`${m}.wps.libre`, { affaire: conformite.data.affaire_code })}</p>
              ) : (
                <p>
                  {conformite.data.affaire_code} :{" "}
                  <Badge tone={conformite.data.conforme ? "ok" : "err"}>{t(conformite.data.conforme ? `${m}.wps.conforme` : `${m}.wps.nonConforme`)}</Badge>{" "}
                  {conformite.data.requis.map((r) => r.wps_code).join(", ")}
                </p>
              )}
            </div>
          )}
        </SectionCard>
      </div>
    </>
  );
}
