BEGIN;

-- Additive migration: existing tables and external-webhook behaviour are unchanged.
-- The UUID is derived from bot ID, chat ID and the /start message ID.
CREATE OR REPLACE FUNCTION public.create_bot_lead(
    p_id UUID, p_name TEXT, p_contact TEXT, p_request TEXT
)
RETURNS UUID LANGUAGE plpgsql SECURITY INVOKER SET search_path = '' AS $$
DECLARE
    new_lead_id UUID;
    current_tag_id UUID;
BEGIN
    IF p_id IS NULL OR p_request IS NULL OR length(btrim(p_request)) NOT BETWEEN 1 AND 10000 THEN
        RAISE EXCEPTION 'Invalid bot application' USING ERRCODE = '22023';
    END IF;

    INSERT INTO public.leads (id, name, contact, request, source)
    VALUES (p_id, btrim(p_name), btrim(p_contact), btrim(p_request), 'bot')
    ON CONFLICT (id) DO NOTHING
    RETURNING id INTO new_lead_id;

    IF new_lead_id IS NULL THEN
        -- A retry must neither overwrite manager edits nor reassign removed tags.
        IF NOT EXISTS (SELECT 1 FROM public.leads WHERE id = p_id AND source = 'bot') THEN
            RAISE EXCEPTION 'Submission ID conflict' USING ERRCODE = '23505';
        END IF;
        RETURN p_id;
    END IF;

    INSERT INTO public.tags (name) VALUES ('Telegram-бот')
    ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name
    RETURNING id INTO current_tag_id;
    INSERT INTO public.lead_tags (lead_id, tag_id) VALUES (new_lead_id, current_tag_id);
    RETURN new_lead_id;
END;
$$;

REVOKE ALL ON FUNCTION public.create_bot_lead(UUID, TEXT, TEXT, TEXT) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.create_bot_lead(UUID, TEXT, TEXT, TEXT) TO service_role;

COMMIT;
