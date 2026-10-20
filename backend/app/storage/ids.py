import uuid


def new_id() -> str:
    """Primary key for every table except users_profile: a random UUID4 string."""
    return str(uuid.uuid4())
