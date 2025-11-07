-- PostgreSQL database dump

-- Dumped from database version 13.18 (Debian 13.18-0+deb11u1)
-- Dumped by pg_dump version 13.18 (Debian 13.18-0+deb11u1)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

SET default_tablespace = '';

SET default_table_access_method = heap;

-- Name: chatd_channel; Type: TABLE; Schema: public; Owner: -

CREATE TABLE public.chatd_channel (
    name text NOT NULL,
    state character varying(24) NOT NULL,
    line_id integer NOT NULL,
    CONSTRAINT chatd_channel_state_check CHECK (state IN ('undefined', 'holding', 'ringing', 'talking', 'progressing'))
);

-- Name: chatd_endpoint; Type: TABLE; Schema: public; Owner: -

CREATE TABLE public.chatd_endpoint (
    name text NOT NULL,
    state character varying(24) NOT NULL,
    CONSTRAINT chatd_endpoint_state_check CHECK (state IN ('available', 'unavailable'))
);

-- Name: chatd_line; Type: TABLE; Schema: public; Owner: -

CREATE TABLE public.chatd_line (
    id integer NOT NULL,
    user_uuid uuid NOT NULL,
    media character varying(24),
    endpoint_name text,
    CONSTRAINT chatd_line_media_check CHECK (media IN ('audio', 'video'))
);

-- Name: chatd_line_id_seq; Type: SEQUENCE; Schema: public; Owner: -

CREATE SEQUENCE public.chatd_line_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

-- Name: chatd_line_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -

ALTER SEQUENCE public.chatd_line_id_seq OWNED BY public.chatd_line.id;

-- Name: chatd_refresh_token; Type: TABLE; Schema: public; Owner: -

CREATE TABLE public.chatd_refresh_token (
    client_id text NOT NULL,
    user_uuid uuid NOT NULL,
    mobile boolean NOT NULL
);

-- Name: chatd_room; Type: TABLE; Schema: public; Owner: -

CREATE TABLE public.chatd_room (
    uuid uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    name text,
    tenant_uuid uuid NOT NULL
);

-- Name: chatd_room_message; Type: TABLE; Schema: public; Owner: -

CREATE TABLE public.chatd_room_message (
    uuid uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    room_uuid uuid NOT NULL,
    content text,
    alias character varying(256),
    user_uuid uuid NOT NULL,
    tenant_uuid uuid NOT NULL,
    wazo_uuid uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);

-- Name: chatd_room_user; Type: TABLE; Schema: public; Owner: -

CREATE TABLE public.chatd_room_user (
    room_uuid uuid NOT NULL,
    uuid uuid NOT NULL,
    tenant_uuid uuid NOT NULL,
    wazo_uuid uuid NOT NULL
);

-- Name: chatd_session; Type: TABLE; Schema: public; Owner: -

CREATE TABLE public.chatd_session (
    uuid uuid NOT NULL,
    mobile boolean NOT NULL,
    user_uuid uuid NOT NULL
);

-- Name: chatd_tenant; Type: TABLE; Schema: public; Owner: -

CREATE TABLE public.chatd_tenant (
    uuid uuid NOT NULL
);

-- Name: chatd_user; Type: TABLE; Schema: public; Owner: -

CREATE TABLE public.chatd_user (
    uuid uuid NOT NULL,
    tenant_uuid uuid NOT NULL,
    state character varying(24) NOT NULL,
    status text,
    do_not_disturb boolean DEFAULT false NOT NULL,
    last_activity timestamp with time zone,
    CONSTRAINT chatd_user_state_check CHECK (state IN ('available', 'unavailable', 'invisible', 'away'))
);

-- Name: chatd_line id; Type: DEFAULT; Schema: public; Owner: -

ALTER TABLE ONLY public.chatd_line ALTER COLUMN id SET DEFAULT nextval('public.chatd_line_id_seq'::regclass);

-- Data for Name: chatd_channel; Type: TABLE DATA; Schema: public; Owner: -

-- Data for Name: chatd_endpoint; Type: TABLE DATA; Schema: public; Owner: -

-- Data for Name: chatd_line; Type: TABLE DATA; Schema: public; Owner: -

-- Data for Name: chatd_refresh_token; Type: TABLE DATA; Schema: public; Owner: -

-- Data for Name: chatd_room; Type: TABLE DATA; Schema: public; Owner: -

-- Data for Name: chatd_room_message; Type: TABLE DATA; Schema: public; Owner: -

-- Data for Name: chatd_room_user; Type: TABLE DATA; Schema: public; Owner: -

-- Data for Name: chatd_session; Type: TABLE DATA; Schema: public; Owner: -

-- Data for Name: chatd_tenant; Type: TABLE DATA; Schema: public; Owner: -

-- Data for Name: chatd_user; Type: TABLE DATA; Schema: public; Owner: -

-- Name: chatd_line_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -

SELECT pg_catalog.setval('public.chatd_line_id_seq', 1, false);

-- Name: chatd_channel chatd_channel_pkey; Type: CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.chatd_channel
    ADD CONSTRAINT chatd_channel_pkey PRIMARY KEY (name);

-- Name: chatd_endpoint chatd_endpoint_pkey; Type: CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.chatd_endpoint
    ADD CONSTRAINT chatd_endpoint_pkey PRIMARY KEY (name);

-- Name: chatd_line chatd_line_pkey; Type: CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.chatd_line
    ADD CONSTRAINT chatd_line_pkey PRIMARY KEY (id);

-- Name: chatd_refresh_token chatd_refresh_token_pkey; Type: CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.chatd_refresh_token
    ADD CONSTRAINT chatd_refresh_token_pkey PRIMARY KEY (client_id, user_uuid);

-- Name: chatd_room_message chatd_room_message_pkey; Type: CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.chatd_room_message
    ADD CONSTRAINT chatd_room_message_pkey PRIMARY KEY (uuid);

-- Name: chatd_room chatd_room_pkey; Type: CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.chatd_room
    ADD CONSTRAINT chatd_room_pkey PRIMARY KEY (uuid);

-- Name: chatd_room_user chatd_room_user_pkey; Type: CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.chatd_room_user
    ADD CONSTRAINT chatd_room_user_pkey PRIMARY KEY (room_uuid, uuid, tenant_uuid, wazo_uuid);

-- Name: chatd_session chatd_session_pkey; Type: CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.chatd_session
    ADD CONSTRAINT chatd_session_pkey PRIMARY KEY (uuid);

-- Name: chatd_tenant chatd_tenant_pkey; Type: CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.chatd_tenant
    ADD CONSTRAINT chatd_tenant_pkey PRIMARY KEY (uuid);

-- Name: chatd_user chatd_user_pkey; Type: CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.chatd_user
    ADD CONSTRAINT chatd_user_pkey PRIMARY KEY (uuid);

-- Name: chatd_channel__idx__line_id; Type: INDEX; Schema: public; Owner: -

CREATE INDEX chatd_channel__idx__line_id ON public.chatd_channel USING btree (line_id);

-- Name: chatd_line__idx__endpoint_name; Type: INDEX; Schema: public; Owner: -

CREATE INDEX chatd_line__idx__endpoint_name ON public.chatd_line USING btree (endpoint_name);

-- Name: chatd_line__idx__user_uuid; Type: INDEX; Schema: public; Owner: -

CREATE INDEX chatd_line__idx__user_uuid ON public.chatd_line USING btree (user_uuid);

-- Name: chatd_room__idx__tenant_uuid; Type: INDEX; Schema: public; Owner: -

CREATE INDEX chatd_room__idx__tenant_uuid ON public.chatd_room USING btree (tenant_uuid);

-- Name: chatd_room_message__idx__room_uuid; Type: INDEX; Schema: public; Owner: -

CREATE INDEX chatd_room_message__idx__room_uuid ON public.chatd_room_message USING btree (room_uuid);

-- Name: chatd_session__idx__user_uuid; Type: INDEX; Schema: public; Owner: -

CREATE INDEX chatd_session__idx__user_uuid ON public.chatd_session USING btree (user_uuid);

-- Name: chatd_user__idx__tenant_uuid; Type: INDEX; Schema: public; Owner: -

CREATE INDEX chatd_user__idx__tenant_uuid ON public.chatd_user USING btree (tenant_uuid);

-- Name: chatd_channel chatd_channel_line_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.chatd_channel
    ADD CONSTRAINT chatd_channel_line_id_fkey FOREIGN KEY (line_id) REFERENCES public.chatd_line(id) ON DELETE CASCADE;

-- Name: chatd_line chatd_line_endpoint_name_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.chatd_line
    ADD CONSTRAINT chatd_line_endpoint_name_fkey FOREIGN KEY (endpoint_name) REFERENCES public.chatd_endpoint(name) ON DELETE SET NULL;

-- Name: chatd_line chatd_line_user_uuid_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.chatd_line
    ADD CONSTRAINT chatd_line_user_uuid_fkey FOREIGN KEY (user_uuid) REFERENCES public.chatd_user(uuid) ON DELETE CASCADE;

-- Name: chatd_refresh_token chatd_refresh_token_user_uuid_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.chatd_refresh_token
    ADD CONSTRAINT chatd_refresh_token_user_uuid_fkey FOREIGN KEY (user_uuid) REFERENCES public.chatd_user(uuid) ON DELETE CASCADE;

-- Name: chatd_room_message chatd_room_message_room_uuid_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.chatd_room_message
    ADD CONSTRAINT chatd_room_message_room_uuid_fkey FOREIGN KEY (room_uuid) REFERENCES public.chatd_room(uuid) ON DELETE CASCADE;

-- Name: chatd_room chatd_room_tenant_uuid_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.chatd_room
    ADD CONSTRAINT chatd_room_tenant_uuid_fkey FOREIGN KEY (tenant_uuid) REFERENCES public.chatd_tenant(uuid) ON DELETE CASCADE;

-- Name: chatd_room_user chatd_room_user_room_uuid_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.chatd_room_user
    ADD CONSTRAINT chatd_room_user_room_uuid_fkey FOREIGN KEY (room_uuid) REFERENCES public.chatd_room(uuid) ON DELETE CASCADE;

-- Name: chatd_session chatd_session_user_uuid_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.chatd_session
    ADD CONSTRAINT chatd_session_user_uuid_fkey FOREIGN KEY (user_uuid) REFERENCES public.chatd_user(uuid) ON DELETE CASCADE;

-- Name: chatd_user chatd_user_tenant_uuid_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.chatd_user
    ADD CONSTRAINT chatd_user_tenant_uuid_fkey FOREIGN KEY (tenant_uuid) REFERENCES public.chatd_tenant(uuid) ON DELETE CASCADE;

-- PostgreSQL database dump complete
