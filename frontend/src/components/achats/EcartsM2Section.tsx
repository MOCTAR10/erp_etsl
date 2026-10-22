import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../../api/client";
import { formatDate, formatMoney, formatNumber } from "../../lib/format";
import { describeError } from "../../lib/offlineQueue";
import { ActionBar, Badge, QuickForm, SectionCard } from "../ui";

interface Parametre {
  id: string;
  code: string;
  label: string;
  valeur: string;
  unite: string;
  est_provisoire: boolean;
}
interface LigneCatalogue {
  id: number;
  code: string;
  nom: string;
  is_global_rental: boolean;
  agree_qualite_jusqu: string | null;
  agree_hse_jusqu: string | null;
  etat: "agree" | "a_renouveler" | "non_agree" | "intra_groupe";
  jours_restants: number | null;
  demande_en_cours: boolean;
  note: number | null;
  commandes: number;
}
interface Agrement {
  id: string;
  code: string;
  fournisseur_nom: string;
  domaine: string;
  domaine_label: string;
  reference: string;
  date_fin: string | null;
  statut: string;
  statut_label: string;
}
interface Regle {
  id: string;
  article_type: string;
  article_type_label: string;
  article_code: string | null;
  exige_itp: boolean;
  exige_cnd: boolean;
  methode_cnd: string;
  is_active: boolean;
  est_provisoire: boolean;
}
interface Avoir {
  id: string;
  code: string;
  facture_code: string;
  fournisseur_nom: string | null;
  date_avoir: string;
  montant_ht: string | null;
  motif: string;
  statut: string;
  statut_label: string;
  move_number: string | null;
}
interface Piece {
  nature: string;
  piece: string;
  titre: string;
  archive_le: string;
  conservation_ans: number | null;
}
interface Ref {
  id: string | number;
  code: string;
  title?: string;
  name?: string;
  label?: string;
  status?: string;
  supplier_name?: string | null;
  order_code?: string;
}

const ETAT_TONE = { agree: "ok", a_renouveler: "warn", non_agree: "err", intra_groupe: "brand" } as const;
const TYPES_ARTICLE = ["matiere", "consommable", "produit", "service"];
const opt = (rows: Ref[], label: (r: Ref) => string) => rows.map((r) => ({ value: String(r.id), label: label(r) }));
const useRefs = (key: string, path: string) =>
  useQuery({ queryKey: ["m2e", key], queryFn: () => api.listAll<Ref>(path), retry: 0 }).data ?? [];

/** Paramètres M2 attendus d'ETSL : provisoires tant qu'ils ne sont pas confirmés. */
function ParametresAchats() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [edit, setEdit] = useState<{ id: string; valeur: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const q = useQuery({ queryKey: ["m2e", "parametres"], queryFn: () => api.listAll<Parametre>("/api/achats/parametres/"), retry: 0 });
  const done = () => {
    setError(null);
    setEdit(null);
    void qc.invalidateQueries();
  };
  const modifier = useMutation({
    mutationFn: (v: { id: string; valeur: string }) => api.patch(`/api/achats/parametres/${v.id}/`, { valeur: v.valeur }),
    onSuccess: done,
    onError: (e) => setError(describeError(e)),
  });
  const confirmer = useMutation({
    mutationFn: (id: string) => api.post(`/api/achats/parametres/${id}/confirmer/`),
    onSuccess: done,
    onError: (e) => setError(describeError(e)),
  });
  if (q.isError || !q.data) return null;
  const provisoires = q.data.filter((p) => p.est_provisoire).length;
  return (
    <div data-testid="parametres-achats">
      {provisoires > 0 && (
        <p className="action-error" role="note">
          {t("ecarts_m2.params.warn", { count: provisoires })}
        </p>
      )}
      {error && (
        <p className="action-error" role="alert">
          {error}
        </p>
      )}
      <table className="table">
        <caption className="sr-only">{t("ecarts_m2.params.title")}</caption>
        <tbody>
          {q.data.map((p) => (
            <tr key={p.id}>
              <td>{p.label}</td>
              <td className="num">
                {edit?.id === p.id ? (
                  <input type="number" min={0} step="1" aria-label={p.label} value={edit.valeur} onChange={(e) => setEdit({ id: p.id, valeur: e.target.value })} />
                ) : (
                  `${formatNumber(Number(p.valeur))} ${p.unite === "choix" ? "" : p.unite}`
                )}
              </td>
              <td>
                <Badge tone={p.est_provisoire ? "warn" : "ok"}>{p.est_provisoire ? t("ecarts_m2.provisoire") : t("ecarts_m2.confirme")}</Badge>
              </td>
              <td>
                {edit?.id === p.id ? (
                  <>
                    <button type="button" className="btn" onClick={() => modifier.mutate(edit)}>
                      {t("ecarts_m2.params.enregistrer")}
                    </button>{" "}
                    <button type="button" className="btn ghost" onClick={() => setEdit(null)}>
                      {t("ecarts_m2.params.annuler")}
                    </button>
                  </>
                ) : (
                  <>
                    <button type="button" className="btn ghost" onClick={() => setEdit({ id: p.id, valeur: p.valeur })}>
                      {t("ecarts_m2.params.modifier")}
                    </button>{" "}
                    {p.est_provisoire && (
                      <button type="button" className="btn ghost" onClick={() => window.confirm(t("ecarts_m2.params.confirmQuestion")) && confirmer.mutate(p.id)}>
                        {t("ecarts_m2.params.confirmer")}
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

/** Écarts M2 : catalogue / agréments M6-M7, inspections ITP / CND, lot + certificat à réception, circuit affaire → DA,
 * location GR → BC, avoirs fournisseurs, pièces archivées en GED, paramètres provisoires. */
export function EcartsM2Section() {
  const { t } = useTranslation();
  const catalogue = useQuery({
    queryKey: ["m2e", "catalogue"],
    queryFn: () => api.get<{ rows: LigneCatalogue[]; alerte_jours: number }>("/api/achats/agrements/catalogue/"),
    retry: 0,
  }).data;
  const agrements = useQuery({ queryKey: ["m2e", "agrements"], queryFn: () => api.listAll<Agrement>("/api/achats/agrements/?statut=demande"), retry: 0 }).data ?? [];
  const regles = useQuery({ queryKey: ["m2e", "regles"], queryFn: () => api.listAll<Regle>("/api/achats/regles-inspection/"), retry: 0 }).data ?? [];
  const avoirs = useQuery({ queryKey: ["m2e", "avoirs"], queryFn: () => api.listAll<Avoir>("/api/achats/avoirs/"), retry: 0 }).data ?? [];
  const pieces = useQuery({
    queryKey: ["m2e", "pieces"],
    queryFn: () => api.get<{ rows: Piece[]; conservation_ans: number }>("/api/achats/orders/pieces-archivees/"),
    retry: 0,
  }).data;
  const articles = useRefs("articles", "/api/referentiels/articles/");
  const affaires = useRefs("affaires", "/api/commercial/affaires/");
  const locations = useRefs("locations", "/api/logistique/locations/");
  const factures = useRefs("factures", "/api/achats/invoices/?status=comptabilisee");
  const receptions = useRefs("receptions", "/api/achats/receipts/");
  const lignesBc = useRefs("lignes-bc", "/api/achats/order-lines/");

  const fournisseurs = (catalogue?.rows ?? []).map((f) => ({ value: String(f.id), label: `${f.code} · ${f.nom}` }));
  const ouiNon = [
    { value: "true", label: t("ecarts_m2.oui") },
    { value: "false", label: t("ecarts_m2.non") },
  ];
  const bools = (v: Record<string, string>) => ({ ...v, exige_itp: v.exige_itp === "true", exige_cnd: v.exige_cnd === "true" });

  return (
    <>
      <SectionCard title={t("ecarts_m2.catalogue.title")}>
        <div className="action-bar-buttons">
          <QuickForm
            title={t("ecarts_m2.catalogue.demander")}
            endpoint="/api/achats/agrements/"
            fields={[
              { name: "fournisseur", label: t("ecarts_m2.catalogue.fournisseur"), type: "select", required: true, options: fournisseurs },
              {
                name: "domaine",
                label: t("ecarts_m2.catalogue.domaine"),
                type: "select",
                required: true,
                defaultValue: "qualite",
                options: [
                  { value: "qualite", label: t("ecarts_m2.catalogue.qualite") },
                  { value: "hse", label: t("ecarts_m2.catalogue.hse") },
                ],
              },
              { name: "reference", label: t("ecarts_m2.catalogue.reference") },
              { name: "date_evaluation", label: t("ecarts_m2.catalogue.dateEvaluation"), type: "date" },
              { name: "date_fin", label: t("ecarts_m2.catalogue.dateFin"), type: "date" },
              { name: "note_evaluation", label: t("ecarts_m2.catalogue.noteEvaluation"), type: "number", min: 0 },
            ]}
          />
        </div>
        {agrements.length > 0 && (
          <table className="table" data-testid="agrements-en-attente">
            <caption>{t("ecarts_m2.catalogue.enAttente")}</caption>
            <tbody>
              {agrements.map((a) => (
                <tr key={a.id}>
                  <td>
                    {a.code} · {a.fournisseur_nom}
                  </td>
                  <td>{a.domaine_label}</td>
                  <td>{a.reference || "—"}</td>
                  <td>
                    <ActionBar
                      actions={[
                        { label: t("ecarts_m2.catalogue.valider"), path: `/api/achats/agrements/${a.id}/valider/` },
                        { label: t("ecarts_m2.catalogue.refuser"), path: `/api/achats/agrements/${a.id}/refuser/`, tone: "danger", prompt: { name: "motif", label: t("ecarts_m2.catalogue.motif") } },
                      ]}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <table className="table" data-testid="catalogue-fournisseurs">
          <thead>
            <tr>
              <th>{t("ecarts_m2.catalogue.fournisseur")}</th>
              <th>{t("ecarts_m2.catalogue.qualite")}</th>
              <th>{t("ecarts_m2.catalogue.hse")}</th>
              <th>{t("ecarts_m2.catalogue.etat")}</th>
              <th>{t("ecarts_m2.catalogue.note")}</th>
            </tr>
          </thead>
          <tbody>
            {(catalogue?.rows ?? []).map((f) => (
              <tr key={f.id}>
                <td>
                  {f.code} · {f.nom}
                </td>
                <td>{f.agree_qualite_jusqu ? formatDate(f.agree_qualite_jusqu) : "—"}</td>
                <td>{f.agree_hse_jusqu ? formatDate(f.agree_hse_jusqu) : "—"}</td>
                <td>
                  <Badge tone={ETAT_TONE[f.etat]}>{t(`ecarts_m2.catalogue.etats.${f.etat}`)}</Badge>
                  {f.etat === "a_renouveler" && f.jours_restants !== null ? ` J-${f.jours_restants}` : ""}
                  {f.demande_en_cours && <Badge tone="neutral">{t("ecarts_m2.catalogue.demandeEnCours")}</Badge>}
                </td>
                <td>{f.note === null ? "—" : `${f.note} / 100`}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="muted">{t("ecarts_m2.catalogue.note_bas", { jours: catalogue?.alerte_jours ?? 30 })}</p>
      </SectionCard>

      <SectionCard title={t("ecarts_m2.reception.title")}>
        <div className="action-bar-buttons">
          <QuickForm
            title={t("ecarts_m2.reception.ligneLot")}
            endpoint="/api/achats/receipt-lines/"
            fields={[
              { name: "receipt", label: t("ecarts_m2.reception.reception"), type: "select", required: true, options: opt(receptions.filter((r) => r.status === "en_attente"), (r) => `${r.code} · ${r.order_code ?? ""}`) },
              { name: "purchase_order_line", label: t("ecarts_m2.reception.ligneBc"), type: "select", required: true, options: opt(lignesBc, (r) => `${r.order_code ?? ""} · ${r.label ?? ""}`) },
              { name: "quantity", label: t("ecarts_m2.reception.quantite"), type: "number", required: true, min: 0, step: "0.01" },
              { name: "numero_lot", label: t("ecarts_m2.reception.lot") },
              { name: "numero_coulee", label: t("ecarts_m2.reception.coulee") },
              { name: "date_peremption", label: t("ecarts_m2.reception.peremption"), type: "date" },
              {
                name: "certificat_type",
                label: t("ecarts_m2.reception.certificat"),
                type: "select",
                options: [
                  { value: "mtc", label: "MTC" },
                  { value: "coc", label: "CoC" },
                ],
              },
              { name: "numero_certificat", label: t("ecarts_m2.reception.numeroCertificat") },
              { name: "organisme_certificat", label: t("ecarts_m2.reception.organisme") },
            ]}
          />
          <QuickForm
            title={t("ecarts_m2.inspection.ajouter")}
            endpoint="/api/achats/regles-inspection/"
            transform={bools}
            fields={[
              { name: "article_type", label: t("ecarts_m2.inspection.categorie"), type: "select", options: TYPES_ARTICLE.map((v) => ({ value: v, label: t(`ecarts_m2.inspection.types.${v}`) })) },
              { name: "article", label: t("ecarts_m2.inspection.article"), type: "select", options: opt(articles, (a) => `${a.code} · ${a.label ?? ""}`) },
              { name: "exige_itp", label: t("ecarts_m2.inspection.itp"), type: "select", required: true, defaultValue: "true", options: ouiNon },
              { name: "exige_cnd", label: t("ecarts_m2.inspection.cnd"), type: "select", required: true, defaultValue: "false", options: ouiNon },
              {
                name: "methode_cnd",
                label: t("ecarts_m2.inspection.methode"),
                type: "select",
                options: ["RT", "UT", "PT", "MT"].map((m) => ({ value: m, label: m })),
              },
            ]}
          />
        </div>
        <table className="table" data-testid="regles-inspection">
          <thead>
            <tr>
              <th>{t("ecarts_m2.inspection.cible")}</th>
              <th>{t("ecarts_m2.inspection.itp")}</th>
              <th>{t("ecarts_m2.inspection.cnd")}</th>
              <th>{t("ecarts_m2.inspection.statut")}</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {regles.map((r) => (
              <tr key={r.id}>
                <td>{r.article_code ?? r.article_type_label}</td>
                <td>{r.exige_itp ? t("ecarts_m2.oui") : t("ecarts_m2.non")}</td>
                <td>{r.exige_cnd ? `${t("ecarts_m2.oui")} ${r.methode_cnd}` : t("ecarts_m2.non")}</td>
                <td>
                  <Badge tone={r.est_provisoire ? "warn" : "ok"}>{r.est_provisoire ? t("ecarts_m2.provisoire") : t("ecarts_m2.confirme")}</Badge>
                  {!r.is_active && <Badge tone="neutral">{t("ecarts_m2.inspection.inactive")}</Badge>}
                </td>
                <td>{r.est_provisoire && <ActionBar actions={[{ label: t("ecarts_m2.params.confirmer"), path: `/api/achats/regles-inspection/${r.id}/confirmer/`, tone: "ghost" }]} />}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="muted">{t("ecarts_m2.reception.note")}</p>
      </SectionCard>

      <SectionCard title={t("ecarts_m2.amont.title")}>
        <div className="action-bar-buttons">
          <QuickForm
            title={t("ecarts_m2.amont.daAffaire")}
            endpoint="/api/achats/requests/depuis-affaire/"
            submitLabel={t("ecarts_m2.amont.generer")}
            fields={[{ name: "affaire", label: t("ecarts_m2.amont.affaire"), type: "select", required: true, options: opt(affaires, (a) => `${a.code} · ${a.title ?? ""}`) }]}
          />
          <QuickForm
            title={t("ecarts_m2.amont.bcGr")}
            endpoint="/api/achats/orders/depuis-location-gr/"
            submitLabel={t("ecarts_m2.amont.generer")}
            fields={[{ name: "location", label: t("ecarts_m2.amont.location"), type: "select", required: true, options: opt(locations, (l) => l.code) }]}
          />
        </div>
        <p className="muted">{t("ecarts_m2.amont.note")}</p>
      </SectionCard>

      <SectionCard title={t("ecarts_m2.avoirs.title")}>
        <div className="action-bar-buttons">
          <QuickForm
            title={t("ecarts_m2.avoirs.nouveau")}
            endpoint="/api/achats/avoirs/"
            fields={[
              { name: "facture", label: t("ecarts_m2.avoirs.facture"), type: "select", required: true, options: opt(factures, (f) => `${f.code} · ${f.supplier_name ?? ""}`) },
              { name: "montant_ht", label: t("ecarts_m2.avoirs.montant"), type: "number", required: true, min: 0, step: "0.01" },
              { name: "reference_fournisseur", label: t("ecarts_m2.avoirs.reference") },
              { name: "date_avoir", label: t("ecarts_m2.avoirs.date"), type: "date" },
              { name: "motif", label: t("ecarts_m2.avoirs.motif"), type: "textarea", required: true },
            ]}
          />
        </div>
        <table className="table" data-testid="avoirs-fournisseurs">
          <thead>
            <tr>
              <th>{t("ecarts_m2.avoirs.code")}</th>
              <th>{t("ecarts_m2.avoirs.facture")}</th>
              <th>{t("ecarts_m2.avoirs.date")}</th>
              <th>{t("ecarts_m2.avoirs.montant")}</th>
              <th>{t("ecarts_m2.avoirs.statut")}</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {avoirs.map((a) => (
              <tr key={a.id}>
                <td>{a.code}</td>
                <td>
                  {a.facture_code} · {a.fournisseur_nom ?? "—"}
                </td>
                <td>{formatDate(a.date_avoir)}</td>
                <td>{formatMoney(a.montant_ht)}</td>
                <td>
                  <Badge tone={a.statut === "comptabilise" ? "ok" : "warn"}>{a.statut_label}</Badge> {a.move_number ?? ""}
                </td>
                <td>
                  {a.statut === "brouillon" && (
                    <ActionBar actions={[{ label: t("ecarts_m2.avoirs.comptabiliser"), path: `/api/achats/avoirs/${a.id}/comptabiliser/`, confirm: t("ecarts_m2.avoirs.confirm") }]} />
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="muted">{t("ecarts_m2.avoirs.note")}</p>
      </SectionCard>

      <SectionCard title={t("ecarts_m2.ged.title")}>
        <table className="table" data-testid="pieces-archivees">
          <thead>
            <tr>
              <th>{t("ecarts_m2.ged.nature")}</th>
              <th>{t("ecarts_m2.ged.piece")}</th>
              <th>{t("ecarts_m2.ged.archive")}</th>
              <th>{t("ecarts_m2.ged.conservation")}</th>
            </tr>
          </thead>
          <tbody>
            {(pieces?.rows ?? []).slice(0, 30).map((p) => (
              <tr key={`${p.nature}-${p.piece}`}>
                <td>{p.nature}</td>
                <td>{p.piece}</td>
                <td>{formatDate(p.archive_le)}</td>
                <td>{p.conservation_ans === null ? "—" : t("ecarts_m2.ged.ans", { n: p.conservation_ans })}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="muted">{t("ecarts_m2.ged.note", { n: pieces?.conservation_ans ?? 10 })}</p>
      </SectionCard>

      <SectionCard title={t("ecarts_m2.params.title")}>
        <ParametresAchats />
        <p className="muted">{t("ecarts_m2.params.note")}</p>
      </SectionCard>
    </>
  );
}
