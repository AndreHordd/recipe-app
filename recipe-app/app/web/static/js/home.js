import { api } from "/static/js/api.js";
import { recipeCard } from "/static/js/ui.js";

const list = document.getElementById("home-recommendation-list");
const status = document.getElementById("home-list-status");

try {
  const data = await api("/recipes?sort=newest&page=1&page_size=6");
  list.replaceChildren(...data.items.map(recipeCard));
  status.textContent = data.items.length ? "" : "Поки що немає опублікованих рецептів.";
} catch (error) {
  status.textContent = "";
  const pageError = document.getElementById("page-error");
  pageError.textContent = error.message;
  pageError.hidden = false;
}
