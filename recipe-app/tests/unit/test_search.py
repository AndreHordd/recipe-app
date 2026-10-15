from dataclasses import replace

import pytest

from app.domain.contracts import IRecipeReader, SearchStrategy
from app.domain.criteria import SearchCriteria
from app.domain.exceptions import InvalidSearch
from app.domain.recipes import Recipe
from app.services.search import (
    BaseSearchStrategy,
    RecipeSearchService,
    SearchByCategoryStrategy,
    SearchByIngredientStrategy,
    SearchByTitleStrategy,
)


class RecordingReader(IRecipeReader):
    def __init__(self):
        self.queries = []
        self.result = [Recipe(author_id=1, title="Приклад", id=1)]

    def find_by_id(self, recipe_id):
        return None

    def find(self, criteria):
        self.queries.append(criteria)
        return self.result


@pytest.mark.parametrize(
    "strategy_class,q,field",
    [
        (SearchByTitleStrategy, "  Омлет  ", "title_substring"),
        (SearchByIngredientStrategy, "  Яйце  ", "ingredient_substring"),
        (SearchByCategoryStrategy, "", None),
    ],
)
def test_strategies_keep_public_scope_and_combine_shared_filters(strategy_class, q, field):
    reader = RecordingReader()
    service = RecipeSearchService(strategy_class(reader))
    criteria = SearchCriteria(
        q=q, category_id=5, tag_id=8, max_cooking_time=30, sort="title", page=3, page_size=2
    )
    assert service.search(criteria) is reader.result
    query = reader.queries[0]
    assert query.scope == "public" and query.status is None and query.author_id is None
    assert (query.category_id, query.tag_id, query.max_cooking_time) == (5, 8, 30)
    assert (query.sort, query.offset, query.limit) == ("title", 4, 3)
    if field:
        assert getattr(query, field) == q.strip()
    else:
        assert query.title_substring is None and query.ingredient_substring is None


def test_empty_title_search_opens_catalogue():
    reader = RecordingReader()
    RecipeSearchService(SearchByTitleStrategy(reader)).search(SearchCriteria(q="  "))
    assert reader.queries[0].title_substring is None


@pytest.mark.parametrize(
    "strategy,criteria",
    [
        (SearchByIngredientStrategy, SearchCriteria(mode="ingredient")),
        (SearchByIngredientStrategy, SearchCriteria(mode="ingredient", q="  ")),
        (SearchByCategoryStrategy, SearchCriteria(mode="category")),
        (SearchByCategoryStrategy, SearchCriteria(mode="category", category_id=1, q="Омлет")),
    ],
)
def test_mode_specific_validation_happens_before_reader(strategy, criteria):
    reader = RecordingReader()
    with pytest.raises(InvalidSearch):
        RecipeSearchService(strategy(reader)).search(criteria)
    assert reader.queries == []


@pytest.mark.parametrize(
    "changes",
    [
        {"q": "x" * 101},
        {"page": 0},
        {"page_size": 0},
        {"page_size": 51},
        {"page": 2**64},
        {"category_id": 0},
        {"tag_id": -1},
        {"max_cooking_time": 0},
        {"max_cooking_time": 1441},
        {"sort": "unsafe"},
    ],
)
def test_invalid_shared_criteria_never_reach_reader(changes):
    reader = RecordingReader()
    criteria = replace(SearchCriteria(), **changes)
    with pytest.raises(InvalidSearch):
        RecipeSearchService(SearchByTitleStrategy(reader)).search(criteria)
    assert reader.queries == []


def test_search_service_accepts_another_strategy_without_mode_branches():
    class AdditionalStrategy(SearchStrategy):
        def search(self, criteria):
            return [Recipe(author_id=1, title=criteria.q)]

    result = RecipeSearchService(AdditionalStrategy()).search(
        SearchCriteria(mode="another", q="Новий спосіб")
    )
    assert result[0].title == "Новий спосіб"
    with pytest.raises(TypeError):
        BaseSearchStrategy(RecordingReader())
