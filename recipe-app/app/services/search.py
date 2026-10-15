from dataclasses import replace

from app.domain.contracts import IRecipeReader, SearchStrategy
from app.domain.criteria import RecipeQuery, SearchCriteria
from app.domain.exceptions import InvalidSearch
from app.domain.recipes import Recipe


class BaseSearchStrategy(SearchStrategy):
    def __init__(self, reader: IRecipeReader):
        self.reader = reader

    def common_query(self, criteria: SearchCriteria) -> RecipeQuery:
        return RecipeQuery(
            scope="public",
            category_id=criteria.category_id,
            tag_id=criteria.tag_id,
            max_cooking_time=criteria.max_cooking_time,
            sort=criteria.sort,
            offset=(criteria.page - 1) * criteria.page_size,
            limit=criteria.page_size + 1,
        )


class SearchByTitleStrategy(BaseSearchStrategy):
    def search(self, criteria: SearchCriteria) -> list[Recipe]:
        query = replace(self.common_query(criteria), title_substring=criteria.q.strip() or None)
        return self.reader.find(query)


class SearchByIngredientStrategy(BaseSearchStrategy):
    def search(self, criteria: SearchCriteria) -> list[Recipe]:
        if not criteria.q.strip():
            raise InvalidSearch("Для пошуку за інгредієнтом введіть його назву.")
        query = replace(self.common_query(criteria), ingredient_substring=criteria.q.strip())
        return self.reader.find(query)


class SearchByCategoryStrategy(BaseSearchStrategy):
    def search(self, criteria: SearchCriteria) -> list[Recipe]:
        if criteria.category_id is None:
            raise InvalidSearch("Для пошуку за категорією оберіть категорію.")
        if criteria.q.strip():
            raise InvalidSearch("У режимі категорії поле пошукового тексту має бути порожнім.")
        return self.reader.find(self.common_query(criteria))


class RecipeSearchService:
    def __init__(self, strategy: SearchStrategy):
        self.strategy = strategy

    def search(self, criteria: SearchCriteria) -> list[Recipe]:
        criteria.validate()
        return self.strategy.search(criteria)
