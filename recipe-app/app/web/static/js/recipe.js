import { api, getSession } from "./api.js";
import { sessionReady } from "./auth.js";
import { element, message, statuses, units } from "./ui.js";

const content = document.getElementById("recipe-content");
const id = content.dataset.recipeId;
let recipe;
let collectionsLoading = false;
let collectionsLoaded = false;

function render() {
  document.title = `${recipe.title} · Кулінарні рецепти`;
  document.getElementById("recipe-title").textContent = recipe.title;
  document.getElementById("recipe-meta").textContent = [recipe.author.display_name, recipe.category?.name, recipe.cooking_time ? `${recipe.cooking_time} хв` : null, `${recipe.servings} порц.`, statuses[recipe.status]].filter(Boolean).join(" · ");
  document.getElementById("recipe-description").textContent = recipe.description;
  document.getElementById("recipe-tags").textContent = recipe.tags.map(tag => tag.name).join(" · ");
  const photo = document.getElementById("recipe-photo");
  photo.hidden = !recipe.photo_url;
  if (recipe.photo_url) { photo.src = recipe.photo_url; photo.alt = `Фото: ${recipe.title}`; }
  else photo.removeAttribute("src");
  photo.onerror = () => { photo.hidden = true; photo.removeAttribute("src"); };
  message("hide-reason", recipe.hide_reason ? `Причина приховування: ${recipe.hide_reason}` : "");
  document.getElementById("recipe-ingredients").replaceChildren(...recipe.ingredients.map(item => element("li", `${item.name} — ${Number(item.quantity)} ${units[item.unit]}`)));
  document.getElementById("recipe-steps").replaceChildren(...recipe.steps.map(step => element("li", step.description)));
  const isOwner = getSession()?.user.id === recipe.author.id;
  document.getElementById("recipe-actions").hidden = !isOwner;
  document.getElementById("edit-recipe").href = `/recipes/${id}/edit`;
  document.getElementById("publish-recipe").hidden = recipe.status !== "DRAFT";
  document.getElementById("unpublish-recipe").hidden = recipe.status !== "PUBLISHED";
  content.hidden = false;
  message("recipe-loading", "");
  document.getElementById("save-login-hint").hidden = !!getSession();
  const canSave = !!getSession() && recipe.status === "PUBLISHED";
  document.getElementById("save-collection-panel").hidden = !canSave;
  if (canSave && !collectionsLoaded && !collectionsLoading) loadCollections();
}

async function loadCollections() {
  collectionsLoading = true;
  try {
    const items = [];
    let page = 1;
    let hasNext;
    do {
      const data = await api(`/collections?page=${page}&page_size=50`, { protectedAction: true });
      items.push(...data.items); hasNext = data.has_next; page++;
    } while (hasNext);
    const select = document.getElementById("save-collection");
    for (const collection of items) {
      const option = element("option", collection.name);
      option.value = collection.id;
      select.append(option);
    }
    document.getElementById("save-to-collection").disabled = items.length === 0;
    message("collection-choice-status", items.length ? "" : "Спершу створіть колекцію за посиланням нижче.");
    collectionsLoaded = true;
  } catch (error) { message("collection-choice-status", ""); message("save-collection-error", error.message); }
  finally { collectionsLoading = false; }
}

document.getElementById("save-collection-form").addEventListener("submit", async event => {
  event.preventDefault();
  message("save-collection-error", ""); message("save-collection-success", "");
  const button = document.getElementById("save-to-collection");
  button.disabled = true;
  try {
    const collectionId = document.getElementById("save-collection").value;
    await api(`/collections/${collectionId}/recipes/${id}`, { method: "PUT", protectedAction: true });
    message("save-collection-success", "Рецепт збережено. Повторне додавання не створює дубля.");
  } catch (error) { message("save-collection-error", error.message); }
  finally { button.disabled = false; }
});

async function change(action) {
  const buttons = document.getElementById("recipe-actions").querySelectorAll("button");
  buttons.forEach(button => { button.disabled = true; });
  message("page-error", "");
  try {
    recipe = await api(`/recipes/${id}/${action}`, { method: "POST", body: { version: recipe.version }, protectedAction: true });
    render();
  } catch (error) { message("page-error", error.message); }
  finally { buttons.forEach(button => { button.disabled = false; }); }
}
document.getElementById("publish-recipe").addEventListener("click", () => change("publish"));
document.getElementById("unpublish-recipe").addEventListener("click", () => change("unpublish"));
document.getElementById("delete-recipe").addEventListener("click", async event => {
  if (!window.confirm("Видалити рецепт? Цю дію не можна скасувати.")) return;
  event.currentTarget.disabled = true;
  try {
    await api(`/recipes/${id}?version=${recipe.version}`, { method: "DELETE", protectedAction: true });
    window.location.assign("/my-recipes");
  } catch (error) { message("page-error", error.message); document.getElementById("delete-recipe").disabled = false; }
});
await sessionReady;
try { recipe = await api(`/recipes/${id}`); render(); }
catch (error) { message("recipe-loading", ""); message("page-error", error.message); }
