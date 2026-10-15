class ApplicationError(Exception):
    def __init__(self, code: str, message: str, status_code: int):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class EmailAlreadyExists(ApplicationError):
    def __init__(self):
        super().__init__("EMAIL_EXISTS", "Ця електронна адреса вже зареєстрована.", 409)


class AuthenticationRequired(ApplicationError):
    def __init__(self):
        super().__init__("AUTH_REQUIRED", "Увійдіть до облікового запису.", 401)


class InvalidCredentials(ApplicationError):
    def __init__(self):
        super().__init__("INVALID_CREDENTIALS", "Неправильна адреса або пароль.", 401)


class InactiveUser(ApplicationError):
    def __init__(self):
        super().__init__("USER_INACTIVE", "Обліковий запис заблоковано.", 403)


class AccessDenied(ApplicationError):
    def __init__(self):
        super().__init__("ACCESS_DENIED", "Недостатньо прав для цієї дії.", 403)


class RecipeNotFound(ApplicationError):
    def __init__(self):
        super().__init__("RECIPE_NOT_FOUND", "Рецепт не знайдено або він недоступний.", 404)


class VersionConflict(ApplicationError):
    def __init__(self):
        super().__init__("VERSION_CONFLICT", "Рецепт уже змінено. Оновіть сторінку.", 409)


class InvalidRecipe(ApplicationError):
    def __init__(self, message: str):
        super().__init__("INVALID_RECIPE", message, 422)


class InvalidPhoto(ApplicationError):
    def __init__(self):
        super().__init__(
            "INVALID_PHOTO",
            "Оберіть справне статичне фото JPEG, PNG або WebP до 20 мегапікселів.",
            422,
        )


class PhotoTooLarge(ApplicationError):
    def __init__(self):
        super().__init__("PHOTO_TOO_LARGE", "Розмір фотографії має бути не більшим за 5 МБ.", 413)


class PhotoNotFound(ApplicationError):
    def __init__(self):
        super().__init__("PHOTO_NOT_FOUND", "Фотографію не знайдено.", 404)


class PhotoStorageUnavailable(ApplicationError):
    def __init__(self):
        super().__init__(
            "PHOTO_STORAGE_UNAVAILABLE", "Не вдалося зберегти фото. Спробуйте ще раз.", 503
        )


class InvalidTransition(ApplicationError):
    def __init__(self):
        super().__init__("INVALID_STATE", "Ця дія недоступна для поточного стану рецепта.", 409)


class InvalidReference(ApplicationError):
    def __init__(self):
        super().__init__("INVALID_REFERENCE", "Обрана категорія, тег або інгредієнт не існує.", 422)


class InvalidSearch(ApplicationError):
    def __init__(self, message: str):
        super().__init__("INVALID_SEARCH", message, 422)


class CollectionNotFound(ApplicationError):
    def __init__(self):
        super().__init__("COLLECTION_NOT_FOUND", "Колекцію не знайдено або вона недоступна.", 404)


class InvalidCollection(ApplicationError):
    def __init__(self, message: str):
        super().__init__("INVALID_COLLECTION", message, 422)


class RecipeNotPublished(ApplicationError):
    def __init__(self):
        super().__init__(
            "RECIPE_NOT_PUBLISHED", "До колекції можна додати лише опублікований рецепт.", 409
        )


class UserNotFound(ApplicationError):
    def __init__(self):
        super().__init__("USER_NOT_FOUND", "Користувача не знайдено.", 404)


class CatalogItemNotFound(ApplicationError):
    def __init__(self):
        super().__init__("CATALOG_NOT_FOUND", "Запис довідника не знайдено.", 404)


class CatalogNameExists(ApplicationError):
    def __init__(self):
        super().__init__("CATALOG_NAME_EXISTS", "Така назва вже є в цьому довіднику.", 409)


class CatalogItemInUse(ApplicationError):
    def __init__(self):
        super().__init__(
            "CATALOG_IN_USE", "Запис використовується в рецептах. Його можна перейменувати.", 409
        )
