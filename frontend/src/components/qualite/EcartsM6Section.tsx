import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../../api/client";
import { formatDate, formatNumber } from "../../lib/format";
import { describeError } from "../../lib/offlineQueue";
import type { ActionCorrective, NonConformite, ParametreStock } from "../../types";
import { ActionBar, Badge, Kpi, QuickForm, SectionCard } from "../ui";

interface Option {
  id: string;
  code: string;
}
interface OfOption extends Option {
  label: string;
}
interface SoudeurOption extends Option {
  display_name: string;
  employe_code: string | null;
}
interface WpsOption extends Option {
  type: "wps" | "wpqr";
  reference: string;
  procede_label: string;
  position: string;
  statut: "brouillon" | "valide" | "obsolete";
  wpqr_code: string | null;
  fichier: string | null;
  ordres_diffusion: string[];
}
interface ControleOption extends Option {
  type_controle: string;
  point_controle: string;
  ordre_code: string | null;
}
interface PunchItem extends Option {
  ordre_code: string;
  repere: string;
  description: string;
  categorie: "A" | "B" | "C";
  responsable: string;
  echeance: string | null;
  en_retard: boolean;
  statut: "ouverte" | "levee";
}
interface Indicateurs {
  controles: number;
  taux_conformite: number | null;
  non_conformites: number;
  taux_nc: number | null;
  taux_rebut: number | null;
  joints_soudes: number;
  densite_defauts: number | null;
  delai_levee_reserves_jours: number | null;
  capa_dans_les_delais: number | null;
  capa_en_retard: number;
}

const NORMES = ["iso9606", "asme_ix"];
const PROCEDES = ["smaw", "gtaw", "gmaw", "fcaw"];

function useOptions<T>(key: string, path: string) {
  return useQuery({ queryKey: ["m6e", key], queryFn: () => api.listAll<T>(path), retry: 0 }).data ?? [];
}

const pct = (v: number | null) => (v === null ? "—" : `${formatNumber(v)} %`);

/** Écarts M6-A : saisies de soudage / ITP / punch list, cycle WPS, CAPA, indicateurs et paramètres qualité. */
export function EcartsM6Section() {
  const { t } = useTranslation();
  const ofs = useOptions<OfOption>("ofs", "/api/operations/ordres/");
  const soudeurs = useOptions<SoudeurOption>("soudeurs", "/api/qualite/soudeurs/?active=1");
  const wps = useOptions<WpsOption>("wps", "/api/qualite/wps/");
  const itps = useOptions<ControleOption>("itps", "/api/qualite/controles/?type=itp");
  const cnds = useOptions<ControleOption>("cnds", "/api/qualite/controles/?type=cnd");
  const personnel = useQuery({
    queryKey: ["m6e", "personnel"],
    queryFn: () => api.get<Array<{ id: string; code: string; nom_complet: string }>>("/api/qualite/personnel/"),
    retry: 0,
  }).data ?? [];

  const ofOpts = ofs.map((o) => ({ value: o.id, label: `${o.code} · ${o.label}` }));
  const soudeurOpts = soudeurs.map((s) => ({ value: s.id, label: `${s.code} · ${s.display_name}` }));
  const wpsValides = wps.filter((w) => w.type === "wps" && w.statut === "valide").map((w) => ({ value: w.id, label: `${w.code} · ${w.procede_label} ${w.position}` }));
  const wpqrValides = wps.filter((w) => w.type === "wpqr" && w.statut === "valide").map((w) => ({ value: w.id, label: `${w.code} · ${w.reference}` }));
  const itpOpts = itps.map((c) => ({ value: c.id, label: `${c.code} · ${c.point_controle || c.ordre_code || ""}` }));
  const cndOpts = cnds.map((c) => ({ value: c.id, label: `${c.code} · ${c.point_controle || ""}` }));
  const choix = (vals: string[], prefix: string) => vals.map((v) => ({ value: v, label: t(`${prefix}.${v}`) }));

  return (
    <>
      <SectionCard title={t("m6e.saisies.title")}>
        <div className="action-bar-buttons" data-testid="saisies-m6">
          <QuickForm
            title={t("m6e.saisies.soudeur")}
            endpoint="/api/qualite/soudeurs/"
            fields={[
              { name: "nom", label: t("m6e.f.nom"), required: true },
              { name: "prenoms", label: t("m6e.f.prenoms") },
              { name: "matricule", label: t("m6e.f.matricule") },
              { name: "employe", label: t("m6e.f.employe"), type: "select", options: personnel.map((p) => ({ value: p.id, label: `${p.code} · ${p.nom_complet}` })) },
            ]}
          />
          <QuickForm
            title={t("m6e.saisies.qualif")}
            endpoint="/api/qualite/qualifications/"
            fields={[
              { name: "soudeur", label: t("qualite.col.soudeur"), type: "select", required: true, options: soudeurOpts },
              { name: "norme", label: t("qualite.col.norme"), type: "select", required: true, defaultValue: "iso9606", options: choix(NORMES, "qualite.norms") },
              { name: "procede", label: t("qualite.col.procede"), type: "select", required: true, defaultValue: "smaw", options: choix(PROCEDES, "m6e.procedes") },
              { name: "position", label: t("m6e.f.position") },
              { name: "groupe_materiaux", label: t("m6e.f.materiaux") },
              { name: "date_qualification", label: t("m6e.f.dateQualif"), type: "date", required: true },
              { name: "date_validite", label: t("qualite.col.validite"), type: "date", required: true },
              { name: "certificat", label: t("m6e.f.certificat") },
            ]}
          />
          <QuickForm
            title={t("m6e.saisies.wps")}
            endpoint="/api/qualite/wps/"
            fields={[
              { name: "type", label: t("qualite.col.type"), type: "select", required: true, defaultValue: "wps", options: choix(["wps", "wpqr"], "qualite.wps_type") },
              { name: "reference", label: t("qualite.col.reference"), required: true },
              { name: "norme", label: t("qualite.col.norme"), type: "select", required: true, defaultValue: "iso9606", options: choix(NORMES, "qualite.norms") },
              { name: "procede", label: t("qualite.col.procede"), type: "select", required: true, defaultValue: "smaw", options: choix(PROCEDES, "m6e.procedes") },
              { name: "materiau", label: t("qualite.col.materiau") },
              { name: "position", label: t("m6e.f.position") },
              { name: "epaisseur", label: t("m6e.f.epaisseur") },
              { name: "gaz_protection", label: t("m6e.f.gaz") },
              { name: "wpqr", label: t("m6e.f.wpqr"), type: "select", options: wpqrValides },
            ]}
          />
          <QuickForm
            title={t("m6e.saisies.joint")}
            endpoint="/api/qualite/joints/"
            fields={[
              { name: "ordre", label: t("qualite.m6.of"), type: "select", required: true, options: ofOpts },
              { name: "repere", label: t("qualite.m6.joint"), required: true },
              { name: "soudeur", label: t("qualite.col.soudeur"), type: "select", required: true, options: soudeurOpts },
              { name: "wps", label: "WPS", type: "select", required: true, options: wpsValides },
              { name: "numero_coulee", label: t("qualite.m6.coulee") },
              { name: "consommable", label: t("m6e.f.consommable") },
              { name: "date_soudage", label: t("qualite.col.date"), type: "date" },
            ]}
          />
          <QuickForm
            title={t("m6e.saisies.itp")}
            endpoint="/api/qualite/controles/"
            transform={(v) => ({ ...v, type_controle: "itp" })}
            fields={[
              { name: "ordre", label: t("qualite.m6.of"), type: "select", required: true, options: ofOpts },
              { name: "point_controle", label: t("m6e.f.perimetreItp"), required: true },
            ]}
          />
          <QuickForm
            title={t("m6e.saisies.point")}
            endpoint="/api/qualite/points-inspection/"
            fields={[
              { name: "controle", label: "ITP", type: "select", required: true, options: itpOpts },
              { name: "ordre", label: t("m6e.f.ordre"), type: "number", required: true, min: 1 },
              { name: "description", label: t("m6e.f.point"), required: true },
              { name: "type_point", label: t("qualite.col.type"), type: "select", required: true, defaultValue: "arret", options: choix(["arret", "observation"], "m6e.typesPoint") },
              { name: "responsable_levee", label: t("m6e.f.leveePar") },
              { name: "date_prevue", label: t("m6e.f.datePrevue"), type: "date" },
            ]}
          />
          <QuickForm
            title={t("m6e.saisies.epreuve")}
            endpoint="/api/qualite/epreuves/"
            fields={[
              { name: "ordre", label: t("qualite.m6.of"), type: "select", required: true, options: ofOpts },
              { name: "type_epreuve", label: t("qualite.col.type"), type: "select", required: true, defaultValue: "hydraulique", options: choix(["hydraulique", "etancheite"], "m6e.typesEpreuve") },
              { name: "pression_essai", label: t("m6e.f.pression"), type: "number", required: true, step: "0.01" },
              { name: "duree_minutes", label: t("m6e.f.duree"), type: "number", required: true, min: 1 },
              { name: "chute_max", label: t("m6e.f.chute"), type: "number", required: true, step: "0.01" },
            ]}
          />
          <ImageCndForm cndOpts={cndOpts} />
        </div>
      </SectionCard>

      <WpsCycleSection wps={wps} ofOpts={ofOpts} />
      <CapaSection />
      <PunchListSection ofOpts={ofOpts} itpOpts={itpOpts} />
      <IndicateursSection />
      <ParametresQualiteSection />
    </>
  );
}

function ImageCndForm({ cndOpts }: { cndOpts: { value: string; label: string }[] }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [controle, setControle] = useState("");
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const send = useMutation({
    mutationFn: (f: File) => api.upload("/api/qualite/images-controle/", f, "fichier", { controle }),
    onSuccess: () => {
      setMsg({ ok: true, text: t("m6e.image.ok") });
      void qc.invalidateQueries();
    },
    onError: (e) => setMsg({ ok: false, text: describeError(e) }),
  });
  return (
    <div className="field">
      <label htmlFor="m6e-cnd">{t("m6e.image.title")}</label>
      <select id="m6e-cnd" value={controle} onChange={(e) => setControle(e.target.value)}>
        <option value="">{t("m6e.image.choisir")}</option>
        {cndOpts.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
      <input
        type="file"
        aria-label={t("m6e.image.fichier")}
        accept="image/*,.pdf,.dcm"
        disabled={!controle || send.isPending}
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) send.mutate(f);
          e.target.value = "";
        }}
      />
      {msg && <p className={msg.ok ? "quick-form-ok" : "action-error"} role={msg.ok ? "status" : "alert"}>{msg.text}</p>}
    </div>
  );
}

function WpsCycleSection({ wps, ofOpts }: { wps: WpsOption[]; ofOpts: { value: string; label: string }[] }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const joindre = useMutation({
    mutationFn: (v: { id: string; f: File }) => api.upload(`/api/qualite/wps/${v.id}/fichier/`, v.f),
    onSuccess: () => {
      setError(null);
      void qc.invalidateQueries();
    },
    onError: (e) => setError(describeError(e)),
  });
  if (wps.length === 0) return null;
  return (
    <SectionCard title={t("m6e.wps.title")}>
      {error && <p className="action-error" role="alert">{error}</p>}
      <div className="table-wrap">
        <table className="table" data-testid="wps-cycle">
          <thead>
            <tr>
              <th>{t("qualite.col.code")}</th>
              <th>{t("qualite.col.type")}</th>
              <th>{t("m6e.f.wpqr")}</th>
              <th>{t("m6e.wps.diffusion")}</th>
              <th>{t("qualite.col.statut")}</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {wps.map((w) => (
              <tr key={w.id}>
                <td>{w.code} <span className="muted">· {w.reference}</span></td>
                <td>{t(`qualite.wps_type.${w.type}`)} · {w.procede_label} {w.position}</td>
                <td>{w.wpqr_code ?? "—"}</td>
                <td>{w.ordres_diffusion.join(", ") || "—"}</td>
                <td>
                  <Badge tone={w.statut === "valide" ? "ok" : w.statut === "obsolete" ? "err" : "brand"}>{t(`qualite.wps_status.${w.statut}`)}</Badge>
                  {w.fichier && <span className="muted"> · {t("m6e.wps.fiche")}</span>}
                </td>
                <td>
                  {w.statut === "brouillon" && (
                    <label className="btn ghost">
                      {t("m6e.wps.joindre")}
                      <input
                        type="file"
                        accept=".pdf,.jpg,.jpeg,.png"
                        hidden
                        onChange={(e) => {
                          const f = e.target.files?.[0];
                          if (f) joindre.mutate({ id: w.id, f });
                          e.target.value = "";
                        }}
                      />
                    </label>
                  )}
                  <ActionBar
                    actions={[
                      ...(w.statut === "valide" && w.type === "wps"
                        ? [{ label: t("m6e.wps.diffuser"), path: `/api/qualite/wps/${w.id}/diffuser/`, tone: "ghost" as const, prompt: { name: "ordre", label: t("m6e.wps.choisirOf"), options: ofOpts } }]
                        : []),
                      ...(w.statut === "valide"
                        ? [{ label: t("m6e.wps.obsolete"), path: `/api/qualite/wps/${w.id}/obsolete/`, tone: "danger" as const, prompt: { name: "motif", label: t("m6e.wps.motif") } }]
                        : []),
                    ]}
                  />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </SectionCard>
  );
}

function CapaSection() {
  const { t, i18n } = useTranslation();
  const ncs = useOptions<NonConformite>("ncs", "/api/qualite/non-conformites/?ouvertes=1");
  const capas = useOptions<ActionCorrective & { en_retard?: boolean; escaladee_le?: string | null }>("capas", "/api/qualite/actions-correctives/?ouvertes=1");
  return (
    <SectionCard title={`${t("m6e.capa.title")} · ${capas.length}`}>
      <div data-testid="capa-m6">
        <QuickForm
          title={t("m6e.capa.nouvelle")}
          endpoint="/api/qualite/actions-correctives/"
          fields={[
            { name: "non_conformite", label: "NC", type: "select", required: true, options: ncs.map((n) => ({ value: n.id, label: `${n.code} · ${n.description.slice(0, 60)}` })) },
            { name: "type", label: t("qualite.col.type"), type: "select", required: true, defaultValue: "corrective", options: choix2(t, ["corrective", "preventive"]) },
            { name: "description", label: t("m6e.capa.action"), type: "textarea", required: true },
            { name: "echeance", label: t("m6e.capa.echeance"), type: "date" },
          ]}
        />
        {capas.length > 0 && (
          <table className="table">
            <thead>
              <tr>
                <th>{t("qualite.col.code")}</th>
                <th>NC</th>
                <th>{t("m6e.capa.action")}</th>
                <th>{t("m6e.capa.echeance")}</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {capas.map((a) => (
                <tr key={a.id}>
                  <td>{a.code}</td>
                  <td>{a.non_conformite_code}</td>
                  <td>{a.description}</td>
                  <td>
                    {a.echeance ? formatDate(a.echeance, i18n.language) : "—"}{" "}
                    {a.en_retard && <Badge tone="err">{a.escaladee_le ? t("m6e.capa.escaladee") : t("m6e.capa.retard")}</Badge>}
                  </td>
                  <td>
                    <ActionBar
                      actions={[
                        { label: t("m6e.capa.efficace"), path: `/api/qualite/actions-correctives/${a.id}/cloturer/`, body: { efficace: true }, confirm: t("actions.confirmCloturer") },
                        { label: t("m6e.capa.inefficace"), path: `/api/qualite/actions-correctives/${a.id}/cloturer/`, body: { efficace: false }, tone: "ghost", confirm: t("actions.confirmCloturer") },
                      ]}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </SectionCard>
  );
}

function choix2(t: (k: string) => string, vals: string[]) {
  return vals.map((v) => ({ value: v, label: t(`m6e.capa.types.${v}`) }));
}

function PunchListSection({ ofOpts, itpOpts }: { ofOpts: { value: string; label: string }[]; itpOpts: { value: string; label: string }[] }) {
  const { t, i18n } = useTranslation();
  const items = useOptions<PunchItem>("punch", "/api/qualite/punch-list/");
  return (
    <SectionCard title={`${t("m6e.punch.title")} · ${items.filter((i) => i.statut === "ouverte").length}`}>
      <div data-testid="punch-list">
        <QuickForm
          title={t("m6e.punch.nouvelle")}
          endpoint="/api/qualite/punch-list/"
          fields={[
            { name: "ordre", label: t("qualite.m6.of"), type: "select", required: true, options: ofOpts },
            { name: "itp", label: "ITP", type: "select", options: itpOpts },
            { name: "repere", label: t("m6e.punch.repere") },
            { name: "description", label: t("m6e.punch.reserve"), required: true },
            { name: "categorie", label: t("m6e.punch.categorie"), type: "select", required: true, defaultValue: "B", options: ["A", "B", "C"].map((c) => ({ value: c, label: t(`m6e.punch.cat.${c}`) })) },
            { name: "responsable", label: t("m6e.punch.responsable") },
            { name: "echeance", label: t("m6e.capa.echeance"), type: "date" },
          ]}
        />
        {items.length > 0 && (
          <table className="table">
            <thead>
              <tr>
                <th>{t("qualite.col.code")}</th>
                <th>{t("qualite.m6.of")}</th>
                <th>{t("m6e.punch.reserve")}</th>
                <th>{t("m6e.punch.categorie")}</th>
                <th>{t("m6e.capa.echeance")}</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {items.map((i) => (
                <tr key={i.id}>
                  <td>{i.code}</td>
                  <td>{i.ordre_code}</td>
                  <td>{i.repere ? `${i.repere} · ` : ""}{i.description}</td>
                  <td><Badge tone={i.categorie === "A" ? "err" : i.categorie === "B" ? "warn" : "brand"}>{i.categorie}</Badge></td>
                  <td>
                    {i.echeance ? formatDate(i.echeance, i18n.language) : "—"} {i.en_retard && <Badge tone="err">{t("m6e.capa.retard")}</Badge>}
                  </td>
                  <td>
                    {i.statut === "ouverte" ? (
                      <ActionBar actions={[{ label: t("m6e.punch.lever"), path: `/api/qualite/punch-list/${i.id}/lever/`, prompt: { name: "commentaire", label: t("m6e.punch.commentaire") } }]} />
                    ) : (
                      <Badge tone="ok">{t("m6e.punch.levee")}</Badge>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </SectionCard>
  );
}

function IndicateursSection() {
  const { t } = useTranslation();
  const now = new Date();
  const [annee, setAnnee] = useState(now.getFullYear());
  const [mois, setMois] = useState(now.getMonth() + 1);
  const q = useQuery({
    queryKey: ["m6e", "indicateurs", annee, mois],
    queryFn: () => api.get<Indicateurs>(`/api/qualite/indicateurs/?annee=${annee}&mois=${mois}`),
    retry: 0,
  });
  const d = q.data;
  return (
    <SectionCard title={t("m6e.ind.title")}>
      <div data-testid="indicateurs-qualite">
        <label>
          {t("m6e.ind.periode")}{" "}
          <input
            type="month"
            aria-label={t("m6e.ind.periode")}
            value={`${annee}-${String(mois).padStart(2, "0")}`}
            onChange={(e) => {
              const [a, m] = e.target.value.split("-").map(Number);
              if (a && m) {
                setAnnee(a);
                setMois(m);
              }
            }}
          />
        </label>{" "}
        <button type="button" className="btn ghost" onClick={() => void api.download(`/api/qualite/indicateurs/?annee=${annee}&mois=${mois}&export=pdf`, `rapport-qualite-${annee}-${mois}.pdf`)}>
          {t("m6e.ind.rapport")}
        </button>
        {d && (
          <div className="kpi-grid">
            <Kpi label={t("m6e.ind.conformite")} value={pct(d.taux_conformite)} hint={`${t("m6e.ind.controles")} · ${d.controles}`} tone="ok" delay={0} />
            <Kpi label={t("m6e.ind.tauxNc")} value={pct(d.taux_nc)} hint={`NC · ${d.non_conformites}`} tone="warn" delay={0.05} />
            <Kpi label={t("m6e.ind.rebut")} value={pct(d.taux_rebut)} tone="err" delay={0.1} />
            <Kpi label={t("m6e.ind.densite")} value={d.densite_defauts === null ? "—" : formatNumber(d.densite_defauts)} hint={`${t("m6e.ind.joints")} · ${d.joints_soudes}`} tone="brand" delay={0.15} />
            <Kpi label={t("m6e.ind.delaiReserves")} value={d.delai_levee_reserves_jours === null ? "—" : `${formatNumber(d.delai_levee_reserves_jours)} j`} tone="accent" delay={0.2} />
            <Kpi label={t("m6e.ind.capaDelais")} value={pct(d.capa_dans_les_delais)} hint={`${t("m6e.capa.retard")} · ${d.capa_en_retard}`} tone="brand" delay={0.25} />
          </div>
        )}
      </div>
    </SectionCard>
  );
}

/** Paramètres qualité (délai CAPA, escalade, alerte de péremption) : provisoires jusqu'à confirmation QA/QC. */
function ParametresQualiteSection() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const q = useQuery({ queryKey: ["qualite-parametres"], queryFn: () => api.listAll<ParametreStock>("/api/qualite/parametres/"), retry: 0 });
  const modifier = useMutation({
    mutationFn: (v: { id: string; valeur: string }) => api.patch(`/api/qualite/parametres/${v.id}/`, { valeur: v.valeur }),
    onSuccess: () => {
      setError(null);
      void qc.invalidateQueries({ queryKey: ["qualite-parametres"] });
    },
    onError: (e) => setError(describeError(e)),
  });
  if (q.isError || !q.data) return null;
  const provisoires = q.data.filter((p) => p.est_provisoire).length;
  return (
    <SectionCard title={t("m6e.params.title")}>
      {provisoires > 0 && <p className="muted" role="note">{t("m6e.params.bandeau", { count: provisoires })}</p>}
      <table className="table" data-testid="parametres-qualite">
        <caption className="sr-only">{t("m6e.params.title")}</caption>
        <tbody>
          {q.data.map((p) => (
            <tr key={p.id}>
              <td>{p.label}</td>
              <td className="num">{formatNumber(Number(p.valeur))} {p.unite}</td>
              <td><Badge tone={p.est_provisoire ? "warn" : "ok"}>{p.est_provisoire ? t("m5e.params.provisoire") : t("m5e.params.confirme")}</Badge></td>
              <td>
                <button
                  type="button"
                  className="btn ghost"
                  onClick={() => {
                    const v = window.prompt(p.label, p.valeur);
                    if (v !== null) modifier.mutate({ id: p.id, valeur: v });
                  }}
                >
                  {t("m5e.params.modifier")}
                </button>{" "}
                {p.est_provisoire && (
                  <ActionBar actions={[{ label: t("m5e.params.confirmer"), path: `/api/qualite/parametres/${p.id}/confirmer/`, confirm: t("m5e.params.confirmConfirmer") }]} />
                )}
                {error && <span className="action-error" role="alert"> {error}</span>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </SectionCard>
  );
}
