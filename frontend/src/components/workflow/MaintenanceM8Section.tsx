import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Gauge } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../../api/client";
import { formatMoney, formatParametre, formatPercent } from "../../lib/format";
import { describeError } from "../../lib/offlineQueue";
import type {
  Depot,
  FiabiliteResult,
  MaintenanceCoutsResult,
  OrdreTravail,
  ParametreMaintenance,
  PieceOT,
  ReapproBesoin,
} from "../../types";
import { Badge, currentMonth, MonthPicker, SectionCard } from "../ui";
import { ParamsPanel } from "../parametres/ParamsPanel";
import { ParamValueTable } from "../parametres/ParamValueTable";

const montant = (v: string | null) => (v === null ? "••••••" : formatMoney(v));
/** Nombre sans décimales inutiles (« 24 », « 2,5 ») : jamais « 24.00 ». */
const nombre = (v: string | null) => (v === null ? "—" : formatParametre(v, null));
/** Valeur lisible d'un paramètre (« 24 heures », « 15 000 FCFA/h », « 661000 ») ; espace simple avant l'unité finale. */
const valeurParametre = (valeur: string, unite: string) => formatParametre(valeur, unite).replace(/\u00a0(?=[^\d\u00a0]+$)/, " ");
/** Nombre de machines affichées avant « Voir plus » (les machines sous le seuil viennent en tête). */
const FIABILITE_LIGNES = 8;

/** Fiabilité du parc (CDC M8, publiée à la Couche D) : MTBF / MTTR / disponibilité par machine. */
export function FiabiliteSection() {
  const { t } = useTranslation();
  const [tout, setTout] = useState(false);
  const q = useQuery({
    queryKey: ["maintenance-fiabilite"],
    queryFn: () => api.get<FiabiliteResult>("/api/maintenance/actifs/fiabilite/"),
    retry: 0,
  });
  if (q.isError || !q.data) return null;
  // Machines sous le seuil d'abord (tri stable), puis les machines conformes ; liste repliée au-delà de 8 lignes.
  const lignes = [...q.data.rows].sort((a, b) => Number(b.alertes.length > 0) - Number(a.alertes.length > 0));
  const sousSeuil = lignes.filter((r) => r.alertes.length > 0).length;
  const visibles = tout ? lignes : lignes.slice(0, FIABILITE_LIGNES);
  return (
    <SectionCard title={t("m8.fiabilite.title")}>
      <div data-testid="fiabilite-parc">
        <p className="muted">{t("m8.fiabilite.hint", { jours: q.data.observation_jours })}</p>
        <p className="muted">{t("m8e.fiab.seuils", { dispo: nombre(q.data.seuil_disponibilite_pct), mtbf: nombre(q.data.seuil_mtbf_h) })}</p>
        {q.data.provisoire && (
          <div className="banner warn" role="note" data-testid="alerte-provisoire-maintenance">
            <Gauge size={18} aria-hidden />
            <div className="banner-body">
              <p className="banner-text">{t("m8.fiabilite.warnProvisoire")}</p>
            </div>
          </div>
        )}
        <p className="muted">{t("revueKit.ops.fiabilite.resume", { count: lignes.length, sousSeuil })}</p>
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>{t("m8.fiabilite.machine")}</th>
                <th className="num">{t("m8.fiabilite.pannes")}</th>
                <th className="num">MTBF (h)</th>
                <th className="num">MTTR (h)</th>
                <th className="num">{t("m8.fiabilite.dispo")}</th>
                <th>{t("m8e.fiab.etat")}</th>
              </tr>
            </thead>
            <tbody>
              {visibles.map((r) => (
                <tr key={r.actif}>
                  <td>{r.actif} — {r.designation}</td>
                  <td className="num">{r.pannes}</td>
                  <td className="num">{nombre(r.mtbf_h)}</td>
                  <td className="num">{nombre(r.mttr_h)}</td>
                  <td className="num cell-nowrap">{r.disponibilite_pct === null ? "—" : formatPercent(r.disponibilite_pct, { decimals: 1 })}</td>
                  <td>
                    {r.alertes.length > 0 ? (
                      <>
                        <Badge tone="err">{t("m8e.fiab.sousSeuil")}</Badge>
                        <span className="cell-sub">{r.alertes.join(" ; ")}</span>
                      </>
                    ) : (
                      <Badge tone="ok">{t("m8e.fiab.ok")}</Badge>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {lignes.length > FIABILITE_LIGNES && (
          <button type="button" className="btn ghost sm" aria-expanded={tout} onClick={() => setTout((v) => !v)}>
            {tout ? t("revueKit.ops.fiabilite.reduire") : t("revueKit.ops.fiabilite.voirPlus", { count: lignes.length - FIABILITE_LIGNES })}
          </button>
        )}
      </div>
    </SectionCard>
  );
}

/** Paramètres M8 (période d'observation, heures de service) : modifiables par ETSL, provisoires puis confirmés. */
export function ParametresMaintenanceSection() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const params = useQuery({
    queryKey: ["maint-parametres"],
    queryFn: () => api.listAll<ParametreMaintenance>("/api/maintenance/parametres/"),
    retry: 0,
  });
  const refresh = () => {
    void qc.invalidateQueries({ queryKey: ["maint-parametres"] });
    void qc.invalidateQueries({ queryKey: ["maintenance-fiabilite"] });
  };
  const modifier = useMutation({
    mutationFn: (v: { id: string; valeur: string }) => api.patch(`/api/maintenance/parametres/${v.id}/`, { valeur: v.valeur }),
    onSuccess: () => {
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
    <ParamsPanel
      variant="card"
      module="maintenance"
      title={t("m8.params.title")}
      count={params.data ? provisoires : undefined}
      total={params.data?.length}
      testId="parametres-maintenance"
      alertTestId="alerte-provisoire-parametres-m8"
    >
      <p className="muted">{t("m8.params.hint")}</p>
      {error && <p className="action-error" role="alert">{error}</p>}
      <ParamValueTable
        rows={params.data ?? []}
        caption={t("m8.params.title")}
        libelle={(p) => t(`revueKit.ops.param.libelles.${p.code}`, { defaultValue: p.label })}
        valeur={(p) => valeurParametre(p.valeur, p.unite)}
        min="1"
        pending={modifier.isPending || confirmer.isPending}
        confirmMessage={t("m8.params.confirmConfirmer")}
        onSave={(id, valeur) => modifier.mutateAsync({ id, valeur })}
        onConfirm={(id) => confirmer.mutate(id)}
      />
    </ParamsPanel>
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
        <div className="list-toolbar">
          <div className="field">
            <label htmlFor="pieces-rechange-ot">{t("m8.pieces.ot")}</label>
            <select id="pieces-rechange-ot" className="control" value={ot} onChange={(e) => setOt(e.target.value)}>
              <option value="">—</option>
              {ouverts.map((o) => <option key={o.id} value={o.id}>{o.code} — {o.actif_code}</option>)}
            </select>
          </div>
          <div className="field">
            <label htmlFor="pieces-rechange-piece">{t("m8.pieces.piece")}</label>
            <select id="pieces-rechange-piece" className="control" value={article} onChange={(e) => setArticle(e.target.value)}>
              <option value="">—</option>
              {(articles.data ?? []).map((a) => <option key={a.id} value={a.id}>{a.code} — {a.label}</option>)}
            </select>
          </div>
          <div className="field">
            <label htmlFor="pieces-rechange-depot">{t("m8.pieces.depot")}</label>
            <select id="pieces-rechange-depot" className="control" value={depot} onChange={(e) => setDepot(e.target.value)}>
              <option value="">—</option>
              {(depots.data ?? []).map((d) => <option key={d.id} value={d.id}>{d.code} — {d.label}</option>)}
            </select>
          </div>
          <div className="field">
            <label htmlFor="pieces-rechange-quantite">{t("m8.pieces.quantite")}</label>
            <input id="pieces-rechange-quantite" className="control" type="number" min="0.01" step="0.01" value={quantite} onChange={(e) => setQuantite(e.target.value)} />
          </div>
          <button type="button" className="btn ghost" disabled={!pret || sortir.isPending} onClick={() => sortir.mutate()}>{t("m8.pieces.sortir")}</button>
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
                  <td className="num cell-nowrap">{montant(p.cout_unitaire)}</td>
                  <td className="num cell-nowrap">{montant(p.cout_total)}</td>
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
  const [periode, setPeriode] = useState(currentMonth());
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
        <div className="list-toolbar">
          <div className="field">
            <label htmlFor="maintenance-couts-mois">{t("m8.couts.periode")}</label>
            <MonthPicker id="maintenance-couts-mois" value={periode} onChange={setPeriode} />
          </div>
        </div>
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
                  <td className="num cell-nowrap">{montant(r.main_oeuvre)}</td>
                  <td className="num cell-nowrap">{montant(r.pieces)}</td>
                  <td className="num cell-nowrap">{montant(r.total)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {q.data && (
          <p>
            {t("revueKit.ops.gr.total")} (618) : <strong className="cell-nowrap">{montant(q.data.totaux.gr_618)}</strong> · {t("revueKit.ops.gr.totalHors")} :{" "}
            <strong className="cell-nowrap">{montant(q.data.totaux.hors_gr)}</strong>
          </p>
        )}
      </div>
    </SectionCard>
  );
}
