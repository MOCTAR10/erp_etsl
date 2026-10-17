import type { ReactNode } from "react";

export interface Column<T> {
  key: string;
  header: ReactNode;
  render: (row: T) => ReactNode;
  /** Colonne numérique : alignée à droite, chiffres tabulaires. */
  num?: boolean;
}

/** Tableau de données dense (listes d'entités) — remplace les grilles de cartes KPI pour les listes. */
export function DataTable<T extends { id: string | number }>({
  columns,
  rows,
  caption,
}: {
  columns: Column<T>[];
  rows: T[];
  caption?: string;
}) {
  return (
    <div className="table-wrap">
      <table className="table">
        {caption && <caption className="sr-only">{caption}</caption>}
        <thead>
          <tr>
            {columns.map((c) => (
              <th key={c.key} scope="col" className={c.num ? "num" : undefined}>
                {c.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.id}>
              {columns.map((c) => (
                <td key={c.key} className={c.num ? "num" : undefined}>
                  {c.render(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
