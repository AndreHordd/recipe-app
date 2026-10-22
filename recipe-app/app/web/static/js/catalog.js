import { api } from "./api.js";
import { message, renderRecipes, renderPagination } from "./ui.js";

const form = document.getElementById("search-form");
const defaults = { mode: "title", q: "", category_id: "", tag_id: "", max_cooking_time: "", sort: "newest" };
let applied = new URLSearchParams();
let page = 1;
let requestNumber = 0;

function configureMode() {
  const mode = form.elements.namedItem("mode").value;
  const text = form.elements.namedItem("q");
  text.disabled = mode === "category";
  text.required = mode === "ingredient";
  if (text.disabled) text.value = "";
  form.elements.namedItem("category_id").required = mode === "category";
  document.getElementById("search-text-label").textContent = mode === "ingredient" ? "Назва інгредієнта" : "Назва рецепта";
  message("search-hint", mode === "ingredient"
    ? "Введіть назву інгредієнта. Знайдемо рецепти, що містять хоча б один відповідний інгредієнт."
    : mode === "category"
      ? "Оберіть категорію. За потреби додайте тег або максимальний час."
      : "Порожнє поле назви показує весь каталог. Фільтри можна поєднувати.");
}

function readForm() {
  const query = new URLSearchParams();
  for (const [key, value] of new FormData(form)) {
    if (String(value).trim()) query.set(key, String(value).trim());
  }
  return query;
}

function restoreFromUrl() {
  const query = new URLSearchParams(window.location.search);
  for (const [key, fallback] of Object.entries(defaults)) {
    const control = form.elements.namedItem(key);
    const value = query.get(key) ?? fallback;
    if (control.tagName === "SELECT" && ![...control.options].some(option => option.value === value)) {
      if (["category_id", "tag_id"].includes(key) && /^\d+$/.test(value)) {
        const option = document.createElement("option");
        option.value = value;
        option.textContent = key === "category_id" ? "Недоступна категорія" : "Недоступний тег";
        control.append(option);
      } else { control.value = fallback; continue; }
    }
    control.value = value;
  }
  configureMode();
  applied = readForm();
  const requestedPage = Number(query.get("page") || 1);
  page = Number.isSafeInteger(requestedPage) && requestedPage >= 1 ? requestedPage : 1;
}

function saveUrl() {
  const query = new URLSearchParams(applied);
  if (query.get("mode") === "title") query.delete("mode");
  if (query.get("sort") === "newest") query.delete("sort");
  if (page > 1) query.set("page", page);
  const url = query.size ? `/recipes?${query}` : "/recipes";
  if (url !== `${window.location.pathname}${window.location.search}`) window.history.pushState(null, "", url);
}

async function load(updateUrl = true) {
  const currentRequest = ++requestNumber;
  if (updateUrl) saveUrl();
  document.getElementById("previous-page").disabled = true;
  document.getElementById("next-page").disabled = true;
  renderRecipes([]);
  renderPagination({ page: 1, items: [], has_next: false });
  message("list-status", "Шукаємо рецепти…");
  message("page-error", "");
  try {
    const query = new URLSearchParams(applied);
    query.set("page", page);
    query.set("page_size", 12);
    const data = await api(`/recipes?${query}`);
    if (currentRequest !== requestNumber) return;
    renderRecipes(data.items);
    renderPagination(data);
    message("list-status", data.items.length ? "" : page > 1
      ? "На цій сторінці немає рецептів. Поверніться на попередню сторінку."
      : "Рецептів не знайдено. Змініть запит або скиньте фільтри.");
  } catch (error) {
    if (currentRequest === requestNumber) { message("list-status", ""); message("page-error", error.message); }
  } finally {
    if (currentRequest === requestNumber) {
      document.getElementById("previous-page").disabled = false;
      document.getElementById("next-page").disabled = false;
    }
  }
}
form.addEventListener("submit", event => {
  event.preventDefault(); applied = readForm(); page = 1; load();
});
form.elements.namedItem("mode").addEventListener("change", configureMode);
document.getElementById("reset-search").addEventListener("click", () => {
  for (const [key, value] of Object.entries(defaults)) form.elements.namedItem(key).value = value;
  configureMode(); applied = readForm(); page = 1; load();
});
document.getElementById("previous-page").addEventListener("click", () => { page--; load(); });
document.getElementById("next-page").addEventListener("click", () => { page++; load(); });
window.addEventListener("popstate", () => { restoreFromUrl(); load(false); });

async function initialize() {
  try {
    const [categories, tags] = await Promise.all([api("/categories"), api("/tags")]);
    for (const [key, items] of [["category_id", categories], ["tag_id", tags]]) {
      for (const item of items) {
        const option = document.createElement("option");
        option.value = item.id;
        option.textContent = item.name;
        form.elements.namedItem(key).append(option);
      }
    }
    restoreFromUrl();
    document.getElementById("search-submit").disabled = false;
    await load(false);
  } catch (error) { message("list-status", ""); message("page-error", error.message); }
}
initialize();
