import type { Variants } from "framer-motion";

export const EASE_OUT_EXPO = [0.22, 1, 0.36, 1] as const;
export const EASE_SPRING   = [0.34, 1.56, 0.64, 1] as const;

export const fadeUp: Variants = {
  hidden:  { opacity: 0, y: 20 },
  visible: {
    opacity: 1, y: 0,
    transition: { duration: 0.5, ease: EASE_OUT_EXPO },
  },
  exit: { opacity: 0, y: -10, transition: { duration: 0.22 } },
};

export const staggerContainer: Variants = {
  hidden:  {},
  visible: {
    transition: { staggerChildren: 0.07, delayChildren: 0.05 },
  },
};

export const slideInLeft: Variants = {
  hidden:  { opacity: 0, x: -28 },
  visible: {
    opacity: 1, x: 0,
    transition: { duration: 0.5, ease: EASE_OUT_EXPO },
  },
};

export const slideInRight: Variants = {
  hidden:  { opacity: 0, x: 28 },
  visible: {
    opacity: 1, x: 0,
    transition: { duration: 0.5, ease: EASE_OUT_EXPO },
  },
};

export const popIn: Variants = {
  hidden:  { opacity: 0, scale: 0.78 },
  visible: {
    opacity: 1, scale: 1,
    transition: { duration: 0.38, ease: EASE_SPRING },
  },
};
