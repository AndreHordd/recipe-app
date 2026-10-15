export const statuses = { DRAFT: "Чернетка", PUBLISHED: "Опубліковано", HIDDEN: "Приховано" };
export const units = { g: "г", kg: "кг", ml: "мл", l: "л", pcs: "шт.", tsp: "ч. л.", tbsp: "ст. л.", pinch: "дрібка" };

export function element(tag, text = "", className = "") {
  const node = document.createElement(tag);
  node.textContent = text;
  if (className) node.className = className;
  return node;
}

export function message(id, text) {
  const node = document.getElementById(id);
  if (node) { node.textContent = text; node.hidden = !text; }
}

export function renderRecipes(items) {
  const list = document.getElementById("recipe-list");
  list.replaceChildren();
  for (const recipe of items) {
    list.append(recipeCard(recipe));
  }
}

export function recipeCard(recipe) {
  const card = element("article", "", "panel recipe-card");
  if (recipe.thumbnail_url) {
    const photo = element("img", "", "recipe-card-photo");
    photo.src = recipe.thumbnail_url; photo.alt = `Фото: ${recipe.title}`;
    photo.loading = "lazy"; photo.decoding = "async";
    photo.onerror = () => photo.remove();
    card.append(photo);
  }
  const title = element("h2");
  const link = element("a", recipe.title);
  link.href = `/recipes/${recipe.id}`;
  title.append(link);
  card.append(title, element("p", recipe.description, "card-description"));
  card.append(element("p", [recipe.category?.name, recipe.cooking_time ? `${recipe.cooking_time} хв` : null, `${recipe.servings} порц.`].filter(Boolean).join(" · "), "muted"));
  card.append(element("p", `${recipe.author.display_name} · ${statuses[recipe.status]}`, "muted"));
  return card;
}

export function renderPagination(data) {
  document.getElementById("previous-page").hidden = data.page === 1;
  document.getElementById("next-page").hidden = !data.has_next;
  document.getElementById("page-number").textContent = data.items.length || data.page > 1 ? `Сторінка ${data.page}` : "";
}
