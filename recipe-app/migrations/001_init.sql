-- Система організації кулінарних рецептів, PostgreSQL 17.
-- Проєкт початкової міграції. Нічого не застосовує автоматично.
-- schema_migrations створює майбутній скрипт міграцій.

CREATE TABLE users (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email VARCHAR(254) NOT NULL UNIQUE,
    display_name VARCHAR(80) NOT NULL,
    password_hash TEXT NOT NULL,
    role VARCHAR(10) NOT NULL DEFAULT 'USER'
        CHECK (role IN ('USER', 'ADMIN')),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (email = lower(btrim(email))),
    CHECK (char_length(btrim(display_name)) BETWEEN 1 AND 80)
);

CREATE TABLE user_sessions (
    token_hash CHAR(64) PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    csrf_token VARCHAR(128) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMPTZ NOT NULL,
    CHECK (expires_at > created_at)
);

CREATE TABLE categories (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name VARCHAR(80) NOT NULL,
    normalized_name TEXT NOT NULL UNIQUE,
    CHECK (char_length(btrim(name)) BETWEEN 1 AND 80),
    CHECK (char_length(normalized_name) > 0)
);

CREATE TABLE tags (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name VARCHAR(80) NOT NULL,
    normalized_name TEXT NOT NULL UNIQUE,
    CHECK (char_length(btrim(name)) BETWEEN 1 AND 80),
    CHECK (char_length(normalized_name) > 0)
);

CREATE TABLE ingredients (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name VARCHAR(80) NOT NULL,
    normalized_name TEXT NOT NULL UNIQUE,
    CHECK (char_length(btrim(name)) BETWEEN 1 AND 80),
    CHECK (char_length(normalized_name) > 0)
);

CREATE TABLE recipes (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    author_id BIGINT NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    category_id BIGINT REFERENCES categories(id) ON DELETE RESTRICT,
    title VARCHAR(150) NOT NULL,
    description VARCHAR(3000) NOT NULL DEFAULT '',
    cooking_time SMALLINT CHECK (cooking_time BETWEEN 1 AND 1440),
    servings SMALLINT NOT NULL DEFAULT 1 CHECK (servings BETWEEN 1 AND 100),
    status VARCHAR(10) NOT NULL DEFAULT 'DRAFT'
        CHECK (status IN ('DRAFT', 'PUBLISHED', 'HIDDEN')),
    hide_reason VARCHAR(500),
    version INTEGER NOT NULL DEFAULT 1 CHECK (version >= 1),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    published_at TIMESTAMPTZ,
    CHECK (char_length(btrim(title)) BETWEEN 1 AND 150),
    CHECK (
        (status = 'HIDDEN' AND hide_reason IS NOT NULL
            AND char_length(btrim(hide_reason)) BETWEEN 1 AND 500)
        OR (status <> 'HIDDEN' AND hide_reason IS NULL)
    ),
    CHECK (
        status <> 'PUBLISHED'
        OR (category_id IS NOT NULL AND cooking_time IS NOT NULL
            AND published_at IS NOT NULL)
    )
);

CREATE TABLE recipe_ingredients (
    recipe_id BIGINT NOT NULL REFERENCES recipes(id) ON DELETE CASCADE,
    position SMALLINT NOT NULL CHECK (position BETWEEN 1 AND 50),
    ingredient_id BIGINT NOT NULL REFERENCES ingredients(id) ON DELETE RESTRICT,
    quantity NUMERIC(9, 3) NOT NULL CHECK (quantity > 0),
    unit VARCHAR(10) NOT NULL
        CHECK (unit IN ('g', 'kg', 'ml', 'l', 'pcs', 'tsp', 'tbsp', 'pinch')),
    PRIMARY KEY (recipe_id, position)
);

CREATE TABLE instruction_steps (
    recipe_id BIGINT NOT NULL REFERENCES recipes(id) ON DELETE CASCADE,
    number SMALLINT NOT NULL CHECK (number BETWEEN 1 AND 50),
    description VARCHAR(2000) NOT NULL,
    PRIMARY KEY (recipe_id, number),
    CHECK (char_length(btrim(description)) BETWEEN 1 AND 2000)
);

CREATE TABLE recipe_tags (
    recipe_id BIGINT NOT NULL REFERENCES recipes(id) ON DELETE CASCADE,
    tag_id BIGINT NOT NULL REFERENCES tags(id) ON DELETE RESTRICT,
    PRIMARY KEY (recipe_id, tag_id)
);

CREATE TABLE collections (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    owner_id BIGINT NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    name VARCHAR(100) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (char_length(btrim(name)) BETWEEN 1 AND 100)
);

CREATE TABLE collection_entries (
    collection_id BIGINT NOT NULL REFERENCES collections(id) ON DELETE CASCADE,
    recipe_id BIGINT NOT NULL REFERENCES recipes(id) ON DELETE CASCADE,
    saved_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (collection_id, recipe_id)
);

CREATE INDEX ix_user_sessions_user ON user_sessions(user_id);
CREATE INDEX ix_user_sessions_expiry ON user_sessions(expires_at);
CREATE INDEX ix_recipes_author ON recipes(author_id, created_at DESC, id DESC);
CREATE INDEX ix_recipes_public ON recipes(created_at DESC, id DESC)
    WHERE status = 'PUBLISHED';
CREATE INDEX ix_recipes_category ON recipes(category_id);
CREATE INDEX ix_recipe_ingredients_ingredient
    ON recipe_ingredients(ingredient_id, recipe_id);
CREATE INDEX ix_recipe_tags_tag ON recipe_tags(tag_id, recipe_id);
CREATE INDEX ix_collections_owner ON collections(owner_id, created_at DESC, id DESC);
CREATE INDEX ix_collection_entries_recipe ON collection_entries(recipe_id);

-- Додаткова валідація у домені та API:
-- * нормалізація назв і email;
-- * повнота інгредієнтів та кроків перед публікацією;
-- * максимум 10 тегів та послідовна нумерація списків;
-- * максимум 3 десяткові знаки quantity до запису NUMERIC;
-- * права, переходи статусів та expected_version;
-- * оновлення updated_at і published_at репозиторієм.
-- SQL CHECK не перевіряє наявність рядків в інших таблицях.
