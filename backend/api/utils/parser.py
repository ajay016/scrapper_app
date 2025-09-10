import requests
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from api.models import *





def parse_page(url, current_depth=0, max_depth=1, max_links_per_page=2):
    """
    Recursion function
    Fetch page content and crawl children up to max_depth.
    Returns nested structure with 'children'.
    """

    # If depth is 0, return immediately
    if max_depth == 0:
        return {"url": url, "title": None}

    # If we are at depth 1, only return URL
    if current_depth >= max_depth:
        return {"url": url, "title": None}

    try:
        resp = requests.get(url, timeout=5, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
    except Exception as e:
        return {"url": url, "title": None, "error": str(e)}

    soup = BeautifulSoup(resp.text, "html.parser")
    title = soup.title.string.strip() if soup.title else None

    data = {"url": url, "title": title, "children": []}

    # Collect links for next level
    links = []
    for a in soup.find_all("a", href=True):
        new_url = urljoin(url, a["href"])
        if new_url.startswith("http") and not any(new_url.endswith(ext) for ext in [".jpg", ".png", ".pdf", ".zip"]):
            links.append(new_url)

    # Crawl children (limited)
    for link in links[:max_links_per_page]:
        child_data = parse_page(link, current_depth=current_depth + 1, max_depth=max_depth, max_links_per_page=max_links_per_page)
        data["children"].append(child_data)

    return data


def save_page_hierarchy(data, keyword_obj, parent=None, depth=0, seen_urls=None, folder=None, user=None):
        """
        Recursively save SearchResultLink objects and preserve hierarchy.
        - Uses get_or_create to avoid duplicate (keyword + folder + url).
        - Always processes children so they get attached to the saved node.
        - Uses seen_urls set (per-request) to avoid cycles/duplicate work.
        """
        if not data or not data.get("url"):
            return None

        url = data["url"]

        # init seen set
        if seen_urls is None:
            seen_urls = set()

        # Avoid cyclical loops in the same crawl
        if url in seen_urls:
            # Already processed in this crawl - return existing DB node if present
            existing = SearchResultLink.objects.filter(keyword=keyword_obj, folder=folder, url=url).first()
            if existing:
                return {
                    "id": existing.id,
                    "url": existing.url,
                    "title": existing.title,
                    "depth": existing.depth,
                    "children": []  # child subtree will be handled by DB or earlier processing
                }
            return None

        seen_urls.add(url)

        # Try to find an existing record for this (keyword, folder, url)
        result_obj, created = SearchResultLink.objects.get_or_create(
            keyword=keyword_obj,
            folder=folder,
            url=url,
            defaults={
                "parent": parent,
                "depth": depth,
                "user": user,
                "title": data.get("title")
            }
        )

        # If it already existed, ensure parent/depth/title are set reasonably
        if not created:
            changed = False
            if parent and result_obj.parent is None:
                result_obj.parent = parent
                changed = True
            # If depth is different and current depth is smaller (we found a shallower path), update it
            if result_obj.depth != depth:
                # you can decide policy here; below we update if new depth is smaller
                if depth < result_obj.depth or result_obj.depth is None:
                    result_obj.depth = depth
                    changed = True
            # update title if missing or changed
            incoming_title = data.get("title")
            if incoming_title and incoming_title != result_obj.title:
                result_obj.title = incoming_title
                changed = True
            if changed:
                result_obj.save()

        # Build the return node
        node = {
            "id": result_obj.id,
            "url": result_obj.url,
            "title": result_obj.title,
            "depth": result_obj.depth,
            "children": []
        }

        # Recurse into children and attach them (always process children)
        for child in data.get("children", []):
            child_node = save_page_hierarchy(
                child,
                keyword_obj,
                parent=result_obj,
                depth=depth + 1,
                seen_urls=seen_urls,
                folder=folder,
                user=user
            )
            if child_node:
                node["children"].append(child_node)

        return node