import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../../api/client";
import { formatNumber } from "../../lib/format";
import { describeError } from "../../lib/offlineQueue";
import type {
  Depot,
  FiabiliteResult,
  MaintenanceCoutsResult,
  OrdreTravail,
  Paginated,
  ParametreMaintenance,
  PieceOT,
  ReapproBesoin,
} from "../../types";
import { Badge, SectionCard } from "../ui";

const montant = (v: string | null) => (v === null ? "••••••" : formatNumber(Number(v)));
const nombre = (v: string | null) => (v === null ? "—" : formatNumber(Number(v)));
const moisCourant = () => new Date().toISOString().slice(0, 7);

/** Fiabilité du parc (CDC M8, publiée à la Couche D) : MTBF / MTTR / disponibilité par machine. */
export function FiabiliteSection() {
  const { t } = useTranslation();
  const q = useQuery({
    queryKey: ["maintenance-fiabilite"],
    queryFn: () => api.get<FiabiliteResult>("/api/maintenance/actifs/fiabilite/"),
    retry: 0,
  });
  if (q.isError || !q.data) return null;
  return (
    <SectionCard title={t("m8.fiabilite.title")}>
      <div data-testid="fiabilite-parc">
        <p className="muted">{t("m8.fiabilite.hint", { jours: q.data.observation_jours })}</p>
        {q.data.provisoire && (
          <p className="action-error" role="note" data-testid="alerte-provisoire-maintenance">{t("m8.fiabilite.warnProvisoire")}</p>
        )}
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>{t("m8.fiabilite.machine")}</th>
                <th className="num">{t("m8.fiabilite.pannes")}</th>
                <th className="num">MTBF (h)</th>
                <th className="num">MTTR (h)</th>
                <th className="num">{t("m8.fiabilite.dispo")}</th>
              </tr>
            </thead>
            <tbody>
              {q.data.rows.map((r) => (
                <tr key={r.actif}>
                  <td>{r.actif} — {r.designation}</td>
                  <td className="num">{r.pannes}</td>
                  <td className="num">{nombre(r.mtbf_h)}</td>
                  <td className="num">{nombre(r.mttr_h)}</td>
                  <td className="num">{r.disponibilite_pct === null ? "—" : `${nombre(r.disponibilite_pct)} %`}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </SectionCard>
  );
}

/** Paramètres M8 (période d'observation, heures de service) : modifiables par ETSL, provisoires puis confirmés. */
export function ParametresMaintenanceSection() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const [edit, setEdit] = useState<{ id: string; valeur: string } | null>(null);
  const params = useQuery({
    queryKey: ["maint-parametres"],
    queryFn: () => api.get<Paginated<ParametreMaintenance>>("/api/maintenance/parametres/").then((p) => p.results),
    retry: 0,
  });
  const refresh = () => {
    void qc.invalidateQueries({ queryKey: ["maint-parametres"] });
    void qc.invalidateQueries({ queryKey: ["maintenance-fiabilite"] });
  };
  const modifier = useMutation({
    mutationFn: (v: { id: string; valeur: string }) => api.patch(`/api/maintenance/parametres/${v.id}/`, { valeur: v.valeur }),
    onSuccess: () => {
      setEdit(null);
      setError(null);
      refresh();
    },
    onError: (e) => setError(describeError(e)),
  });
  const confirmer = useMutation({
    mutationFn: (id: string) => api.post(`/api/maintenance/parametres/${id}/confirmer/`),
    onSuccess: () => {
      setError(null);
      refresh();
    },
    onError: (e) => setError(describeError(e)),
  });

  if (params.isError) return null;
  const provisoires = (params.data ?? []).filter((p) => p.est_provisoire).length;
  return (
    <SectionCard title={t("m8.params.title")}>
      <div data-testid="parametres-maintenance">
        <p className="muted">{t("m8.params.hint")}</p>
        {provisoires > 0 && (
          <p className="action-error" role="note" data-testid="alerte-provisoire-parametres-m8">
            {t("m8.params.warnProvisoire", { count: provisoires })}
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
                        <button type="button" className="btn ghost" onClick={() => window.confirm(t("m8.params.confirmConfirmer")) && confirmer.mutate(p.id)}>
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
    </SectionCard>
  );
}

/** Pièces de rechange : sortie du stock M5 liée à un OT (valorisée au CUMP) et réapprovisionnement sous seuil. */
export function PiecesRechangeSection() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [ot, setOt] = useState("");
  const [article, setArticle] = useState("");
  const [depot, setDepot] = useState("");
  const [quantite, setQuantite] = useState("1");
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);

  const ordres = useQuery({
    queryKey: ["m8-ot-ouverts"],
    queryFn: () => api.listAll<OrdreTravail>("/api/maintenance/ordres/?ouverts=1"),
    retry: 0,
  });
  const articles = useQuery({
    queryKey: ["m8-articles-stock"],
    queryFn: () =>
      api.listAll<{ id: string; code: string; label: string }>("/api/referentiels/articles/?stockable=1"),
    retry: 0,
  });
  const depots = useQuery({
    queryKey: ["m8-depots"],
    queryFn: () => api.listAll<Depot>("/api/stocks/depots/"),
    retry: 0,
  });
  const pieces = useQuery({
    queryKey: ["m8-pieces", ot],
    queryFn: () => api.get<PieceOT[]>(`/api/maintenance/ordres/${ot}/pieces/`),
    enabled: ot !== "",
    retry: 0,
  });
  const reappro = useQuery({
    queryKey: ["m8-reappro"],
    queryFn: () => api.get<{ rows: ReapproBesoin[] }>("/api/maintenance/pieces/reappro/").then((r) => r.rows),
    retry: 0,
  });

  const refresh = () => {
    void qc.invalidateQueries({ queryKey: ["m8-pieces"] });
    void qc.invalidateQueries({ queryKey: ["m8-reappro"] });
    void qc.invalidateQueries({ queryKey: ["maintenance-ordres"] });
    void qc.invalidateQueries({ queryKey: ["maintenance-stats"] });
  };
  const sortir = useMutation({
    mutationFn: () => api.post(`/api/maintenance/ordres/${ot}/sortir-piece/`, { article, depot, quantite }),
    onSuccess: () => {
      setError(null);
      setInfo(t("m8.pieces.sortie"));
      refresh();
    },
    onError: (e) => {
      setInfo(null);
      setError(describeError(e));
    },
  });
  const generer = useMutation({
    mutationFn: () => api.post<{ da: string | null; lignes_ajoutees: number }>("/api/maintenance/pieces/reappro/"),
    onSuccess: (r) => {
      setError(null);
      setInfo(r.da ? t("m8.pieces.daCreee", { da: r.da, n: r.lignes_ajoutees }) : t("m8.pieces.rienAGenerer"));
      refresh();
    },
    onError: (e) => setError(describeError(e)),
  });

  if (ordres.isError) return null;
  const ouverts = (ordres.data ?? []).filter((o) => o.statut === "planifie" || o.statut === "en_cours");
  const pret = ot !== "" && article !== "" && depot !== "" && Number(quantite) > 0;
  return (
    <SectionCard title={t("m8.pieces.title")}>
      <div data-testid="pieces-rechange">
        <p className="muted">{t("m8.pieces.hint")}</p>
        {error && <p className="action-error" role="alert">{error}</p>}
        {info && <p className="muted" role="status" data-testid="pieces-info">{info}</p>}
        <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", alignItems: "center" }}>
          <select aria-label={t("m8.pieces.ot")} value={ot} onChange={(e) => setOt(e.target.value)}>
            <option value="">{t("m8.pieces.ot")}</option>
            {ouverts.map((o) => <option key={o.id} value={o.id}>{o.code} — {o.actif_code}</option>)}
          </select>
          <select aria-label={t("m8.pieces.piece")} value={article} onChange={(e) => setArticle(e.target.value)}>
            <option value="">{t("m8.pieces.piece")}</option>
            {(articles.data ?? []).map((a) => <option key={a.id} value={a.id}>{a.code} — {a.label}</option>)}
          </select>
          <select aria-label={t("m8.pieces.depot")} value={depot} onChange={(e) => setDepot(e.target.value)}>
            <option value="">{t("m8.pieces.depot")}</option>
            {(depots.data ?? []).map((d) => <option key={d.id} value={d.id}>{d.code} — {d.label}</option>)}
          </select>
          <input type="number" min="0.01" step="0.01" aria-label={t("m8.pieces.quantite")} value={quantite} onChange={(e) => setQuantite(e.target.value)} style={{ width: "6rem" }} />
          <button type="button" className="btn" disabled={!pret || sortir.isPending} onClick={() => sortir.mutate()}>{t("m8.pieces.sortir")}</button>
        </div>

        {ot !== "" && (pieces.data ?? []).length > 0 && (
          <table className="table" data-testid="pieces-ot">
            <thead>
              <tr>
                <th>{t("m8.pieces.piece")}</th>
                <th className="num">{t("m8.pieces.quantite")}</th>
                <th className="num">CUMP</th>
                <th className="num">{t("m8.pieces.total")}</th>
              </tr>
            </thead>
            <tbody>
              {(pieces.data ?? []).map((p) => (
                <tr key={p.id}>
                  <td>{p.article_code} — {p.article_label}</td>
                  <td className="num">{nombre(p.quantite)}</td>
                  <td className="num">{montant(p.cout_unitaire)}</td>
                  <td className="num">{montant(p.cout_total)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        <h4>{t("m8.pieces.reappro")}</h4>
        {(reappro.data ?? []).length === 0 ? (
          <p className="muted">{t("m8.pieces.aucunBesoin")}</p>
        ) : (
          <div data-testid="reappro-pieces">
            <table className="table">
              <thead>
                <tr>
                  <th>{t("m8.pieces.piece")}</th>
                  <th className="num">{t("m8.pieces.stock")}</th>
                  <th className="num">{t("m8.pieces.seuil")}</th>
                  <th className="num">{t("m8.pieces.aCommander")}</th>
                </tr>
              </thead>
              <tbody>
                {(reappro.data ?? []).map((b) => (
                  <tr key={b.article_id}>
                    <td>{b.article} — {b.designation}</td>
                    <td className="num">{nombre(b.stock)}</td>
                    <td className="num">{nombre(b.seuil)}</td>
                    <td className="num">{nombre(b.a_commander)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <button type="button" className="btn ghost" disabled={generer.isPending} onClick={() => generer.mutate()}>{t("m8.pieces.genererDa")}</button>
          </div>
        )}
      </div>
    </SectionCard>
  );
}

/** Flux M8 → M11 : coût de maintenance du mois par machine (GR isolé au compte 618), sans écriture comptable. */
export function MaintenanceCoutsSection() {
  const { t } = useTranslation();
  const [periode, setPeriode] = useState(moisCourant());
  const q = useQuery({
    queryKey: ["cg-maintenance-couts", periode],
    queryFn: () => api.get<MaintenanceCoutsResult>(`/api/controle-gestion/maintenance-couts/?periode=${periode}`),
    enabled: /^\d{4}-\d{2}$/.test(periode),
    retry: 0,
  });
  if (q.isError && !q.data) return null;
  return (
    <SectionCard title={t("m8.couts.title")}>
      <div data-testid="maintenance-couts">
        <p className="muted">{t("m8.couts.hint")}</p>
        <label>
          {t("m8.couts.periode")}{" "}
          <input type="month" value={periode} onChange={(e) => setPeriode(e.target.value)} aria-label={t("m8.couts.periode")} />
        </label>
        {q.data && q.data.rows.length === 0 && <p className="muted">{t("m8.couts.aucun")}</p>}
        {q.data && q.data.rows.length > 0 && (
          <table className="table">
            <thead>
              <tr>
                <th>{t("m8.fiabilite.machine")}</th>
                <th className="num">OT</th>
                <th className="num">{t("m8.couts.mo")}</th>
                <th className="num">{t("m8.couts.pieces")}</th>
                <th className="num">{t("m8.couts.total")}</th>
              </tr>
            </thead>
            <tbody>
              {q.data.rows.map((r) => (
                <tr key={r.actif}>
                  <td>{r.actif} — {r.designation} {r.gr && <Badge tone="warn">618</Badge>}</td>
                  <td className="num">{r.nb_ot}</td>
                  <td className="num">{montant(r.main_oeuvre)}</td>
                  <td className="num">{montant(r.pieces)}</td>
                  <td className="num">{montant(r.total)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {q.data && (
          <p>
            {t("m8.couts.totalGr")} (618) : <strong>{montant(q.data.totaux.gr_618)}</strong> · {t("m8.couts.totalHorsGr")} : <strong>{montant(q.data.totaux.hors_gr)}</strong>
          </p>
        )}
      </div>
    </SectionCard>
  );
}
