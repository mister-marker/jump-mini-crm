BEGIN;

CREATE TABLE public.users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    telegram_id BIGINT UNIQUE CHECK (telegram_id > 0),
    role TEXT NOT NULL CHECK (role IN ('admin', 'manager')) DEFAULT 'manager',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE public.leads (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL CHECK (length(btrim(name)) BETWEEN 1 AND 200),
    contact TEXT NOT NULL CHECK (length(btrim(contact)) BETWEEN 1 AND 320),
    request TEXT CHECK (length(request) <= 10000),
    source TEXT NOT NULL CHECK (source IN ('bot', 'manual', 'telegram', 'webhook')) DEFAULT 'manual',
    status TEXT NOT NULL CHECK (status IN ('new', 'in_progress', 'done', 'rejected')) DEFAULT 'new',
    next_contact_date DATE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE public.tags (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT UNIQUE NOT NULL CHECK (length(btrim(name)) BETWEEN 1 AND 64),
    color TEXT NOT NULL DEFAULT '#6B7280' CHECK (color ~ '^#[0-9a-fA-F]{6}$')
);

CREATE TABLE public.lead_tags (
    lead_id UUID REFERENCES public.leads(id) ON DELETE CASCADE,
    tag_id UUID REFERENCES public.tags(id) ON DELETE CASCADE,
    PRIMARY KEY (lead_id, tag_id)
);

CREATE INDEX leads_created_at_idx ON public.leads (created_at DESC, id);
CREATE INDEX leads_status_idx ON public.leads (status);
CREATE INDEX leads_next_contact_date_idx ON public.leads (next_contact_date)
    WHERE next_contact_date IS NOT NULL;
CREATE INDEX lead_tags_tag_id_idx ON public.lead_tags (tag_id, lead_id);

CREATE FUNCTION public.set_lead_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql SECURITY INVOKER SET search_path = '' AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;

CREATE TRIGGER leads_updated_at BEFORE UPDATE ON public.leads
    FOR EACH ROW EXECUTE FUNCTION public.set_lead_updated_at();

-- The API authorizes our own JWTs. No direct access from browser Supabase clients.
ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.leads ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.tags ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.lead_tags ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.users, public.leads, public.tags, public.lead_tags FROM anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.users, public.leads, public.tags, public.lead_tags
    TO service_role;
REVOKE ALL ON FUNCTION public.set_lead_updated_at() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.set_lead_updated_at() TO service_role;

-- Fixed demo identity, usable only while PIN_LOGIN_ENABLED=true. Never an admin.
INSERT INTO public.users (id, role)
VALUES ('00000000-0000-4000-8000-000000000026', 'manager');

-- A single RPC keeps lead creation and automatic tag assignment atomic.
CREATE FUNCTION public.create_webhook_lead(p_name TEXT, p_contact TEXT, p_request TEXT)
RETURNS UUID LANGUAGE plpgsql SECURITY INVOKER SET search_path = '' AS $$
DECLARE
    new_lead_id UUID;
    current_tag_id UUID;
    tag_name TEXT;
    tag_names TEXT[] := ARRAY['Веб-форма'];
BEGIN
    -- Defense in depth: even direct RPC calls cannot persist excluded requests.
    IF p_request IS NULL OR length(btrim(p_request)) = 0 OR EXISTS (
        SELECT 1 FROM unnest(ARRAY['spam', 'test', 'игнор', 'ignore', 'null', 'undefined']) AS word
        WHERE strpos(lower(p_request), word) > 0
    ) THEN
        RAISE EXCEPTION 'Request filtered as spam' USING ERRCODE = '22023';
    END IF;
    IF char_length(btrim(p_request)) < 10 THEN
        tag_names := array_append(tag_names, 'short_request');
    END IF;
    INSERT INTO public.leads (name, contact, request, source)
    VALUES (p_name, p_contact, btrim(p_request), 'webhook') RETURNING id INTO new_lead_id;
    FOREACH tag_name IN ARRAY tag_names LOOP
        INSERT INTO public.tags (name) VALUES (tag_name)
        ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name
        RETURNING id INTO current_tag_id;
        INSERT INTO public.lead_tags (lead_id, tag_id) VALUES (new_lead_id, current_tag_id);
    END LOOP;
    RETURN new_lead_id;
END;
$$;

REVOKE ALL ON FUNCTION public.create_webhook_lead(TEXT, TEXT, TEXT) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.create_webhook_lead(TEXT, TEXT, TEXT) TO service_role;

COMMIT;
