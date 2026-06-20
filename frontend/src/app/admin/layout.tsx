// Old non-localized admin route. All child pages redirect to /fa/admin/...
// This layout is intentionally a passthrough — UI lives under app/[locale]/admin/.
export default function AdminLegacyLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}
