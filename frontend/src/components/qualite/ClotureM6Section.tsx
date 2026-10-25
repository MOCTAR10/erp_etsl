import { useTranslation } from "react-i18next";

import { api } from "../../api/client";
import { formatDate, formatNumber } from "../../lib/format";
import { usePagedList } from "../../lib/usePagedList";
import type { Paginated } from "../../types";
import { ActionBar, Badge, PagedDataGrid, QuickForm, SectionCard } from "../ui";
import type { Column } from "../ui";

interface Instrument {
  id: string;
  code: string;
  designation: string;
  type_equipement: string;
  type_label: string;
  periodicite_mois: number;
  organisme: string;
  localisation: string;
  operation_attendue: "etalonnage" | "verification" | "validation";
  numero_serie: string;
  echeance_etalonnage: string;
  statut: "actif" | "bloque";
  statut_label: string;
  utilisable: boolean;
}

interface Joint {
  id: string;
  code: string;
  ordre_code: string | null;
  repere: string;
  soudeur_nom: string;
  wps_code: string | null;
  numero_coulee: string;
  date_soudage: string;
}

interface Epreuve {
  id: string;
  code: string;
  ordre_code: string | null;
  type_epreuve: "hydraulique" | "etancheite";
  pression_essai: string;
  duree_minutes: number;
  chute_max: string;
  releves: Array<{ minute: number; pression: string; temperature: string }>;
  statut: "en_cours" | "conclue";
  statut_label: string;
  resultat: "" | "conforme" | "non_conforme";
}

function useList<T>(key: string, path: string) {
  return usePagedList<T>(key, (q) => api.get<Paginated<T>>(`${path}${q}`));
}

/** Clôture M6 : métrologie (étalonnage, blocage d'usage), registre des joints, épreuves hydrauliques P/T. */
export function ClotureM6Section() {
  const { t, i18n } = useTranslation();
  const instruments = useList<Instrument>("instruments", "/api/qualite/instruments/");
  const joints = useList<Joint>("joints", "/api/qualite/joints/");
  const epreuves = useList<Epreuve>("epreuves", "/api/qualite/epreuves/");
  const echeance = (mois: number) => {
    const d = new Date();
    d.setMonth(d.getMonth() + (mois || 12));
    return d.toISOString().slice(0, 10);
  };
  const TYPES_EQUIPEMENT = ["instrument", "poste_souder", "four_tth", "manometre", "thermometre", "autre"];
  const actionsHeader = <span className="sr-only">{t("ui.actions")}</span>;

  const instCols: Column<Instrument>[] = [
    { key: "code", header: t("qualite.col.code"), render: (i) => i.code, sortValue: (i) => i.code },
    {
      key: "designation",
      header: t("qualite.m6.designation"),
      render: (i) => (
        <>
          {i.designation} <span className="muted">· {i.numero_serie}</span>
        </>
      ),
      sortValue: (i) => i.designation,
    },
    {
      key: "type",
      header: t("qualite.col.type"),
      render: (i) => (
        <>
          {i.type_label}
          <span className="muted">
            {" "}
            · {t(`qualite.m6.ops.${i.operation_attendue}`)} / {i.periodicite_mois} {t("qualite.m6.mois")}
            {i.organisme ? ` · ${i.organisme}` : ""}
          </span>
        </>
      ),
    },
    {
      key: "echeance",
      header: t("qualite.m6.echeance"),
      kind: "date",
      render: (i) => formatDate(i.echeance_etalonnage, i18n.language),
      sortValue: (i) => i.echeance_etalonnage,
    },
    {
      key: "statut",
      header: t("qualite.col.statut"),
      render: (i) => <Badge tone={i.utilisable ? "ok" : "err"}>{i.utilisable ? t("qualite.m6.utilisable") : t("qualite.m6.usageBloque")}</Badge>,
    },
    {
      key: "actions",
      header: actionsHeader,
      render: (i) => (
        <div className="action-bar-buttons">
          <ActionBar
            actions={[
              {
                label: t("qualite.m6.etalonnerConforme"),
                path: `/api/qualite/instruments/${i.id}/etalonner/`,
                body: { conforme: true, echeance: echeance(i.periodicite_mois) },
                confirm: t("qualite.m6.confirmEtalonnage"),
              },
              {
                label: t("qualite.m6.horsTolerance"),
                path: `/api/qualite/instruments/${i.id}/etalonner/`,
                body: { conforme: false },
                tone: "danger",
                confirm: t("qualite.m6.confirmHorsTolerance"),
              },
            ]}
          />
          <button type="button" className="btn ghost sm" onClick={() => void api.download(`/api/qualite/instruments/${i.id}/etiquette/`, `etiquette-${i.code}.pdf`)}>
            {t("qualite.m6.etiquette")}
          </button>
        </div>
      ),
    },
  ];

  const jointCols: Column<Joint>[] = [
    { key: "code", header: t("qualite.col.code"), render: (j) => j.code, sortValue: (j) => j.code },
    { key: "of", header: t("qualite.m6.of"), render: (j) => j.ordre_code ?? "—", sortValue: (j) => j.ordre_code },
    { key: "repere", header: t("qualite.m6.joint"), render: (j) => j.repere },
    { key: "soudeur", header: t("qualite.col.soudeur"), render: (j) => j.soudeur_nom, sortValue: (j) => j.soudeur_nom },
    { key: "wps", header: "WPS", render: (j) => j.wps_code ?? "—" },
    { key: "coulee", header: t("qualite.m6.coulee"), render: (j) => j.numero_coulee || "—" },
    { key: "date", header: t("qualite.col.date"), kind: "date", render: (j) => formatDate(j.date_soudage, i18n.language), sortValue: (j) => j.date_soudage },
  ];

  const epCols: Column<Epreuve>[] = [
    { key: "code", header: t("qualite.col.code"), render: (e) => e.code, sortValue: (e) => e.code },
    { key: "of", header: t("qualite.m6.of"), render: (e) => e.ordre_code ?? "—", sortValue: (e) => e.ordre_code },
    {
      key: "pression",
      header: t("qualite.m6.pressionEssai"),
      num: true,
      render: (e) => `${formatNumber(e.pression_essai, { decimals: 1 })} bar · ${e.duree_minutes} min`,
      sortValue: (e) => Number(e.pression_essai),
    },
    { key: "releves", header: t("qualite.m6.releves"), num: true, render: (e) => e.releves.length, sortValue: (e) => e.releves.length },
    {
      key: "resultat",
      header: t("qualite.col.resultat"),
      render: (e) =>
        e.statut === "conclue" ? (
          <Badge tone={e.resultat === "conforme" ? "ok" : "err"}>{t(`qualite.m6.res.${e.resultat}`)}</Badge>
        ) : (
          <Badge tone="warn">{e.statut_label}</Badge>
        ),
    },
    {
      key: "actions",
      header: actionsHeader,
      render: (e) =>
        e.statut === "en_cours" ? (
          <ActionBar actions={[{ label: t("qualite.m6.conclure"), path: `/api/qualite/epreuves/${e.id}/conclure/`, confirm: t("qualite.m6.confirmConclure") }]} />
        ) : null,
    },
  ];

  return (
    <>
      <SectionCard
        title={`${t("qualite.m6.metrologie")} · ${instruments.count}`}
        actions={
          <QuickForm
            title={t("qualite.m6.newInstrument")}
            endpoint="/api/qualite/instruments/"
            fields={[
              { name: "designation", label: t("qualite.m6.designation"), required: true },
              {
                name: "type_equipement",
                label: t("qualite.col.type"),
                type: "select",
                required: true,
                defaultValue: "instrument",
                options: TYPES_EQUIPEMENT.map((v) => ({ value: v, label: t(`qualite.m6.types.${v}`) })),
              },
              { name: "periodicite_mois", label: t("qualite.m6.periodicite"), type: "number", min: 1, defaultValue: "12" },
              { name: "organisme", label: t("qualite.m6.organisme") },
              { name: "localisation", label: t("qualite.m6.localisation") },
              { name: "numero_serie", label: t("qualite.m6.serie"), required: true },
              { name: "date_etalonnage", label: t("qualite.m6.dernierEtalonnage"), type: "date", required: true },
              { name: "echeance_etalonnage", label: t("qualite.m6.echeance"), type: "date", required: true },
            ]}
          />
        }
      >
        <PagedDataGrid
          list={instruments}
          columns={instCols}
          caption={t("qualite.m6.metrologie")}
          searchPlaceholder={t("qualite.m6.searchInstruments")}
          maxHeight="none"
        />
      </SectionCard>

      <SectionCard title={`${t("qualite.m6.joints")} · ${joints.count}`}>
        <PagedDataGrid
          list={joints}
          columns={jointCols}
          caption={t("qualite.m6.joints")}
          searchPlaceholder={t("qualite.m6.searchJoints")}
          emptyLabel={t("qualite.m6.jointsVide")}
          maxHeight="none"
        />
      </SectionCard>

      <SectionCard title={`${t("qualite.m6.epreuves")} · ${epreuves.count}`}>
        <PagedDataGrid
          list={epreuves}
          columns={epCols}
          caption={t("qualite.m6.epreuves")}
          searchPlaceholder={t("qualite.m6.searchEpreuves")}
          emptyLabel={t("qualite.m6.epreuvesVide")}
          maxHeight="none"
        />
      </SectionCard>
    </>
  );
}
