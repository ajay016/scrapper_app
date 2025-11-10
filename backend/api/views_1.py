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
from django.core.exceptions import MultipleObjectsReturned
from django.db import transaction
from django.db.utils import IntegrityError
from bs4 import BeautifulSoup
import traceback
import logging
import json
import time
from django.shortcuts import get_object_or_404
from urllib.parse import urljoin, urlparse
import requests
from .utils.parser import parse_page, save_page_hierarchy
from .serializers import *
from .models import *
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
import json
import time
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
import re
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
import threading
from collections import deque
import uuid
import logging
from .utils.search_engine_scrappers import(
    scrape_bing_results,
    scrape_duckduckgo_results
)










logger = logging.getLogger(__name__)

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def current_user(request):
    serializer = UserSerializer(request.user)
    print('serializer.data: ', serializer.data)
    return Response(serializer.data)


# ---------- SSE streaming view with fallback ----------
@csrf_exempt
@require_GET
def search_and_parse_stream(request):
    keyword_raw = request.GET.get("q", "headphones")
    engine = request.GET.get("engine", "bing").lower()
    max_depth = int(request.GET.get("depth", 0))
    
    # limit = int(request.GET.get("limit", 20))
    limit_raw = request.GET.get("limit", "").strip()
    limit = int(limit_raw) if limit_raw.isdigit() else 0

    keyword_stripped = keyword_raw.strip()
    keyword_obj, _ = Keyword.objects.get_or_create(word=keyword_stripped)

    try:
        keyword_serialized = KeywordSerializer(keyword_obj).data
    except Exception:
        keyword_serialized = {"id": keyword_obj.id, "word": keyword_obj.word}

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
            child_node = parse_to_dict(child, depth + 1)
            if child_node:
                node["children"].append(child_node)
        return node

    def event_stream():
        # meta info first
        meta_payload = {"keyword": keyword_serialized}
        yield f"event: meta\ndata: {json.dumps(meta_payload)}\n\n"

        # pick search generator
        generator = scrape_bing_results(keyword_stripped, num_results=limit) if engine == "bing" else scrape_duckduckgo_results(keyword_stripped, num_results=limit)

        # collect results with auto-fallback
        results_found = False
        idx = 0
        for href in generator:
            results_found = True
            idx += 1
            try:
                parsed_data = parse_page(href, current_depth=0, max_depth=max_depth)
                node = parse_to_dict(parsed_data)
            except Exception as e:
                print("parse_page error for", href, e)
                node = {"url": href, "title": None, "depth": 0, "children": []}

            payload = {
                "keyword_id": keyword_obj.id,
                "node": node,
                "progress": {"current": idx, "total": limit or None}
            }
            yield f"data: {json.dumps(payload)}\n\n"
            time.sleep(0.02)

        # if Bing failed — retry with DuckDuckGo
        if not results_found and engine == "bing":
            print("⚠️ No Bing results found. Switching to DuckDuckGo fallback.")
            for href in scrape_duckduckgo_results(keyword_stripped, num_results=limit):
                idx += 1
                try:
                    parsed_data = parse_page(href, current_depth=0, max_depth=max_depth)
                    node = parse_to_dict(parsed_data)
                except Exception as e:
                    print("parse_page error for", href, e)
                    node = {"url": href, "title": None, "depth": 0, "children": []}

                payload = {
                    "keyword_id": keyword_obj.id,
                    "node": node,
                    "progress": {"current": idx, "total": limit or None}
                }
                yield f"data: {json.dumps(payload)}\n\n"
                time.sleep(0.02)

        done_payload = {"message": "Streaming complete", "total_received": idx, "keyword_id": keyword_obj.id}
        yield f"event: done\ndata: {json.dumps(done_payload)}\n\n"

    response = StreamingHttpResponse(event_stream(), content_type="text/event-stream")
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
def bulk_keywords_search_stream(request):
    """
    Streamed bulk keyword search (SSE).
    Reads .txt file line-by-line and streams Bing/DuckDuckGo results.
    """

    keywords_file = request.FILES.get('keywords_file')
    if not keywords_file:
        return Response({"detail": "No file uploaded"}, status=400)

    try:
        keywords = [line.strip() for line in keywords_file.read().decode('utf-8').splitlines() if line.strip()]
    except Exception:
        return Response({"detail": "Could not read file. Ensure it's a valid .txt file."}, status=400)

    max_depth = 0
    num_results = int(request.GET.get("bulk_limit", 20))
    print('num_results: ', num_results)

    def event_stream():
        total_keywords = len(keywords)
        yield f"event: meta\ndata: {json.dumps({'total_keywords': total_keywords})}\n\n"

        for idx, keyword_raw in enumerate(keywords, start=1):
            keyword_stripped = keyword_raw.strip()
            keyword_obj, _ = Keyword.objects.get_or_create(word=keyword_stripped)
            keyword_serialized = KeywordSerializer(keyword_obj).data
            
            print('bulk keyword: ', keyword_obj)

            yield f"event: keyword_start\ndata: {json.dumps({'keyword': keyword_serialized, 'index': idx})}\n\n"

            # --- Try Bing first ---
            try:
                generator = scrape_bing_results(keyword_stripped, num_results)
                links = list(generator)
            except Exception as e:
                print(f"[WARN] Bing failed for '{keyword_stripped}': {e}")
                links = []

            used_engine = "bing"

            # If Bing failed or returned no links → fallback
            if not links:
                print(f"[INFO] Fallback to DuckDuckGo for '{keyword_stripped}'")
                used_engine = "duckduckgo"
                links = list(scrape_duckduckgo_results(keyword_stripped, num_results))

            results = []
            for link in links:
                try:
                    parsed_data = parse_page(link, current_depth=0, max_depth=max_depth)
                    node = {
                        "url": parsed_data.get("url"),
                        "title": parsed_data.get("title"),
                        "depth": 0,
                        "children": []
                    }
                except Exception as e:
                    node = {"url": link, "title": None, "depth": 0, "children": []}
                    print("parse_page error:", e)

                results.append(node)
                payload = {
                    "keyword": keyword_serialized,
                    "engine": used_engine,
                    "progress": {"current": len(results), "total": num_results},
                    "node": node,
                }
                yield f"data: {json.dumps(payload)}\n\n"
                time.sleep(0.05)

            done_payload = {
                "keyword": keyword_serialized,
                "total_results": len(results),
                "engine_used": used_engine,
            }
            print('bulk keyword payload: ', done_payload)
            yield f"event: keyword_done\ndata: {json.dumps(done_payload)}\n\n"

        yield f"event: done\ndata: {json.dumps({'message': 'Bulk streaming complete'})}\n\n"

    response = StreamingHttpResponse(event_stream(), content_type="text/event-stream")
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response
    



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


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def save_bulk_keyword_results(request):
    """
    Save bulk keyword search results with multiple keywords.
    This version:
      - Validates inputs early
      - Runs inside a transaction so partial saves rollback on error
      - Avoids get_or_create() `MultipleObjectsReturned` by using filter().first()
      - Handles and returns a proper error message if anything goes wrong
    """
    bulk_data = request.data.get("bulk_data")
    keyword_results = request.data.get("keyword_results", [])
    folder_id = request.data.get("folder_id")
    project_id = request.data.get("project_id")
    
    print('bulk_data: ', bool(bulk_data))
    print('keyword_results length: ', len(keyword_results))
    print('project_id: ', project_id)
    print('folder_id: ', folder_id)

    if not bulk_data or not keyword_results:
        return Response({"error": "Missing bulk_data or keyword_results"}, status=400)

    if not project_id:
        return Response({"error": "Project must be provided"}, status=400)

    project = Project.objects.filter(id=project_id, user=request.user).first()
    if not project:
        return Response({"error": "Invalid project"}, status=400)

    total_saved = 0
    keyword_stats = []

    def save_node(node, keyword_obj, folder_obj, parent=None, depth=0):
        """
        Save a single node and its children.
        Uses filter().first() to avoid MultipleObjectsReturned.
        Returns number of newly created rows for this subtree.
        """
        url = node.get("url")
        title = node.get("title") or ""

        # Find parent object by parentUrl (if provided)
        if node.get("parentUrl"):
            parent = SearchResultLink.objects.filter(url=node["parentUrl"], keyword=keyword_obj).first()

        # Use filter().first() to avoid MultipleObjectsReturned
        existing = SearchResultLink.objects.filter(keyword=keyword_obj, folder=folder_obj, url=url).first()
        if existing:
            obj = existing
            created = False
        else:
            obj = SearchResultLink.objects.create(
                keyword=keyword_obj,
                folder=folder_obj,
                url=url,
                parent=parent,
                depth=depth,
                user=request.user,
                title=title
            )
            created = True

        saved = 1 if created else 0

        # Recursively save children
        for child in node.get("children", []):
            saved += save_node(child, keyword_obj, folder_obj, parent=obj, depth=depth+1)

        return saved

    # Run all saves inside a transaction so we rollback on exceptions
    try:
        with transaction.atomic():
            for keyword_data in keyword_results:
                keyword_id = keyword_data.get("keyword_id")
                keyword_name = keyword_data.get("keyword")
                items = keyword_data.get("items", [])

                if not keyword_id and not keyword_name:
                    continue

                try:
                    if keyword_id:
                        keyword_obj = Keyword.objects.get(id=keyword_id)
                    else:
                        keyword_obj, _ = Keyword.objects.get_or_create(word=keyword_name)
                except Keyword.DoesNotExist:
                    # Skip invalid keyword
                    continue

                # Auto-create folder for this keyword under the project
                folder_obj, _ = ProjectFolder.objects.get_or_create(
                    project=project,
                    name=keyword_obj.word,
                    defaults={"description": f"Folder for keyword {keyword_obj.word}"}
                )

                # Assign folder to keyword if not already assigned
                if keyword_obj.folder != folder_obj:
                    keyword_obj.folder = folder_obj
                    keyword_obj.save()

                keyword_saved = 0

                # Save all items for this keyword
                for item in items:
                    keyword_saved += save_node(item, keyword_obj, folder_obj)

                total_saved += keyword_saved
                keyword_stats.append({
                    "keyword": keyword_obj.word,
                    "keyword_id": keyword_obj.id,
                    "saved_count": keyword_saved
                })

    except MultipleObjectsReturned as e:
        # Defensive: if duplicates are found elsewhere, present a clear error and rollback
        return Response({"error": "Duplicate search result entries detected in DB. Please contact admin."}, status=500)
    except IntegrityError as e:
        # DB integrity issues (unique constraints, etc.)
        return Response({"error": "Database integrity error while saving results."}, status=500)
    except Exception as e:
        # Generic fallback with rollback
        return Response({"error": f"Unexpected error: {str(e)}"}, status=500)

    return Response({
        "message": f"Saved {total_saved} items across {len(keyword_stats)} keywords",
        "total_saved": total_saved,
        "keyword_stats": keyword_stats
    })
    
    
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

# Set up logging
logger = logging.getLogger(__name__)

# In-memory storage for real-time updates
crawler_sessions = {}

class URLCrawler:
    def __init__(self, session_id, base_url, max_depth=2, use_selenium=False):
        self.session_id = session_id
        self.base_url = base_url
        self.max_depth = max_depth
        self.visited_urls = set()
        self.found_links = []
        self.driver = None
        self.is_running = True
        self.base_domain = urlparse(base_url).netloc
        self.use_selenium = use_selenium
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
        # Track all unique URLs to avoid duplicates
        self.all_unique_urls = set()
        
    def get_driver(self):
        """Initialize Selenium driver only when needed"""
        if self.driver:
            return self.driver
            
        try:
            chrome_options = Options()
            chrome_options.add_argument("--headless")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument("--window-size=1920,1080")
            chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
            
            self.driver = webdriver.Chrome(options=chrome_options)
            return self.driver
        except Exception as e:
            logger.error(f"Failed to initialize Selenium driver: {e}")
            return None
        
    def close_driver(self):
        """Close Selenium driver if it exists"""
        if self.driver:
            try:
                self.driver.quit()
            except:
                pass
            self.driver = None
            
    def crawl(self):
        """Main crawling function using BFS algorithm - unlimited pages"""
        try:
            # Initialize session in crawler_sessions if not exists
            if self.session_id not in crawler_sessions:
                crawler_sessions[self.session_id] = {
                    'crawler': self,
                    'results': [],
                    'started_at': time.time(),
                    'status': 'running',
                    'stats': {
                        'total_found': 0,
                        'pages_crawled': 0,
                        'beautifulsoup_success': 0,
                        'selenium_fallback': 0,
                        'errors': 0,
                        'duplicates_skipped': 0
                    }
                }
            
            queue = deque([(self.base_url, 0)])
            
            while queue and self.is_running:
                url, depth = queue.popleft()
                
                if url in self.visited_urls or depth > self.max_depth:
                    continue
                    
                self.visited_urls.add(url)
                
                # Process the current URL
                new_links = self.process_page(url, depth)
                
                # Add new links to queue if within depth limit
                if depth < self.max_depth:
                    for link in new_links:
                        if link['is_internal'] and link['url'] not in self.visited_urls:
                            queue.append((link['url'], depth + 1))
                            
                # Small delay to be respectful to the server
                time.sleep(0.1)
                
                # Send progress update every 10 pages
                if len(self.visited_urls) % 10 == 0:
                    self.add_result({
                        'type': 'progress',
                        'visited': len(self.visited_urls),
                        'found': len(self.found_links),
                        'queued': len(queue),
                        'message': f'Progress: {len(self.visited_urls)} pages visited, {len(self.found_links)} links found, {len(queue)} in queue'
                    })
                            
        except Exception as e:
            logger.error(f"Crawling error: {e}")
            self.add_result({
                'type': 'error',
                'message': f'Crawling error: {str(e)}'
            })
        finally:
            self.close_driver()
            # Update session status
            if self.session_id in crawler_sessions:
                crawler_sessions[self.session_id]['status'] = 'completed'
            
            self.add_result({
                'type': 'complete',
                'message': f'Crawling completed. Visited {len(self.visited_urls)} pages and found {len(self.found_links)} unique links.',
                'total_links': len(self.found_links),
                'total_pages': len(self.visited_urls)
            })
            
    def process_page(self, url, depth):
        """Process a single page and extract links - try BeautifulSoup first"""
        new_links = []
        
        try:
            # Notify start of page processing
            self.add_result({
                'type': 'processing',
                'url': url,
                'depth': depth,
                'message': f'Processing page (depth {depth})'
            })
            
            # Update stats
            if self.session_id in crawler_sessions:
                crawler_sessions[self.session_id]['stats']['pages_crawled'] += 1
            
            # Try with BeautifulSoup first (faster)
            links = self.process_with_beautifulsoup(url, depth)
            
            # If no links found with BeautifulSoup, try with Selenium
            if not links and self.use_selenium:
                links = self.process_with_selenium(url, depth)
                
            for link in links:
                # Check if URL is already in our global unique set
                if link['url'] in self.all_unique_urls:
                    # Skip duplicate URL
                    if self.session_id in crawler_sessions:
                        crawler_sessions[self.session_id]['stats']['duplicates_skipped'] += 1
                    continue
                
                # Add to global unique URLs set
                self.all_unique_urls.add(link['url'])
                
                link['depth'] = depth
                link['found_at'] = time.time()
                self.found_links.append(link)
                new_links.append(link)
                
                # Update stats
                if self.session_id in crawler_sessions:
                    crawler_sessions[self.session_id]['stats']['total_found'] += 1
                
                # Send real-time update
                self.add_result({
                    'type': 'link_found',
                    'link': link,
                    'total_found': len(self.found_links),
                    'total_visited': len(self.visited_urls)
                })
                    
        except Exception as e:
            logger.error(f"Error processing page {url}: {e}")
            if self.session_id in crawler_sessions:
                crawler_sessions[self.session_id]['stats']['errors'] += 1
                
            self.add_result({
                'type': 'error',
                'url': url,
                'message': f'Error processing {url}: {str(e)}'
            })
            
        return new_links
        
    def process_with_beautifulsoup(self, url, depth):
        """Process page using BeautifulSoup (fast method)"""
        try:
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            links = self.extract_links(soup, url)
            
            # Update stats
            if self.session_id in crawler_sessions:
                crawler_sessions[self.session_id]['stats']['beautifulsoup_success'] += 1
            
            self.add_result({
                'type': 'info',
                'url': url,
                'message': f'Found {len(links)} links with BeautifulSoup'
            })
            
            return links
            
        except Exception as e:
            self.add_result({
                'type': 'warning',
                'url': url,
                'message': f'BeautifulSoup failed for {url}: {str(e)}'
            })
            return []
            
    def process_with_selenium(self, url, depth):
        """Process page using Selenium (for JavaScript-heavy pages)"""
        driver = self.get_driver()
        if not driver:
            return []
            
        links = []
        
        try:
            driver.get(url)
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            
            # Scroll to load lazy content
            self.scroll_page(driver)
            
            # Extract links
            page_source = driver.page_source
            soup = BeautifulSoup(page_source, 'html.parser')
            links = self.extract_links(soup, url)
            
            # Update stats
            if self.session_id in crawler_sessions:
                crawler_sessions[self.session_id]['stats']['selenium_fallback'] += 1
            
            self.add_result({
                'type': 'info',
                'url': url,
                'message': f'Found {len(links)} links with Selenium'
            })
            
        except Exception as e:
            self.add_result({
                'type': 'error',
                'url': url,
                'message': f'Selenium failed for {url}: {str(e)}'
            })
            
        return links
        
    def scroll_page(self, driver):
        """Scroll page to load lazy content"""
        try:
            last_height = driver.execute_script("return document.body.scrollHeight")
            
            for _ in range(2):  # Reduced scroll attempts for speed
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(0.3)
                new_height = driver.execute_script("return document.body.scrollHeight")
                if new_height == last_height:
                    break
                last_height = new_height
        except:
            pass
            
    def extract_links(self, soup, base_url):
        """Extract all links from BeautifulSoup object - remove duplicates at extraction level too"""
        links = []
        base_domain = urlparse(base_url).netloc
        
        # Use a set to track URLs found on this page to avoid duplicates
        page_seen_urls = set()
        
        for a_tag in soup.find_all('a', href=True):
            try:
                href = a_tag['href'].strip()
                if not href:
                    continue
                    
                full_url = urljoin(base_url, href)
                
                # Skip invalid URLs
                if not full_url or full_url.startswith(('javascript:', 'mailto:', 'tel:', '#')):
                    continue
                    
                # Normalize URL
                parsed_url = urlparse(full_url)
                normalized_url = f"{parsed_url.scheme}://{parsed_url.netloc}{parsed_url.path}"
                if parsed_url.query:
                    normalized_url += f"?{parsed_url.query}"
                
                # Skip if we've already seen this URL on current page
                if normalized_url in page_seen_urls:
                    continue
                    
                page_seen_urls.add(normalized_url)
                
                # Determine if link is internal
                is_internal = parsed_url.netloc == self.base_domain
                
                # Extract link text
                link_text = a_tag.get_text(strip=True)
                if not link_text:
                    link_text = a_tag.get('title', '') or normalized_url
                
                # Skip very long text
                link_text = link_text[:200]
                
                links.append({
                    'url': normalized_url,
                    'text': link_text,
                    'is_internal': is_internal,
                    'is_external': not is_internal,
                    'source_url': base_url
                })
                
            except Exception as e:
                continue
                
        return links
        
    def add_result(self, result):
        """Add result to session storage"""
        if self.session_id in crawler_sessions:
            crawler_sessions[self.session_id]['results'].append(result)
            
    def stop(self):
        """Stop the crawler"""
        self.is_running = False
        self.close_driver()
        if self.session_id in crawler_sessions:
            crawler_sessions[self.session_id]['status'] = 'stopped'

# Session cleanup function
def cleanup_old_sessions():
    """Remove sessions older than 1 hour"""
    current_time = time.time()
    sessions_to_remove = []
    
    for session_id, session_data in crawler_sessions.items():
        if current_time - session_data['started_at'] > 3600:  # 1 hour
            sessions_to_remove.append(session_id)
    
    for session_id in sessions_to_remove:
        if session_id in crawler_sessions:
            crawler_sessions.pop(session_id)

@require_http_methods(["POST"])
@csrf_exempt
def start_url_crawl(request):
    """Start a new URL crawling session - unlimited pages"""
    try:
        # Clean up old sessions first
        cleanup_old_sessions()
        
        data = json.loads(request.body)
        url = data.get('url', '').strip()
        max_depth = int(data.get('max_depth', 2))
        use_selenium = data.get('use_selenium', False)
        
        if not url:
            return JsonResponse({'error': 'URL is required'}, status=400)
            
        # Validate URL
        try:
            parsed = urlparse(url)
            if not parsed.scheme or not parsed.netloc:
                return JsonResponse({'error': 'Invalid URL format'}, status=400)
        except:
            return JsonResponse({'error': 'Invalid URL format'}, status=400)
            
        # Generate session ID
        session_id = str(uuid.uuid4())
        
        # Initialize crawler session
        crawler_sessions[session_id] = {
            'crawler': None,
            'results': [],
            'started_at': time.time(),
            'status': 'starting',
            'stats': {
                'total_found': 0,
                'pages_crawled': 0,
                'beautifulsoup_success': 0,
                'selenium_fallback': 0,
                'errors': 0,
                'duplicates_skipped': 0
            }
        }
        
        # Start crawler in separate thread - NO PAGE LIMIT
        crawler = URLCrawler(session_id, url, max_depth, use_selenium)
        crawler_sessions[session_id]['crawler'] = crawler
        crawler_sessions[session_id]['status'] = 'running'
        
        thread = threading.Thread(target=crawler.crawl)
        thread.daemon = True
        thread.start()
        
        logger.info(f"Started unlimited crawling session {session_id} for URL: {url}")
        
        return JsonResponse({
            'success': True,
            'session_id': session_id,
            'message': 'Unlimited crawling started - will continue until all links are found or stopped manually',
            'max_depth': max_depth,
            'unlimited': True
        })
        
    except Exception as e:
        logger.error(f"Failed to start crawling: {e}")
        return JsonResponse({'error': f'Failed to start crawling: {str(e)}'}, status=500)

@require_http_methods(["GET"])
def get_crawl_results(request):
    """Get real-time crawling results for a session"""
    # Clean up old sessions first
    cleanup_old_sessions()
    
    session_id = request.GET.get('session_id')
    
    if not session_id:
        return JsonResponse({'error': 'Session ID is required'}, status=400)
        
    if session_id not in crawler_sessions:
        return JsonResponse({'error': 'Invalid session ID or session expired'}, status=404)
        
    session = crawler_sessions[session_id]
    
    # Get new results and clear them from session
    results = session['results'].copy()
    session['results'] = []
    
    return JsonResponse({
        'results': results,
        'status': session['status'],
        'stats': session['stats'],
        'total_results': len(results)
    })

@require_http_methods(["GET"])
def get_crawl_status(request):
    """Get current crawling status"""
    # Clean up old sessions first
    cleanup_old_sessions()
    
    session_id = request.GET.get('session_id')
    
    if not session_id:
        return JsonResponse({'error': 'Session ID is required'}, status=400)
        
    if session_id not in crawler_sessions:
        return JsonResponse({'error': 'Invalid session ID or session expired'}, status=404)
        
    session = crawler_sessions[session_id]
    
    return JsonResponse({
        'status': session['status'],
        'stats': session['stats'],
        'running_time': time.time() - session['started_at'],
        'session_exists': True
    })

@require_http_methods(["POST"])
@csrf_exempt
def stop_crawl(request):
    """Stop a crawling session"""
    try:
        data = json.loads(request.body)
        session_id = data.get('session_id')
        
        if not session_id:
            return JsonResponse({'error': 'Session ID is required'}, status=400)
            
        if session_id not in crawler_sessions:
            return JsonResponse({'error': 'Invalid session ID'}, status=404)
            
        session = crawler_sessions[session_id]
        if session['crawler']:
            session['crawler'].stop()
            session['status'] = 'stopped'
            
        logger.info(f"Stopped crawling session {session_id}")
            
        return JsonResponse({'success': True, 'message': 'Crawling stopped'})
        
    except Exception as e:
        logger.error(f"Failed to stop crawling: {e}")
        return JsonResponse({'error': f'Failed to stop crawling: {str(e)}'}, status=500)

@require_http_methods(["GET"])
def list_sessions(request):
    """List all active sessions (for debugging)"""
    cleanup_old_sessions()
    
    sessions_info = {}
    for session_id, session_data in crawler_sessions.items():
        sessions_info[session_id] = {
            'status': session_data['status'],
            'started_at': session_data['started_at'],
            'stats': session_data['stats'],
            'running_time': time.time() - session_data['started_at']
        }
    
    return JsonResponse({
        'active_sessions': len(crawler_sessions),
        'sessions': sessions_info
    })
    
# def search_url(request):
#     """Parse URL and extract all links with pagination support"""
#     url = request.GET.get('url', '').strip()
#     max_pages = int(request.GET.get('max_pages', 1))
#     max_depth = int(request.GET.get('max_depth', 0))
    
#     if not url:
#         return JsonResponse({'error': 'URL is required'}, status=400)
    
#     try:
#         # Parse the initial page
#         results = parse_url_with_pagination(url, max_pages, max_depth)
        
#         return JsonResponse({
#             'success': True,
#             'url': url,
#             'all_links': results,
#             'total_links': len(results)
#         })
        
#     except Exception as e:
#         return JsonResponse({'error': f'Failed to parse URL: {str(e)}'}, status=500)

# @csrf_exempt
# @require_http_methods(["POST"])
# def save_url_results(request):
#     """Save selected URL results to database project-wise"""
#     try:
#         data = json.loads(request.body)
#         items = data.get('items', [])
#         project_id = data.get('project_id')
#         folder_id = data.get('folder_id')
#         source_url = data.get('source_url')
#         search_name = data.get('search_name', f"URL Crawl - {source_url}")
        
#         if not items:
#             return JsonResponse({'error': 'No items to save'}, status=400)
        
#         if not project_id:
#             return JsonResponse({'error': 'Project ID is required'}, status=400)
        
#         # Import models
#         from django.db import transaction
#         from datetime import datetime
        
#         # Get or create project and folder
#         try:
#             project = Project.objects.get(id=project_id, user=request.user)
#             folder = None
#             if folder_id:
#                 folder = ProjectFolder.objects.get(id=folder_id, project=project)
#         except (Project.DoesNotExist, ProjectFolder.DoesNotExist):
#             return JsonResponse({'error': 'Invalid project or folder'}, status=400)
        
#         saved_count = 0
#         saved_urls = set()
        
#         with transaction.atomic():
#             # Create a new search job for this project
#             search_job = SearchJob.objects.create(
#                 user=request.user,
#                 project=project,  # Associate with project
#                 folder=folder,
#                 name=search_name,
#                 search_type="url_crawl",
#                 status="completed",
#                 total_results=len(items),
#                 metadata={
#                     'source_url': source_url,
#                     'crawled_at': datetime.now().isoformat(),
#                     'total_links_found': len(items)
#                 }
#             )
            
#             # Create search settings for this job
#             SearchSetting.objects.create(
#                 job=search_job,
#                 project=project,
#                 engines=["url_parser"],
#                 results_per_keyword=len(items),
#                 crawl_depth=0,
#                 crawl_entire_domain=False,
#                 search_url=source_url
#             )
            
#             # Create or get keyword for this search
#             keyword, created = Keyword.objects.get_or_create(
#                 user=request.user,
#                 project=project,  # Associate keyword with project
#                 folder=folder,
#                 word=f"url_crawl_{source_url}",
#                 defaults={
#                     'search_volume': len(items),
#                     'is_primary': False
#                 }
#             )
            
#             # Save each result
#             for item in items:
#                 try:
#                     url = item.get('url', '').strip()
#                     if not url or url in saved_urls:
#                         continue
                        
#                     saved_urls.add(url)
                    
#                     # Extract potential company name from URL or text
#                     name = extract_company_name(url, item.get('text', ''))
                    
#                     # Extract potential email and phone
#                     email, phone = extract_contact_info(url, item.get('text', ''))
                    
#                     # Create search result link
#                     SearchResultLink.objects.create(
#                         user=request.user,
#                         project=project,  # Associate with project
#                         folder=folder,
#                         job=search_job,
#                         keyword=keyword,
#                         url=url,
#                         title=item.get('text', '')[:500],
#                         name=name,
#                         email=email,
#                         phone_number=phone,
#                         domain=urlparse(url).netloc,
#                         is_internal=item.get('is_internal', False),
#                         is_external=item.get('is_external', False),
#                         depth=item.get('depth', 0),
#                         metadata={
#                             'source_url': source_url,
#                             'original_text': item.get('text', '')[:1000],
#                             'crawled_at': datetime.now().isoformat(),
#                             'link_depth': item.get('depth', 0)
#                         }
#                     )
#                     saved_count += 1
                    
#                 except Exception as e:
#                     print(f"Error saving item {item.get('url', 'unknown')}: {str(e)}")
#                     continue
        
#         # Update project stats
#         project.total_keywords = Keyword.objects.filter(project=project).count()
#         project.total_results = SearchResultLink.objects.filter(project=project).count()
#         project.last_activity = datetime.now()
#         project.save()
        
#         return JsonResponse({
#             'success': True,
#             'message': f'Successfully saved {saved_count} links to project "{project.name}"',
#             'saved_count': saved_count,
#             'project_id': project.id,
#             'project_name': project.name,
#             'job_id': search_job.id
#         })
        
#     except Exception as e:
#         return JsonResponse({'error': f'Failed to save results: {str(e)}'}, status=500)


@require_http_methods(["GET"])
def get_project_search_history(request):
    """Get search history for a specific project"""
    try:
        project_id = request.GET.get('project_id')
        
        if not project_id:
            return JsonResponse({'error': 'Project ID is required'}, status=400)
        
        project = Project.objects.get(id=project_id, user=request.user)
        
        # Get search jobs for this project
        search_jobs = SearchJob.objects.filter(
            project=project, 
            user=request.user
        ).order_by('-created_at')[:50]  # Last 50 searches
        
        search_history = []
        for job in search_jobs:
            search_history.append({
                'id': job.id,
                'name': job.name,
                'type': job.search_type,
                'created_at': job.created_at.isoformat(),
                'total_results': job.total_results,
                'status': job.status,
                'metadata': job.metadata or {}
            })
        
        return JsonResponse({
            'success': True,
            'project_id': project.id,
            'project_name': project.name,
            'search_history': search_history,
            'total_searches': len(search_history)
        })
        
    except Project.DoesNotExist:
        return JsonResponse({'error': 'Project not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': f'Failed to get search history: {str(e)}'}, status=500)


@require_http_methods(["GET"])
def get_project_results(request):
    """Get saved results for a specific project"""
    try:
        project_id = request.GET.get('project_id')
        page = int(request.GET.get('page', 1))
        per_page = int(request.GET.get('per_page', 20))
        
        if not project_id:
            return JsonResponse({'error': 'Project ID is required'}, status=400)
        
        project = Project.objects.get(id=project_id, user=request.user)
        
        # Get results for this project with pagination
        results = SearchResultLink.objects.filter(
            project=project, 
            user=request.user
        ).select_related('job', 'keyword').order_by('-created_at')
        
        total_results = results.count()
        total_pages = (total_results + per_page - 1) // per_page
        
        # Paginate results
        start_index = (page - 1) * per_page
        end_index = start_index + per_page
        paginated_results = results[start_index:end_index]
        
        formatted_results = []
        for result in paginated_results:
            formatted_results.append({
                'id': result.id,
                'url': result.url,
                'title': result.title,
                'name': result.name,
                'email': result.email,
                'phone_number': result.phone_number,
                'domain': result.domain,
                'is_internal': result.is_internal,
                'is_external': result.is_external,
                'depth': result.depth,
                'created_at': result.created_at.isoformat(),
                'job_name': result.job.name if result.job else 'Unknown',
                'keyword': result.keyword.word if result.keyword else 'URL Crawl',
                'metadata': result.metadata or {}
            })
        
        return JsonResponse({
            'success': True,
            'project_id': project.id,
            'project_name': project.name,
            'results': formatted_results,
            'pagination': {
                'current_page': page,
                'total_pages': total_pages,
                'total_results': total_results,
                'per_page': per_page
            }
        })
        
    except Project.DoesNotExist:
        return JsonResponse({'error': 'Project not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': f'Failed to get project results: {str(e)}'}, status=500)