import { motion } from "motion/react";
import type { ComponentProps, ReactNode } from "react";

type Props = Omit<ComponentProps<typeof motion.button>, "children"> & { children: ReactNode };

/** Bouton avec retour de pression subtil (respecte prefers-reduced-motion). */
export function Pressable({ children, className = "", ...rest }: Props) {
  return (
    <motion.button whileTap={{ scale: 0.98 }} className={className} {...rest}>
      {children}
    </motion.button>
  );
}