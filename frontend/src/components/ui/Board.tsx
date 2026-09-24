import { motion } from "motion/react";
import type { LucideIcon } from "lucide-react";
import type { CSSProperties, ReactNode } from "react";

import { motionTokens } from "../../theme/tokens";
import { itemRefresh } from "../../lib/motion";
import { Badge } from "./Badge";
import type { BadgeTone } from "./Badge";

export function Board({ children, className = "", style }: { children: ReactNode; className?: string; style?: CSSProperties }) {
  return (
    <div className={`board ${className}`.trim()} style={style}>
      {children}
    </div>
  );
}

export function BoardColumn({
  title,
  count,
  tone = "neutral",
  icon: Icon,
  children,
  delay = 0,
  minWidth,
}: {
  title: ReactNode;
  count?: number;
  tone?: BadgeTone;
  icon?: LucideIcon;
  children: ReactNode;
  delay?: number;
  minWidth?: number;
}) {
  return (
    <motion.section
      layout
      initial={{ opacity: 0, y: motionTokens.distance.sm }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: motionTokens.duration.base, ease: motionTokens.ease.out, delay }}
      className="board-col"
      style={minWidth ? { minWidth } : undefined}
    >
      <div className="board-col-head">
        <span className="title">
          {Icon ? <Icon size={13} /> : null}
          {title}
        </span>
        {typeof count === "number" ? <Badge tone={tone}>{count}</Badge> : null}
      </div>
      {children}
    </motion.section>
  );
}

export function BoardCard({
  children,
  delay = 0,
  className = "",
}: {
  children: ReactNode;
  delay?: number;
  className?: string;
}) {
  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: motionTokens.distance.xs, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, scale: 0.96 }}
      transition={{ ...itemRefresh, delay }}
      className={`task-card ${className}`.trim()}
    >
      {children}
    </motion.div>
  );
}