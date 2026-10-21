import { useTranslation } from "react-i18next";

import { api } from "../../api/client";
import { formatDate } from "../../lib/format";
import { usePagedList } from "../../lib/usePagedList";
import type { Paginated } from "../../types";
import { ActionBar, Badge, Pagination, QuickForm, SearchField, SectionCard } from "../ui";

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
  const instRows = instruments.rows;
  const jointRows = joints.rows;
  const epRows = epreuves.rows;
  const echeance = (mois: number) => {
    const d = new Date();
    d.setMonth(d.getMonth() + (mois || 12));
    return d.toISOString().slice(0, 10);
  };
  const TYPES_EQUIPEMENT = ["instrument", "poste_souder", "four_tth", "manometre", "thermometre", "autre"];

  return (
    <>
      <SectionCard title={`${t("qualite.m6.metrologie")} · ${instruments.count}`}>
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
        <SearchField value={instruments.search} onChange={instruments.setSearch} placeholder={t("qualite.m6.searchInstruments")} />
        {instRows.length > 0 && (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>{t("qualite.col.code")}</th>
                  <th>{t("qualite.m6.designation")}</th>
                  <th>{t("qualite.col.type")}</th>
                  <th>{t("qualite.m6.echeance")}</th>
                  <th>{t("qualite.col.statut")}</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {instRows.map((i) => (
                  <tr key={i.id}>
                    <td>{i.code}</td>
                    <td>
                      {i.designation} <span className="muted">· {i.numero_serie}</span>
                    </td>
                    <td>
                      {i.type_label}
                      <span className="muted">
                        {" "}
                        · {t(`qualite.m6.ops.${i.operation_attendue}`)} / {i.periodicite_mois} {t("qualite.m6.mois")}
                        {i.organisme ? ` · ${i.organisme}` : ""}
                      </span>
                    </td>
                    <td>{formatDate(i.echeance_etalonnage, i18n.language)}</td>
                    <td>
                      <Badge tone={i.utilisable ? "ok" : "err"}>{i.utilisable ? t("qualite.m6.utilisable") : t("qualite.m6.usageBloque")}</Badge>
                    </td>
                    <td>
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
                      />{" "}
                      <button type="button" className="btn ghost" onClick={() => void api.download(`/api/qualite/instruments/${i.id}/etiquette/`, `etiquette-${i.code}.pdf`)}>
                        {t("qualite.m6.etiquette")}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <Pagination page={instruments.page} pageSize={instruments.pageSize} count={instruments.count} onPageChange={instruments.setPage} onPageSizeChange={instruments.setPageSize} />
      </SectionCard>

      <SectionCard title={`${t("qualite.m6.joints")} · ${joints.count}`}>
        <SearchField value={joints.search} onChange={joints.setSearch} placeholder={t("qualite.m6.searchJoints")} />
        {jointRows.length === 0 ? (
          <p className="muted">{t("qualite.m6.jointsVide")}</p>
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>{t("qualite.col.code")}</th>
                  <th>{t("qualite.m6.of")}</th>
                  <th>{t("qualite.m6.joint")}</th>
                  <th>{t("qualite.col.soudeur")}</th>
                  <th>WPS</th>
                  <th>{t("qualite.m6.coulee")}</th>
                  <th>{t("qualite.col.date")}</th>
                </tr>
              </thead>
              <tbody>
                {jointRows.map((j) => (
                  <tr key={j.id}>
                    <td>{j.code}</td>
                    <td>{j.ordre_code}</td>
                    <td>{j.repere}</td>
                    <td>{j.soudeur_nom}</td>
                    <td>{j.wps_code}</td>
                    <td>{j.numero_coulee}</td>
                    <td>{formatDate(j.date_soudage, i18n.language)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <Pagination page={joints.page} pageSize={joints.pageSize} count={joints.count} onPageChange={joints.setPage} onPageSizeChange={joints.setPageSize} />
      </SectionCard>

      <SectionCard title={`${t("qualite.m6.epreuves")} · ${epreuves.count}`}>
        <SearchField value={epreuves.search} onChange={epreuves.setSearch} placeholder={t("qualite.m6.searchEpreuves")} />
        {epRows.length === 0 ? (
          <p className="muted">{t("qualite.m6.epreuvesVide")}</p>
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>{t("qualite.col.code")}</th>
                  <th>{t("qualite.m6.of")}</th>
                  <th className="num">{t("qualite.m6.pressionEssai")}</th>
                  <th className="num">{t("qualite.m6.releves")}</th>
                  <th>{t("qualite.col.resultat")}</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {epRows.map((e) => (
                  <tr key={e.id}>
                    <td>{e.code}</td>
                    <td>{e.ordre_code}</td>
                    <td className="num">
                      {e.pression_essai} bar · {e.duree_minutes} min
                    </td>
                    <td className="num">{e.releves.length}</td>
                    <td>
                      {e.statut === "conclue" ? (
                        <Badge tone={e.resultat === "conforme" ? "ok" : "err"}>{t(`qualite.m6.res.${e.resultat}`)}</Badge>
                      ) : (
                        <Badge tone="warn">{e.statut_label}</Badge>
                      )}
                    </td>
                    <td>
                      {e.statut === "en_cours" && (
                        <ActionBar actions={[{ label: t("qualite.m6.conclure"), path: `/api/qualite/epreuves/${e.id}/conclure/`, confirm: t("qualite.m6.confirmConclure") }]} />
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <Pagination page={epreuves.page} pageSize={epreuves.pageSize} count={epreuves.count} onPageChange={epreuves.setPage} onPageSizeChange={epreuves.setPageSize} />
      </SectionCard>
    </>
  );
}
