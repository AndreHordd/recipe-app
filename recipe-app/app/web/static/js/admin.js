import { api } from "./api.js";
import { sessionReady } from "./auth.js";
import { element, message, recipeCard } from "./ui.js";

const tabs = [...document.querySelectorAll('[role="tab"]')];
const pages = { recipe: 1, user: 1 };
const requestNumbers = { recipe: 0, user: 0 };
const filters = { recipe: new URLSearchParams(), user: new URLSearchParams() };
const loaded = new Set();
let catalogRequestNumber = 0;

function showTab(name) {
  for (const tab of tabs) {
    const selected = tab.dataset.tab === name;
    tab.setAttribute("aria-selected", String(selected));
    tab.tabIndex = selected ? 0 : -1;
    document.getElementById(tab.getAttribute("aria-controls")).hidden = !selected;
  }
  if (!loaded.has(name)) {
    loaded.add(name);
    if (name === "recipes") loadList("recipe");
    else if (name === "users") loadList("user");
    else loadCatalog();
  }
}

tabs.forEach((tab, index) => {
  tab.addEventListener("click", () => showTab(tab.dataset.tab));
  tab.addEventListener("keydown", event => {
    const positions = { ArrowRight: (index + 1) % tabs.length, ArrowLeft: (index + tabs.length - 1) % tabs.length, Home: 0, End: tabs.length - 1 };
    if (!(event.key in positions)) return;
    event.preventDefault();
    const next = tabs[positions[event.key]];
    showTab(next.dataset.tab); next.focus();
  });
});

function pagination(kind, data) {
  document.getElementById(`${kind}-previous`).hidden = data.page === 1;
  document.getElementById(`${kind}-next`).hidden = !data.has_next;
  document.getElementById(`${kind}-page`).textContent = data.items.length || data.page > 1 ? `Сторінка ${data.page}` : "";
}

async function loadList(kind) {
  const request = ++requestNumbers[kind];
  const buttons = [document.getElementById(`${kind}-previous`), document.getElementById(`${kind}-next`)];
  buttons.forEach(button => { button.disabled = true; });
  message(`${kind}-error`, "");
  message(`${kind}-list-status`, "Завантажуємо…");
  const params = new URLSearchParams(filters[kind]);
  params.set("page", pages[kind]); params.set("page_size", 12);
  try {
    const data = await api(`/admin/${kind === "recipe" ? "recipes" : "users"}?${params}`, { protectedAction: true });
    if (request !== requestNumbers[kind]) return;
    if (!data.items.length && pages[kind] > 1) { pages[kind]--; await loadList(kind); return; }
    const list = document.getElementById(`admin-${kind}-list`);
    list.replaceChildren(...data.items.map(kind === "recipe" ? moderationCard : userCard));
    pagination(kind, data);
    message(`${kind}-list-status`, data.items.length ? "" : "Нічого не знайдено.");
  } catch (error) {
    if (request === requestNumbers[kind]) { message(`${kind}-list-status`, ""); message(`${kind}-error`, error.message); }
  } finally {
    if (request === requestNumbers[kind]) buttons.forEach(button => { button.disabled = false; });
  }
}

function moderationCard(recipe) {
  const card = recipeCard(recipe);
  card.append(element("p", `ID автора: ${recipe.author.id} · Версія: ${recipe.version}`, "muted"));
  if (recipe.status === "PUBLISHED") {
    const form = element("form", "", "moderation-form");
    const label = element("label", "Причина приховування");
    const reason = element("textarea");
    reason.id = `hide-reason-${recipe.id}`; reason.name = "reason";
    reason.required = true; reason.maxLength = 500; reason.rows = 2;
    label.htmlFor = reason.id;
    const submit = element("button", "Приховати", "danger"); submit.type = "submit";
    form.append(label, reason, submit);
    form.addEventListener("submit", event => {
      event.preventDefault(); moderate(recipe, "hide", reason.value, card);
    });
    card.append(form);
  } else if (recipe.status === "HIDDEN") {
    const restore = element("button", "Повернути до чернетки", "secondary"); restore.type = "button";
    restore.addEventListener("click", () => moderate(recipe, "restore", null, card));
    card.append(restore);
  }
  return card;
}

async function moderate(recipe, action, reason, card) {
  const controls = [...card.querySelectorAll("button, textarea")];
  controls.forEach(control => { control.disabled = true; });
  message("recipe-feedback", ""); message("recipe-error", "");
  const body = { version: recipe.version };
  if (action === "hide") body.reason = reason;
  try {
    await api(`/admin/recipes/${recipe.id}/${action}`, {method:"POST", body, protectedAction:true});
    message("recipe-feedback", action === "hide" ? "Рецепт приховано." : "Рецепт повернуто до чернетки. Публікація доступна автору.");
    await loadList("recipe");
  } catch (error) {
    message("recipe-error", error.code === "VERSION_CONFLICT" ? "Рецепт уже змінено. Введена причина залишилась у формі. Натисніть «Знайти рецепти», щоб завантажити актуальні версії." : error.message);
  } finally { controls.forEach(control => { control.disabled = false; }); }
}

function userCard(user) {
  const card = element("article", "", "panel recipe-card");
  card.append(element("h3", user.display_name), element("p", user.email), element("p", `ID: ${user.id} · ${user.role === "ADMIN" ? "Адміністратор" : "Користувач"} · ${user.is_active ? "Активний" : "Заблоковано"}`, "muted"));
  if (user.role === "USER") {
    const button = element("button", user.is_active ? "Заблокувати" : "Розблокувати", user.is_active ? "danger" : "secondary");
    button.type = "button";
    button.addEventListener("click", async () => {
      if (user.is_active && !window.confirm(`Заблокувати користувача «${user.display_name}» і завершити всі його сесії?`)) return;
      button.disabled = true; message("user-feedback", ""); message("user-error", "");
      try {
        await api(`/admin/users/${user.id}`, {method:"PATCH", body:{is_active:!user.is_active}, protectedAction:true});
        message("user-feedback", user.is_active ? "Користувача заблоковано, сесії завершено." : "Користувача розблоковано. Він має увійти знову.");
        await loadList("user");
      } catch (error) { message("user-error", error.message); }
      finally { button.disabled = false; }
    });
    card.append(button);
  }
  return card;
}

for (const kind of ["recipe", "user"]) {
  document.getElementById(`admin-${kind}-filter`).addEventListener("submit", event => {
    event.preventDefault(); filters[kind] = new URLSearchParams();
    for (const [name, value] of new FormData(event.currentTarget)) if (value.trim()) filters[kind].set(name, value.trim());
    pages[kind] = 1; loadList(kind);
  });
  document.getElementById(`${kind}-previous`).addEventListener("click", () => { pages[kind]--; loadList(kind); });
  document.getElementById(`${kind}-next`).addEventListener("click", () => { pages[kind]++; loadList(kind); });
}

async function loadCatalog() {
  const request = ++catalogRequestNumber;
  try {
    const [categories, tags] = await Promise.all([api("/categories"), api("/tags")]);
    if (request !== catalogRequestNumber) return;
    renderCatalog("category", categories); renderCatalog("tag", tags);
  } catch (error) {
    if (request === catalogRequestNumber) { message("catalog-error", error.message); loaded.delete("catalog"); }
  }
}

function catalogPath(kind) { return kind === "category" ? "categories" : "tags"; }

function renderCatalog(kind, items) {
  const list = document.getElementById(`${kind}-list`);
  list.replaceChildren();
  for (const item of items) {
    const row = element("form", "", "catalog-row");
    const label = element("label", `${kind === "category" ? "Категорія" : "Тег"}: ${item.name}`);
    const input = element("input"); input.id = `${kind}-${item.id}`; input.name = "name"; input.value = item.name; input.required = true; input.maxLength = 80; label.htmlFor = input.id;
    const actions = element("div", "", "actions");
    const save = element("button", "Перейменувати", "secondary"); save.type = "submit";
    const remove = element("button", "Видалити", "danger"); remove.type = "button";
    actions.append(save, remove); row.append(label, input, actions); list.append(row);
    row.addEventListener("submit", event => { event.preventDefault(); changeCatalog(kind, item.id, "PUT", {name:input.value}, row); });
    remove.addEventListener("click", () => {
      if (window.confirm(`Видалити запис «${item.name}»? Використаний запис видалити не можна.`)) changeCatalog(kind, item.id, "DELETE", undefined, row);
    });
  }
  if (!items.length) list.append(element("p", "Довідник порожній.", "muted"));
}

async function changeCatalog(kind, id, method, body, form) {
  const controls = [...form.querySelectorAll("button, input")];
  controls.forEach(control => { control.disabled = true; });
  message("catalog-error", ""); message("catalog-feedback", "");
  try {
    await api(`/admin/${catalogPath(kind)}${id === null ? "" : `/${id}`}`, {method, body, protectedAction:true});
    if (method === "POST") form.reset();
    message("catalog-feedback", method === "DELETE" ? "Запис видалено." : "Запис збережено.");
    await loadCatalog();
  } catch (error) { message("catalog-error", error.message); }
  finally { controls.forEach(control => { control.disabled = false; }); }
}

for (const kind of ["category", "tag"]) {
  document.getElementById(`create-${kind}`).addEventListener("submit", event => {
    event.preventDefault(); const form = event.currentTarget;
    changeCatalog(kind, null, "POST", {name:form.elements.namedItem("name").value}, form);
  });
}

const session = await sessionReady;
if (session === null) window.location.assign("/login");
else if (session?.user.role === "ADMIN") { document.getElementById("admin-content").hidden = false; showTab("recipes"); }
else if (session) message("page-error", "Ця сторінка доступна лише адміністратору.");
message("admin-loading", "");
