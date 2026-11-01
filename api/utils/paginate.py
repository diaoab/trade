def paginate(page, limit):
    """Page et taille bornees : 20 par defaut, 100 au plus."""

    page = max(1, page or 1)
    limit = min(100, max(1, limit or 20))

    return {"page": page, "limit": limit, "offset": (page - 1) * limit}


def page_info(total, page, limit):
    return {"total": total, "page": page, "limit": limit, "pages": max(1, -(-total // limit))}
