BEGIN;

-- Sources answer "where did this lead come from?"; tags classify a lead.
CREATE TABLE public.sources (
    id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    name TEXT NOT NULL CHECK (length(btrim(name)) BETWEEN 1 AND 64)
);
CREATE UNIQUE INDEX sources_name_unique ON public.sources (lower(name));
INSERT INTO public.sources (id, name) VALUES
    ('bot', 'Telegram-бот'),
    ('manual', 'Не уточнён (ручной ввод)'),
    ('telegram', 'Личный Telegram'),
    ('webhook', 'Внешний вебхук');
ALTER TABLE public.sources ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.sources FROM anon, authenticated;
GRANT SELECT, INSERT ON public.sources TO service_role;

ALTER TABLE public.leads DROP CONSTRAINT leads_source_check;
ALTER TABLE public.leads ADD CONSTRAINT leads_source_fkey
    FOREIGN KEY (source) REFERENCES public.sources(id);

-- Remove associations created automatically by the old RPC versions.
DELETE FROM public.lead_tags AS lt USING public.leads AS l, public.tags AS t
WHERE lt.lead_id = l.id AND lt.tag_id = t.id
  AND ((l.source = 'bot' AND t.name = 'Telegram-бот')
    OR (l.source = 'webhook' AND t.name = 'Веб-форма'));
DELETE FROM public.tags AS t WHERE t.name IN ('Telegram-бот', 'Веб-форма')
  AND NOT EXISTS (SELECT 1 FROM public.lead_tags AS lt WHERE lt.tag_id = t.id);

CREATE OR REPLACE FUNCTION public.create_bot_lead(
    p_id UUID, p_name TEXT, p_contact TEXT, p_request TEXT
)
RETURNS UUID LANGUAGE plpgsql SECURITY INVOKER SET search_path = '' AS $$
DECLARE
    new_lead_id UUID;
BEGIN
    IF p_id IS NULL OR p_request IS NULL OR length(btrim(p_request)) NOT BETWEEN 1 AND 10000 THEN
        RAISE EXCEPTION 'Invalid bot application' USING ERRCODE = '22023';
    END IF;
    INSERT INTO public.leads (id, name, contact, request, source)
    VALUES (p_id, btrim(p_name), btrim(p_contact), btrim(p_request), 'bot')
    ON CONFLICT (id) DO NOTHING RETURNING id INTO new_lead_id;
    IF new_lead_id IS NULL THEN
        IF NOT EXISTS (SELECT 1 FROM public.leads WHERE id = p_id AND source = 'bot') THEN
            RAISE EXCEPTION 'Submission ID conflict' USING ERRCODE = '23505';
        END IF;
        RETURN p_id;
    END IF;
    RETURN new_lead_id;
END;
$$;
REVOKE ALL ON FUNCTION public.create_bot_lead(UUID, TEXT, TEXT, TEXT) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.create_bot_lead(UUID, TEXT, TEXT, TEXT) TO service_role;

CREATE OR REPLACE FUNCTION public.create_webhook_lead(p_name TEXT, p_contact TEXT, p_request TEXT)
RETURNS UUID LANGUAGE plpgsql SECURITY INVOKER SET search_path = '' AS $$
DECLARE
    new_lead_id UUID;
    short_tag_id UUID;
BEGIN
    IF p_request IS NULL OR length(btrim(p_request)) = 0 OR EXISTS (
        SELECT 1 FROM unnest(ARRAY['spam', 'test', 'игнор', 'ignore', 'null', 'undefined']) AS word
        WHERE strpos(lower(p_request), word) > 0
    ) THEN
        RAISE EXCEPTION 'Request filtered as spam' USING ERRCODE = '22023';
    END IF;
    INSERT INTO public.leads (name, contact, request, source)
    VALUES (p_name, p_contact, btrim(p_request), 'webhook') RETURNING id INTO new_lead_id;
    IF char_length(btrim(p_request)) < 10 THEN
        INSERT INTO public.tags (name) VALUES ('short_request')
        ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name
        RETURNING id INTO short_tag_id;
        INSERT INTO public.lead_tags (lead_id, tag_id) VALUES (new_lead_id, short_tag_id);
    END IF;
    RETURN new_lead_id;
END;
$$;
REVOKE ALL ON FUNCTION public.create_webhook_lead(TEXT, TEXT, TEXT) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.create_webhook_lead(TEXT, TEXT, TEXT) TO service_role;

COMMIT;
