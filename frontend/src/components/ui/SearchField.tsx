import { Search } from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

/** Champ de recherche : la valeur n'est transmise qu'après `delay` ms sans frappe (évite une requête par touche). */
export function SearchField({
  value,
  onChange,
  placeholder,
  delay = 300,
}: {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  delay?: number;
}) {
  const { t } = useTranslation();
  const [local, setLocal] = useState(value);

  useEffect(() => setLocal(value), [value]);
  useEffect(() => {
    if (local === value) return;
    const id = setTimeout(() => onChange(local), delay);
    return () => clearTimeout(id);
  }, [local, value, delay, onChange]);

  return (
    <label className="search-field">
      <Search size={14} aria-hidden />
      <input
        type="search"
       
        value={local}
        onChange={(e) => setLocal(e.target.value)}
        placeholder={placeholder ?? t("common.searchPlaceholder")}
        aria-label={placeholder ?? t("common.searchLabel")}
      />
    </label>
  );
}
