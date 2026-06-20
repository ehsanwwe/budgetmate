"use client";
import React, { useState, useRef, useEffect, forwardRef, useMemo, ComponentType } from "react";
import PhoneInput, { getCountryCallingCode, isValidPhoneNumber } from "react-phone-number-input";
import type { Country } from "react-phone-number-input";
import enLabels from "react-phone-number-input/locale/en.json";
import "react-phone-number-input/style.css";
import type { Locale } from "@/i18n/config";

// --------------------------------------------------------------------------
// Helpers
// --------------------------------------------------------------------------

const LOCALE_DEFAULT_COUNTRY: Record<string, Country> = {
  fa: "IR",
  ar: "SA",
  en: "US",
  de: "DE",
  zh: "CN",
};

const toFlag = (cc: string) =>
  String.fromCodePoint(...[...cc.toUpperCase()].map((c) => 127397 + c.charCodeAt(0)));

// --------------------------------------------------------------------------
// Country dropdown (replaces the library's default <select>)
// --------------------------------------------------------------------------

interface CountryOption {
  value?: Country;
  label: string;
  divider?: boolean;
}

interface CountrySelectComponentProps {
  value?: string;
  onChange(value?: string): void;
  options: CountryOption[];
  iconComponent: ComponentType<{ country?: Country; label: string }>;
  disabled?: boolean;
  searchPlaceholder?: string;
}

function CountryDropdown({
  value,
  onChange,
  options,
  disabled,
  searchPlaceholder = "Search countries…",
}: CountrySelectComponentProps) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const containerRef = useRef<HTMLDivElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);

  const allCountries = useMemo(
    () => options.filter((o): o is CountryOption & { value: Country } => !!o.value && !o.divider),
    [options]
  );

  const filtered = useMemo(
    () => allCountries.filter((o) => o.label.toLowerCase().includes(search.toLowerCase())),
    [allCountries, search]
  );

  // Close on outside click
  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (!containerRef.current?.contains(e.target as Node)) {
        setOpen(false);
        setSearch("");
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  // Auto-focus search when dropdown opens
  useEffect(() => {
    if (open) setTimeout(() => searchRef.current?.focus(), 60);
  }, [open]);

  // Close on Escape
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") { setOpen(false); setSearch(""); }
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [open]);

  const calling = value ? `+${getCountryCallingCode(value as Country)}` : "";
  const flag = value ? toFlag(value) : "🌐";

  return (
    <div ref={containerRef} className="relative h-full" dir="ltr">
      {/* Trigger */}
      <button
        type="button"
        disabled={disabled}
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-1.5 px-3 py-4 bg-[#2d1812]/5 border-r border-[#2d1812]/10 shrink-0 hover:bg-[#2d1812]/10 transition-colors h-full"
        aria-label="Select country"
        aria-expanded={open}
        aria-haspopup="listbox"
      >
        <span className="text-xl leading-none">{flag}</span>
        <span className="text-sm font-bold text-[#2d1812] font-mono tabular-nums">{calling}</span>
        <svg
          className={`w-3 h-3 text-[#2d1812]/40 transition-transform duration-200 ${open ? "rotate-180" : ""}`}
          fill="none"
          stroke="currentColor"
          strokeWidth={2.5}
          viewBox="0 0 24 24"
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {/* Dropdown */}
      {open && (
        <div
          role="listbox"
          className="absolute top-full left-0 z-[60] mt-2 w-72 bg-white rounded-2xl shadow-2xl border border-gray-100 overflow-hidden"
        >
          {/* Search */}
          <div className="p-2 border-b border-gray-100">
            <input
              ref={searchRef}
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder={searchPlaceholder}
              className="w-full px-3 py-2 text-sm rounded-xl bg-[#f5f1eb] placeholder:text-gray-400 focus:outline-none"
            />
          </div>

          {/* Country list */}
          <ul className="max-h-64 overflow-y-auto py-1">
            {filtered.length === 0 ? (
              <li className="py-5 text-center text-sm text-gray-400">No results</li>
            ) : (
              filtered.map((opt) => (
                <li key={opt.value} role="option" aria-selected={opt.value === value}>
                  <button
                    type="button"
                    onClick={() => {
                      onChange(opt.value as string);
                      setOpen(false);
                      setSearch("");
                    }}
                    className={`w-full flex items-center gap-3 px-4 py-2.5 text-sm text-left transition-colors ${
                      opt.value === value
                        ? "bg-emerald-50 text-emerald-800 font-semibold"
                        : "text-gray-700 hover:bg-gray-50"
                    }`}
                  >
                    <span className="w-7 shrink-0 text-center text-base leading-none">
                      {toFlag(opt.value as string)}
                    </span>
                    <span className="flex-1 truncate">{opt.label}</span>
                    <span className="shrink-0 text-xs font-mono text-gray-400">
                      +{getCountryCallingCode(opt.value as Country)}
                    </span>
                  </button>
                </li>
              ))
            )}
          </ul>
        </div>
      )}
    </div>
  );
}

// --------------------------------------------------------------------------
// Styled phone number input — replaces the library's default <input>
// --------------------------------------------------------------------------

const PhoneNumberInput = forwardRef<
  HTMLInputElement,
  React.InputHTMLAttributes<HTMLInputElement>
>(
  // Destructure className so the library's default class doesn't override ours
  ({ className: _, ...props }, ref) => ( // eslint-disable-line @typescript-eslint/no-unused-vars
    <input
      {...props}
      ref={ref}
      className="flex-1 min-w-0 px-4 py-4 bg-transparent text-xl font-mono tabular-nums text-[#2d1812] placeholder:text-gray-300 focus:outline-none"
      dir="ltr"
    />
  )
);
PhoneNumberInput.displayName = "PhoneNumberInput";

// --------------------------------------------------------------------------
// Public component
// --------------------------------------------------------------------------

export interface InternationalPhoneInputProps {
  value: string;
  onChange: (value: string) => void;
  locale: Locale;
  error?: string;
  disabled?: boolean;
  placeholder?: string;
  countrySearchPlaceholder?: string;
}

export default function InternationalPhoneInput({
  value,
  onChange,
  locale,
  error,
  disabled,
  placeholder,
  countrySearchPlaceholder,
}: InternationalPhoneInputProps) {
  const defaultCountry = LOCALE_DEFAULT_COUNTRY[locale] ?? "IR";
  const isValid = value ? isValidPhoneNumber(value) : false;

  // Stable countrySelectComponent that has searchPlaceholder in closure.
  // Named function expression so React DevTools and ESLint react/display-name are happy.
  const CountrySelectComponent = useMemo(
    () =>
      function CountrySelectWithSearch(props: CountrySelectComponentProps) {
        return (
          <CountryDropdown
            {...props}
            searchPlaceholder={countrySearchPlaceholder}
          />
        );
      },
    [countrySearchPlaceholder]
  );

  return (
    // dir="ltr" ensures the phone input is always rendered left-to-right
    <div dir="ltr">
      <div
        className={`flex items-stretch rounded-2xl bg-white shadow-sm border-2 transition-colors ${
          error
            ? "border-red-400"
            : isValid
            ? "border-emerald-400"
            : "border-transparent focus-within:border-[#2d1812]/30"
        }`}
      >
        <PhoneInput
          value={value}
          onChange={(val) => onChange(val ?? "")}
          defaultCountry={defaultCountry}
          international
          countrySelectComponent={CountrySelectComponent}
          inputComponent={PhoneNumberInput}
          placeholder={placeholder}
          disabled={disabled}
          labels={enLabels as Record<string, string>}
          addInternationalOption={false}
          className="flex flex-1 items-stretch"
        />
      </div>
      {error && (
        <p className="mt-2 text-sm text-red-500">{error}</p>
      )}
    </div>
  );
}
