"""JSON REST API for the library. Routes only translate HTTP into
LibraryCollection method calls; the rules live in custom_classes.py."""

from flask import Flask, jsonify, request
from werkzeug.exceptions import HTTPException

from custom_classes import (
    Book,
    DVD,
    LibraryCollection,
    ItemNotFoundError,
    ItemStateError,
)

app = Flask(__name__)

ITEM_CLASSES = {"book": Book, "dvd": DVD}

library = LibraryCollection()
library.add_item(Book("Dune", "Frank Herbert", 412))
library.add_item(Book("1984", "George Orwell", 328))
library.add_item(DVD("The Matrix", "Wachowski Sisters", 136))
library.add_item(DVD("Interstellar", "Christopher Nolan", 169))


# --- Error handlers: exceptions from custom_classes become JSON errors ---

def error_response(message, status):
    return jsonify({"error": str(message)}), status


@app.errorhandler(ItemNotFoundError)
def handle_not_found(error):
    return error_response(error, 404)


@app.errorhandler(ItemStateError)
def handle_state_error(error):
    return error_response(error, 409)


@app.errorhandler(ValueError)
@app.errorhandler(TypeError)
def handle_bad_input(error):
    return error_response(error, 400)


@app.errorhandler(HTTPException)
def handle_http_error(error):
    # Unknown URLs, wrong methods, etc. also answer with JSON.
    return error_response(error.description, error.code)


# --- Input helpers: only check basic types, not library rules ---

def read_json_body():
    """Return the request body as a dict, or raise ValueError."""
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ValueError("Request body must be a JSON object.")
    return data


def check_field_types(data):
    """Raise ValueError if a known field has the wrong type.

    Unknown field names are left to update_item(), which decides what is editable.
    """
    for name in ("title", "author"):
        if name in data and (not isinstance(data[name], str) or not data[name].strip()):
            raise ValueError(f"'{name}' must be a non-empty string.")
    for name in ("page_count", "duration"):
        if name in data:
            value = data[name]
            # bool is a subclass of int in Python, so exclude it explicitly.
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise ValueError(f"'{name}' must be a positive integer.")


def parse_bool(value, name):
    if value == "true":
        return True
    if value == "false":
        return False
    raise ValueError(f"'{name}' must be 'true' or 'false'.")


# --- Routes ---

@app.get("/")
def index():
    # The frontend is plain static files; Flask serves them from static/.
    return app.send_static_file("index.html")


@app.post("/api/items")
def create_item():
    data = read_json_body()
    item_class = ITEM_CLASSES.get(data.get("type"))
    if item_class is None:
        raise ValueError("'type' must be 'book' or 'dvd'.")

    fields = {name: value for name, value in data.items() if name != "type"}
    missing = [name for name in item_class.EDITABLE_FIELDS if name not in fields]
    if missing:
        raise ValueError(f"Missing fields: {', '.join(missing)}.")
    unknown = [name for name in fields if name not in item_class.EDITABLE_FIELDS]
    if unknown:
        raise ValueError(f"Unknown fields: {', '.join(unknown)}.")
    check_field_types(fields)

    item = item_class(**fields)
    library.add_item(item)
    return jsonify(item.to_dict()), 201


@app.get("/api/items")
def list_items():
    available = request.args.get("available")
    item_type = request.args.get("type")
    if available is not None:
        available = parse_bool(available, "available")
    if item_type is not None and item_type not in ITEM_CLASSES:
        raise ValueError("'type' must be 'book' or 'dvd'.")

    items = library.list_items(available=available, item_type=item_type)
    return jsonify([item.to_dict() for item in items]), 200


@app.get("/api/items/<int:item_id>")
def get_item(item_id):
    return jsonify(library.get_item(item_id).to_dict()), 200


@app.put("/api/items/<int:item_id>")
def replace_item(item_id):
    data = read_json_body()
    item = library.get_item(item_id)
    missing = [name for name in item.EDITABLE_FIELDS if name not in data]
    if missing:
        raise ValueError(f"PUT needs all editable fields. Missing: {', '.join(missing)}.")
    check_field_types(data)
    return jsonify(library.update_item(item_id, **data).to_dict()), 200


@app.patch("/api/items/<int:item_id>")
def update_item(item_id):
    data = read_json_body()
    if not data:
        raise ValueError("Give at least one field to change.")
    check_field_types(data)
    return jsonify(library.update_item(item_id, **data).to_dict()), 200


@app.delete("/api/items/<int:item_id>")
def delete_item(item_id):
    library.remove_item(item_id)
    return "", 204


@app.post("/api/items/<int:item_id>/checkout")
def checkout_item(item_id):
    item = library.get_item(item_id)
    message = item.checkout()
    return jsonify({"item": item.to_dict(), "message": message}), 200


@app.post("/api/items/<int:item_id>/return")
def return_item(item_id):
    item = library.get_item(item_id)
    item.return_item()
    return jsonify(item.to_dict()), 200


if __name__ == "__main__":
    app.run(port=5001, debug=True)
