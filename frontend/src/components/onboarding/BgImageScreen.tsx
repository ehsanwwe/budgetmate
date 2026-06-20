"use client";
import { motion } from "framer-motion";
import { ReactNode } from "react";
import { useLocale } from "@/i18n/LocaleContext";
import { isRTL } from "@/i18n/config";

interface Props {
  imageUrl: string;
  children: ReactNode;
  back?: boolean;
}

export default function BgImageScreen({ imageUrl, children, back = false }: Props) {
  const { locale } = useLocale();
  const dir = isRTL(locale) ? "rtl" : "ltr";
  const directionMultiplier = back ? -1 : 1;

  return (
    <motion.div
      initial={{ x: 50 * directionMultiplier, opacity: 0 }}
      animate={{ x: 0, opacity: 1 }}
      exit={{ x: -50 * directionMultiplier, opacity: 0 }}
      transition={{ duration: 0.3, ease: "easeOut" }}
      className="min-h-screen flex flex-col relative overflow-hidden"
      dir={dir}
    >
      {/* Background image — top 60% */}
      <div className="absolute inset-0">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={imageUrl}
          alt=""
          className="w-full h-full object-cover"
        />
        {/* Gradient overlay — transparent at top, dark at bottom */}
        <div className="absolute inset-0 bg-gradient-to-t from-[#1a0f0a] via-[#1a0f0a]/70 to-transparent" />
      </div>

      {/* Content at bottom 40% */}
      <div className="relative flex-1 flex flex-col justify-end max-w-[440px] mx-auto w-full px-6 pb-12 pt-[60vh]">
        {children}
      </div>
    </motion.div>
  );
}
