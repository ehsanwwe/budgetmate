import { redirect } from "next/navigation";

export default async function AdminUserDetailRedirect({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  redirect(`/fa/admin/users/${id}`);
}
