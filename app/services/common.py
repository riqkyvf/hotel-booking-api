from sqlalchemy import func, select

from app.core.errors import BusinessError


def require(obj, message="Resource not found."):
    if obj is None:
        raise BusinessError(404, "NOT_FOUND", message)
    return obj


def page(db, statement, limit, offset):
    total = db.scalar(select(func.count()).select_from(statement.order_by(None).subquery()))
    return {
        "items": list(db.scalars(statement.limit(limit).offset(offset))),
        "total": total,
        "limit": limit,
        "offset": offset,
    }


def validate_range(low, high):
    if low is not None and high is not None and low > high:
        raise BusinessError(422, "INVALID_FILTER_RANGE", "Minimum cannot exceed maximum.")


def order(statement, sort, mapping, id_column):
    descending = sort.startswith("-")
    column = mapping.get(sort.removeprefix("-"))
    if column is None:
        raise BusinessError(422, "INVALID_SORT", "Unsupported sort field.")
    return statement.order_by(
        column.desc().nulls_last() if descending else column.asc().nulls_last(), id_column
    )
