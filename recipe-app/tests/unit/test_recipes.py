from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.api.recipe_schemas import RecipeCreate
from app.domain.enums import IngredientUnit, RecipeStatus
from app.domain.exceptions import InvalidRecipe, InvalidTransition
from app.domain.recipes import InstructionStep, Recipe, RecipeDetails, RecipeIngredient


def complete_details():
    return RecipeDetails(
        title="  Омлет  ",
        cooking_time=10,
        category_id=1,
        ingredients=[RecipeIngredient(1, Decimal("2"), IngredientUnit.PIECE, 1)],
        steps=[InstructionStep(1, "Збити яйця й посмажити.")],
    )


def test_draft_can_be_incomplete_but_publishing_requires_complete_recipe():
    recipe = Recipe.create(1, RecipeDetails("Задум"))
    assert recipe.status == RecipeStatus.DRAFT
    with pytest.raises(InvalidRecipe):
        recipe.publish()
    assert recipe.status == RecipeStatus.DRAFT and recipe.published_at is None
    recipe.update_details(complete_details())
    assert recipe.title == "Омлет"
    recipe.publish()
    assert recipe.status == RecipeStatus.PUBLISHED and recipe.published_at is not None


@pytest.mark.parametrize("missing", ["category_id", "cooking_time", "ingredients", "steps"])
def test_each_required_component_is_checked_before_publication(missing):
    details = complete_details()
    details = replace(details, **{missing: [] if missing in {"ingredients", "steps"} else None})
    with pytest.raises(InvalidRecipe):
        Recipe.create(1, details).publish()


def test_editing_published_recipe_unpublishes_and_preserves_last_publication_time():
    recipe = Recipe.create(1, complete_details())
    recipe.publish()
    previous = datetime(2020, 1, 1, tzinfo=UTC)
    recipe.published_at = previous
    recipe.update_details(RecipeDetails("Нова чернетка"))
    assert recipe.status == RecipeStatus.DRAFT and recipe.published_at == previous
    recipe.update_details(complete_details())
    recipe.publish()
    assert recipe.published_at > previous
    recipe.unpublish()
    assert recipe.published_at > previous


def test_hidden_recipe_stays_hidden_after_edit_and_cannot_bypass_moderation():
    recipe = Recipe.create(1, complete_details())
    recipe.publish()
    published_at = recipe.published_at
    recipe.hide("  Уточніть інструкцію  ")
    recipe.update_details(RecipeDetails("Виправлено"))
    assert recipe.status == RecipeStatus.HIDDEN
    assert recipe.hide_reason == "Уточніть інструкцію"
    assert recipe.published_at == published_at
    for action in [recipe.publish, recipe.unpublish]:
        with pytest.raises(InvalidTransition):
            action()
    recipe.restore_to_draft()
    assert recipe.status == RecipeStatus.DRAFT and recipe.hide_reason is None
    with pytest.raises(InvalidRecipe):
        recipe.publish()


def test_invalid_edit_does_not_change_existing_state():
    recipe = Recipe.create(1, complete_details())
    recipe.publish()
    with pytest.raises(InvalidRecipe):
        recipe.update_details(RecipeDetails(" "))
    assert recipe.title == "Омлет" and recipe.status == RecipeStatus.PUBLISHED


@pytest.mark.parametrize("quantity", ["0", "-1", "0.0001", "1000000", "NaN", "Infinity"])
def test_domain_rejects_invalid_quantities(quantity):
    with pytest.raises(InvalidRecipe):
        RecipeIngredient(1, Decimal(quantity), IngredientUnit.GRAM, 1).validate()


@pytest.mark.parametrize("quantity", ["0.001", "999999.999", "1.0000"])
def test_domain_accepts_quantities_without_precision_loss(quantity):
    RecipeIngredient(1, Decimal(quantity), IngredientUnit.GRAM, 1).validate()


def test_lists_must_be_sequential_and_tags_unique():
    details = complete_details()
    for invalid in [
        replace(details, tag_ids=[1, 1]),
        replace(details, ingredients=[replace(details.ingredients[0], position=2)]),
        replace(details, steps=[InstructionStep(2, "Змішати")]),
        replace(details, steps=[InstructionStep(1, "Змішати")] * 51),
    ]:
        with pytest.raises(InvalidRecipe):
            invalid.validate()


@pytest.mark.parametrize("quantity", [1, 0.5, True, "0", "NaN", "0.0001", "1000000"])
def test_request_requires_bounded_decimal_string(quantity):
    with pytest.raises(ValidationError):
        RecipeCreate.model_validate(
            {
                "title": "Рецепт",
                "ingredients": [
                    {"ingredient_id": 1, "quantity": quantity, "unit": "g"},
                ],
            }
        )
