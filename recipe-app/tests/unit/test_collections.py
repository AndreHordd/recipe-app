from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.api.collection_schemas import CollectionNameRequest
from app.domain.collections import Collection, CollectionEntry
from app.domain.enums import RecipeStatus
from app.domain.exceptions import InvalidCollection
from app.domain.recipes import Recipe, RecipeDetails


def test_name_is_trimmed_and_invalid_rename_preserves_previous_value():
    collection = Collection.create(7, "  Сніданки  ")
    assert collection.owner_id == 7 and collection.name == "Сніданки"
    collection.rename("Ї" * 100)
    for invalid in [" \t\n", "Ї" * 101]:
        with pytest.raises(InvalidCollection):
            collection.rename(invalid)
        assert collection.name == "Ї" * 100


@pytest.mark.parametrize("status", list(RecipeStatus))
@pytest.mark.parametrize("author_id", [7, 8])
def test_entry_visibility_depends_on_publication_or_authorship(status, author_id):
    recipe = Recipe.create(author_id, RecipeDetails("Приватний вміст"))
    recipe.status = status
    entry = CollectionEntry(1, 2, datetime.now(UTC), recipe)
    visible = entry.for_owner(7)
    expected = status == RecipeStatus.PUBLISHED or author_id == 7
    assert visible.available == expected
    assert (visible.recipe is recipe) == expected
    assert visible.recipe_id == entry.recipe_id and visible.saved_at == entry.saved_at
    assert entry.recipe is recipe  # Filtering does not mutate the loaded entry.


@pytest.mark.parametrize(
    "data", [{"name": 123}, {"name": " "}, {"name": "Ї" * 101}, {"name": "Мої", "owner_id": 8}]
)
def test_name_request_rejects_invalid_values_and_assigned_owner(data):
    with pytest.raises(ValidationError):
        CollectionNameRequest.model_validate(data)
