from supabase import create_client, Client
from app.core.config import settings

# Anon client — respects Row Level Security
supabase: Client = create_client(settings.supabase_url, settings.supabase_anon_key)

# Service-role client — bypasses RLS for trusted server-side operations
_service_key = settings.supabase_service_key or settings.supabase_anon_key
supabase_admin: Client = create_client(settings.supabase_url, _service_key)
# Explicitly set service key as the PostgREST auth token so RLS is bypassed
supabase_admin.postgrest.auth(_service_key)