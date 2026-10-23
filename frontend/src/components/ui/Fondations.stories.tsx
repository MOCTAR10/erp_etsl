import type { Story, StoryDefault } from "@ladle/react";

import { designTokens, palette } from "../../theme/tokens";
import type { ThemeColors } from "../../theme/tokens";

export default { title: "Kit UI / Fondations" } satisfies StoryDefault;

const GROUPES: { titre: string; cles: (keyof ThemeColors)[] }[] = [
  { titre: "Surfaces et texte", cles: ["bg", "surface", "surface2", "border", "borderStrong", "text", "textMuted", "textSubtle"] },
  { titre: "Marque", cles: ["brand", "brandDeep", "brandSoft", "brandTint", "accent", "accentSoft", "steel", "steelSoft"] },
  { titre: "Sémantique", cles: ["ok", "okSoft", "warn", "warnSoft", "err", "errSoft", "info", "infoSoft"] },
];

function Palette({ mode }: { mode: "light" | "dark" }) {
  const p = palette[mode];
  return (
    <div style={{ display: "grid", gap: 24 }}>
      {GROUPES.map((g) => (
        <section key={g.titre}>
          <h3 style={{ margin: "0 0 12px" }}>{g.titre}</h3>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(150px, 1fr))", gap: 12 }}>
            {g.cles.map((k) => (
              <div key={k} className="card" style={{ padding: 0, overflow: "hidden" }}>
                <div style={{ height: 56, background: p[k], borderBottom: "1px solid var(--border)" }} />
                <div style={{ padding: "8px 12px" }}>
                  <div style={{ fontWeight: 600, fontSize: 13 }}>{k}</div>
                  <code className="muted" style={{ fontSize: 12 }}>{p[k]}</code>
                </div>
              </div>
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}

export const PaletteClaire: Story = () => <Palette mode="light" />;
PaletteClaire.storyName = "Palette claire";

export const PaletteSombre: Story = () => <Palette mode="dark" />;
PaletteSombre.storyName = "Palette sombre";
PaletteSombre.meta = { theme: "dark" };

export const Typographie: Story = () => (
  <div style={{ display: "grid", gap: 16 }}>
    {Object.entries(designTokens.font).map(([nom, f]) => (
      <div key={nom} style={{ display: "grid", gridTemplateColumns: "120px 1fr", alignItems: "baseline", gap: 16 }}>
        <code className="muted">
          {nom} · {f.size}/{f.line}
        </code>
        <span style={{ fontSize: f.size, lineHeight: `${f.line}px`, fontVariantNumeric: "tabular-nums" }}>
          Bon de commande 25 000 000 FCFA
        </span>
      </div>
    ))}
  </div>
);

export const EspacesRayonsOmbres: Story = () => (
  <div style={{ display: "grid", gap: 32 }}>
    <section>
      <h3>Espacements (rythme 8 px)</h3>
      {Object.entries(designTokens.space).map(([k, v]) => (
        <div key={k} style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 6 }}>
          <code className="muted" style={{ width: 80 }}>space-{k}</code>
          <span style={{ width: v, height: 12, background: "var(--brand)", borderRadius: 2 }} />
          <span className="muted">{v} px</span>
        </div>
      ))}
    </section>
    <section style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
      {Object.entries(designTokens.radius).filter(([k]) => k !== "full").map(([k, r]) => (
        <div key={k} className="card" style={{ borderRadius: r, width: 120, textAlign: "center" }}>
          radius-{k}<br />
          <span className="muted">{r} px</span>
        </div>
      ))}
    </section>
    <section style={{ display: "flex", gap: 24, flexWrap: "wrap" }}>
      {Object.entries(designTokens.shadow).map(([k, s]) => (
        <div key={k} style={{ boxShadow: s, background: "var(--surface)", borderRadius: 10, padding: 24, width: 160 }}>
          shadow-{k}
        </div>
      ))}
    </section>
  </div>
);
EspacesRayonsOmbres.storyName = "Espaces rayons et ombres";
