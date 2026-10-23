import type { Story, StoryDefault } from "@ladle/react";
import { AlertTriangle, CheckCircle2, Clock } from "lucide-react";

import { Badge } from "./Badge";
import type { BadgeTone } from "./Badge";

export default { title: "Kit UI / Badge" } satisfies StoryDefault;

const TONS: [BadgeTone, string][] = [
  ["ok", "Validé"],
  ["warn", "En attente"],
  ["err", "Rejeté"],
  ["brand", "Émis"],
  ["accent", "Prioritaire"],
  ["info", "Brouillon"],
  ["neutral", "Archivé"],
];

const Tonalites = () => (
  <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
    {TONS.map(([tone, label]) => (
      <Badge key={tone} tone={tone}>
        {label}
      </Badge>
    ))}
  </div>
);

export const Tons: Story = () => <Tonalites />;
Tons.storyName = "Tonalités";

export const AvecIcone: Story = () => (
  <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
    <Badge tone="ok" icon={CheckCircle2}>Conforme</Badge>
    <Badge tone="warn" icon={Clock}>Échéance J-15</Badge>
    <Badge tone="err" icon={AlertTriangle}>Échu</Badge>
  </div>
);
AvecIcone.storyName = "Avec icône";

export const Sombre: Story = () => <Tonalites />;
Sombre.meta = { theme: "dark" };
