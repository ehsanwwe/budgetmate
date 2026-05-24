"use client";

import * as React from "react";
import { cn } from "@/lib/utils";

const DIGIT_MAP: Record<string, string> = {
  "۰": "0",
  "۱": "1",
  "۲": "2",
  "۳": "3",
  "۴": "4",
  "۵": "5",
  "۶": "6",
  "۷": "7",
  "۸": "8",
  "۹": "9",
  "٠": "0",
  "١": "1",
  "٢": "2",
  "٣": "3",
  "٤": "4",
  "٥": "5",
  "٦": "6",
  "٧": "7",
  "٨": "8",
  "٩": "9",
};

function toEnglishDigits(value: string): string {
  return value.replace(/[۰-۹٠-٩]/g, (digit) => DIGIT_MAP[digit] || digit);
}

function parseAmount(value: string): number | undefined {
  const digits = toEnglishDigits(value).replace(/[^\d]/g, "");
  return digits ? Number(digits) : undefined;
}

function formatAmount(value: number | undefined): string {
  if (value === undefined || Number.isNaN(value)) return "";
  return new Intl.NumberFormat("fa-IR").format(value);
}

export interface MoneyInputProps extends Omit<React.InputHTMLAttributes<HTMLInputElement>, "type" | "value" | "onChange"> {
  value?: number;
  onChange: (value: number | undefined) => void;
  error?: boolean;
}

export function MoneyInput({ value, onChange, className, error, disabled, ...props }: MoneyInputProps) {
  const displayValue = React.useMemo(() => formatAmount(value), [value]);

  return (
    <input
      {...props}
      type="text"
      inputMode="numeric"
      dir="ltr"
      value={displayValue}
      disabled={disabled}
      onChange={(event) => onChange(parseAmount(event.target.value))}
      className={cn(
        "flex h-10 w-full rounded-xl border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50",
        "text-left",
        error && "border-destructive focus-visible:ring-destructive",
        className
      )}
    />
  );
}
