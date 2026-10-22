import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Archive, RefreshCw } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../../api/client";
import { formatDate, formatMoney, formatNumber } from "../../lib/format";
import { describeError } from "../../lib/offlineQueue";
import type { CubeArchive, CubeAxe, CubeLecture, ParametreCube } from "../../types";
import { Badge, DataGrid, notify } from "../ui";
import type { GridColumn } from "../ui";

const AXES: CubeAxe[] = ["affaire", "chantier", "site", "activite", "centre", "periode"];
const moisPrecedent = () => {
  const d = new Date();
  d.setMonth(d.getMonth() - 1);
  return d.toISOString().slice(0, 7);
};
/** Paramètre de type liste (destinataires des alertes calendaires) : la valeur est le texte (rôles séparés par « , »). */
const estTexte = (p: ParametreCube) => p.unite === "rôles";
const texte = (p: ParametreCube) => (p as ParametreCube & { texte?: string }).texte ?? "";
/** « direction,finance » → « Direction, finance » (jamais d'identifiant brut à l'écran). */
const lisible = (s: string) =>
  s
    .split(",")
    .map((x) => x.trim().replace(/_/g, " "))
    .filter(Boolean)
    .join(", ")
    .replace(/^./, (c) => c.toUpperCase());
const valeur = (v: string) => {
  const n = Number(v);
  return Number.isFinite(n) ? formatNumber(n, { decimals: n % 1 ? 2 : 0 }) : v;
};

/** Durée de conservation de l'archive du cube et destinataires : données ETSL modifiables, provisoires puis confirmées. */
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
    mutationFn: (v: { id: string; valeur: string; texte?: boolean }) =>
      api.patch(`/api/analytics/cubes/parametres/${v.id}/`, v.texte ? { texte: v.valeur } : { valeur: v.valeur }),
    onSuccess: () => {
      setEdit(null);
      setError(null);
      notify.success(t("cube2.parametreModifie"));
      refresh();
    },
    onError: (e) => setError(describeError(e)),
  });
  const confirmer = useMutation({
    mutationFn: (id: string) => api.post(`/api/analytics/cubes/parametres/${id}/confirmer/`),
    onSuccess: () => {
      setError(null);
      notify.success(t("cube2.parametreConfirme"));
      refresh();
    },
    onError: (e) => setError(describeError(e)),
  });
  const provisoires = (params.data ?? []).filter((p) => p.est_provisoire).length;
  return (
    <div data-testid="parametres-cube" className="cube-params">
      <div className="cube-block-head">
        <h4 className="dir-panel-title">{t("cube2.parametres")}</h4>
        {provisoires > 0 && (
          <span className="cube-warn" role="note" data-testid="alerte-provisoire-cube">
            {t("cube.warnProvisoire", { count: provisoires })}
          </span>
        )}
      </div>
      {error && (
        <p className="action-error" role="alert">
          {error}
        </p>
      )}
      <div className="table-wrap">
        <table className="table cube-params-table">
          <caption className="sr-only">{t("cube2.parametres")}</caption>
          <tbody>
            {(params.data ?? []).map((p) => (
              <tr key={p.id}>
                <td>{p.label}</td>
                <td className="cube-param-value">
                  {edit?.id === p.id ? (
                    estTexte(p) ? (
                      <input className="control" aria-label={p.label} value={edit.valeur} onChange={(e) => setEdit({ id: p.id, valeur: e.target.value })} />
                    ) : (
                      <input
                        className="control"
                        type="number"
                        min="0"
                        step="1"
                        aria-label={p.label}
                        value={edit.valeur}
                        onChange={(e) => setEdit({ id: p.id, valeur: e.target.value })}
                      />
                    )
                  ) : estTexte(p) ? (
                    lisible(texte(p))
                  ) : (
                    `${valeur(p.valeur)} ${p.unite}`
                  )}
                </td>
                <td>
                  <Badge tone={p.est_provisoire ? "warn" : "ok"}>{t(`pilotageGestion.${p.statut_valeur}`)}</Badge>
                </td>
                <td className="cube-param-actions">
                  {edit?.id === p.id ? (
                    <>
                      <button type="button" className="btn primary sm" onClick={() => modifier.mutate({ ...edit, texte: estTexte(p) })}>
                        {t("pilotageGestion.valider")}
                      </button>
                      <button type="button" className="btn ghost sm" onClick={() => setEdit(null)}>
                        {t("pilotageGestion.annuler")}
                      </button>
                    </>
                  ) : (
                    <>
                      {p.est_provisoire && (
                        <button type="button" className="btn ghost sm" onClick={() => window.confirm(t("cube.confirmConfirmer")) && confirmer.mutate(p.id)}>
                          {t("pilotageGestion.confirmer")}
                        </button>
                      )}
                      <button type="button" className="btn ghost sm" onClick={() => setEdit({ id: p.id, valeur: estTexte(p) ? texte(p) : p.valeur })}>
                        {t("pilotageGestion.modifier")}
                      </button>
                    </>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

type Ligne = CubeLecture["rows"][number] & { id: number };

/** Cubes OLAP à 6 axes : lecture par axe, alimentation idempotente, archive scellée conservée 10 ans. */
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
      setInfo(t("cube.archive", { periode: a.periode, date: formatDate(a.conserve_jusqu_au) }));
      refresh();
    },
    onError: (e) => {
      setInfo(null);
      setError(describeError(e));
    },
  });

  if (cube.isError) return null; // hors cercle des montants : section masquée
  const basculer = (a: CubeAxe) => setAxes((cur) => (cur.includes(a) ? cur.filter((x) => x !== a) : [...cur, a]));
  const lecture = cube.data;
  const axesLus = lecture?.axes ?? axes;
  const rows: Ligne[] = (lecture?.rows ?? []).map((r, i) => ({ ...r, id: i }));
  const columns: GridColumn<Ligne>[] = [
    ...axesLus.map((a) => ({ key: a, header: t(`cube.axe.${a}`), render: (r: Ligne) => (r[a] as string) || "—", sortValue: (r: Ligne) => (r[a] as string) ?? "" })),
    { key: "produits", header: t("cube.produits"), num: true, render: (r) => formatMoney(r.produits), sortValue: (r) => Number(r.produits) },
    { key: "charges", header: t("cube.charges"), num: true, render: (r) => formatMoney(r.charges), sortValue: (r) => Number(r.charges) },
    { key: "cout_gr", header: t("cube2.coutGr"), num: true, render: (r) => formatMoney(r.cout_gr), sortValue: (r) => Number(r.cout_gr) },
    { key: "marge", header: t("cube.marge"), num: true, render: (r) => <strong>{formatMoney(r.marge)}</strong>, sortValue: (r) => Number(r.marge) },
  ];
  const archiveCols: GridColumn<CubeArchive>[] = [
    { key: "periode", header: t("cube.periode"), render: (a) => <strong>{a.periode}</strong>, sortValue: (a) => a.periode },
    { key: "faits", header: t("cube2.faits"), num: true, render: (a) => formatNumber(a.nb_faits) },
    {
      key: "conserve",
      header: t("cube2.conservation"),
      render: (a) => (
        <>
          {t("cube.conserveJusqu", { date: formatDate(a.conserve_jusqu_au) })}
          {a.retention_provisoire ? (
            <>
              {" "}
              <Badge tone="warn">{t("cube2.provisoire")}</Badge>
            </>
          ) : null}
        </>
      ),
    },
    {
      key: "sha",
      header: t("cube2.empreinte"),
      render: (a) => (
        <code className="dir-hash" title={a.sha256}>
          {a.sha256.slice(0, 12)}…
        </code>
      ),
    },
    { key: "integre", header: t("cube2.integrite"), render: (a) => <Badge tone={a.integre ? "ok" : "err"}>{a.integre ? t("cube.integre") : t("cube.altere")}</Badge> },
  ];

  return (
    <div data-testid="cube-olap" className="cube">
      <p className="dir-note">{t("cube.hint")}</p>

      <fieldset className="cube-axes">
        <legend>{t("cube.axes")}</legend>
        {AXES.map((a) => (
          <label key={a} className={`cube-axe${axes.includes(a) ? " is-on" : ""}`}>
            <input type="checkbox" checked={axes.includes(a)} onChange={() => basculer(a)} /> {t(`cube.axe.${a}`)}
          </label>
        ))}
      </fieldset>

      <div data-testid="cube-table">
        <DataGrid
          columns={columns}
          rows={rows}
          loading={cube.isPending}
          caption={t("cube2.lecture")}
          density="compact"
          maxHeight={480}
          emptyLabel={t("cube.vide")}
        />
      </div>

      <div className="cube-actions">
        <div className="field cube-month">
          <label htmlFor="cube-periode">{t("cube.periode")}</label>
          <input id="cube-periode" className="control" type="month" aria-label={t("cube.periode")} value={periode} onChange={(e) => setPeriode(e.target.value)} />
        </div>
        <button type="button" className="btn ghost" disabled={!periode || alimenter.isPending} onClick={() => alimenter.mutate()}>
          <RefreshCw size={15} aria-hidden />
          {t("cube.alimenterBtn")}
        </button>
        <button
          type="button"
          className="btn primary"
          disabled={!periode || archiver.isPending}
          onClick={() => window.confirm(t("cube.confirmArchiver", { periode })) && archiver.mutate()}
        >
          <Archive size={15} aria-hidden />
          {t("cube.archiverBtn")}
        </button>
      </div>
      {error && (
        <p className="action-error" role="alert">
          {error}
        </p>
      )}
      {info && (
        <p className="cube-info" role="status" data-testid="cube-info">
          {info}
        </p>
      )}

      <h4 className="dir-panel-title">{t("cube.archivesTitle")}</h4>
      <div data-testid="cube-archives">
        <DataGrid
          columns={archiveCols}
          rows={archives.data ?? []}
          loading={archives.isPending}
          caption={t("cube.archivesTitle")}
          density="compact"
          maxHeight={360}
          emptyLabel={t("cube.aucuneArchive")}
        />
      </div>

      <ParametresCube />
    </div>
  );
}
