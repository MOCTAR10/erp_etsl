import { Paperclip, X } from "lucide-react";
import { useId, useRef, useState } from "react";
import type { ChangeEvent } from "react";
import { useTranslation } from "react-i18next";

export interface FileFieldProps {
  /** Identifiant du champ natif (pour un `<label htmlFor>` externe) ; généré sinon. */
  id?: string;
  /** Nom du champ dans un `FormData` (formulaire natif). */
  name?: string;
  /** Types acceptés (`".csv,.xml"`, `"image/*"`…). */
  accept?: string;
  /** Capture appareil photo (terrain, mobile). */
  capture?: "user" | "environment";
  multiple?: boolean;
  required?: boolean;
  disabled?: boolean;
  /** Texte du bouton (défaut « Choisir un fichier »). */
  buttonLabel?: string;
  /** Nom accessible quand aucun `<label>` externe n'est relié (ex. « Relevé MT940 »). */
  "aria-label"?: string;
  /** Texte affiché tant qu'aucun fichier n'est choisi (défaut « Aucun fichier choisi »). */
  placeholder?: string;
  /** Fichier(s) choisi(s) ; `[]` après « Retirer ». */
  onFiles?: (files: File[]) => void;
  /** Raccourci : premier fichier choisi, `null` après « Retirer ». */
  onChange?: (file: File | null) => void;
}

/**
 * Sélecteur de fichier du kit (B10) : remplace l'`<input type="file">` natif, dont le bouton et la mention
 * (« Choose File / No file chosen ») suivent la langue du navigateur et ignorent le thème. Le champ natif reste
 * dans le DOM (visuellement masqué, focusable, `name` pour `FormData`) ; le bouton `.btn` est son `<label>`,
 * le nom du fichier s'affiche en texte discret, avec « Retirer ».
 * `<FileField accept=".sta,.mt940" aria-label="Relevé bancaire" onChange={setFichier} />`
 */
export function FileField({
  id,
  name,
  accept,
  capture,
  multiple = false,
  required,
  disabled,
  buttonLabel,
  placeholder,
  onFiles,
  onChange,
  "aria-label": ariaLabel,
}: FileFieldProps) {
  const { t } = useTranslation();
  const auto = useId();
  const inputId = id ?? `${auto}-file`;
  const statusId = `${inputId}-status`;
  const input = useRef<HTMLInputElement>(null);
  const [files, setFiles] = useState<File[]>([]);

  const emit = (next: File[]) => {
    setFiles(next);
    onFiles?.(next);
    onChange?.(next[0] ?? null);
  };
  const choose = (e: ChangeEvent<HTMLInputElement>) => emit(Array.from(e.target.files ?? []));
  const clear = () => {
    if (input.current) input.current.value = "";
    emit([]);
    input.current?.focus();
  };

  const names = files.map((f) => f.name).join(", ");
  return (
    <div className={`ui-file${disabled ? " is-disabled" : ""}`}>
      <input
        ref={input}
        id={inputId}
        className="ui-file-input"
        type="file"
        name={name}
        accept={accept}
        capture={capture}
        multiple={multiple}
        required={required}
        disabled={disabled}
        aria-label={ariaLabel}
        aria-describedby={statusId}
        onChange={choose}
      />
      <label htmlFor={inputId} className="btn ghost sm ui-file-btn">
        <Paperclip size={14} aria-hidden />
        {buttonLabel ?? t("premiumKit.file.choose")}
      </label>
      <span id={statusId} className={`ui-file-name${files.length ? " has-file" : ""}`} title={names || undefined}>
        {files.length ? names : (placeholder ?? t("premiumKit.file.none"))}
      </span>
      {files.length > 0 && !disabled ? (
        <button type="button" className="icon-btn ui-file-clear" aria-label={t("premiumKit.file.clear")} onClick={clear}>
          <X size={14} aria-hidden />
        </button>
      ) : null}
    </div>
  );
}
