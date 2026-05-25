"use client";
import { motion } from "framer-motion";
import { ReactNode } from "react";

interface Props {
  children: ReactNode;
  back?: boolean;
  className?: string;
}

export default function PageTransition({ children, back = false, className = "" }: Props) {
  const dir = back ? -1 : 1;
  return (
    <motion.div
      initial={{ x: 50 * dir, opacity: 0 }}
      animate={{ x: 0, opacity: 1 }}
      exit={{ x: -50 * dir, opacity: 0 }}
      transition={{ duration: 0.3, ease: "easeOut" }}
      className={className}
    >
      {children}
    </motion.div>
  );
}
