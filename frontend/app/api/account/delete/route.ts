import { createClient } from "@supabase/supabase-js";
import { NextResponse } from "next/server";
import { createSupabaseServerClient } from "@/lib/supabase/server";

export async function POST() {
  const supabase = await createSupabaseServerClient();
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL?.trim();
  const serviceRoleKey = process.env.SUPABASE_SERVICE_ROLE_KEY?.trim();
  if (!supabase || !url || !serviceRoleKey) {
    return NextResponse.json({ error: "Account deletion is not configured." }, { status: 503 });
  }

  const { data, error } = await supabase.auth.getUser();
  if (error || !data.user) {
    return NextResponse.json({ error: "Authentication required." }, { status: 401 });
  }

  const admin = createClient(url, serviceRoleKey, {
    auth: { autoRefreshToken: false, persistSession: false },
  });
  const result = await admin.auth.admin.deleteUser(data.user.id);
  if (result.error) {
    return NextResponse.json({ error: "Account deletion failed." }, { status: 500 });
  }

  return NextResponse.json({ deleted: true }, {
    headers: { "Cache-Control": "no-store" },
  });
}
