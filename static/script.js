// Frontend for the library API. All rules (validation, filtering,
// availability) live on the server; this file only sends requests
// and shows what the API answers.

const API = "/api/items";

const errorBox = document.getElementById("error");
const noticeBox = document.getElementById("notice");

const form = document.getElementById("item-form");
const formTitle = document.getElementById("form-title");
const titleInput = document.getElementById("title");
const authorInput = document.getElementById("author");
const typeSelect = document.getElementById("type");
const extraLabel = document.getElementById("extra-label");
const extraInput = document.getElementById("extra");
const saveButton = document.getElementById("save-button");
const cancelButton = document.getElementById("cancel-button");

const filterAvailable = document.getElementById("filter-available");
const filterType = document.getElementById("filter-type");

const itemList = document.getElementById("item-list");
const emptyState = document.getElementById("empty-state");

// The id of the item being edited, or null when the form adds a new item.
let editingId = null;


// --- Talking to the API ---

// Send a request and return the JSON body (or null for 204 No Content).
// Any non-2xx answer is thrown as an Error carrying the API's "error" message.
async function request(url, options = {}) {
    const response = await fetch(url, {
        headers: { "Content-Type": "application/json" },
        ...options,
    });

    if (response.status === 204) {
        return null;
    }

    let data = null;
    try {
        data = await response.json();
    } catch {
        // Body was not JSON; fall through with data = null.
    }

    if (!response.ok) {
        const message = data && data.error ? data.error : `Request failed (${response.status}).`;
        throw new Error(message);
    }
    return data;
}


// --- Messages ---

function showError(message) {
    errorBox.textContent = message;
}

function showNotice(message) {
    noticeBox.textContent = message;
}

function clearMessages() {
    errorBox.textContent = "";
    noticeBox.textContent = "";
}


// --- Item list ---

async function loadItems() {
    const params = new URLSearchParams();
    if (filterAvailable.checked) {
        params.set("available", "true");
    }
    if (filterType.value) {
        params.set("type", filterType.value);
    }

    try {
        const query = params.toString();
        const items = await request(query ? `${API}?${query}` : API);
        renderItems(items);
    } catch (error) {
        showError(error.message);
    }
}

function renderItems(items) {
    itemList.innerHTML = "";
    emptyState.hidden = items.length > 0;
    for (const item of items) {
        itemList.appendChild(createCard(item));
    }
}

function createCard(item) {
    const card = document.createElement("li");
    card.className = "card";

    const typeName = item.type === "dvd" ? "DVD" : "Book";
    const extra = item.type === "dvd"
        ? `${item.duration} min`
        : `${item.page_count} pages`;

    const info = document.createElement("div");
    const heading = document.createElement("h3");
    heading.textContent = item.title;
    const meta = document.createElement("p");
    meta.className = "meta";
    meta.textContent = `${item.author} · ${typeName} · ${extra}`;
    const badge = document.createElement("span");
    badge.className = item.is_available ? "badge available" : "badge checked-out";
    badge.textContent = item.is_available ? "Available" : "Checked out";
    info.append(heading, meta, badge);

    const actions = document.createElement("div");
    actions.className = "actions";

    const stateButton = document.createElement("button");
    stateButton.textContent = item.is_available ? "Checkout" : "Return";
    stateButton.addEventListener("click", () =>
        item.is_available ? checkoutItem(item.id) : returnItem(item.id)
    );

    const editButton = iconButton("✎", "Edit", () => startEdit(item));
    const deleteButton = iconButton("🗑", "Delete", () => deleteItem(item));

    actions.append(stateButton, editButton, deleteButton);
    card.append(info, actions);
    return card;
}

function iconButton(symbol, label, onClick) {
    const button = document.createElement("button");
    button.className = "icon-button";
    button.textContent = symbol;
    button.title = label;
    button.setAttribute("aria-label", label);
    button.addEventListener("click", onClick);
    return button;
}


// --- Actions ---

// Run an API action, show its result or error, then reload the list.
async function runAction(action) {
    clearMessages();
    try {
        await action();
    } catch (error) {
        showError(error.message);
    }
    await loadItems();
}

function checkoutItem(id) {
    return runAction(async () => {
        const data = await request(`${API}/${id}/checkout`, { method: "POST" });
        // Books answer "Successful checkout"; DVDs add the care reminder.
        showNotice(data.message);
    });
}

function returnItem(id) {
    return runAction(() => request(`${API}/${id}/return`, { method: "POST" }));
}

function deleteItem(item) {
    if (!confirm(`Delete '${item.title}'?`)) {
        return;
    }
    return runAction(async () => {
        await request(`${API}/${item.id}`, { method: "DELETE" }); // 204, no body
        if (editingId === item.id) {
            resetForm();
        }
    });
}


// --- Add / Edit form ---

// Show "Page count" for books and "Duration (minutes)" for DVDs.
function updateExtraField() {
    extraLabel.textContent = typeSelect.value === "dvd" ? "Duration (minutes)" : "Page count";
}

function startEdit(item) {
    clearMessages();
    editingId = item.id;
    titleInput.value = item.title;
    authorInput.value = item.author;
    typeSelect.value = item.type;
    // The API does not allow changing an item's type.
    typeSelect.disabled = true;
    extraInput.value = item.type === "dvd" ? item.duration : item.page_count;
    updateExtraField();

    formTitle.textContent = "Edit item";
    saveButton.textContent = "Save";
    cancelButton.hidden = false;
    titleInput.focus();
}

function resetForm() {
    editingId = null;
    form.reset();
    typeSelect.disabled = false;
    updateExtraField();
    formTitle.textContent = "Add item";
    saveButton.textContent = "Add";
    cancelButton.hidden = true;
}

// Build the JSON body. Values are sent as typed; the API decides if they are valid.
function formData() {
    const extraName = typeSelect.value === "dvd" ? "duration" : "page_count";
    const extraValue = extraInput.value === "" ? null : Number(extraInput.value);
    return {
        title: titleInput.value,
        author: authorInput.value,
        [extraName]: extraValue,
    };
}

form.addEventListener("submit", (event) => {
    event.preventDefault();
    runAction(async () => {
        const body = formData();
        if (editingId === null) {
            body.type = typeSelect.value;
            await request(API, { method: "POST", body: JSON.stringify(body) }); // 201
        } else {
            await request(`${API}/${editingId}`, { method: "PUT", body: JSON.stringify(body) });
        }
        // Only reached on success, so a failed save keeps the user's input.
        resetForm();
    });
});

cancelButton.addEventListener("click", () => {
    clearMessages();
    resetForm();
});

typeSelect.addEventListener("change", updateExtraField);
filterAvailable.addEventListener("change", loadItems);
filterType.addEventListener("change", loadItems);


// --- Start ---

updateExtraField();
loadItems();
