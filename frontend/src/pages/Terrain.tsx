import { useQuery } from "@tanstack/react-query";
import { CheckCheck, CloudOff, RefreshCw, Trash2, Wifi } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../api/client";
import { Badge, PageHeader, SectionCard } from "../components/ui";
import { FichesSecuriteTerrain } from "../components/hse/FichesSecuriteTerrain";
import { offlineQueue, submitOffline, submitOfflineChain, syncNow, useOnline, useQueueItems } from "../lib/offline";
import { REF, type QueuedFile } from "../lib/offlineQueue";
import { useAuth } from "../store/auth";

type Tab = "pointage" | "gaz" | "reception" | "controle" | "anomalie" | "permis";

/** Types de permis proposés hors ligne (le serveur reste juge : liste HSE paramétrable). */
const TYPES_PERMIS = ["chaud", "froid", "hauteur", "levage", "confine", "atex", "electrique", "fouille", "chimique"];

/** Photo prise sur le terrain : gardée sur l'appareil (IndexedDB) jusqu'à l'envoi. */
const photo = (f: File | undefined, field = "fichier"): QueuedFile[] =>
  f ? [{ field, name: f.name || "photo.jpg", type: f.type || "image/jpeg", blob: f }] : [];

interface Ref {
  id: string | number;
  code?: string;
  label?: string;
  [k: string]: unknown;
}

/** Listes de référence : le service worker en garde une copie pour la saisie hors-ligne (URLs fixes). */
const useRef_ = (key: string, path: string) =>
  useQuery({ queryKey: ["terrain", key], queryFn: () => api.listAll<Ref>(path), retry: 0 });

const today = () => new Date().toISOString().slice(0, 10);

export function TerrainPage() {
  const { t } = useTranslation();
  const online = useOnline();
  const items = useQueueItems();
  const user = useAuth((s) => s.user);
  const [tab, setTab] = useState<Tab>("pointage");
  const [toast, setToast] = useState<string | null>(null);
  const [syncing, setSyncing] = useState(false);

  const ordres = useRef_("ordres", "/api/operations/ordres/");
  const permis = useRef_("permis", "/api/hse/permis/");
  const receipts = useRef_("receipts", "/api/achats/receipts/");
  const orderLines = useRef_("order-lines", "/api/achats/order-lines/");

  const pending = items.filter((i) => i.status === "pending").length;
  const failed = items.filter((i) => i.status === "failed").length;
  const conflicts = items.filter((i) => i.status === "conflict").length;
  const lastSync = offlineQueue.lastSyncAt();

  const enqueue = async (path: string, body: unknown, label: string) => {
    await submitOffline({ path, body, label });
    setToast(online ? t("terrain.sent") : t("terrain.saved"));
  };
  /** Saisie + photo jointe (envoyée après la saisie, avec son identifiant). */
  const enqueueAvecPhoto = async (
    parent: { path: string; body: unknown; label: string },
    child?: { path: string; body: unknown; label: string; files: QueuedFile[] },
  ) => {
    await submitOfflineChain(parent, child && child.files.length ? [child] : []);
    setToast(online ? t("terrain.sent") : t("terrain.saved"));
  };
  const sync = async () => {
    setSyncing(true);
    try {
      await syncNow();
    } finally {
      setSyncing(false);
    }
  };

  const gazPermis = (permis.data ?? []).filter(
    (p) => ["valide", "actif"].includes(String(p.statut)) && p.gaz_obligatoire,
  );

  return (
    <>
      <PageHeader title={t("terrain.title")} subtitle={t("terrain.subtitle")} />

      <div className={`terrain-status ${online ? "on" : "off"}`} role="status">
        {online ? <Wifi size={18} /> : <CloudOff size={18} />}
        <strong>{online ? t("terrain.online") : t("terrain.offline")}</strong>
        <span>
          {pending > 0 ? t("terrain.pending", { count: pending }) : t("terrain.allSynced")}
          {failed > 0 ? ` · ${t("terrain.failed", { count: failed })}` : ""}
        </span>
        {conflicts > 0 && <Badge tone="err">{t("ecarts_a3.terrain.conflicts", { count: conflicts })}</Badge>}
        {lastSync && (
          <span className="muted" style={{ fontSize: 12 }}>
            {t("ecarts_a3.terrain.lastSync", { date: new Date(lastSync).toLocaleTimeString() })}
          </span>
        )}
        <button className="btn ghost" onClick={() => void sync()} disabled={!online || syncing || pending === 0}>
          <RefreshCw size={15} /> {t("terrain.sync")}
        </button>
      </div>

      {items.length > 0 && (
        <SectionCard title={t("terrain.queue")}>
          <ul className="terrain-queue">
            {items.map((i) => (
              <li key={i.id}>
                <div>
                  <strong>{i.label}</strong>
                  <div className="muted" style={{ fontSize: 12 }}>
                    {t("ecarts_a3.terrain.horodatage", { date: new Date(i.createdAt).toLocaleString() })}
                    {i.files?.length ? ` · ${t("ecarts_a3.terrain.photoQueued")}` : ""}
                    {i.dependsOn ? ` · ${t("ecarts_a3.terrain.attente")}` : ""}
                    {i.error ? ` · ${i.error}` : ""}
                  </div>
                </div>
                <Badge tone={i.status === "pending" ? "warn" : "err"}>
                  {i.status === "failed"
                    ? t("terrain.statusFailed")
                    : i.status === "conflict"
                      ? t("ecarts_a3.terrain.statusConflict")
                      : t("terrain.statusPending")}
                </Badge>
                {i.status === "failed" && (
                  <button className="btn ghost" onClick={() => void offlineQueue.retry(i.id).then(syncNow)}>
                    <RefreshCw size={14} />
                  </button>
                )}
                {i.status === "conflict" && (
                  <button
                    className="btn ghost"
                    title={t("ecarts_a3.terrain.forceHint")}
                    onClick={() => void offlineQueue.force(i.id).then(syncNow)}
                  >
                    <CheckCheck size={14} /> {t("ecarts_a3.terrain.force")}
                  </button>
                )}
                <button
                  className="icon-btn"
                  aria-label={t("terrain.discard")}
                  onClick={() => void offlineQueue.discard(i.id)}
                >
                  <Trash2 size={15} />
                </button>
              </li>
            ))}
          </ul>
        </SectionCard>
      )}

      <div className="terrain-tabs" role="tablist">
        {(["pointage", "gaz", "reception", "controle", "anomalie", "permis"] as Tab[]).map((k) => (
          <button
            key={k}
            role="tab"
            aria-selected={tab === k}
            className={tab === k ? "active" : ""}
            onClick={() => {
              setTab(k);
              setToast(null);
            }}
          >
            {k === "permis" ? t("ecarts_a3.terrain.tabPermis") : t(`terrain.tabs.${k}`)}
          </button>
        ))}
      </div>

      {toast && (
        <p className="terrain-toast" role="status">
          {toast}
        </p>
      )}

      {tab === "pointage" && (
        <Form
          submitLabel={t("terrain.save")}
          onSubmit={async (f) => {
            await enqueue(
              "/api/operations/pointages/",
              { ordre: f.ordre, worker_name: f.worker_name, date: f.date, hours: f.hours },
              `${t("terrain.tabs.pointage")} · ${f.worker_name} · ${f.hours} h`,
            );
          }}
          fields={[
            { name: "ordre", label: t("terrain.fields.ordre"), kind: "select", required: true,
              options: (ordres.data ?? []).map((o) => ({ value: String(o.id), label: `${o.code} · ${o.label}` })) },
            { name: "worker_name", label: t("terrain.fields.operateur"), kind: "text", required: true },
            { name: "date", label: t("terrain.fields.date"), kind: "date", required: true, initial: today() },
            { name: "hours", label: t("terrain.fields.heures"), kind: "number", required: true, initial: "8", step: "0.5" },
          ]}
        />
      )}

      {tab === "gaz" && (
        <Form
          submitLabel={t("terrain.save")}
          onSubmit={async (f) => {
            await enqueue(
              `/api/hse/permis/${f.permis}/test-gaz/`,
              { resultat: f.resultat, valeur: f.valeur },
              `${t("terrain.tabs.gaz")} · ${f.resultat === "conforme" ? "OK" : "NON CONFORME"} · ${f.valeur || "—"}`,
            );
          }}
          fields={[
            { name: "permis", label: t("terrain.fields.permis"), kind: "select", required: true,
              options: gazPermis.map((p) => ({ value: String(p.id), label: `${p.code} · ${p.emplacement}` })) },
            { name: "resultat", label: t("terrain.fields.resultat"), kind: "select", required: true, initial: "conforme",
              options: [
                { value: "conforme", label: t("terrain.conforme") },
                { value: "non_conforme", label: t("terrain.nonConforme") },
              ] },
            { name: "valeur", label: t("terrain.fields.mesures"), kind: "text", placeholder: "LIE 0 %, O2 20,9 %, H2S 0 ppm" },
          ]}
        />
      )}

      {tab === "reception" && (
        <Form
          submitLabel={t("terrain.save")}
          onSubmit={async (f) => {
            await enqueue(
              "/api/achats/receipt-lines/",
              { receipt: f.receipt, purchase_order_line: f.line, quantity: f.quantity, comment: f.comment },
              `${t("terrain.tabs.reception")} · ${f.quantity}`,
            );
          }}
          fields={[
            { name: "receipt", label: t("terrain.fields.bl"), kind: "select", required: true,
              options: (receipts.data ?? []).map((r) => ({ value: String(r.id), label: String(r.code ?? r.id) })) },
            { name: "line", label: t("terrain.fields.ligneBc"), kind: "select", required: true,
              options: (orderLines.data ?? []).map((l) => ({ value: String(l.id), label: String(l.label ?? l.id) })) },
            { name: "quantity", label: t("terrain.fields.quantite"), kind: "number", required: true, step: "0.01" },
            { name: "comment", label: t("terrain.fields.commentaire"), kind: "text" },
          ]}
        />
      )}

      {tab === "controle" && (
        <Form
          submitLabel={t("terrain.save")}
          onSubmit={async (f, fichiers) => {
            await enqueueAvecPhoto(
              {
                path: "/api/qualite/controles/",
                body: { type_controle: f.type_controle, point_controle: f.point_controle, resultat: f.resultat,
                  date_controle: f.date, statut: "en_cours" },
                label: `${t("terrain.tabs.controle")} · ${f.type_controle} · ${f.point_controle}`,
              },
              {
                path: "/api/qualite/images-controle/",
                body: { controle: REF, legende: f.point_controle },
                label: `${t("terrain.tabs.controle")} · ${f.point_controle} · ${t("ecarts_a3.terrain.photoQueued")}`,
                files: photo(fichiers.photo),
              },
            );
          }}
          fields={[
            { name: "type_controle", label: t("terrain.fields.typeControle"), kind: "select", required: true, initial: "cnd",
              options: ["visuel", "dimensionnel", "cnd", "peinture"].map((v) => ({ value: v, label: v.toUpperCase() })) },
            { name: "point_controle", label: t("terrain.fields.pointControle"), kind: "text", required: true },
            { name: "resultat", label: t("terrain.fields.resultat"), kind: "select", required: true, initial: "conforme",
              options: [
                { value: "conforme", label: t("terrain.conforme") },
                { value: "reserve", label: t("terrain.reserve") },
                { value: "non_conforme", label: t("terrain.nonConforme") },
              ] },
            { name: "date", label: t("terrain.fields.date"), kind: "date", required: true, initial: today() },
            { name: "photo", label: t("ecarts_a3.terrain.photoCnd"), kind: "file" },
          ]}
        />
      )}

      {tab === "permis" && (
        <Form
          submitLabel={t("terrain.save")}
          onSubmit={async (f, fichiers) => {
            // Demande de permis saisie hors ligne (CL-OM-08) : circuit de visas inchangé au serveur.
            await enqueueAvecPhoto(
              {
                path: "/api/hse/permis/",
                body: { type_permis: f.type_permis, emplacement: f.emplacement, description: f.description,
                  mesures: f.mesures, date_debut: f.date_debut, ...(f.ordre ? { ordre: f.ordre } : {}) },
                label: `${t("ecarts_a3.terrain.tabPermis")} · ${f.type_permis} · ${f.emplacement}`,
              },
              {
                path: `/api/hse/permis/${REF}/joindre-photo/`,
                body: {},
                label: `${t("ecarts_a3.terrain.tabPermis")} · ${f.emplacement} · ${t("ecarts_a3.terrain.photoQueued")}`,
                files: photo(fichiers.photo),
              },
            );
          }}
          fields={[
            { name: "type_permis", label: t("ecarts_a3.terrain.permis.type"), kind: "select", required: true, initial: "chaud",
              options: TYPES_PERMIS.map((v) => ({ value: v, label: t(`ecarts_a3.terrain.types.${v}`) })) },
            { name: "emplacement", label: t("ecarts_a3.terrain.permis.emplacement"), kind: "text", required: true },
            { name: "description", label: t("ecarts_a3.terrain.permis.description"), kind: "text", required: true },
            { name: "mesures", label: t("ecarts_a3.terrain.permis.mesures"), kind: "text" },
            { name: "ordre", label: t("terrain.fields.ordre"), kind: "select",
              options: (ordres.data ?? []).map((o) => ({ value: String(o.id), label: `${o.code} · ${o.label}` })) },
            { name: "date_debut", label: t("ecarts_a3.terrain.permis.debut"), kind: "date", required: true, initial: today() },
            { name: "photo", label: t("ecarts_a3.terrain.photo"), kind: "file" },
          ]}
        />
      )}

      {tab === "anomalie" && (
        <Form
          submitLabel={t("terrain.save")}
          onSubmit={async (f) => {
            // Signalement d'anomalie HSE (CDC M7-08) : situation dangereuse, déclarée hors ligne si besoin.
            await enqueue(
              "/api/hse/incidents/",
              { type_incident: "situation_dangereuse", gravite: f.gravite, date_evenement: new Date().toISOString(),
                lieu: f.lieu, zone: f.zone, description: f.description },
              `${t("terrain.tabs.anomalie")} · ${f.lieu}`,
            );
          }}
          fields={[
            { name: "lieu", label: t("terrain.anomalie.lieu"), kind: "text", required: true },
            { name: "zone", label: t("terrain.anomalie.zone"), kind: "select", required: true, initial: "chantier",
              options: ["atelier", "chantier", "bureau", "site_client", "site_gr"].map((v) => ({ value: v, label: t(`m7e.zones.${v}`) })) },
            { name: "gravite", label: t("terrain.anomalie.gravite"), kind: "select", required: true, initial: "mineure",
              options: ["mineure", "majeure", "critique"].map((v) => ({ value: v, label: t(`terrain.anomalie.gravites.${v}`) })) },
            { name: "description", label: t("terrain.anomalie.description"), kind: "text", required: true },
          ]}
        />
      )}

      <p className="muted" style={{ fontSize: 12 }} data-testid="terrain-cache">
        {t("ecarts_a3.terrain.cache", {
          ordres: (ordres.data ?? []).length,
          permis: (permis.data ?? []).length,
          receptions: (receipts.data ?? []).length,
        })}{" "}
        {t("ecarts_a3.terrain.provisoire")}
      </p>

      <FichesSecuriteTerrain />
      {user ? null : null}
    </>
  );
}

interface Field {
  name: string;
  label: string;
  kind: "text" | "number" | "date" | "select" | "file";
  required?: boolean;
  initial?: string;
  step?: string;
  placeholder?: string;
  options?: { value: string; label: string }[];
}

function Form({
  fields,
  onSubmit,
  submitLabel,
}: {
  fields: Field[];
  onSubmit: (values: Record<string, string>, files: Record<string, File | undefined>) => Promise<void>;
  submitLabel: string;
}) {
  const init = () => Object.fromEntries(fields.map((f) => [f.name, f.initial ?? ""]));
  const [values, setValues] = useState<Record<string, string>>(init);
  const [files, setFiles] = useState<Record<string, File | undefined>>({});
  const [formKey, setFormKey] = useState(0); // remet à zéro les champs fichier après envoi
  const [busy, setBusy] = useState(false);

  return (
    <form
      key={formKey}
      className="terrain-form"
      onSubmit={async (e) => {
        e.preventDefault();
        setBusy(true);
        try {
          await onSubmit(values, files);
          setValues(init());
          setFiles({});
          setFormKey((k) => k + 1);
        } finally {
          setBusy(false);
        }
      }}
    >
      {fields.map((f) => (
        <label className="field" key={f.name}>
          <span>{f.label}</span>
          {f.kind === "file" ? (
            <input
              type="file"
              accept="image/*"
              capture="environment"
              onChange={(e) => setFiles({ ...files, [f.name]: e.target.files?.[0] })}
            />
          ) : f.kind === "select" ? (
            <select required={f.required} value={values[f.name]} onChange={(e) => setValues({ ...values, [f.name]: e.target.value })}>
              <option value="">—</option>
              {(f.options ?? []).map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          ) : (
            <input
              type={f.kind}
              required={f.required}
              step={f.step}
              placeholder={f.placeholder}
              inputMode={f.kind === "number" ? "decimal" : undefined}
              value={values[f.name]}
              onChange={(e) => setValues({ ...values, [f.name]: e.target.value })}
            />
          )}
        </label>
      ))}
      <button className="btn terrain-submit" type="submit" disabled={busy}>
        {submitLabel}
      </button>
    </form>
  );
}
