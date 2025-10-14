# views.py
from rest_framework.decorators import api_view, permission_classes
from django.http import StreamingHttpResponse
from urllib.parse import unquote
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET
from playwright.sync_api import sync_playwright
from rest_framework import status
from collections import deque
from django.utils import timezone
from bs4 import BeautifulSoup
import logging
import json
import time
from django.shortcuts import get_object_or_404
from urllib.parse import urljoin, urlparse
import requests
from .utils.google_search import scrape_search_results
from .utils.parser import parse_page, save_page_hierarchy
from .serializers import *
from .models import *

logger = logging.getLogger(__name__)








@api_view(["GET"])
@permission_classes([IsAuthenticated])
def current_user(request):
    serializer = UserSerializer(request.user)
    print('serializer.data: ', serializer.data)
    return Response(serializer.data)


# Search and parse for saving the data before sending it to the front end
# @api_view(['GET'])
# @permission_classes([AllowAny])
# def search_and_parse(request):
#     keyword_raw = request.GET.get("q", "headphones")
#     max_depth = int(request.GET.get("depth", 0))

#     keyword_stripped = keyword_raw.strip()
#     # optionally accept folder_id param
#     folder_id = request.GET.get("folder_id")
#     folder = None
#     if folder_id:
#         try:
#             folder = ProjectFolder.objects.get(id=folder_id)
#         except ProjectFolder.DoesNotExist:
#             folder = None

#     # pass user if you have authentication; otherwise user=None
#     user = request.user if request.user.is_authenticated else None

#     keyword_obj, _ = Keyword.objects.get_or_create(word=keyword_stripped, folder=folder, user=user)

#     # Step 1: Get Google links
#     links = google_search(keyword_stripped, num_results=10)

#     results = []

#     # Create a seen set for this search to avoid cycles
#     seen_urls = set()

#     for link in links:
#         parsed_data = parse_page(link, current_depth=0, max_depth=max_depth)
#         node = save_page_hierarchy(parsed_data, keyword_obj, parent=None, depth=0, seen_urls=seen_urls, folder=folder, user=user)
#         if node:
#             results.append(node)

#     return Response({
#         "keyword": KeywordSerializer(keyword_obj).data,
#         "results": results
#     }, status=200)


# Search and parse without saving the data and send it to the front end
# @api_view(['GET'])
# @permission_classes([AllowAny])
# def search_and_parse(request):
#     keyword_raw = request.GET.get("q", "headphones")
#     max_depth = int(request.GET.get("depth", 0))

#     keyword_stripped = keyword_raw.strip()
#     keyword_obj, _ = Keyword.objects.get_or_create(word=keyword_stripped)

#     # Step 1: Get Google links
#     links = google_search(keyword_stripped, num_results=10)

#     results = []

#     def parse_to_dict(data, depth=0):
#         if not data.get("url"):
#             return None
#         node = {
#             "url": data["url"],
#             "title": data.get("title"),
#             "depth": depth,
#             "children": []
#         }
#         for child in data.get("children", []):
#             child_node = parse_to_dict(child, depth=depth+1)
#             if child_node:
#                 node["children"].append(child_node)
#         return node

#     for link in links:
#         parsed_data = parse_page(link, current_depth=0, max_depth=max_depth)
#         node = parse_to_dict(parsed_data)
#         if node:
#             results.append(node)

#     return Response({
#         "keyword": KeywordSerializer(keyword_obj).data,
#         "results": results
#     }, status=200)



# Return 100 results from google custom search API
# @api_view(['GET'])
# @permission_classes([AllowAny])
# def search_and_parse(request):
#     try:
#         keyword_raw = request.GET.get("q", "headphones")
#         max_depth = int(request.GET.get("depth", 0))
#         num_results = int(request.GET.get("limit", 100))

#         keyword_stripped = keyword_raw.strip()
#         keyword_obj, _ = Keyword.objects.get_or_create(word=keyword_stripped)

#         # Step 1: Get Google links (with pagination)
#         links = google_search(keyword_stripped, num_results=num_results)

#         results = []

#         def parse_to_dict(data, depth=0):
#             if not data.get("url"):
#                 return None
#             node = {
#                 "url": data["url"],
#                 "title": data.get("title"),
#                 "depth": depth,
#                 "children": []
#             }
#             for child in data.get("children", []):
#                 child_node = parse_to_dict(child, depth=depth+1)
#                 if child_node:
#                     node["children"].append(child_node)
#             return node

#         # Step 2: Parse each link recursively
#         for link in links:
#             parsed_data = parse_page(link, current_depth=0, max_depth=max_depth)
#             node = parse_to_dict(parsed_data)
#             if node:
#                 results.append(node)

#         return Response({
#             "keyword": KeywordSerializer(keyword_obj).data,
#             "results": results
#         }, status=200)

#     except Exception as e:
#         logger.exception("Error in search_and_parse")
#         return Response({"error": str(e)}, status=500)


# @api_view(['GET'])
# @permission_classes([AllowAny])
# def search_and_parse(request):
#     keyword_raw = request.GET.get("q", "headphones")
#     max_depth = int(request.GET.get("depth", 0))
#     num_results = int(request.GET.get("limit", 500))  # user can control

#     keyword_stripped = keyword_raw.strip()
#     keyword_obj, _ = Keyword.objects.get_or_create(word=keyword_stripped)

#     # Step 1: Scrape search results (DuckDuckGo)
#     links = scrape_bing_results(keyword_stripped, num_results=num_results, pause=1.5, verbose=True)
    
#     print('Search results from Bing: ', links)

#     results = []

#     def parse_to_dict(data, depth=0):
#         if not data.get("url"):
#             return None
#         node = {
#             "url": data["url"],
#             "title": data.get("title"),
#             "depth": depth,
#             "children": []
#         }
#         for child in data.get("children", []):
#             child_node = parse_to_dict(child, depth=depth + 1)
#             if child_node:
#                 node["children"].append(child_node)
#         return node

#     # Step 2: Parse each link recursively
#     for link in links:
#         parsed_data = parse_page(link, current_depth=0, max_depth=max_depth)
#         node = parse_to_dict(parsed_data)
#         if node:
#             results.append(node)

#     return Response({
#         "keyword": KeywordSerializer(keyword_obj).data,
#         "results": results
#     }, status=200)


# @api_view(['GET'])
# @permission_classes([AllowAny])
# def search_and_parse(request):
#     try:
#         keyword_raw = request.GET.get("q", "headphones")
#         max_depth = int(request.GET.get("depth", 0))
#         num_results = int(request.GET.get("limit", 100))

#         keyword_stripped = keyword_raw.strip()
#         keyword_obj, _ = Keyword.objects.get_or_create(word=keyword_stripped)

#         # Step 1: Get Google links (with pagination)
#         links = scrape_google_search(keyword_stripped)

#         results = []

#         def parse_to_dict(data, depth=0):
#             if not data.get("url"):
#                 return None
#             node = {
#                 "url": data["url"],
#                 "title": data.get("title"),
#                 "depth": depth,
#                 "children": []
#             }
#             for child in data.get("children", []):
#                 child_node = parse_to_dict(child, depth=depth+1)
#                 if child_node:
#                     node["children"].append(child_node)
#             return node

#         # Step 2: Parse each link recursively
#         for link in links:
#             parsed_data = parse_page(link, current_depth=0, max_depth=max_depth)
#             node = parse_to_dict(parsed_data)
#             if node:
#                 results.append(node)

#         return Response({
#             "keyword": KeywordSerializer(keyword_obj).data,
#             "results": results
#         }, status=200)

#     except Exception as e:
#         logger.exception("Error in search_and_parse")
#         return Response({"error": str(e)}, status=500)


# @api_view(['GET'])
# @permission_classes([AllowAny])
# def search_and_parse(request):
#     keyword = request.GET.get("q", "headphones")
#     max_depth = int(request.GET.get("depth", 0))
#     limit = int(request.GET.get("limit", 20))

#     # Recursive parser
#     def parse_to_dict(data, depth=0):
#         if not data.get("url"):
#             return None
#         node = {
#             "url": data["url"],
#             "title": data.get("title"),
#             "depth": depth,
#             "children": []
#         }
#         for child in data.get("children", []):
#             child_node = parse_to_dict(child, depth=depth + 1)
#             if child_node:
#                 node["children"].append(child_node)
#         return node

#     def event_stream():
#         links = scrape_search_results(keyword, num_results=limit)
#         total_links = len(links)
#         for idx, link in enumerate(links, 1):
#             parsed = parse_page(link, 0, max_depth)
#             node = parse_to_dict(parsed)
#             if node:
#                 payload = {
#                     "node": node,
#                     "progress": {"current": idx, "total": total_links}
#                 }
#                 yield f"data: {json.dumps(payload)}\n\n"
#             time.sleep(0.05)
#         yield f"event: done\ndata: {{\"message\": \"Streaming complete\"}}\n\n"

#     return StreamingHttpResponse(event_stream(), content_type="text/event-stream")


# @api_view(['GET'])
# @permission_classes([AllowAny])
# def search_and_parse(request):
#     keyword_raw = request.GET.get("q", "headphones")
#     max_depth = int(request.GET.get("depth", 0))
#     num_results = int(request.GET.get("limit", 50))  # user can control

#     keyword_stripped = keyword_raw.strip()
#     keyword_obj, _ = Keyword.objects.get_or_create(word=keyword_stripped)

#     # Step 1: Scrape search results (DuckDuckGo)
#     links = scrape_search_results(keyword_stripped, num_results=num_results)

#     results = []

#     def parse_to_dict(data, depth=0):
#         if not data.get("url"):
#             return None
#         node = {
#             "url": data["url"],
#             "title": data.get("title"),
#             "depth": depth,
#             "children": []
#         }
#         for child in data.get("children", []):
#             child_node = parse_to_dict(child, depth=depth + 1)
#             if child_node:
#                 node["children"].append(child_node)
#         return node

#     # Step 2: Parse each link recursively
#     for link in links:
#         parsed_data = parse_page(link, current_depth=0, max_depth=max_depth)
#         node = parse_to_dict(parsed_data)
#         if node:
#             results.append(node)

#     return Response({
#         "keyword": KeywordSerializer(keyword_obj).data,
#         "results": results
#     }, status=200)



# Returns DuuckDuckGo results. Fully working
def scrape_search_results_stream(query, num_results=50):
    """
    Generator: yields href strings as they are found from DuckDuckGo search.
    Note: uses sync_playwright and yields while the browser is still open.
    """
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False, args=["--disable-blink-features=AutomationControlled"])
            page = browser.new_page(viewport={"width": 1280, "height": 800})
            url = f"https://duckduckgo.com/?q={query}&ia=web"
            page.goto(url, timeout=60000)
            # Wait initial results
            page.wait_for_selector("a[data-testid='result-title-a']", timeout=15000)

            collected = set()
            while True:
                links = page.locator("a[data-testid='result-title-a']")
                count = links.count()
                for i in range(count):
                    try:
                        href = links.nth(i).get_attribute("href")
                    except Exception:
                        href = None
                    if href and href not in collected:
                        collected.add(href)
                        yield href
                        if len(collected) >= num_results:
                            break
                if len(collected) >= num_results:
                    break

                # try click "More results" or scroll to load more
                more_button = page.locator("#more-results")
                if more_button.count() > 0:
                    try:
                        more_button.scroll_into_view_if_needed()
                        more_button.click()
                        page.wait_for_timeout(1000)
                    except Exception:
                        break
                else:
                    # try scrolling to bottom to load lazy results (optional)
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    page.wait_for_timeout(1000)
                    # if no new links after scroll attempt, break
                    new_count = page.locator("a[data-testid='result-title-a']").count()
                    if new_count <= count:
                        break

            browser.close()
    except Exception as e:
        # yield nothing on error, but could yield an error event instead if desired
        print("scrape search error:", e)


# ---------- SSE view that consumes the above generator -------------
@csrf_exempt
@require_GET
def search_and_parse_stream(request):
    """
    SSE streaming view (improved):
    - ensures Keyword object exists (like old endpoint)
    - emits an initial `meta` event with keyword metadata
    - includes `keyword_id` inside every `data` payload so clients always get context
    """
    keyword_raw = request.GET.get("q", "headphones")
    max_depth = int(request.GET.get("depth", 0))
    limit = int(request.GET.get("limit", 20))

    keyword_stripped = keyword_raw.strip()
    # ensure Keyword exists (same behavior as your old endpoint)
    keyword_obj, _created = Keyword.objects.get_or_create(word=keyword_stripped)

    # try to serialize keyword (fallback minimal if serializer fails)
    try:
        keyword_serialized = KeywordSerializer(keyword_obj).data
    except Exception:
        keyword_serialized = {"id": keyword_obj.id, "word": getattr(keyword_obj, "word", keyword_stripped)}

    def parse_to_dict(data, depth=0):
        if not data or not data.get("url"):
            return None
        node = {
            "url": data["url"],
            "title": data.get("title"),
            "depth": depth,
            "children": []
        }
        for child in data.get("children", []):
            child_node = parse_to_dict(child, depth=depth + 1)
            if child_node:
                node["children"].append(child_node)
        return node

    def event_stream():
        # 1) Send a meta event first so clients have immediate keyword context
        meta_payload = {"keyword": keyword_serialized}
        yield f"event: meta\ndata: {json.dumps(meta_payload)}\n\n"

        # 2) Stream nodes as before, but include keyword_id in each payload
        idx = 0
        expected_total = limit
        for href in scrape_search_results_stream(keyword_stripped, num_results=limit):
            idx += 1
            try:
                parsed_data = parse_page(href, current_depth=0, max_depth=max_depth)
                node = parse_to_dict(parsed_data)
            except Exception as e:
                node = {"url": href, "title": None, "depth": 0, "children": []}
                # optional server-side log
                print("parse_page error for", href, e)

            payload = {
                "keyword_id": keyword_obj.id,
                "node": node,
                "progress": {"current": idx, "total": expected_total}
            }
            yield f"data: {json.dumps(payload)}\n\n"
            # slight throttle for smoother frontend rendering
            time.sleep(0.02)

        # 3) Final done event includes final counts + keyword_id
        done_payload = {"message": "Streaming complete", "total_received": idx, "keyword_id": keyword_obj.id}
        yield f"event: done\ndata: {json.dumps(done_payload)}\n\n"

    response = StreamingHttpResponse(event_stream(), content_type="text/event-stream")
    # recommended headers to reduce buffering (important behind nginx)
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response


# @csrf_exempt
# @require_GET
# def search_and_parse(request):
#     keyword = request.GET.get("q", "headphones")
#     max_depth = int(request.GET.get("depth", 0))
#     limit = int(request.GET.get("limit", 20))

#     def parse_to_dict(data, depth=0):
#         if not data.get("url"):
#             return None
#         node = {
#             "url": data["url"],
#             "title": data.get("title"),
#             "depth": depth,
#             "children": []
#         }
#         for child in data.get("children", []):
#             child_node = parse_to_dict(child, depth=depth + 1)
#             if child_node:
#                 node["children"].append(child_node)
#         return node

#     def event_stream():
#         # ⬇️ You can replace this with your real scraping logic
#         links = scrape_search_results(keyword, num_results=limit)
#         total_links = len(links)

#         for idx, link in enumerate(links, 1):
#             parsed = parse_page(link, 0, max_depth)
#             node = parse_to_dict(parsed)
#             if node:
#                 payload = {
#                     "node": node,
#                     "progress": {"current": idx, "total": total_links}
#                 }
#                 yield f"data: {json.dumps(payload)}\n\n"
#             time.sleep(0.05)

#         # Signal end of stream
#         yield "event: done\ndata: {\"message\": \"Streaming complete\"}\n\n"

#     response = StreamingHttpResponse(event_stream(), content_type="text/event-stream")
#     response["Cache-Control"] = "no-cache"
#     return response
    
    
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def bulk_keywords_search(request):
    """
    Handle bulk keyword search from uploaded .txt file.
    Each line in the file is treated as one keyword.
    """
    keywords_file = request.FILES.get('keywords_file')
    print('keywords_file: ', keywords_file)
    if not keywords_file:
        return Response({"detail": "No file uploaded"}, status=400)

    # Default params
    max_depth = 0  # always 0 for bulk
    num_results = int(request.GET.get("bulk_limit", 20))

    # Read file lines into keywords
    try:
        keywords = [line.strip() for line in keywords_file.read().decode('utf-8').splitlines() if line.strip()]
    except Exception:
        return Response({"detail": "Could not read file. Ensure it's a valid .txt file."}, status=400)

    all_results = []

    for keyword_raw in keywords:
        keyword_stripped = keyword_raw.strip()
        keyword_obj, _ = Keyword.objects.get_or_create(word=keyword_stripped)

        # Scrape search results (DuckDuckGo)
        links = scrape_search_results(keyword_stripped, num_results=num_results)

        results = []

        def parse_to_dict(data, depth=0):
            if not data.get("url"):
                return None
            node = {
                "url": data["url"],
                "title": data.get("title"),
                "depth": depth,
                "children": []
            }
            for child in data.get("children", []):
                child_node = parse_to_dict(child, depth=depth + 1)
                if child_node:
                    node["children"].append(child_node)
            return node

        # No recursive depth, just top links
        for link in links:
            parsed_data = parse_page(link, current_depth=0, max_depth=max_depth)
            node = parse_to_dict(parsed_data)
            if node:
                results.append(node)

        all_results.append({
            "keyword": KeywordSerializer(keyword_obj).data,
            "results": results
        })

    return Response({
        "keywords": all_results,
        "count": len(all_results)
    }, status=200)
    



@api_view(['POST'])
@permission_classes([IsAuthenticated])
def save_keyword_results(request):
    """
    Save only user-selected results.
    Ensures parent links are also saved if a child is selected.
    """
    items = request.data.get("items", [])
    keyword_id = request.data.get("keyword_id")
    folder_id = request.data.get("folder_id")

    if not items or not keyword_id:
        return Response({"error": "Missing items or keyword_id"}, status=400)

    try:
        keyword = Keyword.objects.get(id=keyword_id)
    except Keyword.DoesNotExist:
        return Response({"error": "Invalid keyword"}, status=404)

    project_id = request.data.get("project_id")
    if not project_id:
        return Response({"error": "Project must be provided"}, status=400)

    project = Project.objects.filter(id=project_id, user=request.user).first()
    if not project:
        return Response({"error": "Invalid project"}, status=400)

    # Auto-create folder for this keyword under the project
    folder, _ = ProjectFolder.objects.get_or_create(
        project=project,
        name=keyword.word,
        defaults={"description": f"Folder for keyword {keyword.word}"}
    )
    
    # Assign folder to keyword if not already assigned
    if keyword.folder != folder:
        keyword.folder = folder
        keyword.save()

    saved_nodes = []

    def save_node(node, parent=None, depth=0):
        url = node.get("url")
        title = node.get("title")

        # Find parent object by parentUrl
        if node.get("parentUrl"):
            parent = SearchResultLink.objects.filter(url=node["parentUrl"], keyword=keyword).first()

        obj, created = SearchResultLink.objects.get_or_create(
            keyword=keyword,
            folder=folder,
            url=url,
            defaults={"parent": parent, "depth": depth, "user": request.user, "title": title},
        )

        if created:
            saved_nodes.append(obj.id)  # only count new saves

        for child in node.get("children", []):
            save_node(child, parent=obj, depth=depth+1)

    for item in items:
        save_node(item)

    return Response({"message": f"Saved {len(saved_nodes)} items", "ids": saved_nodes})
    
    
@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
@csrf_exempt
def projects(request):
    if request.method == 'GET':
        qs = Project.objects.all().order_by('-created_at')  # later filter by user
        return Response(ProjectSerializer(qs, many=True).data)

    # POST create
    name = (request.data.get('name') or '').strip()
    description = request.data.get('description') or ''
    if not name:
        return Response({"error": "Project name is required"}, status=400)

    user = request.user if request.user.is_authenticated else None
    project = Project.objects.create(name=name, description=description, user=user)
    return Response(ProjectSerializer(project).data, status=201)


@api_view(['GET'])
@permission_classes([AllowAny])
def project_detail(request, pk):
    try:
        project = Project.objects.get(pk=pk)
    except Project.DoesNotExist:
        return Response({"error": "Not found"}, status=404)
    return Response(ProjectSerializer(project).data)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def delete_projects(request):
    ids = request.data.get("ids", [])
    
    print('All the project ids to be deleted: ', ids)

    if not isinstance(ids, list) or not ids:
        return Response(
            {"detail": "Please provide a list of project IDs."},
            status=status.HTTP_400_BAD_REQUEST
        )

    # Delete only projects belonging to the current user
    deleted_count, _ = Project.objects.filter(id__in=ids, user=request.user).delete()

    return Response(
        {"detail": f"{deleted_count} project(s) deleted successfully."},
        status=status.HTTP_200_OK
    )



# Update custom name for a link
@api_view(['POST'])
@permission_classes([AllowAny])
def update_link_name(request, pk):
    """Assign a custom name to a saved link"""
    result = get_object_or_404(SearchResultLink, pk=pk)
    name = request.data.get("name")

    if not name:
        return Response({"error": "Name is required"}, status=status.HTTP_400_BAD_REQUEST)

    result.name = name
    result.save()

    return Response({"id": result.id, "url": result.url, "name": result.name}, status=status.HTTP_200_OK)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def list_projects(request):
    """Return all projects for the logged-in user."""
    projects = Project.objects.filter(user=request.user).order_by("-created_at")
    # projects = Project.objects.all().order_by("-created_at")
    serializer = ProjectSerializer(projects, many=True)
    return Response(serializer.data)


@api_view(["GET"])
@permission_classes([AllowAny])
def list_project_folders(request, project_id):
    """Return all folders for a given project."""
    folders = ProjectFolder.objects.filter(project__id=project_id, project__user=request.user)
    serializer = ProjectFolderSerializer(folders, many=True)
    return Response(serializer.data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def user_projects(request):
    """
    Return all projects of the logged-in user with their folders.
    """
    projects = Project.objects.filter(user=request.user).prefetch_related("folders")
    serializer = ProjectSerializer(projects, many=True)
    return Response(serializer.data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def project_folders(request, project_id):
    try:
        project = Project.objects.get(id=project_id, user=request.user)
    except Project.DoesNotExist:
        return Response({"detail": "Project not found"}, status=404)

    folders = project.folders.all()
    serializer = ProjectFolderSerializer(folders, many=True)
    return Response(serializer.data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def folder_details(request, folder_id):
    # 1. Get folder
    folder = ProjectFolder.objects.filter(id=folder_id, project__user=request.user).first()
    print('folder: ', folder)
    if not folder:
        return Response({"error": "Folder not found"}, status=404)

    # 2. Get last keyword associated with this folder
    keyword = folder.keywords.order_by('-created_at').first()
    print('keyword: ', keyword)
    if not keyword:
        return Response({"keyword": None, "results": []})

    # 3. Fetch all SearchResultLink objects for this keyword and folder
    def build_hierarchy(node_queryset, parent=None):
        nodes = []
        children_qs = node_queryset.filter(parent=parent).order_by('id')
        for node in children_qs:
            nodes.append({
                "id": node.id,
                "url": node.url,
                "title": node.title,
                "children": build_hierarchy(node_queryset, parent=node)
            })
        return nodes

    all_results = SearchResultLink.objects.filter(keyword=keyword, folder=folder)
    hierarchy = build_hierarchy(all_results)

    return Response({
        "folder": {"id": folder.id, "name": folder.name},
        "keyword": {"id": keyword.id, "word": keyword.word},
        "results": hierarchy
    })
    

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def keywords_list(request):
    # Get all projects for the current user
    projects = Project.objects.filter(user=request.user)

    # Get all folders across those projects
    folders = ProjectFolder.objects.filter(project__in=projects)

    serializer = ProjectFolderSerializer(folders, many=True)
    return Response(serializer.data)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def delete_folders(request):
    ids = request.data.get("ids", [])

    print("All the folder ids to be deleted:", ids)

    if not isinstance(ids, list) or not ids:
        return Response(
            {"detail": "Please provide a list of folder IDs."},
            status=status.HTTP_400_BAD_REQUEST
        )

    # Delete only folders belonging to projects of the current user
    deleted_count, _ = ProjectFolder.objects.filter(
        id__in=ids,
        project__user=request.user
    ).delete()
    
    print(f"{deleted_count} folder(s) deleted successfully.")

    return Response(
        {
            "detail": f"{deleted_count} folder(s) deleted successfully.",
            
        },
        status=status.HTTP_200_OK
    )
    

@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def delete_project_folders(request):
    ids = request.data.get("ids", [])
    project_id = request.data.get('project_id', '')

    print("All the folder ids to be deleted:", ids)

    if not isinstance(ids, list) or not ids:
        return Response(
            {"detail": "Please provide a list of folder IDs."},
            status=status.HTTP_400_BAD_REQUEST
        )

    # Delete only folders belonging to projects of the current user
    folders_to_delete = ProjectFolder.objects.filter(
        id__in=ids,
        project__user=request.user
    )

    num_folders = folders_to_delete.count()  # ✅ count only folders
    folders_to_delete.delete()
        
    print(f"{num_folders} folder(s) deleted successfully.")

    return Response(
        {
            "detail": f"{num_folders} folder(s) deleted successfully.",
            "project_id": project_id
        },
        status=status.HTTP_200_OK
    )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def delete_folder_results(request, folder_id):
    """
    Delete selected SearchResultLink(s).
    - If parent is selected: delete parent + all its descendants.
    - If only children selected: delete just those.
    """
    folder = ProjectFolder.objects.filter(id=folder_id, project__user=request.user).first()
    if not folder:
        return Response({"error": "Folder not found"}, status=status.HTTP_404_NOT_FOUND)

    ids_to_delete = request.data.get("ids", [])
    if not ids_to_delete:
        return Response({"error": "No IDs provided"}, status=status.HTTP_400_BAD_REQUEST)

    # Get only results belonging to this folder
    qs = SearchResultLink.objects.filter(folder=folder)

    deleted_ids = []

    def delete_with_children(node):
        nonlocal deleted_ids
        children = qs.filter(parent=node)
        for child in children:
            delete_with_children(child)
        deleted_ids.append(node.id)
        node.delete()

    for id_ in ids_to_delete:
        try:
            link = qs.get(id=id_)
        except SearchResultLink.DoesNotExist:
            continue
        delete_with_children(link)

    return Response({"deleted": deleted_ids}, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def upload_keywords(request):
    """
    Handle keywords file upload
    """
    if 'keywords_file' not in request.FILES:
        return Response(
            {"detail": "No file provided"},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    file = request.FILES['keywords_file']
    
    # Validate file type
    if not file.name.endswith('.txt'):
        return Response(
            {"detail": "Only .txt files are allowed"},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        # Read and process the file
        content = file.read().decode('utf-8')
        keywords = [line.strip() for line in content.split('\n') if line.strip()]
        
        # Here you can save the keywords to your database
        # Example: save_keywords_to_db(request.user, keywords)
        
        return Response({
            "detail": f"Successfully processed {len(keywords)} keywords",
            "count": len(keywords)
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response(
            {"detail": f"Error processing file: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
