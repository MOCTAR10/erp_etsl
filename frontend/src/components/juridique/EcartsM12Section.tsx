import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { api } from "../../api/client";
import { formatDate, formatMoney } from "../../lib/format";
import { ActionBar, Badge, QuickForm, SectionCard } from "../ui";

interface Parametre {
  id: number;
  cle: string;
  libelle: string;
  valeur: unknown;
  provisoire: boolean;
}
interface Completude {
  requises: string[];
  manquantes: string[];
  complet: boolean;
  taux_pct: string;
}
interface Contentieux {
  id: string;
  code: string;
  objet: string;
  nature: string;
  phase: string;
  phase_label: string;
  statut: string;
  juridiction: string;
  probabilite: string | null;
  probabilite_label: string;
  completude: Completude;
}
interface Convention {
  id: string;
  code: string;
  titre: string;
  completude: Completude;
}
interface Jalon {
  id: string;
  contentieux_code: string;
  libelle: string;
  date_prevue: string;
  date_realisee: string | null;
  statut: string;
  statut_label: string;
  days_left: number;
}
interface ActionJournal {
  id: string;
  contentieux_code: string;
  date_action: string;
  type_label: string;
  description: string;
  auteur_name: string | null;
}
interface LigneRisque {
  id: string;
  code: string;
  objet: string;
  juridiction: string;
  phase: string;
  probabilite: string | null;
  probabilite_pct: number | null;
  niveau: "eleve" | "moyen" | "faible" | "non_cote";
  montant_en_jeu: string | null;
  exposition: string | null;
}
interface VueRisque {
  contentieux: LigneRisque[];
  par_niveau: Record<string, number>;
  total_enjeu: string | null;
  total_exposition: string | null;
  cautions_en_cours: number;
  engagements_cautions: string | null;
}
interface Garantie {
  id: string;
  code: string;
  type_label: string;
  statut: string;
  statut_label: string;
  date_echeance: string;
  en_attente_dg: boolean;
  beneficiaire?: string;
  numero_police?: string;
}
interface Alerte {
  type: string;
  code: string;
  libelle: string;
  date_echeance: string;
  bande: string;
  jours: number;
}
interface Alertes {
  contrats_m1: Alerte[];
  jalons: Alerte[];
  mandats_gr: Alerte[];
}
interface DossierGr {
  id: string;
  code: string;
  objet: string;
  statut: string;
  mandat_reference: string;
  mandat_date_fin: string | null;
  date_revue: string | null;
  controle: { a_jour: boolean; motifs: string[]; tarifs_en_vigueur: number; completude: Completude };
}
interface TypeDoc {
  id: string;
  label: string;
  retention_years: number | null;
  retention_provisoire: boolean;
}
interface Candidat {
  id: string;
  title: string;
  type_label: string;
  fin_retention: string;
}
interface Purge {
  id: string;
  document_title: string;
  type_label: string;
  fin_retention: string;
  statut: string;
  statut_label: string;
  motif: string;
}
interface DocRef {
  id: string;
  title: string;
}

const PHASES = ["pre_contentieux", "tribunal", "arbitrage", "appel"];
const PROBAS = ["faible", "moyenne", "forte", "certaine"];
const TYPES_ACTION = ["audience", "conclusions", "courrier", "expertise", "negociation", "decision", "autre"];
const NIVEAU_TONE = { eleve: "err", moyen: "warn", faible: "ok", non_cote: "brand" } as const;
const fcfa = (v: string | null) => (v === null ? "—" : formatMoney(Number(v)));
const rows = <T,>(p: T[] | { results: T[] } | undefined): T[] => (Array.isArray(p) ? p : (p?.results ?? []));

function useListe<T>(key: string, path: string): T[] {
  return useQuery({ queryKey: ["m12e", key], queryFn: () => api.listAll<T>(path), retry: 0 }).data ?? [];
}

function CompletudeCell({ c }: { c: Completude }) {
  const { t } = useTranslation();
  return (
    <>
      <Badge tone={c.complet ? "ok" : "warn"}>{c.taux_pct} %</Badge>{" "}
      {c.manquantes.length > 0 && <span className="muted">{t("ecarts_m12.manquantes")} : {c.manquantes.join(", ")}</span>}
    </>
  );
}

/** Écarts M12 : paramètres provisoires, dossiers complets, suivi contentieux, vue Risk, validation DG, GR, archivage. */
export function EcartsM12Section() {
  const { t } = useTranslation();
  const params = useListe<Parametre>("params", "/api/juridique/parametres/");
  const contentieux = useListe<Contentieux>("contentieux", "/api/juridique/contentieux/");
  const conventions = useListe<Convention>("conventions", "/api/juridique/conventions/");
  const jalons = useListe<Jalon>("jalons", "/api/juridique/jalons/");
  const journal = useListe<ActionJournal>("journal", "/api/juridique/actions-contentieux/");
  const cautions = useListe<Garantie>("cautions", "/api/juridique/cautions/");
  const assurances = useListe<Garantie>("assurances", "/api/juridique/assurances/");
  const dossiersGr = useListe<DossierGr>("gr", "/api/juridique/dossiers-gr/");
  const types = useListe<TypeDoc>("types", "/api/documents/types/");
  const risques = useQuery({ queryKey: ["m12e", "risques"], queryFn: () => api.get<VueRisque>("/api/juridique/risques/"), retry: 0 }).data;
  const alertes = useQuery({ queryKey: ["m12e", "alertes"], queryFn: () => api.get<Alertes>("/api/juridique/alertes/"), retry: 0 }).data;
  const candidats = useQuery({ queryKey: ["m12e", "candidats"], queryFn: () => api.get<Candidat[]>("/api/documents/purges/candidats/"), retry: 0 }).data ?? [];
  const purges = useQuery({ queryKey: ["m12e", "purges"], queryFn: () => api.listAll<Purge>("/api/documents/purges/"), retry: 0 }).data ?? [];
  const docs = rows(
    useQuery({
      queryKey: ["m12e", "docs"],
      queryFn: () => api.get<DocRef[] | { results: DocRef[] }>("/api/documents/documents/?page_size=100"),
      retry: 0,
    }).data,
  );
  const juridictions = (params.find((p) => p.cle === "juridictions")?.valeur as string[] | undefined) ?? [];
  const provisoires = params.filter((p) => p.provisoire).length;
  const contOpts = contentieux.map((c) => ({ value: c.id, label: `${c.code} · ${c.objet}` }));
  const dossierOpts = [
    ...contentieux.map((c) => ({ value: `contentieux:${c.id}`, label: `${t("ecarts_m12.dossiers.contentieux")} ${c.code}` })),
    ...conventions.map((c) => ({ value: `convention:${c.id}`, label: `${t("ecarts_m12.dossiers.convention")} ${c.code}` })),
    ...dossiersGr.map((d) => ({ value: `gr:${d.id}`, label: `${t("ecarts_m12.dossiers.gr")} ${d.code}` })),
  ];
  const alertesExtra = alertes ? [...alertes.contrats_m1, ...alertes.jalons, ...alertes.mandats_gr] : [];
  const garanties = [
    ...cautions.map((c) => ({ ...c, kind: "cautions" as const, label: `${c.type_label} · ${c.beneficiaire ?? ""}` })),
    ...assurances.map((a) => ({ ...a, kind: "assurances" as const, label: `${a.type_label} · ${a.numero_police ?? ""}` })),
  ];

  return (
    <div data-testid="ecarts-m12">
      <SectionCard title={t("ecarts_m12.parametres.title")}>
        {provisoires > 0 && (
          <p className="action-error" role="note" data-testid="m12-provisoire">
            {t("ecarts_m12.parametres.bandeau", { count: provisoires })}
          </p>
        )}
        <table className="table" data-testid="m12-parametres">
          <tbody>
            {params.map((p) => (
              <tr key={p.id}>
                <td>{p.libelle}</td>
                <td>
                  <code style={{ whiteSpace: "pre-wrap", fontSize: "0.8em" }}>{JSON.stringify(p.valeur)}</code>
                </td>
                <td>
                  <Badge tone={p.provisoire ? "warn" : "ok"}>{p.provisoire ? t("ecarts_m12.provisoire") : t("ecarts_m12.confirme")}</Badge>
                </td>
                <td>
                  <ActionBar
                    actions={[
                      { label: t("ecarts_m12.parametres.modifier"), path: `/api/juridique/parametres/${p.id}/modifier/`, tone: "ghost" as const, prompt: { name: "valeur", label: t("ecarts_m12.parametres.json") } },
                      ...(p.provisoire
                        ? [{ label: t("ecarts_m12.parametres.confirmer"), path: `/api/juridique/parametres/${p.id}/confirmer/`, confirm: t("ecarts_m12.parametres.confirmerQ") }]
                        : []),
                    ]}
                  />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </SectionCard>

      <SectionCard title={t("ecarts_m12.contentieux.title")}>
        <div className="action-bar-buttons">
          <QuickForm
            title={t("ecarts_m12.contentieux.jalon")}
            endpoint="/api/juridique/jalons/"
            fields={[
              { name: "contentieux", label: t("ecarts_m12.contentieux.dossier"), type: "select", required: true, options: contOpts },
              { name: "libelle", label: t("ecarts_m12.contentieux.libelle"), required: true },
              { name: "date_prevue", label: t("ecarts_m12.contentieux.datePrevue"), type: "date", required: true },
            ]}
          />
          <QuickForm
            title={t("ecarts_m12.contentieux.action")}
            endpoint="/api/juridique/actions-contentieux/"
            fields={[
              { name: "contentieux", label: t("ecarts_m12.contentieux.dossier"), type: "select", required: true, options: contOpts },
              { name: "type", label: t("ecarts_m12.contentieux.type"), type: "select", required: true, defaultValue: "audience", options: TYPES_ACTION.map((v) => ({ value: v, label: t(`ecarts_m12.typesAction.${v}`) })) },
              { name: "date_action", label: t("ecarts_m12.contentieux.date"), type: "date" },
              { name: "description", label: t("ecarts_m12.contentieux.description"), type: "textarea", required: true },
            ]}
          />
          <QuickForm
            title={t("ecarts_m12.pieces.ajouter")}
            endpoint="/api/juridique/pieces/"
            fields={[
              { name: "dossier", label: t("ecarts_m12.pieces.dossier"), type: "select", required: true, options: dossierOpts },
              { name: "piece", label: t("ecarts_m12.pieces.piece"), required: true },
              { name: "document", label: t("ecarts_m12.pieces.document"), type: "select", required: true, options: docs.map((d) => ({ value: d.id, label: d.title })) },
            ]}
            transform={(v) => {
              const [dossier_type, dossier_id] = (v.dossier ?? "").split(":");
              return { dossier_type, dossier_id, piece: v.piece, document: v.document };
            }}
          />
        </div>
        <table className="table" data-testid="m12-contentieux">
          <thead>
            <tr>
              <th>{t("ecarts_m12.contentieux.dossier")}</th>
              <th>{t("ecarts_m12.contentieux.juridiction")}</th>
              <th>{t("ecarts_m12.contentieux.phase")}</th>
              <th>{t("ecarts_m12.contentieux.probabilite")}</th>
              <th>{t("ecarts_m12.completude")}</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {contentieux.map((c) => (
              <tr key={c.id}>
                <td>{c.code} · {c.objet}</td>
                <td>{c.juridiction || "—"}</td>
                <td>{c.phase_label}</td>
                <td>{c.probabilite ? c.probabilite_label : "—"}</td>
                <td><CompletudeCell c={c.completude} /></td>
                <td>
                  {(c.statut === "ouvert" || c.statut === "en_instruction") && (
                    <ActionBar
                      actions={[
                        { label: t("ecarts_m12.contentieux.juridiction"), path: `/api/juridique/contentieux/${c.id}/qualifier/`, tone: "ghost" as const, prompt: { name: "juridiction", label: t("ecarts_m12.contentieux.juridiction"), options: juridictions.map((j) => ({ value: j, label: j })) } },
                        { label: t("ecarts_m12.contentieux.coter"), path: `/api/juridique/contentieux/${c.id}/qualifier/`, tone: "ghost" as const, prompt: { name: "probabilite", label: t("ecarts_m12.contentieux.probabilite"), options: PROBAS.map((v) => ({ value: v, label: t(`ecarts_m12.probas.${v}`) })) } },
                        { label: t("ecarts_m12.contentieux.phaseSuivante"), path: `/api/juridique/contentieux/${c.id}/avancer-phase/`, tone: "ghost" as const, prompt: { name: "phase", label: t("ecarts_m12.contentieux.phase"), options: PHASES.filter((p) => p !== c.phase).map((v) => ({ value: v, label: t(`ecarts_m12.phases.${v}`) })) } },
                      ]}
                    />
                  )}
                </td>
              </tr>
            ))}
            {conventions.map((c) => (
              <tr key={c.id}>
                <td>{c.code} · {c.titre}</td>
                <td colSpan={3} className="muted">{t("ecarts_m12.dossiers.convention")}</td>
                <td><CompletudeCell c={c.completude} /></td>
                <td />
              </tr>
            ))}
          </tbody>
        </table>
        <h4>{t("ecarts_m12.contentieux.echeancier")}</h4>
        <table className="table" data-testid="m12-jalons">
          <tbody>
            {jalons.map((j) => (
              <tr key={j.id}>
                <td>{j.contentieux_code}</td>
                <td>{j.libelle}</td>
                <td>{formatDate(j.date_prevue)}{j.statut === "a_venir" ? ` · ${j.days_left} ${t("juridique.jours")}` : ""}</td>
                <td><Badge tone={j.statut === "realise" ? "ok" : j.statut === "annule" ? "brand" : j.days_left < 0 ? "err" : "warn"}>{j.statut_label}</Badge></td>
                <td>
                  {j.statut === "a_venir" && (
                    <ActionBar
                      actions={[
                        { label: t("ecarts_m12.contentieux.realiser"), path: `/api/juridique/jalons/${j.id}/realiser/` },
                        { label: t("ecarts_m12.contentieux.annuler"), path: `/api/juridique/jalons/${j.id}/annuler/`, tone: "ghost" as const },
                      ]}
                    />
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <h4>{t("ecarts_m12.contentieux.journal")}</h4>
        <table className="table" data-testid="m12-journal">
          <tbody>
            {journal.slice(0, 50).map((a) => (
              <tr key={a.id}>
                <td>{formatDate(a.date_action)}</td>
                <td>{a.contentieux_code}</td>
                <td>{a.type_label}</td>
                <td>{a.description}</td>
                <td className="muted">{a.auteur_name ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </SectionCard>

      {risques && (
        <SectionCard title={t("ecarts_m12.risk.title")}>
          <p className="muted">
            {t("ecarts_m12.risk.synthese", {
              eleve: risques.par_niveau.eleve, moyen: risques.par_niveau.moyen, faible: risques.par_niveau.faible, nonCote: risques.par_niveau.non_cote,
            })}{" "}
            · {t("ecarts_m12.risk.exposition")} : {fcfa(risques.total_exposition)} · {t("ecarts_m12.risk.engagements", { n: risques.cautions_en_cours })} : {fcfa(risques.engagements_cautions)}
          </p>
          <table className="table" data-testid="m12-risk">
            <thead>
              <tr>
                <th>{t("ecarts_m12.contentieux.dossier")}</th>
                <th>{t("ecarts_m12.contentieux.probabilite")}</th>
                <th>{t("ecarts_m12.risk.enjeu")}</th>
                <th>{t("ecarts_m12.risk.exposition")}</th>
                <th>{t("ecarts_m12.risk.niveau")}</th>
              </tr>
            </thead>
            <tbody>
              {risques.contentieux.map((r) => (
                <tr key={r.id}>
                  <td>{r.code} · {r.objet}</td>
                  <td>{r.probabilite ? `${t(`ecarts_m12.probas.${r.probabilite}`)} (${r.probabilite_pct} %)` : "—"}</td>
                  <td>{fcfa(r.montant_en_jeu)}</td>
                  <td>{fcfa(r.exposition)}</td>
                  <td><Badge tone={NIVEAU_TONE[r.niveau]}>{t(`ecarts_m12.niveaux.${r.niveau}`)}</Badge></td>
                </tr>
              ))}
            </tbody>
          </table>
        </SectionCard>
      )}

      <SectionCard title={t("ecarts_m12.dg.title")}>
        <p className="muted">{t("ecarts_m12.dg.note")}</p>
        <table className="table" data-testid="m12-validation-dg">
          <tbody>
            {garanties.map((g) => (
              <tr key={g.id}>
                <td>{g.code} · {g.label}</td>
                <td>{formatDate(g.date_echeance)}</td>
                <td>
                  <Badge tone={g.en_attente_dg ? "warn" : "ok"}>{g.en_attente_dg ? t("ecarts_m12.dg.attente") : t("ecarts_m12.dg.validee")}</Badge>{" "}
                  <span className="muted">{g.statut_label}</span>
                </td>
                <td>
                  <ActionBar
                    actions={[
                      ...(g.en_attente_dg ? [{ label: t("ecarts_m12.dg.valider"), path: `/api/juridique/${g.kind}/${g.id}/valider-dg/`, confirm: t("ecarts_m12.dg.validerQ") }] : []),
                      ...(g.kind === "cautions" && g.statut === "en_cours"
                        ? [
                            { label: t("ecarts_m12.dg.lever"), path: `/api/juridique/cautions/${g.id}/lever/`, tone: "ghost" as const },
                            { label: t("ecarts_m12.dg.appeler"), path: `/api/juridique/cautions/${g.id}/appeler/`, tone: "danger" as const, confirm: t("ecarts_m12.dg.appelerQ") },
                          ]
                        : []),
                      ...(g.kind === "assurances" && g.statut !== "resiliee"
                        ? [
                            { label: t("ecarts_m12.dg.renouveler"), path: `/api/juridique/assurances/${g.id}/renouveler/`, tone: "ghost" as const, prompt: { name: "date_echeance", label: t("ecarts_m12.dg.nouvelleEcheance") } },
                            { label: t("ecarts_m12.dg.resilier"), path: `/api/juridique/assurances/${g.id}/resilier/`, tone: "danger" as const, confirm: t("ecarts_m12.dg.resilierQ") },
                          ]
                        : []),
                    ]}
                  />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </SectionCard>

      <SectionCard title={t("ecarts_m12.alertes.title")}>
        <ActionBar actions={[{ label: t("ecarts_m12.alertes.notifier"), path: "/api/juridique/alertes/notifier/", tone: "ghost" as const }]} />
        <table className="table" data-testid="m12-alertes">
          <tbody>
            {alertesExtra.map((a) => (
              <tr key={`${a.type}-${a.code}-${a.libelle}`}>
                <td>{t(`ecarts_m12.alertes.types.${a.type}`)}</td>
                <td>{a.code} · {a.libelle}</td>
                <td>{formatDate(a.date_echeance)} · {a.jours} {t("juridique.jours")}</td>
                <td><Badge tone={a.jours < 0 || a.jours <= 15 ? "err" : a.jours <= 60 ? "warn" : "ok"}>{t(`juridique.bande.${a.bande}`)}</Badge></td>
              </tr>
            ))}
          </tbody>
        </table>
        {alertesExtra.length === 0 && <p className="muted">{t("ecarts_m12.alertes.aucune")}</p>}
      </SectionCard>

      <SectionCard title={t("ecarts_m12.gr.title")}>
        <table className="table" data-testid="m12-gr">
          <tbody>
            {dossiersGr.map((d) => (
              <tr key={d.id}>
                <td title={d.objet}>{d.code}</td>
                <td>{d.mandat_date_fin ? `${d.mandat_reference || t("ecarts_m12.gr.mandat")} → ${formatDate(d.mandat_date_fin)}` : "—"}</td>
                <td>
                  <Badge tone={d.controle.a_jour ? "ok" : "warn"}>{d.controle.a_jour ? t("ecarts_m12.gr.aJour") : t("ecarts_m12.gr.pasAJour")}</Badge>{" "}
                  <span className="muted">{d.controle.motifs.join(" ")}</span>
                </td>
                <td>
                  {d.statut !== "cloture" && (
                    <ActionBar
                      actions={[
                        { label: t("ecarts_m12.gr.mandat"), path: `/api/juridique/dossiers-gr/${d.id}/mandat/`, tone: "ghost" as const, prompt: { name: "mandat_date_fin", label: t("ecarts_m12.gr.mandatFin") } },
                        { label: t("ecarts_m12.gr.revoir"), path: `/api/juridique/dossiers-gr/${d.id}/revoir/`, tone: "ghost" as const },
                      ]}
                    />
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </SectionCard>

      <SectionCard title={t("ecarts_m12.archivage.title")}>
        <p className="muted">{t("ecarts_m12.archivage.note")}</p>
        <table className="table" data-testid="m12-retention">
          <tbody>
            {types.map((ty) => (
              <tr key={ty.id}>
                <td>{ty.label}</td>
                <td>{ty.retention_years === null ? t("ecarts_m12.archivage.sansEcheance") : t("ecarts_m12.archivage.ans", { n: ty.retention_years })}</td>
                <td><Badge tone={ty.retention_provisoire ? "warn" : "ok"}>{ty.retention_provisoire ? t("ecarts_m12.provisoire") : t("ecarts_m12.confirme")}</Badge></td>
                <td>
                  <ActionBar
                    actions={[
                      { label: t("ecarts_m12.archivage.modifier"), path: `/api/documents/types/${ty.id}/definir-retention/`, tone: "ghost" as const, prompt: { name: "retention_years", label: t("ecarts_m12.archivage.duree") } },
                      ...(ty.retention_provisoire ? [{ label: t("ecarts_m12.parametres.confirmer"), path: `/api/documents/types/${ty.id}/confirmer-retention/`, tone: "ghost" as const }] : []),
                    ]}
                  />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <h4>{t("ecarts_m12.archivage.candidats")}</h4>
        {candidats.length === 0 && <p className="muted">{t("ecarts_m12.archivage.aucunCandidat")}</p>}
        <table className="table" data-testid="m12-candidats-purge">
          <tbody>
            {candidats.map((c) => (
              <tr key={c.id}>
                <td>{c.title}</td>
                <td>{c.type_label}</td>
                <td>{formatDate(c.fin_retention)}</td>
                <td>
                  <ActionBar actions={[{ label: t("ecarts_m12.archivage.proposer"), path: "/api/documents/purges/", body: { document: c.id }, tone: "ghost" as const }]} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <table className="table" data-testid="m12-purges">
          <tbody>
            {purges.map((p) => (
              <tr key={p.id}>
                <td>{p.document_title}</td>
                <td>{p.type_label}</td>
                <td>{formatDate(p.fin_retention)}</td>
                <td><Badge tone={p.statut === "executee" ? "ok" : p.statut === "rejetee" ? "brand" : "warn"}>{p.statut_label}</Badge></td>
                <td>
                  {p.statut === "proposee" && (
                    <ActionBar
                      actions={[
                        { label: t("ecarts_m12.archivage.valider"), path: `/api/documents/purges/${p.id}/valider/`, tone: "danger" as const, confirm: t("ecarts_m12.archivage.validerQ") },
                        { label: t("ecarts_m12.archivage.rejeter"), path: `/api/documents/purges/${p.id}/rejeter/`, tone: "ghost" as const },
                      ]}
                    />
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </SectionCard>
    </div>
  );
}
