import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../../api/client";
import { formatNumber } from "../../lib/format";
import { describeError } from "../../lib/offlineQueue";
import type { CubeArchive, CubeAxe, CubeLecture, ParametreCube } from "../../types";
import { Badge, SectionCard } from "../ui";

const AXES: CubeAxe[] = ["affaire", "chantier", "site", "activite", "centre", "periode"];
const moisPrecedent = () => {
  const d = new Date();
  d.setMonth(d.getMonth() - 1);
  return d.toISOString().slice(0, 7);
};
const montant = (v: string) => formatNumber(Number(v));

/** Durée de conservation de l'archive du cube : donnée ETSL modifiable, provisoire puis confirmée. */
function ParametresCube() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const [edit, setEdit] = useState<{ id: string; valeur: string } | null>(null);
  const params = useQuery({
    queryKey: ["cube-parametres"],
    queryFn: () => api.listAll<ParametreCube>("/api/analytics/cubes/parametres/"),
    retry: 0,
  });
  const refresh = () => void qc.invalidateQueries({ queryKey: ["cube-parametres"] });
  const modifier = useMutation({
    mutationFn: (v: { id: string; valeur: string }) => api.patch(`/api/analytics/cubes/parametres/${v.id}/`, { valeur: v.valeur }),
    onSuccess: () => {
      setEdit(null);
      setError(null);
      refresh();
    },
    onError: (e) => setError(describeError(e)),
  });
  const confirmer = useMutation({
    mutationFn: (id: string) => api.post(`/api/analytics/cubes/parametres/${id}/confirmer/`),
    onSuccess: () => {
      setError(null);
      refresh();
    },
    onError: (e) => setError(describeError(e)),
  });
  const provisoires = (params.data ?? []).filter((p) => p.est_provisoire).length;
  return (
    <div data-testid="parametres-cube">
      {provisoires > 0 && (
        <p className="action-error" role="note" data-testid="alerte-provisoire-cube">
          {t("cube.warnProvisoire", { count: provisoires })}
        </p>
      )}
      {error && <p className="action-error" role="alert">{error}</p>}
      <table className="table">
        <tbody>
          {(params.data ?? []).map((p) => (
            <tr key={p.id}>
              <td>{p.label}</td>
              <td>
                {edit?.id === p.id ? (
                  <input type="number" min="1" step="1" aria-label={p.label} value={edit.valeur} onChange={(e) => setEdit({ id: p.id, valeur: e.target.value })} />
                ) : (
                  `${p.valeur} ${p.unite}`
                )}
              </td>
              <td><Badge tone={p.est_provisoire ? "warn" : "ok"}>{t(`pilotageGestion.${p.statut_valeur}`)}</Badge></td>
              <td>
                {edit?.id === p.id ? (
                  <>
                    <button type="button" className="btn" onClick={() => modifier.mutate(edit)}>{t("pilotageGestion.valider")}</button>{" "}
                    <button type="button" className="btn ghost" onClick={() => setEdit(null)}>{t("pilotageGestion.annuler")}</button>
                  </>
                ) : (
                  <>
                    <button type="button" className="btn ghost" onClick={() => setEdit({ id: p.id, valeur: p.valeur })}>{t("pilotageGestion.modifier")}</button>{" "}
                    {p.est_provisoire && (
                      <button type="button" className="btn ghost" onClick={() => window.confirm(t("cube.confirmConfirmer")) && confirmer.mutate(p.id)}>
                        {t("pilotageGestion.confirmer")}
                      </button>
                    )}
                  </>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Cubes OLAP à 6 axes (Couche D) : lecture par axe, alimentation idempotente, archive scellée conservée 10 ans. */
export function CubesSection() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [axes, setAxes] = useState<CubeAxe[]>(["periode"]);
  const [periode, setPeriode] = useState(moisPrecedent());
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);

  const cube = useQuery({
    queryKey: ["cube", axes],
    queryFn: () => api.get<CubeLecture>(`/api/analytics/cubes/?axes=${axes.join(",")}`),
    retry: 0,
  });
  const archives = useQuery({
    queryKey: ["cube-archives"],
    queryFn: () => api.listAll<CubeArchive>("/api/analytics/cubes/archives/"),
    retry: 0,
  });
  const refresh = () => {
    void qc.invalidateQueries({ queryKey: ["cube"] });
    void qc.invalidateQueries({ queryKey: ["cube-archives"] });
  };
  const alimenter = useMutation({
    mutationFn: () => api.post<{ faits: number }>("/api/analytics/cubes/alimenter/", { periode }),
    onSuccess: (r) => {
      setError(null);
      setInfo(t("cube.alimente", { periode, count: r.faits }));
      refresh();
    },
    onError: (e) => {
      setInfo(null);
      setError(describeError(e));
    },
  });
  const archiver = useMutation({
    mutationFn: () => api.post<CubeArchive>("/api/analytics/cubes/archives/archiver/", { periode }),
    onSuccess: (a) => {
      setError(null);
      setInfo(t("cube.archive", { periode: a.periode, date: a.conserve_jusqu_au }));
      refresh();
    },
    onError: (e) => {
      setInfo(null);
      setError(describeError(e));
    },
  });

  if (cube.isError) return null; // hors cercle des montants M11 : section masquée
  const basculer = (a: CubeAxe) => setAxes((cur) => (cur.includes(a) ? cur.filter((x) => x !== a) : [...cur, a]));
  const lecture = cube.data;
  return (
    <SectionCard title={t("cube.title")}>
      <div data-testid="cube-olap">
        <p className="muted">{t("cube.hint")}</p>
        <ParametresCube />
        <fieldset className="field">
          <legend>{t("cube.axes")}</legend>
          {AXES.map((a) => (
            <label key={a} style={{ marginRight: 12 }}>
              <input type="checkbox" checked={axes.includes(a)} onChange={() => basculer(a)} /> {t(`cube.axe.${a}`)}
            </label>
          ))}
        </fieldset>
        {error && <p className="action-error" role="alert">{error}</p>}
        {info && <p className="muted" role="status" data-testid="cube-info">{info}</p>}
        <table className="table" data-testid="cube-table">
          <thead>
            <tr>
              {(lecture?.axes ?? axes).map((a) => <th key={a}>{t(`cube.axe.${a}`)}</th>)}
              <th>{t("cube.produits")}</th>
              <th>{t("cube.charges")}</th>
              <th>{t("cube.coutGr")}</th>
              <th>{t("cube.marge")}</th>
            </tr>
          </thead>
          <tbody>
            {(lecture?.rows ?? []).map((r, i) => (
              <tr key={i}>
                {lecture!.axes.map((a) => <td key={a}>{(r[a] as string) || "—"}</td>)}
                <td>{montant(r.produits)}</td>
                <td>{montant(r.charges)}</td>
                <td>{montant(r.cout_gr)}</td>
                <td>{montant(r.marge)}</td>
              </tr>
            ))}
            {lecture && lecture.rows.length === 0 && (
              <tr><td colSpan={lecture.axes.length + 4} className="muted">{t("cube.vide")}</td></tr>
            )}
          </tbody>
        </table>

        <div className="actions">
          <label>
            {t("cube.periode")} <input type="month" aria-label={t("cube.periode")} value={periode} onChange={(e) => setPeriode(e.target.value)} />
          </label>{" "}
          <button type="button" className="btn ghost" disabled={!periode || alimenter.isPending} onClick={() => alimenter.mutate()}>
            {t("cube.alimenterBtn")}
          </button>{" "}
          <button
            type="button"
            className="btn"
            disabled={!periode || archiver.isPending}
            onClick={() => window.confirm(t("cube.confirmArchiver", { periode })) && archiver.mutate()}
          >
            {t("cube.archiverBtn")}
          </button>
        </div>

        <h4 className="subtitle">{t("cube.archivesTitle")}</h4>
        <table className="table" data-testid="cube-archives">
          <tbody>
            {(archives.data ?? []).map((a) => (
              <tr key={a.id}>
                <td>{a.periode}</td>
                <td>{t("cube.conserveJusqu", { date: a.conserve_jusqu_au })}</td>
                <td title={a.sha256}>{a.sha256.slice(0, 12)}…</td>
                <td><Badge tone={a.integre ? "ok" : "err"}>{a.integre ? t("cube.integre") : t("cube.altere")}</Badge></td>
                {a.retention_provisoire && <td><Badge tone="warn">{t("cube.retentionProvisoire")}</Badge></td>}
              </tr>
            ))}
            {archives.data?.length === 0 && <tr><td className="muted">{t("cube.aucuneArchive")}</td></tr>}
          </tbody>
        </table>
      </div>
    </SectionCard>
  );
}
