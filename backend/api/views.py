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
from django.conf import settings
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
import redis
import logging
from .utils.search_engine_scrappers import(
    scrape_bing_results,
    scrape_duckduckgo_results
)
from .tasks import run_url_crawl
from .utils.thread_generator import ThreadedGenerator










logger = logging.getLogger(__name__)

GLOBAL_STOP_FLAG = threading.Event()
BULK_SEARCH_STOP_FLAG = threading.Event()

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def current_user(request):
    serializer = UserSerializer(request.user)
    return Response(serializer.data)



def apply_filters(href, filters):
    """
    Applies include, exclude, domain, and filetype filters to a single URL.
    Returns True if the URL passes all filters, False otherwise.
    """
    url = href.lower()
    include_terms = [term.strip().lower() for term in filters.get("url_include", "").splitlines() if term.strip()]
    exclude_terms = [term.strip().lower() for term in filters.get("url_exclude", "").splitlines() if term.strip()]
    domain_terms = [term.strip().lower() for term in filters.get("domain_filter", "").splitlines() if term.strip()]
    file_type = filters.get("file_type_filter", "").strip().lower()

    # 1️⃣ Exclude unwanted terms
    if exclude_terms and any(ex in url for ex in exclude_terms):
        return False

    # 2️⃣ Include only if contains required terms
    if include_terms and not any(inc in url for inc in include_terms):
        return False

    # 3️⃣ Domain/TLD filter
    if domain_terms and not any(dom in url for dom in domain_terms):
        return False

    # 4️⃣ File type filter (check URL ending)
    if file_type:
        # Allow simple match like ".pdf" or "?file=example.pdf"
        if not url.endswith(f".{file_type}") and f".{file_type}?" not in url:
            return False

    return True


# ---------- SSE streaming view with fallback ----------

@csrf_exempt
@require_http_methods(["GET", "POST"])  # Allow both GET and POST
def search_and_parse_stream(request):
    # Reset global stop before starting
    GLOBAL_STOP_FLAG.clear()

    # Handle both GET and POST requests
    if request.method == 'POST':
        try:
            body = json.loads(request.body)
            keyword_raw = body.get("q", "headphones")
            engine = body.get("engine", "duck duck go").lower()
            max_depth = int(body.get("depth", 0))
            limit_raw_str = str(body.get("limit", "")).strip()
            limit = int(limit_raw_str) if limit_raw_str.isdigit() else 0
            
            # Get filters from POST body
            filters = {
                "url_include": body.get("url_include", ""),
                "url_exclude": body.get("url_exclude", ""),
                "domain_filter": body.get("domain_filter", ""),
                "file_type_filter": body.get("file_type_filter", ""),
                "language_filter": body.get("language_filter", "")
            }
            
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON"}, status=400)
        
    else:  # GET request
        keyword_raw = request.GET.get("q", "headphones")
        engine = request.GET.get("engine", "duck duck go").lower()
        max_depth = int(request.GET.get("depth", 0))
        limit_raw = request.GET.get("limit", "")
        limit = int(limit_raw) if limit_raw.isdigit() else 0
        
        # Get filters from GET parameters (for backward compatibility)
        filters = {
            "url_include": request.GET.get("url_include", ""),
            "url_exclude": request.GET.get("url_exclude", ""),
            "domain_filter": request.GET.get("domain_filter", ""),
            "file_type_filter": request.GET.get("file_type_filter", ""),
            "language_filter": request.GET.get("language_filter", "")
        }

    keyword_stripped = keyword_raw.strip().lower()

    keyword_obj, _ = Keyword.objects.get_or_create(word=keyword_stripped)
    try:
        keyword_serialized = KeywordSerializer(keyword_obj).data
    except Exception:
        keyword_serialized = {"id": keyword_obj.id, "word": keyword_obj.word}

    def parse_to_dict(data, depth=0):
        if not isinstance(data, dict) or not data.get("url"):
            return None
        node = {"url": data["url"], "title": data.get("title"), "depth": depth, "children": []}
        for child in data.get("children", []):
            child_node = parse_to_dict(child, depth + 1)
            if child_node:
                node["children"].append(child_node)
        return node

    def event_stream():
        yield f"event: meta\ndata: {json.dumps({'keyword': keyword_serialized})}\n\n"
        try:
            if engine == "bing":
                generator = ThreadedGenerator(scrape_bing_results, keyword_stripped, num_results=limit)
            else:
                generator = ThreadedGenerator(
                    scrape_duckduckgo_results, 
                    keyword_stripped, 
                    num_results=limit, 
                    stop_flag=GLOBAL_STOP_FLAG
                )

            idx = 0
            
            filtered_count = 0

            for href in generator:
                # 🛑 Immediately stop if global stop is triggered
                if GLOBAL_STOP_FLAG.is_set():
                    print("⛔ Global stop detected — aborting search and closing browser.")
                    break

                # Apply filters using your existing function
                if not apply_filters(href, filters):
                    filtered_count += 1
                    continue

                idx += 1
                try:
                    parsed_data = parse_page(href, current_depth=0, max_depth=max_depth)

                    # Apply filters to children as well
                    if parsed_data and 'children' in parsed_data:
                        parsed_data['children'] = [
                            child for child in parsed_data['children']
                            if child.get('url') and apply_filters(child.get('url'), filters)
                        ]

                    node = parse_to_dict(parsed_data)
                except Exception as e:
                    print("⚠️ parse_page error for", href, e)
                    node = {"url": href, "title": None, "depth": 0, "children": []}

                payload = {
                    "keyword_id": keyword_obj.id,
                    "node": node,
                    "progress": {"current": idx, "total": limit or None},
                    "filters_applied": {
                        "url_include": bool(filters["url_include"]),
                        "url_exclude": bool(filters["url_exclude"]),
                        "domain_filter": bool(filters["domain_filter"]),
                        "language_filter": bool(filters["language_filter"]),
                        "file_type_filter": bool(filters["file_type_filter"]),
                        "filtered_count": filtered_count
                    }
                }
                yield f"data: {json.dumps(payload)}\n\n"
                time.sleep(0.02)

            # FIXED: Use a variable for the done event data
            done_data = {
                'message': 'Search finished',
                'total_received': idx,
                'total_filtered': filtered_count,
                'filters_applied': {
                    'url_include': bool(filters["url_include"]),
                    'url_exclude': bool(filters["url_exclude"]),
                    'domain_filter': bool(filters["domain_filter"]),
                    'language_filter': bool(filters["language_filter"]),
                    'file_type_filter': bool(filters["file_type_filter"]),
                    'filtered_count': filtered_count
                }
            }
            yield f"event: done\ndata: {json.dumps(done_data)}\n\n"

        finally:
            GLOBAL_STOP_FLAG.clear()

    response = StreamingHttpResponse(event_stream(), content_type="text/event-stream")
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response


@csrf_exempt
def stop_search(request):
    GLOBAL_STOP_FLAG.set()
    print("🛑 Global stop triggered! All scrapers will exit now.")
    return JsonResponse({"status": "ok", "message": "Global stop signal sent."})


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
    Streamed bulk keyword search (SSE) using DuckDuckGo by default.
    Reads .txt file line-by-line and streams results.
    """
    keywords_file = request.FILES.get('keywords_file')
    used_engine = request.GET.get("engine", "duckduckgo").lower()  # default DuckDuckGo
    
    print(f"🚀 Starting bulk search using engine: {used_engine}")
    
    filters = {
        "url_include": request.POST.get("url_include", ""),
        "url_exclude": request.POST.get("url_exclude", ""),
        "domain_filter": request.POST.get("domain_filter", ""),
        "file_type_filter": request.POST.get("file_type_filter", ""),
    }

    if not keywords_file:
        return Response({"detail": "No file uploaded"}, status=400)

    try:
        keywords = [line.strip() for line in keywords_file.read().decode('utf-8').splitlines() if line.strip()]
    except Exception:
        return Response({"detail": "Could not read file. Ensure it's a valid .txt file."}, status=400)

    num_results_raw = request.GET.get("bulk_limit", "").strip()
    num_results = int(num_results_raw) if num_results_raw.isdigit() and int(num_results_raw) > 0 else None

    max_depth = 0

    # Reset stop flag
    BULK_SEARCH_STOP_FLAG.clear()

    def event_stream():
        total_keywords = len(keywords)
        yield f"event: meta\ndata: {json.dumps({'total_keywords': total_keywords})}\n\n"

        for idx, keyword_raw in enumerate(keywords, start=1):
            if BULK_SEARCH_STOP_FLAG.is_set():
                print("⛔ Bulk search stopped by user")
                break

            keyword_stripped = keyword_raw.strip()
            keyword_obj, _ = Keyword.objects.get_or_create(word=keyword_stripped)
            try:
                keyword_serialized = KeywordSerializer(keyword_obj).data
            except Exception:
                keyword_serialized = {"id": keyword_obj.id, "word": keyword_obj.word}

            yield f"event: keyword_start\ndata: {json.dumps({'keyword': keyword_serialized, 'index': idx})}\n\n"

            results = []

            # Choose engine
            engines_to_try = [used_engine]
            if used_engine != "duckduckgo":
                engines_to_try.append("duckduckgo")  # fallback

            for engine_name in engines_to_try:
                try:
                    # UPDATED CODE: Use ThreadedGenerator here too
                    if engine_name == "duckduckgo":
                        generator = ThreadedGenerator(
                            scrape_duckduckgo_results, 
                            keyword_stripped, 
                            num_results, 
                            stop_flag=BULK_SEARCH_STOP_FLAG
                        )
                    else:
                        generator = ThreadedGenerator(
                            scrape_bing_results, 
                            keyword_stripped, 
                            num_results
                        )

                    generated_any = False
                    
                    for href in generator:
                        generated_any = True
                        if BULK_SEARCH_STOP_FLAG.is_set():
                            print("⛔ Stop flag detected mid-keyword — breaking links loop")
                            break

                        # 🧩 Apply filters before parsing
                        if not apply_filters(href, filters):
                            continue

                        try:
                            parsed_data = parse_page(href, current_depth=0, max_depth=max_depth)
                            node = {"url": parsed_data.get("url"), "title": parsed_data.get("title"), "depth": 0, "children": []}
                        except Exception as e:
                            node = {"url": href, "title": None, "depth": 0, "children": []}
                            print("parse_page error:", e)

                        results.append(node)
                        payload = {
                            "keyword": keyword_serialized,
                            "engine": engine_name,
                            "progress": {"current": len(results), "total": num_results},
                            "node": node,
                        }
                        
                        yield f"data: {json.dumps(payload)}\n\n"
                        
                        time.sleep(0.02)

                    if generated_any:
                        # If this engine returned results, don't try fallback
                        break

                except Exception as e:
                    print(f"[WARN] Search failed for '{keyword_stripped}' using {engine_name}: {e}")

            done_payload = {
                "keyword": keyword_serialized,
                "total_results": len(results),
                "engine_used": engine_name,
            }
            yield f"event: keyword_done\ndata: {json.dumps(done_payload)}\n\n"

        yield f"event: done\ndata: {json.dumps({'message': 'Bulk streaming complete'})}\n\n"

    response = StreamingHttpResponse(event_stream(), content_type="text/event-stream")
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response

@api_view(['POST'])
@csrf_exempt
def stop_bulk_search(request):
    """
    API endpoint to stop the bulk keyword search immediately.
    """
    BULK_SEARCH_STOP_FLAG.set()
    print("🛑 Stop signal set for bulk search")
    return Response({"status": "ok", "message": "Bulk search stopped."})
    



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
    if not folder:
        return Response({"error": "Folder not found"}, status=404)

    # 2. Get last keyword associated with this folder
    keyword = folder.keywords.order_by('-created_at').first()
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

        

# --- VIEWS ---

@csrf_exempt
@require_http_methods(["POST"])
def start_url_crawl(request):
    data = json.loads(request.body)
    session_id = str(uuid.uuid4())

    raw_max = data.get("max_depth", None)
    if raw_max in (None, "", "null"):
        max_depth = None
    else:
        try:
            max_depth = int(raw_max)
        except Exception:
            max_depth = None

    run_url_crawl.delay(
        session_id=session_id,
        url=data.get("url"),
        max_depth=max_depth,
        filters=data.get("filters", {}),
        max_workers=int(data.get("max_workers", 5) or 5),
    )

    return JsonResponse({"success": True, "session_id": session_id})


def get_redis_client():
    redis_url = getattr(settings, "REDIS_URL", "redis://localhost:6379/0")
    return redis.from_url(redis_url, decode_responses=True)


@csrf_exempt
@require_http_methods(["POST"])
def pause_url_crawl(request):
    try:
        data = json.loads(request.body or "{}")
        session_id = data.get("session_id")

        if not session_id:
            return JsonResponse({"error": "Session ID is required"}, status=400)

        r = get_redis_client()
        r.set(f"crawler:status:{session_id}", "paused", ex=86400)

        return JsonResponse({"status": "paused"})

    except Exception as e:
        logger.error(f"pause_url_crawl error: {e}")
        return JsonResponse({"error": str(e)}, status=500)


# ✅ RESUME
@csrf_exempt
@require_http_methods(["POST"])
def resume_url_crawl(request):
    try:
        data = json.loads(request.body or "{}")
        session_id = data.get("session_id")

        if not session_id:
            return JsonResponse({"error": "Session ID is required"}, status=400)

        r = get_redis_client()
        r.set(f"crawler:status:{session_id}", "running", ex=86400)

        return JsonResponse({"status": "resumed"})

    except Exception as e:
        logger.error(f"resume_url_crawl error: {e}")
        return JsonResponse({"error": str(e)}, status=500)


@require_http_methods(["GET"])
def get_crawl_results(request):
    session_id = request.GET.get("session_id")
    if not session_id:
        return JsonResponse({"error": "Session ID is required"}, status=400)

    r = get_redis_client()

    key = f"crawler:results:{session_id}"
    batch_size = int(request.GET.get("limit", 200))  # default same as your working version

    # ✅ Read first N
    results_raw = r.lrange(key, 0, batch_size - 1)

    # ✅ Trim first N
    if results_raw:
        r.ltrim(key, len(results_raw), -1)

    results = []
    for item in results_raw:
        try:
            results.append(json.loads(item))
        except Exception:
            # ignore broken JSON
            continue

    status = r.get(f"crawler:status:{session_id}") or "unknown"
    stats_raw = r.get(f"crawler:stats:{session_id}")
    stats = json.loads(stats_raw) if stats_raw else {}

    return JsonResponse({
        "results": results,
        "status": status,
        "stats": stats,
        "total_results": len(results),
    })


# ✅ STATUS (SAME FORMAT)
@require_http_methods(["GET"])
def get_crawl_status(request):
    session_id = request.GET.get("session_id")
    if not session_id:
        return JsonResponse({"error": "Session ID is required"}, status=400)

    r = get_redis_client()

    status = r.get(f"crawler:status:{session_id}")
    stats_raw = r.get(f"crawler:stats:{session_id}")
    start_time = r.get(f"crawler:start_time:{session_id}")

    if not status:
        return JsonResponse({"error": "Invalid session ID or session expired"}, status=404)

    stats = json.loads(stats_raw) if stats_raw else {}

    running_time = 0
    if start_time:
        try:
            running_time = round(time.time() - float(start_time), 2)
        except Exception:
            running_time = 0

    return JsonResponse({
        "status": status,
        "stats": stats,
        "running_time": running_time,
        "session_exists": True
    })


# ✅ STOP (SAME FORMAT)
@csrf_exempt
@require_http_methods(["POST"])
def stop_crawl(request):
    try:
        data = json.loads(request.body or "{}")
        session_id = data.get("session_id")

        if not session_id:
            return JsonResponse({"error": "Session ID is required"}, status=400)

        r = get_redis_client()
        r.set(f"crawler:status:{session_id}", "stopped", ex=86400)

        logger.info(f"Stop signal sent to session {session_id}")

        return JsonResponse({
            "success": True,
            "message": "Crawling stopped"
        })

    except Exception as e:
        logger.error(f"stop_crawl error: {e}")
        return JsonResponse({
            "error": f"Failed to stop crawling: {str(e)}"
        }, status=500)
    

@require_http_methods(["GET"])
def list_sessions(request):
    r = redis.from_url(settings.REDIS_URL, decode_responses=True)

    sessions_info = {}
    cursor = 0

    while True:
        cursor, keys = r.scan(cursor=cursor, match="crawler:status:*", count=200)

        for key in keys:
            session_id = key.split(":")[-1]
            status = r.get(key)

            stats_raw = r.get(f"crawler:stats:{session_id}")
            start_time = r.get(f"crawler:start_time:{session_id}")

            stats = json.loads(stats_raw) if stats_raw else {}
            started_at = float(start_time) if start_time else 0

            sessions_info[session_id] = {
                "status": status,
                "started_at": started_at,
                "stats": stats,
                "running_time": round(time.time() - started_at, 2) if started_at else 0,
            }

        if cursor == 0:
            break

    return JsonResponse({
        "active_sessions": len(sessions_info),
        "sessions": sessions_info
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

# @require_http_methods(["GET"])
# def get_all_results(request):
#     """Get all results for a session"""
#     session_id = request.GET.get('session_id')
    
#     if not session_id:
#         return JsonResponse({'error': 'Session ID is required'}, status=400)
    
#     if session_id not in crawler_sessions:
#         return JsonResponse({'error': 'Session not found'}, status=404)
    
#     session = crawler_sessions[session_id]
    
#     return JsonResponse({
#         'results': session.get('crawler', {}).found_links if session.get('crawler') else [],
#         'stats': session.get('stats', {}),
#         'status': session.get('status', 'unknown')
#     })


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


    