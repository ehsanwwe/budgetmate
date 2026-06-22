"use client";

import { useState } from "react";
import { cn } from "@/lib/utils";
import { isoToJalali, jalaliToIso } from "@/lib/fmt";

interface JalaliDateInputProps {
  /** Current value as Gregorian ISO string (YYYY-MM-DD) or empty string. */
  value?: string;
  /** Called with Gregorian ISO string when a valid date is entered, or "" when cleared. */
  onChange: (isoDate: string) => void;
  /**
   * Locale code. "fa" → Jalali calendar with Persian digits.
   * Any other value → plain Gregorian text input.
   */
  locale?: string;
  placeholder?: string;
  disabled?: boolean;
  error?: boolean;
  className?: string;
}

/**
 * Controlled date input with Jalali/Shamsi support for Persian locale.
 *
 * For locale="fa":
 *   - Displays Jalali date in yyyy-mm-dd with Persian digits.
 *   - Accepts both Persian (۰-۹) and Latin (0-9) digit input.
 *   - Converts valid Jalali input to Gregorian ISO before calling onChange.
 *   - Syncs display when value prop changes externally (e.g., form reset).
 *
 * For other locales:
 *   - Plain text input expecting Gregorian YYYY-MM-DD.
 *
 * Does NOT use <input type="date"> because native date inputs are Gregorian
 * and locale-dependent; they cannot show Jalali dates reliably.
 */
export function JalaliDateInput({
  value,
  onChange,
  locale = "fa",
  placeholder,
  disabled,
  error,
  className,
}: JalaliDateInputProps) {
  const isJalali = locale === "fa";

  const [localText, setLocalText] = useState<string>(() =>
    !value ? "" : isJalali ? isoToJalali(value) : value
  );
  // Track prev value so we can sync external changes without useEffect
  const [prevValue, setPrevValue] = useState<string | undefined>(value);

  // "Derived state during render" — React-recommended pattern for tracking prop changes.
  // Runs synchronously when the value prop changes (e.g., form reset).
  if (value !== prevValue) {
    setPrevValue(value);
    setLocalText(!value ? "" : isJalali ? isoToJalali(value) : value);
  }

  function handleChange(e: React.ChangeEvent<HTMLInputElement>) {
    const raw = e.target.value;
    setLocalText(raw);

    if (!raw) {
      onChange("");
      return;
    }

    if (isJalali) {
      const iso = jalaliToIso(raw);
      if (iso) onChange(iso);
    } else {
      if (/^\d{4}-\d{2}-\d{2}$/.test(raw)) onChange(raw);
    }
  }

  const defaultPlaceholder = isJalali ? "۱۴۰۵-۰۱-۰۱" : "2026-01-01";

  return (
    <input
      type="text"
      inputMode="numeric"
      value={localText}
      onChange={handleChange}
      placeholder={placeholder ?? defaultPlaceholder}
      disabled={disabled}
      dir={isJalali ? "rtl" : "ltr"}
      className={cn(
        "flex h-10 w-full rounded-xl border border-input bg-background px-3 py-2 text-sm",
        "placeholder:text-muted-foreground",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
        "disabled:cursor-not-allowed disabled:opacity-50",
        error && "border-destructive focus-visible:ring-destructive",
        className,
      )}
    />
  );
}
