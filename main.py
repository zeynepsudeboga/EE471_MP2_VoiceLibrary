from custom_classes import (
    MediaItem,
    Book,
    DVD,
    LibraryCollection,
    ItemNotFoundError,
    ItemStateError,
)


def heading(text):
    """Print a section heading so the output is easy to follow."""
    print(f"\n--- {text} ---")


def print_items(label, items):
    """Print a label followed by one item per line."""
    print(f"{label}:")
    for item in items:
        print(f"  [{item.id}] {item}")


heading("Create collection and add items")
library = LibraryCollection()
dune = Book("Dune", "Frank Herbert", 412)
matrix = DVD("The Matrix", "Wachowski Sisters", 136)
podcast = MediaItem("Tech Talk", "Lex Fridman")
for item in (dune, matrix, podcast):
    item_id = library.add_item(item)
    print(f"Added with id {item_id}: {item}")

heading("get_item")
print(library.get_item(1))

heading("checkout")
print(dune.checkout())
print(matrix.checkout())  # the DVD adds a care reminder

heading("list_items")
print_items("No filter", library.list_items())
print_items("available=True", library.list_items(available=True))
print_items("available=False", library.list_items(available=False))
print_items('item_type="book"', library.list_items(item_type="book"))

heading("list_available")
print(library.list_available())

heading("return_item")
matrix.return_item()
print(matrix)

heading("to_dict")
print(dune.to_dict())
print(matrix.to_dict())

heading("update_item")
print(library.update_item(1, title="Dune Messiah", page_count=256))

heading("remove_item")
library.remove_item(matrix.id)
print_items("Remaining items", library.list_items())

heading("Error: ItemNotFoundError")
try:
    library.get_item(99)
except ItemNotFoundError as error:
    print("Caught:", error)

heading("Error: ItemStateError (checkout twice)")
try:
    dune.checkout()  # dune is still checked out
except ItemStateError as error:
    print("Caught:", error)

heading("Error: ItemStateError (remove checked-out item)")
try:
    library.remove_item(dune.id)
except ItemStateError as error:
    print("Caught:", error)

heading("Error: ValueError (protected field)")
try:
    library.update_item(podcast.id, id=42)
except ValueError as error:
    print("Caught:", error)
