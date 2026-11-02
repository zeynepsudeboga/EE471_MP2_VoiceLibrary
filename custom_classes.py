"""Media item classes for a simple library system."""

class ItemNotFoundError(Exception):
    """Raised when no item with the given id exists in the collection."""


class ItemStateError(Exception):
    """Raised when an action does not fit the item's current state,
    e.g. checking out an item that is already checked out."""

class MediaItem:
    """A generic item in a library that can be checked out and returned.

    Attributes:
        title (str): Title of the item.
        author (str): Author or creator of the item.
        is_available (bool): True if the item can be checked out.
    """

    CHECKOUT_SUCCESS = "Successful checkout"
    ITEM_TYPE = "item"
    EDITABLE_FIELDS = ("title", "author")

    def __init__(self, title, author, is_available=True):
        """Create a media item, available by default."""
        self.title = title
        self.author = author
        self.is_available = is_available
        self.id: int | None = None  # the collection assigns it in add_item()

    def checkout(self) -> str:
        """Check out the item.

        Returns:
            str: CHECKOUT_SUCCESS.

        Raises:
            ItemStateError: If the item is already checked out.
        """
        if not self.is_available:
            raise ItemStateError(f"'{self.title}' is already checked out.")
        self.is_available = False
        return self.CHECKOUT_SUCCESS

    def return_item(self):
        """Mark the item as available again.

        Raises:
            ItemStateError: If the item is not checked out.
        """
        if self.is_available:
            raise ItemStateError(f"'{self.title}' is not checked out.")
        self.is_available = True

    def __str__(self):
        """Return 'Title by Author [Available/Checked Out]'."""
        status = "Available" if self.is_available else "Checked Out"
        return f"{self.title} by {self.author} [{status}]"
    
    def to_dict(self):
        """Return the item as a dictionary, ready to be sent as JSON."""
        return {
            "id": self.id,
            "type": self.ITEM_TYPE,
            "title": self.title,
            "author": self.author,
            "is_available": self.is_available,
        }

class Book(MediaItem):
    """A book, which also stores its number of pages.

    Attributes:
        page_count (int): Number of pages in the book.
    """
    ITEM_TYPE = "book"
    EDITABLE_FIELDS = MediaItem.EDITABLE_FIELDS + ("page_count",)

    def __init__(self, title, author, page_count, is_available=True):
        """Create a book with a page count."""
        super().__init__(title, author, is_available)
        self.page_count = page_count

    def __str__(self):
        """Return the base description followed by the page count."""
        return f"{super().__str__()} - {self.page_count} pages"
    
    def to_dict(self):
        """Return the item as a dictionary, including the page count."""
        data = super().to_dict()
        data["page_count"] = self.page_count
        return data


class DVD(MediaItem):
    """A DVD, which prints a care reminder on every successful checkout.

    Attributes:
                duration (int): Running time of the DVD in minutes.
    """

    CARE_REMINDER = "Handle with care: Do not scratch the disc."
    ITEM_TYPE = "dvd"
    EDITABLE_FIELDS = MediaItem.EDITABLE_FIELDS + ("duration",)

    def __init__(self, title, author, duration, is_available=True):
        """Create a DVD with its running time in minutes."""
        super().__init__(title, author, is_available)
        self.duration = duration

    def checkout(self):
        """Check out the DVD and include a care reminder in the message.

        Returns:
            str: The success message followed by the care reminder.

        Raises:
            ItemStateError: If the DVD is already checked out.
        """
        # super() raises ItemStateError if the DVD is already out, so reaching the next line means success.
        message = super().checkout()
        return f"{message}. {self.CARE_REMINDER}"
    def to_dict(self):
        """Return the item as a dictionary, including the duration."""
        data = super().to_dict()
        data["duration"] = self.duration
        return data

class LibraryCollection:
    """A container that holds the media items of a library."""

    def __init__(self):
        """Create an empty collection."""
        self.items = []
        self._next_id = 1

    def add_item(self, item):
        """Add a MediaItem (or any of its subclasses) and give it a unique id.

        Returns:
            int: The id assigned to the item.

        Raises:
            TypeError: If item is not a MediaItem.
        """
        # We block wrong objects here, otherwise list_available() would crash when it looks for is_available.
        if not isinstance(item, MediaItem):
            raise TypeError("Only MediaItem objects can be added.")
        # We never reuse ids, even after a delete, so an old id can never point to a different item.
        item.id = self._next_id
        self._next_id += 1
        self.items.append(item)
        return item.id

    def list_available(self):
        """Return the titles of all items that are currently available."""
        return [item.title for item in self.list_items(available=True)]

    def get_item(self, item_id):
        """Return the item with the given id.

        Raises:
            ItemNotFoundError: If no item has this id.
        """
        for item in self.items:
            if item.id == item_id:
                return item
        raise ItemNotFoundError(f"No item with id {item_id}.")
    
    def list_items(self, available=None, item_type=None):
        """Return the items, optionally filtered.

        Args:
            available (bool | None): True for available items only, False for checked-out
                items only, None for no filter.
            item_type (str | None): "book" or "dvd" to filter by type, None for no filter.
        """
        result = list(self.items)
        # "is not None" instead of "if available:", so that available=False also filters.
        if available is not None:
            result = [item for item in result if item.is_available == available]
        if item_type is not None:
            result = [item for item in result if item.ITEM_TYPE == item_type]
        return result
    
    def update_item(self, item_id, **fields):
        """Update only the editable fields of an item.

        Raises:
            ItemNotFoundError: If no item has this id.
            ValueError: If a field is protected (id, type, is_available) or not editable for this item.
        """
        item = self.get_item(item_id)
        # Check every field before changing anything, so a bad field never leaves the item half-updated.
        for name in fields:
            if name in ("id", "type", "is_available"):
                raise ValueError(f"'{name}' cannot be changed with update_item().")
            if name not in item.EDITABLE_FIELDS:
                raise ValueError(f"'{name}' is not an editable field of a {item.ITEM_TYPE}.")
        for name, value in fields.items():
            setattr(item, name, value)
        return item

    def remove_item(self, item_id):
        """Remove an item from the collection.

        Raises:
            ItemNotFoundError: If no item has this id.
            ItemStateError: If the item is checked out.
        """
        item = self.get_item(item_id)
        if not item.is_available:
            raise ItemStateError(f"'{item.title}' is checked out and cannot be removed.")
        self.items.remove(item)
    
 