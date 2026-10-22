--
-- PostgreSQL database dump
--

\restrict CkhZrjTx8sRUGI8jwwfRZpbm5J0ij5Met3RSYNLFzk3AwZzNTsIgDmjJinElLqK

-- Dumped from database version 17.11
-- Dumped by pg_dump version 17.11

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: categories; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.categories (
    id bigint NOT NULL,
    name character varying(80) NOT NULL,
    normalized_name text NOT NULL,
    CONSTRAINT categories_name_check CHECK (((char_length(btrim((name)::text)) >= 1) AND (char_length(btrim((name)::text)) <= 80))),
    CONSTRAINT categories_normalized_name_check CHECK ((char_length(normalized_name) > 0))
);


--
-- Name: categories_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.categories ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.categories_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: collection_entries; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.collection_entries (
    collection_id bigint NOT NULL,
    recipe_id bigint NOT NULL,
    saved_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);


--
-- Name: collections; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.collections (
    id bigint NOT NULL,
    owner_id bigint NOT NULL,
    name character varying(100) NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT collections_name_check CHECK (((char_length(btrim((name)::text)) >= 1) AND (char_length(btrim((name)::text)) <= 100)))
);


--
-- Name: collections_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.collections ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.collections_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: ingredients; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.ingredients (
    id bigint NOT NULL,
    name character varying(80) NOT NULL,
    normalized_name text NOT NULL,
    CONSTRAINT ingredients_name_check CHECK (((char_length(btrim((name)::text)) >= 1) AND (char_length(btrim((name)::text)) <= 80))),
    CONSTRAINT ingredients_normalized_name_check CHECK ((char_length(normalized_name) > 0))
);


--
-- Name: ingredients_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.ingredients ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.ingredients_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: instruction_steps; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.instruction_steps (
    recipe_id bigint NOT NULL,
    number smallint NOT NULL,
    description character varying(2000) NOT NULL,
    CONSTRAINT instruction_steps_description_check CHECK (((char_length(btrim((description)::text)) >= 1) AND (char_length(btrim((description)::text)) <= 2000))),
    CONSTRAINT instruction_steps_number_check CHECK (((number >= 1) AND (number <= 50)))
);


--
-- Name: recipe_ingredients; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.recipe_ingredients (
    recipe_id bigint NOT NULL,
    "position" smallint NOT NULL,
    ingredient_id bigint NOT NULL,
    quantity numeric(9,3) NOT NULL,
    unit character varying(10) NOT NULL,
    CONSTRAINT recipe_ingredients_position_check CHECK ((("position" >= 1) AND ("position" <= 50))),
    CONSTRAINT recipe_ingredients_quantity_check CHECK ((quantity > (0)::numeric)),
    CONSTRAINT recipe_ingredients_unit_check CHECK (((unit)::text = ANY ((ARRAY['g'::character varying, 'kg'::character varying, 'ml'::character varying, 'l'::character varying, 'pcs'::character varying, 'tsp'::character varying, 'tbsp'::character varying, 'pinch'::character varying])::text[])))
);


--
-- Name: recipe_tags; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.recipe_tags (
    recipe_id bigint NOT NULL,
    tag_id bigint NOT NULL
);


--
-- Name: recipes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.recipes (
    id bigint NOT NULL,
    author_id bigint NOT NULL,
    category_id bigint,
    title character varying(150) NOT NULL,
    description character varying(3000) DEFAULT ''::character varying NOT NULL,
    cooking_time smallint,
    servings smallint DEFAULT 1 NOT NULL,
    status character varying(10) DEFAULT 'DRAFT'::character varying NOT NULL,
    hide_reason character varying(500),
    version integer DEFAULT 1 NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    published_at timestamp with time zone,
    photo_key character varying(32),
    CONSTRAINT recipes_check CHECK (((((status)::text = 'HIDDEN'::text) AND (hide_reason IS NOT NULL) AND ((char_length(btrim((hide_reason)::text)) >= 1) AND (char_length(btrim((hide_reason)::text)) <= 500))) OR (((status)::text <> 'HIDDEN'::text) AND (hide_reason IS NULL)))),
    CONSTRAINT recipes_check1 CHECK ((((status)::text <> 'PUBLISHED'::text) OR ((category_id IS NOT NULL) AND (cooking_time IS NOT NULL) AND (published_at IS NOT NULL)))),
    CONSTRAINT recipes_cooking_time_check CHECK (((cooking_time >= 1) AND (cooking_time <= 1440))),
    CONSTRAINT recipes_photo_key_check CHECK (((photo_key IS NULL) OR ((photo_key)::text ~ '^[0-9a-f]{32}$'::text))),
    CONSTRAINT recipes_servings_check CHECK (((servings >= 1) AND (servings <= 100))),
    CONSTRAINT recipes_status_check CHECK (((status)::text = ANY ((ARRAY['DRAFT'::character varying, 'PUBLISHED'::character varying, 'HIDDEN'::character varying])::text[]))),
    CONSTRAINT recipes_title_check CHECK (((char_length(btrim((title)::text)) >= 1) AND (char_length(btrim((title)::text)) <= 150))),
    CONSTRAINT recipes_version_check CHECK ((version >= 1))
);


--
-- Name: recipes_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.recipes ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.recipes_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: schema_migrations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.schema_migrations (
    name text NOT NULL,
    checksum character(64) NOT NULL,
    applied_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);


--
-- Name: tags; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.tags (
    id bigint NOT NULL,
    name character varying(80) NOT NULL,
    normalized_name text NOT NULL,
    CONSTRAINT tags_name_check CHECK (((char_length(btrim((name)::text)) >= 1) AND (char_length(btrim((name)::text)) <= 80))),
    CONSTRAINT tags_normalized_name_check CHECK ((char_length(normalized_name) > 0))
);


--
-- Name: tags_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.tags ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.tags_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: user_sessions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.user_sessions (
    token_hash character(64) NOT NULL,
    user_id bigint NOT NULL,
    csrf_token character varying(128) NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    CONSTRAINT user_sessions_check CHECK ((expires_at > created_at))
);


--
-- Name: users; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.users (
    id bigint NOT NULL,
    email character varying(254) NOT NULL,
    display_name character varying(80) NOT NULL,
    password_hash text NOT NULL,
    role character varying(10) DEFAULT 'USER'::character varying NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT users_display_name_check CHECK (((char_length(btrim((display_name)::text)) >= 1) AND (char_length(btrim((display_name)::text)) <= 80))),
    CONSTRAINT users_email_check CHECK (((email)::text = lower(btrim((email)::text)))),
    CONSTRAINT users_role_check CHECK (((role)::text = ANY ((ARRAY['USER'::character varying, 'ADMIN'::character varying])::text[])))
);


--
-- Name: users_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.users ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.users_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Data for Name: categories; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.categories (id, name, normalized_name) FROM stdin;
1	Сніданки	сніданки
2	Перші страви	перші страви
3	Основні страви	основні страви
4	Салати	салати
5	Десерти	десерти
\.


--
-- Data for Name: collection_entries; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.collection_entries (collection_id, recipe_id, saved_at) FROM stdin;
1	1	2026-10-05 11:48:25.260455+00
1	2	2026-10-05 11:49:10.653844+00
2	14	2026-10-06 13:57:08.993116+00
\.


--
-- Data for Name: collections; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.collections (id, owner_id, name, created_at, updated_at) FROM stdin;
1	4	Швидкі сніданки	2026-10-05 11:47:57.02259+00	2026-10-05 11:50:50.941894+00
2	5	87y87t76	2026-10-06 13:55:52.315794+00	2026-10-06 13:57:08.993116+00
\.


--
-- Data for Name: ingredients; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.ingredients (id, name, normalized_name) FROM stdin;
1	Яйце	яйце
2	Молоко	молоко
3	Борошно	борошно
4	Картопля	картопля
5	Морква	морква
6	Цибуля	цибуля
7	Помідор	помідор
8	Сіль	сіль
9	Цукор	цукор
10	Вершкове масло	вершкове масло
11	Олія	олія
12	Рис	рис
13	Гречка	гречка
14	Куряче філе	куряче філе
15	Сир	сир
16	Сметана	сметана
17	Часник	часник
18	Огірок	огірок
37	Кріп	кріп
38	gre	gre
39	reg	reg
\.


--
-- Data for Name: instruction_steps; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.instruction_steps (recipe_id, number, description) FROM stdin;
1	1	Збийте яйця з молоком.
1	2	Вилийте на сковороду, додайте сир і готуйте під кришкою.
2	1	Змішайте яйця, молоко та борошно до однорідності.
2	2	Додайте олію. Смажте тонкі млинці з обох боків.
3	1	Наріжте овочі й залийте літром води.
3	2	Варіть до м’якості картоплі, посоліть наприкінці.
4	1	Промийте й відваріть рис за вказівками на упаковці.
4	2	Підсмажте нарізані овочі на олії та змішайте з рисом.
5	1	Промийте гречку. Додайте 400 мл води та сіль.
5	2	Варіть під кришкою до готовності, додайте вершкове масло.
6	1	Наріжте філе й подрібніть часник.
6	2	Обсмажте філе на олії, додайте часник і доведіть до повної готовності.
7	1	Помийте та наріжте овочі.
7	2	Заправте олією й перемішайте.
8	1	Натріть моркву та подрібніть часник.
8	2	Додайте сметану і перемішайте.
9	1	Використайте кисломолочний сир. Змішайте його з яйцем, цукром і борошном.
9	2	Сформуйте невеликі сирники та обсмажте з обох боків до готовності.
10	1	Очистьте картоплю та відваріть до м’якості.
10	2	Злийте воду. Розімніть картоплю з теплим молоком і маслом.
12	1	Наріжте помідор і прогрійте на сковороді.
12	2	Додайте яйця та готуйте до бажаної консистенції.
13	1	Збити яйця та посмажити на сковороді до готовності.
13	2	Перед подачею посипати свіжим кропом.
14	1	reg
\.


--
-- Data for Name: recipe_ingredients; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.recipe_ingredients (recipe_id, "position", ingredient_id, quantity, unit) FROM stdin;
1	1	1	3.000	pcs
1	2	2	50.000	ml
1	3	15	60.000	g
2	1	2	300.000	ml
2	2	1	2.000	pcs
2	3	3	150.000	g
2	4	11	1.000	tbsp
3	1	4	400.000	g
3	2	5	1.000	pcs
3	3	6	1.000	pcs
3	4	8	1.000	pinch
4	1	12	200.000	g
4	2	5	1.000	pcs
4	3	6	1.000	pcs
4	4	11	1.000	tbsp
5	1	13	200.000	g
5	2	10	25.000	g
5	3	8	1.000	pinch
6	1	14	400.000	g
6	2	17	2.000	pcs
6	3	11	1.000	tbsp
7	1	18	2.000	pcs
7	2	7	2.000	pcs
7	3	11	1.000	tbsp
8	1	5	2.000	pcs
8	2	16	2.000	tbsp
8	3	17	1.000	pcs
9	1	15	300.000	g
9	2	1	1.000	pcs
9	3	3	3.000	tbsp
9	4	9	1.000	tbsp
9	5	11	1.000	tbsp
10	1	4	500.000	g
10	2	2	100.000	ml
10	3	10	30.000	g
11	1	4	300.000	g
11	2	5	1.000	pcs
12	1	1	2.000	pcs
12	2	7	1.000	pcs
12	3	11	1.000	tsp
13	1	1	3.000	pcs
13	2	37	10.125	g
14	1	38	34.000	g
14	2	39	34.000	g
\.


--
-- Data for Name: recipe_tags; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.recipe_tags (recipe_id, tag_id) FROM stdin;
1	1
1	2
2	5
3	5
3	2
4	2
5	5
6	3
7	1
7	2
8	1
9	4
10	2
11	5
12	1
13	1
14	3
\.


--
-- Data for Name: recipes; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.recipes (id, author_id, category_id, title, description, cooking_time, servings, status, hide_reason, version, created_at, updated_at, published_at, photo_key) FROM stdin;
1	2	1	Омлет із сиром	Домашній рецепт: омлет із сиром.	15	2	PUBLISHED	\N	1	2026-10-05 07:54:07.455041+00	2026-10-05 07:54:07.455041+00	2026-10-05 07:54:07.481592+00	\N
2	3	1	Млинці на молоці	Домашній рецепт: млинці на молоці.	30	2	PUBLISHED	\N	1	2026-10-05 07:54:07.455041+00	2026-10-05 07:54:07.455041+00	2026-10-05 07:54:07.492633+00	\N
3	2	2	Картопляний суп	Домашній рецепт: картопляний суп.	40	2	PUBLISHED	\N	1	2026-10-05 07:54:07.455041+00	2026-10-05 07:54:07.455041+00	2026-10-05 07:54:07.493598+00	\N
4	3	3	Рис із овочами	Домашній рецепт: рис із овочами.	30	2	PUBLISHED	\N	1	2026-10-05 07:54:07.455041+00	2026-10-05 07:54:07.455041+00	2026-10-05 07:54:07.495597+00	\N
5	2	3	Гречка з вершковим маслом	Домашній рецепт: гречка з вершковим маслом.	25	2	PUBLISHED	\N	1	2026-10-05 07:54:07.455041+00	2026-10-05 07:54:07.455041+00	2026-10-05 07:54:07.496597+00	\N
6	3	3	Куряче філе з часником	Домашній рецепт: куряче філе з часником.	35	2	PUBLISHED	\N	1	2026-10-05 07:54:07.455041+00	2026-10-05 07:54:07.455041+00	2026-10-05 07:54:07.497597+00	\N
7	2	4	Салат з огірків і помідорів	Домашній рецепт: салат з огірків і помідорів.	10	2	PUBLISHED	\N	1	2026-10-05 07:54:07.455041+00	2026-10-05 07:54:07.455041+00	2026-10-05 07:54:07.498597+00	\N
8	3	4	Морквяний салат зі сметаною	Домашній рецепт: морквяний салат зі сметаною.	10	2	PUBLISHED	\N	1	2026-10-05 07:54:07.455041+00	2026-10-05 07:54:07.455041+00	2026-10-05 07:54:07.499598+00	\N
9	2	5	Сирники	Домашній рецепт: сирники.	30	2	PUBLISHED	\N	1	2026-10-05 07:54:07.455041+00	2026-10-05 07:54:07.455041+00	2026-10-05 07:54:07.501599+00	\N
10	3	3	Картопляне пюре	Домашній рецепт: картопляне пюре.	30	2	PUBLISHED	\N	1	2026-10-05 07:54:07.455041+00	2026-10-05 07:54:07.455041+00	2026-10-05 07:54:07.501599+00	\N
11	2	3	Задум овочевої запіканки	Домашній рецепт: задум овочевої запіканки.	45	2	DRAFT	\N	1	2026-10-05 07:54:07.455041+00	2026-10-05 07:54:07.455041+00	\N	\N
12	3	1	Яєчня з помідорами	Домашній рецепт: яєчня з помідорами.	15	2	HIDDEN	Демонстрація модерації: уточніть ступінь готовності яєць.	1	2026-10-05 07:54:07.455041+00	2026-10-05 07:54:07.455041+00	2026-10-05 07:54:07.504108+00	\N
13	4	1	Омлет із зеленню для демонстрації	Перевірено збереження з двох відкритих вкладок.	15	2	PUBLISHED	\N	6	2026-10-05 07:55:11.616591+00	2026-10-05 07:57:48.704557+00	2026-10-05 07:57:48.73664+00	\N
14	5	4	ugy		78	1	PUBLISHED	\N	5	2026-10-06 13:56:12.106881+00	2026-10-06 13:57:06.171216+00	2026-10-06 13:57:06.180934+00	6d011a9c9a9e491bb394efca0ea6755b
\.


--
-- Data for Name: schema_migrations; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.schema_migrations (name, checksum, applied_at) FROM stdin;
001_init.sql	2906a57c5bfa2c371d91b88a44f4ea4c83370398ca51d76320d0bf07c4687b55	2026-10-05 06:42:52.54639+00
002_recipe_photos.sql	228ce19b6ee507d1f7fd0e939b5787adce3ef173e19b47f31e5211cacfbb1f5c	2026-10-05 21:28:44.154789+00
\.


--
-- Data for Name: tags; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.tags (id, name, normalized_name) FROM stdin;
1	Швидко	швидко
2	Вегетаріанське	вегетаріанське
3	Без глютену	без глютену
4	Святкове	святкове
5	Бюджетне	бюджетне
\.


--
-- Data for Name: user_sessions; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.user_sessions (token_hash, user_id, csrf_token, created_at, expires_at) FROM stdin;
f6ed492a3b3a3b1ceafc97ca6a5409fb50fde732bf6c1d755bc104052b8fa456	5	sN0QQCZ6HuJ7UEWMpIkqd3Y0F9uJzrkDVJM3jCbR-dg	2026-10-06 13:55:27.04715+00	2026-10-13 13:55:27.154873+00
\.


--
-- Data for Name: users; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.users (id, email, display_name, password_hash, role, is_active, created_at) FROM stdin;
1	admin@example.com	Адміністратор	$argon2id$v=19$m=65536,t=3,p=4$+DkzoP9x53dayFv0hks3Kw$M8onF80AwElEjX4WZsY+HNG120fYgSi2GNEAGQ0C6+w	ADMIN	t	2026-10-05 06:43:03.941689+00
2	andriy@example.com	Андрій	$argon2id$v=19$m=65536,t=3,p=4$sq+JkacS7XIcun0BB5dSIA$OjJlyNI9Fn+AFFsqARZSVt8tNaZjqFymbSeh8baFMII	USER	t	2026-10-05 06:43:03.941689+00
3	viktoriia@example.com	Вікторія	$argon2id$v=19$m=65536,t=3,p=4$3bQJNjKIM4QrP/3vXW3atQ$JW+sff8+h6tNvY4YordPSx8ZQO0VVsbxE0C0ZmQLUTU	USER	t	2026-10-05 06:43:03.941689+00
4	browser-check@example.com	Тестовий користувач	$argon2id$v=19$m=65536,t=3,p=4$kDy93r2jOCIK8R1elyHC/g$abDrodoumasilCyAmVRISbT3eQ4BWagBssItcUv8EXE	USER	t	2026-10-05 06:50:42.267746+00
5	bbb	bbb	$argon2id$v=19$m=65536,t=3,p=4$mZfD43qpRzKgyEG08kGuyA$aIM3BiqFFtjyiZW57MVeXY3fG2dCx5YW4iGqnq1CGlc	ADMIN	t	2026-10-06 13:51:21.521754+00
\.


--
-- Name: categories_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.categories_id_seq', 10, true);


--
-- Name: collections_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.collections_id_seq', 2, true);


--
-- Name: ingredients_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.ingredients_id_seq', 39, true);


--
-- Name: recipes_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.recipes_id_seq', 14, true);


--
-- Name: tags_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.tags_id_seq', 10, true);


--
-- Name: users_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.users_id_seq', 5, true);


--
-- Name: categories categories_normalized_name_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.categories
    ADD CONSTRAINT categories_normalized_name_key UNIQUE (normalized_name);


--
-- Name: categories categories_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.categories
    ADD CONSTRAINT categories_pkey PRIMARY KEY (id);


--
-- Name: collection_entries collection_entries_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.collection_entries
    ADD CONSTRAINT collection_entries_pkey PRIMARY KEY (collection_id, recipe_id);


--
-- Name: collections collections_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.collections
    ADD CONSTRAINT collections_pkey PRIMARY KEY (id);


--
-- Name: ingredients ingredients_normalized_name_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ingredients
    ADD CONSTRAINT ingredients_normalized_name_key UNIQUE (normalized_name);


--
-- Name: ingredients ingredients_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ingredients
    ADD CONSTRAINT ingredients_pkey PRIMARY KEY (id);


--
-- Name: instruction_steps instruction_steps_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.instruction_steps
    ADD CONSTRAINT instruction_steps_pkey PRIMARY KEY (recipe_id, number);


--
-- Name: recipe_ingredients recipe_ingredients_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.recipe_ingredients
    ADD CONSTRAINT recipe_ingredients_pkey PRIMARY KEY (recipe_id, "position");


--
-- Name: recipe_tags recipe_tags_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.recipe_tags
    ADD CONSTRAINT recipe_tags_pkey PRIMARY KEY (recipe_id, tag_id);


--
-- Name: recipes recipes_photo_key_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.recipes
    ADD CONSTRAINT recipes_photo_key_key UNIQUE (photo_key);


--
-- Name: recipes recipes_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.recipes
    ADD CONSTRAINT recipes_pkey PRIMARY KEY (id);


--
-- Name: schema_migrations schema_migrations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.schema_migrations
    ADD CONSTRAINT schema_migrations_pkey PRIMARY KEY (name);


--
-- Name: tags tags_normalized_name_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tags
    ADD CONSTRAINT tags_normalized_name_key UNIQUE (normalized_name);


--
-- Name: tags tags_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tags
    ADD CONSTRAINT tags_pkey PRIMARY KEY (id);


--
-- Name: user_sessions user_sessions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_sessions
    ADD CONSTRAINT user_sessions_pkey PRIMARY KEY (token_hash);


--
-- Name: users users_email_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_email_key UNIQUE (email);


--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);


--
-- Name: ix_collection_entries_recipe; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_collection_entries_recipe ON public.collection_entries USING btree (recipe_id);


--
-- Name: ix_collections_owner; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_collections_owner ON public.collections USING btree (owner_id, created_at DESC, id DESC);


--
-- Name: ix_recipe_ingredients_ingredient; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_recipe_ingredients_ingredient ON public.recipe_ingredients USING btree (ingredient_id, recipe_id);


--
-- Name: ix_recipe_tags_tag; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_recipe_tags_tag ON public.recipe_tags USING btree (tag_id, recipe_id);


--
-- Name: ix_recipes_author; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_recipes_author ON public.recipes USING btree (author_id, created_at DESC, id DESC);


--
-- Name: ix_recipes_category; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_recipes_category ON public.recipes USING btree (category_id);


--
-- Name: ix_recipes_public; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_recipes_public ON public.recipes USING btree (created_at DESC, id DESC) WHERE ((status)::text = 'PUBLISHED'::text);


--
-- Name: ix_user_sessions_expiry; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_user_sessions_expiry ON public.user_sessions USING btree (expires_at);


--
-- Name: ix_user_sessions_user; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_user_sessions_user ON public.user_sessions USING btree (user_id);


--
-- Name: collection_entries collection_entries_collection_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.collection_entries
    ADD CONSTRAINT collection_entries_collection_id_fkey FOREIGN KEY (collection_id) REFERENCES public.collections(id) ON DELETE CASCADE;


--
-- Name: collection_entries collection_entries_recipe_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.collection_entries
    ADD CONSTRAINT collection_entries_recipe_id_fkey FOREIGN KEY (recipe_id) REFERENCES public.recipes(id) ON DELETE CASCADE;


--
-- Name: collections collections_owner_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.collections
    ADD CONSTRAINT collections_owner_id_fkey FOREIGN KEY (owner_id) REFERENCES public.users(id) ON DELETE RESTRICT;


--
-- Name: instruction_steps instruction_steps_recipe_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.instruction_steps
    ADD CONSTRAINT instruction_steps_recipe_id_fkey FOREIGN KEY (recipe_id) REFERENCES public.recipes(id) ON DELETE CASCADE;


--
-- Name: recipe_ingredients recipe_ingredients_ingredient_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.recipe_ingredients
    ADD CONSTRAINT recipe_ingredients_ingredient_id_fkey FOREIGN KEY (ingredient_id) REFERENCES public.ingredients(id) ON DELETE RESTRICT;


--
-- Name: recipe_ingredients recipe_ingredients_recipe_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.recipe_ingredients
    ADD CONSTRAINT recipe_ingredients_recipe_id_fkey FOREIGN KEY (recipe_id) REFERENCES public.recipes(id) ON DELETE CASCADE;


--
-- Name: recipe_tags recipe_tags_recipe_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.recipe_tags
    ADD CONSTRAINT recipe_tags_recipe_id_fkey FOREIGN KEY (recipe_id) REFERENCES public.recipes(id) ON DELETE CASCADE;


--
-- Name: recipe_tags recipe_tags_tag_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.recipe_tags
    ADD CONSTRAINT recipe_tags_tag_id_fkey FOREIGN KEY (tag_id) REFERENCES public.tags(id) ON DELETE RESTRICT;


--
-- Name: recipes recipes_author_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.recipes
    ADD CONSTRAINT recipes_author_id_fkey FOREIGN KEY (author_id) REFERENCES public.users(id) ON DELETE RESTRICT;


--
-- Name: recipes recipes_category_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.recipes
    ADD CONSTRAINT recipes_category_id_fkey FOREIGN KEY (category_id) REFERENCES public.categories(id) ON DELETE RESTRICT;


--
-- Name: user_sessions user_sessions_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_sessions
    ADD CONSTRAINT user_sessions_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- PostgreSQL database dump complete
--

\unrestrict CkhZrjTx8sRUGI8jwwfRZpbm5J0ij5Met3RSYNLFzk3AwZzNTsIgDmjJinElLqK

