import { api, getSession } from "./api.js";
import { sessionReady } from "./auth.js";
import { element, message, units } from "./ui.js";

const form = document.getElementById("recipe-form");
let recipeId = form.dataset.recipeId;
const ingredientRows = document.getElementById("ingredient-rows");
const stepRows = document.getElementById("step-rows");
const ingredientOptions = document.getElementById("ingredient-options");
const ingredients = new Map();
const normalize = value => value.trim().replace(/\s+/g, " ").toLocaleLowerCase("uk");
let version;
let rowId = 0;
let busy = false;
let selectedPhoto = null;
let previewUrl = null;
let savedPhoto = null;
let photoSaveFailed = false;
const photoFile = document.getElementById("photo-file");

function clearPhotoChoice(clearInput = true) {
  if (previewUrl) URL.revokeObjectURL(previewUrl);
  previewUrl = null; selectedPhoto = null;
  if (clearInput) photoFile.value = "";
}

function renderPhoto() {
  const preview = document.getElementById("photo-preview");
  const url = previewUrl || savedPhoto;
  preview.hidden = !url;
  if (url) preview.src = url; else preview.removeAttribute("src");
  document.getElementById("upload-photo").hidden = !recipeId || !selectedPhoto;
  document.getElementById("cancel-photo").hidden = !selectedPhoto;
  document.getElementById("delete-photo").hidden = !savedPhoto;
  const fileName = document.getElementById("photo-file-name");
  if (fileName) fileName.textContent = "Файл ще не обрано · JPG, PNG або WebP";
  message("photo-choice", selectedPhoto
    ? "Нове фото обрано. Воно завантажиться після збереження рецепта або кнопкою «Завантажити фото»."
    : savedPhoto ? "Поточна фотографія рецепта." : "Фотографії ще немає.");
}

function setBusy(value) {
  busy = value;
  form.querySelectorAll("input, select, textarea, button").forEach(control => { control.disabled = value; });
  if (!value) updateRowButtons();
}

function acceptSavedRecipe(recipe) {
  recipeId = String(recipe.id); version = recipe.version; savedPhoto = recipe.photo_url;
  form.dataset.recipeId = recipeId;
  document.querySelector("main h1").textContent = "Редагувати рецепт";
  document.title = "Редагувати рецепт · Кулінарні рецепти";
  document.getElementById("save-recipe").textContent = "Зберегти зміни";
  window.history.replaceState(null, "", `/recipes/${recipeId}/edit`);
  message("state-hint", recipe.status === "HIDDEN"
    ? "Рецепт залишається прихованим до перевірки адміністратором."
    : "Чернетку збережено. Публікація доступна на сторінці готового рецепта.");
  renderPhoto();
}

function photoError(error) {
  message("photo-error", error.message);
  if (error.code === "VERSION_CONFLICT") document.getElementById("reload-recipe").hidden = false;
}

async function uploadChosenPhoto() {
  const result = await api(`/recipes/${recipeId}/photo?version=${version}`, {
    method: "PUT", body: selectedPhoto, binary: true, protectedAction: true,
  });
  clearPhotoChoice(); acceptSavedRecipe(result);
  if (photoSaveFailed) { message("form-error", ""); photoSaveFailed = false; }
  message("photo-message", "Фотографію збережено. Інші зміни у формі збережіть кнопкою нижче.");
}

photoFile.addEventListener("change", () => {
  const file = photoFile.files[0];
  const fileName = document.getElementById("photo-file-name");
  if (fileName) fileName.textContent = file ? file.name : "Файл ще не обрано · JPG, PNG або WebP";
  clearPhotoChoice(false); message("photo-error", ""); message("photo-message", "");
  if (file && file.size > 5 * 1024 * 1024) message("photo-error", "Розмір фотографії має бути не більшим за 5 МБ.");
  else if (file && file.type && !["image/jpeg", "image/png", "image/webp"].includes(file.type)) {
    message("photo-error", "Оберіть JPEG, PNG або WebP.");
  } else if (file) { selectedPhoto = file; previewUrl = URL.createObjectURL(file); }
  if (!selectedPhoto) photoFile.value = "";
  renderPhoto();
});
document.getElementById("cancel-photo").addEventListener("click", () => {
  clearPhotoChoice(); renderPhoto(); message("photo-error", "");
});
document.getElementById("upload-photo").addEventListener("click", async () => {
  if (busy || !recipeId || !selectedPhoto) return;
  setBusy(true); message("photo-error", ""); message("photo-message", "");
  try { await uploadChosenPhoto(); }
  catch (error) { photoError(error); }
  finally { setBusy(false); }
});
document.getElementById("delete-photo").addEventListener("click", async () => {
  if (busy || !savedPhoto) return;
  if (!window.confirm("Видалити фотографію рецепта? Цю дію не можна скасувати.")) return;
  setBusy(true); message("photo-error", ""); message("photo-message", "");
  try {
    const result = await api(`/recipes/${recipeId}/photo?version=${version}`, {method:"DELETE", protectedAction:true});
    clearPhotoChoice(); acceptSavedRecipe(result); message("photo-message", "Фотографію видалено.");
  } catch (error) { photoError(error); }
  finally { setBusy(false); }
});
window.addEventListener("pagehide", () => { if (previewUrl) URL.revokeObjectURL(previewUrl); });

function rememberIngredient(item) {
  const key = normalize(item.name);
  if (!ingredients.has(key)) {
    const option = element("option");
    option.value = item.name;
    ingredientOptions.append(option);
  }
  ingredients.set(key, item);
}

function rememberCategory(category) {
  if (!category) return;
  const select = form.elements.namedItem("category_id");
  let option = [...select.options].find(item => item.value === String(category.id));
  if (!option) {
    option = element("option"); option.value = category.id; select.append(option);
  }
  option.textContent = category.name;
}

function rememberTag(tag) {
  let checkbox = [...form.querySelectorAll('input[name="tag_id"]')].find(input => input.value === String(tag.id));
  if (!checkbox) {
    const label = element("label"); checkbox = element("input");
    checkbox.type = "checkbox"; checkbox.name = "tag_id"; checkbox.value = tag.id;
    label.append(checkbox); document.getElementById("tag-options").append(label);
  }
  checkbox.parentElement.replaceChildren(checkbox, document.createTextNode(tag.name));
}

function field(labelText, input) {
  const wrapper = element("div");
  input.id = `recipe-field-${++rowId}`;
  const label = element("label", labelText);
  label.htmlFor = input.id;
  wrapper.append(label, input);
  return wrapper;
}

function updateRowButtons() {
  document.getElementById("add-ingredient").disabled = ingredientRows.children.length >= 50;
  document.getElementById("add-step").disabled = stepRows.children.length >= 50;
  [...stepRows.children].forEach((row, index) => {
    row.querySelector("label").textContent = `Крок ${index + 1}`;
  });
}

function removeButton(row, label) {
  const button = element("button", "Прибрати", "secondary");
  button.type = "button";
  button.setAttribute("aria-label", label);
  button.addEventListener("click", () => { row.remove(); updateRowButtons(); });
  return button;
}

function addIngredient(item = {}) {
  if (ingredientRows.children.length >= 50) return;
  const row = element("div", "", "ingredient-row");
  const name = element("input");
  name.dataset.field = "name";
  name.setAttribute("list", "ingredient-options");
  name.maxLength = 80;
  name.required = true;
  name.value = item.name || "";
  const quantity = element("input");
  quantity.dataset.field = "quantity";
  quantity.type = "number";
  quantity.min = "0.001";
  quantity.max = "999999.999";
  quantity.step = "0.001";
  quantity.required = true;
  quantity.value = item.quantity || "";
  const unit = element("select");
  unit.dataset.field = "unit";
  for (const [value, label] of Object.entries(units)) {
    const option = element("option", label);
    option.value = value;
    unit.append(option);
  }
  unit.value = item.unit || "g";
  row.append(field("Назва інгредієнта", name), field("Кількість", quantity),
    field("Одиниця", unit), removeButton(row, "Прибрати інгредієнт"));
  ingredientRows.append(row);
  updateRowButtons();
}

function addStep(item = {}) {
  if (stepRows.children.length >= 50) return;
  const row = element("div", "", "step-row");
  const description = element("textarea");
  description.rows = 2;
  description.maxLength = 2000;
  description.required = true;
  description.value = item.description || "";
  row.append(field("Крок", description), removeButton(row, "Прибрати крок"));
  stepRows.append(row);
  updateRowButtons();
}

function fillRecipe(recipe) {
  version = recipe.version;
  clearPhotoChoice(); savedPhoto = recipe.photo_url; renderPhoto();
  photoSaveFailed = false;
  message("photo-error", ""); message("photo-message", "");
  rememberCategory(recipe.category);
  recipe.tags.forEach(rememberTag);
  for (const key of ["title", "description", "cooking_time", "servings"]) {
    form.elements.namedItem(key).value = recipe[key] ?? "";
  }
  form.elements.namedItem("category_id").value = recipe.category?.id || "";
  const tagIds = new Set(recipe.tags.map(tag => String(tag.id)));
  form.querySelectorAll('input[name="tag_id"]').forEach(input => {
    input.checked = tagIds.has(input.value);
  });
  ingredientRows.replaceChildren();
  stepRows.replaceChildren();
  for (const ingredient of recipe.ingredients) {
    rememberIngredient({ id: ingredient.ingredient_id, name: ingredient.name });
    addIngredient(ingredient);
  }
  recipe.steps.forEach(addStep);
  updateRowButtons();
  document.getElementById("save-recipe").textContent = "Зберегти зміни";
  const hint = recipe.status === "HIDDEN"
    ? "Рецепт приховано. Після редагування він залишиться прихованим до перевірки адміністратором."
    : recipe.status === "PUBLISHED"
      ? "Після збереження рецепт стане чернеткою. Перевірте зміни й опублікуйте його повторно."
      : "Можна зберегти неповну чернетку. Публікація доступна на сторінці готового рецепта.";
  message("state-hint", hint);
  document.getElementById("reload-recipe").hidden = true;
}

async function loadRecipe() {
  const recipe = await api(`/recipes/${recipeId}`, { protectedAction: true });
  if (recipe.author.id !== getSession()?.user.id) throw new Error("Редагувати рецепт може його автор.");
  fillRecipe(recipe);
}

document.getElementById("add-ingredient").addEventListener("click", () => addIngredient());
document.getElementById("add-step").addEventListener("click", () => addStep());
document.getElementById("reload-recipe").addEventListener("click", async () => {
  if (!window.confirm("Завантажити актуальну версію? Незбережені зміни у формі буде втрачено.")) return;
  if (busy) return;
  photoSaveFailed = false;
  setBusy(true);
  try { await loadRecipe(); message("form-error", ""); }
  catch (error) { message("form-error", error.message); }
  finally { setBusy(false); }
});

form.addEventListener("submit", async event => {
  event.preventDefault();
  if (busy) return;
  message("form-error", "");
  photoSaveFailed = false;
  const tagIds = [...form.querySelectorAll('input[name="tag_id"]:checked')].map(input => Number(input.value));
  if (tagIds.length > 10) { message("form-error", "Оберіть до десяти тегів."); return; }
  const ingredientValues = [...ingredientRows.children].map(row => ({
    name: row.querySelector('[data-field="name"]').value.trim().replace(/\s+/g, " "),
    quantity: row.querySelector('[data-field="quantity"]').value,
    unit: row.querySelector('[data-field="unit"]').value,
  }));
  if (ingredientValues.some(item => !item.name)) {
    message("form-error", "Вкажіть назву кожного інгредієнта."); return;
  }
  const body = {
    title: form.elements.namedItem("title").value,
    description: form.elements.namedItem("description").value,
    cooking_time: Number(form.elements.namedItem("cooking_time").value) || null,
    servings: Number(form.elements.namedItem("servings").value),
    category_id: Number(form.elements.namedItem("category_id").value) || null,
    tag_ids: tagIds, ingredients: [],
    steps: [...stepRows.children].map(row => ({ description: row.querySelector("textarea").value })),
  };
  setBusy(true);
  try {
    for (const item of ingredientValues) {
      let ingredient = ingredients.get(normalize(item.name));
      if (!ingredient) {
        ingredient = await api("/ingredients", {
          method: "POST", body: { name: item.name }, protectedAction: true,
        });
        rememberIngredient(ingredient);
      }
      body.ingredients.push({ ingredient_id: ingredient.id, quantity: item.quantity, unit: item.unit });
    }
    if (recipeId) body.version = version;
    const result = await api(recipeId ? `/recipes/${recipeId}` : "/recipes", {
      method: recipeId ? "PUT" : "POST", body, protectedAction: true,
    });
    acceptSavedRecipe(result);
    if (selectedPhoto) {
      try { await uploadChosenPhoto(); }
      catch (error) {
        photoSaveFailed = true;
        photoError(error);
        message("form-error", "Рецепт збережено, але фото не завантажилося. Виправте фото та повторіть кнопкою «Завантажити фото».");
        return;
      }
    }
    window.location.assign(`/recipes/${result.id}`);
  } catch (error) {
    message("form-error", error.message);
    if (error.code === "VERSION_CONFLICT") document.getElementById("reload-recipe").hidden = false;
  } finally {
    setBusy(false);
  }
});

async function initialize() {
  const session = await sessionReady;
  if (session === null) { window.location.assign("/login"); return; }
  if (!session) return;
  try {
    const [categories, tags, ingredientPage] = await Promise.all([
      api("/categories"), api("/tags"), api("/ingredients?page_size=50"),
    ]);
    categories.forEach(rememberCategory);
    tags.forEach(rememberTag);
    ingredientPage.items.forEach(rememberIngredient);
    if (recipeId) await loadRecipe();
    form.hidden = false;
  } catch (error) { message("page-error", error.message); }
  finally { document.getElementById("form-loading").hidden = true; }
}
initialize();
