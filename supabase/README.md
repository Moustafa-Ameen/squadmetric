# SquadMetric Supabase setup

SquadMetric uses Supabase for email/password and Google authentication plus owner-only account data.

1. Create a Supabase project.
2. Apply `migrations/202608210001_account_foundation.sql` with the Supabase CLI or SQL editor.
3. Enable email/password and Google in Authentication → Providers.
4. Set the production Site URL and add these exact redirect URLs:
   - `http://localhost:3000/auth/callback` for local development
   - `https://YOUR_DOMAIN/auth/callback` for production
   - the equivalent callback for any explicitly trusted preview deployment
5. Configure custom SMTP before production. Supabase's trial mailer is not a production delivery service.
6. For SSR-safe email links, update the Supabase email templates:
   - Confirm signup: `{{ .SiteURL }}/auth/confirm?token_hash={{ .TokenHash }}&type=email&next=/onboarding`
   - Reset password: `{{ .SiteURL }}/auth/confirm?token_hash={{ .TokenHash }}&type=recovery&next=/update-password`
7. Set the frontend environment variables documented in `frontend/.env.production.example`.
8. Verify every public table has RLS enabled and run a two-account isolation test.
9. Test account export and permanent deletion with a disposable production account.

The service-role key is server-only and is used solely by the authenticated Next.js
account-deletion route. Never prefix it with `NEXT_PUBLIC_`, send it to the browser,
or commit it. The public publishable key is safe only because every user-owned table
is protected by row-level security.
