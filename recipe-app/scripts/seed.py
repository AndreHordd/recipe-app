from psycopg import Connection, sql

from app.config import Settings
from app.infrastructure.database import connect
from app.infrastructure.security import Argon2PasswordHasher
from scripts.demo_recipes import seed_recipes

CATALOG = {
    "categories": ["Сніданки", "Перші страви", "Основні страви", "Салати", "Десерти"],
    "tags": ["Швидко", "Вегетаріанське", "Без глютену", "Святкове", "Бюджетне"],
    "ingredients": [
        "Яйце",
        "Молоко",
        "Борошно",
        "Картопля",
        "Морква",
        "Цибуля",
        "Помідор",
        "Сіль",
        "Цукор",
        "Вершкове масло",
        "Олія",
        "Рис",
        "Гречка",
        "Куряче філе",
        "Сир",
        "Сметана",
        "Часник",
        "Кріп",
        "Огірок",
        "Вода",
    ],
}
SEED_USERS = [
    ("admin@example.com", "Адміністратор", "ADMIN"),
    ("andriy@example.com", "Андрій", "USER"),
    ("viktoriia@example.com", "Вікторія", "USER"),
]


def seed_database(connection: Connection, settings: Settings) -> None:
    admin_password = settings.seed_admin_password.get_secret_value()
    user_password = settings.seed_user_password.get_secret_value()
    if any(not 12 <= len(password) <= 128 for password in [admin_password, user_password]):
        raise ValueError("Set SEED_ADMIN_PASSWORD and SEED_USER_PASSWORD (12–128 characters)")
    passwords = Argon2PasswordHasher()
    with connection.transaction():
        connection.execute("SELECT pg_advisory_xact_lock(748271902)")
        # Repeated seeds never reset passwords or promote a registered user to ADMIN.
        for email, display_name, role in SEED_USERS:
            existing = connection.execute(
                "SELECT role FROM users WHERE email = %s FOR UPDATE", (email,)
            ).fetchone()
            if existing:
                if existing["role"] != role:
                    raise ValueError(f"Seed account has a different role: {email}")
                continue
            password = admin_password if role == "ADMIN" else user_password
            connection.execute(
                """INSERT INTO users (email, display_name, password_hash, role)
                   VALUES (%s, %s, %s, %s)""",
                (email, display_name, passwords.hash(password), role),
            )
        for table, names in CATALOG.items():
            query = sql.SQL(
                "INSERT INTO {} (name, normalized_name) VALUES (%s, %s) "
                "ON CONFLICT (normalized_name) DO NOTHING"
            ).format(sql.Identifier(table))
            for name in names:
                connection.execute(query, (name, " ".join(name.split()).casefold()))
        seed_recipes(connection)


def main() -> None:
    settings = Settings()
    with connect(settings) as connection:
        seed_database(connection, settings)
    print("Користувачі, довідники та 12 демонстраційних рецептів готові. Паролі беруться з .env.")


if __name__ == "__main__":
    main()
