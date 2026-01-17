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


# In-memory storage for real-time updates
# Global in-memory session tracker (for thread management)
crawler_sessions = {}

class FastURLCrawler:
    def __init__(self, session_id, base_url, max_depth=2, filters=None, max_workers=5):
        self.session_id = session_id
        self.base_url = base_url
        self.max_depth = max_depth
        
        # 1. Setup Redis
        redis_url = getattr(settings, 'REDIS_URL', 'redis://localhost:6379/0')
        self.r = redis.from_url(redis_url, decode_responses=True)
        
        # 2. State & Safety
        self.visited_urls = set()
        self.is_running = True
        self.base_domain = urlparse(base_url).netloc
        self.filters = filters or {}
        self.max_workers = max_workers
        self.executor = ThreadPoolExecutor(max_workers=self.max_workers)
        self.url_lock = threading.Lock()
        
        self.found_links = []
        self.all_unique_urls = set()
        self._pause_event = threading.Event()
        self._pause_event.set() # Initialize as "not paused"
        
        # 3. Networking (Optimized for Pure BS4)
        self.session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(pool_connections=max_workers, pool_maxsize=max_workers*2)
        self.session.mount('http://', adapter)
        self.session.mount('https://', adapter)
        
        # Add User-Agent to mimic a browser (Crucial since we removed Selenium)
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        })
        
        # 4. Queue and Timing
        self.queue = deque([(self.base_url, 0)])
        self.last_request_time = 0
        self.min_request_interval = 0.05
        
        # 5. INITIALIZE REDIS KEYS
        self.r.set(f"crawler:status:{self.session_id}", "running", ex=86400)
        # We keep 'selenium_fallback' in the stats to ensure frontend compatibility, 
        # even though it will stay 0.
        self.r.set(f"crawler:stats:{self.session_id}", json.dumps({
            'total_found': 0, 'pages_crawled': 0, 'errors': 0, 
            'filtered_links': 0, 'beautifulsoup_success': 0, 'selenium_fallback': 0,
            'duplicates_skipped': 0, 'parallel_workers': self.max_workers
        }), ex=86400)
        
    def rate_limit(self):
        """Respectful rate limiting"""
        current_time = time.time()
        elapsed = current_time - self.last_request_time
        if elapsed < self.min_request_interval:
            time.sleep(self.min_request_interval - elapsed)
        self.last_request_time = time.time()
    
    def should_follow_link(self, link):
        """Air-tight filter checking with robust key handling"""
        if not self.filters:
            return link.get('is_internal', False)
            
        try:
            url = link.get('url', '')
            is_internal = link.get('is_internal', False)
            
            # Handle 'caseSensitive' (JS style) or 'case_sensitive' (Python style)
            case_sensitive = self.filters.get('caseSensitive') or self.filters.get('case_sensitive') or False
            
            # 1. ALWAYS block external links first
            if not is_internal:
                return False
            
            # Pre-process URL once for comparison
            check_url = url if case_sensitive else url.lower()

            # 2. URL CONTAINS (Whitelist/Requirement)
            # Check both key styles to prevent filter bypassing
            url_contains_raw = self.filters.get('urlContains') or self.filters.get('url_contains')
            
            if url_contains_raw:
                # Ensure we handle list inputs or comma-separated strings
                if isinstance(url_contains_raw, list):
                    keywords = [str(k).strip() for k in url_contains_raw if str(k).strip()]
                else:
                    keywords = [k.strip() for k in str(url_contains_raw).split(',') if k.strip()]

                if keywords:
                    match_found = any(
                        (k if case_sensitive else k.lower()) in check_url 
                        for k in keywords
                    )
                    # STRICT BLOCK: If keywords were provided but URL doesn't match, return False
                    if not match_found:
                        return False

            # 3. URL EXCLUDES (Blacklist)
            url_excludes_raw = self.filters.get('urlExcludes') or self.filters.get('url_excludes')
            
            if url_excludes_raw:
                if isinstance(url_excludes_raw, list):
                    excludes = [str(ex).strip() for ex in url_excludes_raw if str(ex).strip()]
                else:
                    excludes = [ex.strip() for ex in str(url_excludes_raw).split(',') if ex.strip()]
                
                for exclude in excludes:
                    check_exclude = exclude if case_sensitive else exclude.lower()
                    if check_exclude in check_url:
                        return False

            # 4. TEXT CONTAINS (Whitelist)
            text_contains_raw = self.filters.get('textContains') or self.filters.get('text_contains')
            
            if text_contains_raw:
                text = link.get('text', '')
                check_text = text if case_sensitive else text.lower()
                
                if isinstance(text_contains_raw, list):
                    text_keywords = [str(tk).strip() for tk in text_contains_raw if str(tk).strip()]
                else:
                    text_keywords = [tk.strip() for tk in str(text_contains_raw).split(',') if tk.strip()]
                
                if text_keywords:
                    text_match = any(
                        (tk if case_sensitive else tk.lower()) in check_text 
                        for tk in text_keywords
                    )
                    if not text_match:
                        return False

            return True # Passed all checks
            
        except Exception as e:
            # If an error occurs in the filter logic, we block the link to be safe
            logger.error(f"Filter Error on {link.get('url')}: {e}")
            return False
    
    def check_pause(self):
        """Polls Redis to see if we should wait or stop"""
        while True:
            status = self.r.get(f"crawler:status:{self.session_id}")
            if status == "stopped":
                self.is_running = False
                return False
            if status == "paused":
                time.sleep(1)
                continue
            return True

    def update_redis_stats(self, key_name, increment=1):
        """Helper to update stats inside Redis JSON string"""
        with self.url_lock:
            stats_raw = self.r.get(f"crawler:stats:{self.session_id}")
            stats = json.loads(stats_raw) if stats_raw else {}
            stats[key_name] = stats.get(key_name, 0) + increment
            self.r.set(f"crawler:stats:{self.session_id}", json.dumps(stats))
            return stats
            
    def crawl(self):
        """Optimized crawling with parallel processing"""
        try:
            # Re-initialize executor if needed
            self.executor.submit(lambda: None)
        except (RuntimeError, AttributeError):
            logger.info("Re-initializing executor for session")
            self.executor = ThreadPoolExecutor(max_workers=self.max_workers)
            
        try:
            if self.session_id not in crawler_sessions:
                crawler_sessions[self.session_id] = {
                    'crawler': self,
                    'results': [],
                    'started_at': time.time(),
                    'status': 'running',
                    'filters': self.filters,
                    'stats': {
                        'total_found': 0, 'pages_crawled': 0, 'beautifulsoup_success': 0,
                        'selenium_fallback': 0, 'errors': 0, 'duplicates_skipped': 0,
                        'filtered_links': 0, 'parallel_workers': self.max_workers
                    }
                }
            
            batch_size = 10 
            
            while self.queue and self.is_running:
                self.check_pause()
                
                if not self.is_running: break
                
                # Take a batch of URLs to process in parallel
                current_batch = []
                while self.queue and len(current_batch) < batch_size:
                    url, depth = self.queue.popleft()
                    
                    if url not in self.visited_urls and depth < self.max_depth:
                        current_batch.append((url, depth))
                
                if not current_batch:
                    continue
                
                # Process batch in parallel
                new_links = self.process_batch_parallel(current_batch)
                
                # Add new links to queue
                for link in new_links:
                    if link['url'] not in self.visited_urls and link.get('depth', 0) < self.max_depth:
                        if self.should_follow_link(link):
                            self.queue.append((link['url'], link.get('depth', 0)))
                        else:
                            with self.url_lock:
                                crawler_sessions[self.session_id]['stats']['filtered_links'] += 1
                
                # Progress update
                if len(self.visited_urls) % 20 == 0:
                    self.add_result({
                        'type': 'progress',
                        'visited': len(self.visited_urls),
                        'found': len(self.found_links),
                        'queued': len(self.queue),
                        'filtered': crawler_sessions[self.session_id]['stats']['filtered_links'],
                        'message': f'Progress: {len(self.visited_urls)} pages, {len(self.found_links)} links, {len(self.queue)} queued'
                    })
                            
        except Exception as e:
            if self.is_running: 
                logger.error(f"Crawling error: {e}")
                self.add_result({
                    'type': 'error',
                    'message': f'Crawling error: {str(e)}'
                })
        finally:
            self.stop()
    
    def process_batch_parallel(self, url_batch):
        """Process a batch of URLs using the persistent executor"""
        all_new_links = []
        
        # Mark visited immediately
        with self.url_lock:
            for url, depth in url_batch:
                self.visited_urls.add(url)
        
        try:
            future_to_url = {
                self.executor.submit(self.process_single_page, url, depth): (url, depth) 
                for url, depth in url_batch
            }
            
            for future in as_completed(future_to_url):
                if not self.is_running:
                    break
                
                url, depth = future_to_url[future]
                try:
                    new_links = future.result(timeout=15)
                    if self.is_running:
                        all_new_links.extend(new_links)
                        with self.url_lock:
                            self.visited_urls.add(url)
                except Exception as e:
                    if self.is_running:
                        logger.warning(f"Failed to process {url}: {e}")
                        with self.url_lock:
                            crawler_sessions[self.session_id]['stats']['errors'] += 1
                            
        except RuntimeError:
            logger.info("Executor accessed during shutdown. Stopping batch.")
        
        return all_new_links
    
    def process_single_page(self, url, depth):
        """Process a single page - Pure BeautifulSoup version"""
        self.check_pause()
        self.rate_limit()
        
        try:
            # Update stats
            with self.url_lock:
                crawler_sessions[self.session_id]['stats']['pages_crawled'] += 1
            
            # Fetch and Parse (Only using BS4)
            links = self.fast_process_with_beautifulsoup(url, depth)
            
            if not self.is_running: return []
            
            # Filter and process found links
            filtered_links = []
            for link in links:
                self.check_pause()
                if not self.is_running: break
                
                if not self.should_follow_link(link):
                    with self.url_lock:
                        crawler_sessions[self.session_id]['stats']['filtered_links'] += 1
                    continue 

                with self.url_lock:
                    if link['url'] in self.all_unique_urls:
                        crawler_sessions[self.session_id]['stats']['duplicates_skipped'] += 1
                        continue
                    
                    self.all_unique_urls.add(link['url'])
                    crawler_sessions[self.session_id]['stats']['total_found'] += 1
                    current_total = crawler_sessions[self.session_id]['stats']['total_found']
                
                link['depth'] = depth + 1 
                link['found_at'] = time.time()
                filtered_links.append(link)
                
                self.add_result({
                    'type': 'link_found',
                    'link': link,
                    'total_found': current_total, 
                    'total_visited': len(self.visited_urls) + 1
                })
            
            with self.url_lock:
                self.found_links.extend(filtered_links)
            
            return filtered_links
            
        except Exception as e:
            logger.error(f"Error processing page {url}: {e}")
            with self.url_lock:
                crawler_sessions[self.session_id]['stats']['errors'] += 1
            return []
    
    def fast_process_with_beautifulsoup(self, url, depth):
        """Standardized BeautifulSoup processing with DEBUG logging"""
        try:
            logger.info(f"Attempting to fetch: {url}") # <--- ADD THIS
            
            # IMDB often blocks based on TLS fingerprint. 
            # verify=False helps sometimes (but insecure), purely for debugging here.
            response = self.session.get(url, timeout=20, allow_redirects=True)
            
            logger.info(f"Status Code for {url}: {response.status_code}") # <--- ADD THIS

            response.raise_for_status()
            
            # Quick content type check
            content_type = response.headers.get('content-type', '')
            if 'text/html' not in content_type:
                logger.warning(f"Skipping non-HTML content: {content_type}") # <--- ADD THIS
                return []
            
            soup = BeautifulSoup(response.content, 'html.parser')
            links = self.fast_extract_links(soup, url)
            
            with self.url_lock:
                crawler_sessions[self.session_id]['stats']['beautifulsoup_success'] += 1
            
            return links
            
        except Exception as e:
            # <--- CRITICAL CHANGE: Log the actual error instead of silencing it
            logger.error(f"FAILED on {url}: {str(e)}") 
            return []
    
    def fast_extract_links(self, soup, base_url):
        """Optimized link extraction that CAPTURES contacts but flags them"""
        links = []
        base_domain = self.base_domain
        seen_urls = set()
        
        for a_tag in soup.find_all('a', href=True):
            try:
                href = a_tag['href'].strip()
                
                # 1. ONLY filter out crash-prone javascript or empty links
                # We KEEP 'mailto:' and 'tel:' now.
                if not href or href.startswith(('javascript:', '#')):
                    continue
                
                full_url = urljoin(base_url, href)
                parsed_url = urlparse(full_url)
                
                # 2. Check protocol
                scheme = parsed_url.scheme.lower()
                is_http = scheme in ['http', 'https']
                is_contact = scheme in ['mailto', 'tel']

                # Quick normalization
                if is_http:
                    normalized_url = f"{parsed_url.scheme}://{parsed_url.netloc}{parsed_url.path}"
                    if parsed_url.query: normalized_url += f"?{parsed_url.query}"
                else:
                    # Keep mailto/tel exactly as is
                    normalized_url = full_url

                if normalized_url in seen_urls: continue
                seen_urls.add(normalized_url)
                
                is_internal = parsed_url.netloc == base_domain
                
                link_text = a_tag.get_text(strip=True)[:150] or a_tag.get('title', '')[:150]
                
                links.append({
                    'url': normalized_url,
                    'text': link_text,
                    'is_internal': is_internal,
                    'is_external': not is_internal and is_http,
                    'is_contact': is_contact,    # <--- NEW FLAG
                    'crawlable': is_http,        # <--- KEY SAFETY FLAG
                    'source_url': base_url,
                    'domain': parsed_url.netloc
                })
                
            except Exception:
                continue
                
        return links
                
    def add_result(self, result):
        """Push result to Redis List for the UI to pop"""
        if self.session_id:
            self.r.rpush(f"crawler:results:{self.session_id}", json.dumps(result))
    
    def stop(self):
        """Clean shutdown"""
        if not hasattr(self, 'is_running') or not self.is_running:
            return
        
        self.is_running = False 
        if hasattr(self, '_pause_event'):
            self._pause_event.set() 
        
        self.r.set(f"crawler:status:{self.session_id}", "completed")
        
        if hasattr(self, 'executor'):
            try:
                self.executor.shutdown(wait=False, cancel_futures=True)
            except:
                pass
        
        # Session Cleanup
        if self.session_id in crawler_sessions:
            stats = crawler_sessions[self.session_id].get('stats', {})
            
            self.add_result({
                'type': 'complete',
                'message': f'🎉 Crawl finished. Visited {stats.get("pages_crawled", 0)} pages.',
                'total_links': stats.get('total_found', 0),
                'total_pages': stats.get('pages_crawled', 0)
            })
            
            crawler_sessions[self.session_id]['status'] = 'completed'
            
            
# Session cleanup function
def cleanup_old_sessions():
    """Force stop crawlers where the user has closed the tab"""
    current_time = time.time()
    sessions_to_remove = []
    
    # Use list() to avoid "dictionary changed size during iteration" error
    for session_id, session_data in list(crawler_sessions.items()):
        last_polled = session_data.get('last_polled', 0)
        started_at = session_data.get('started_at', 0)
        
        if (current_time - last_polled > 30) or (current_time - started_at > 7200):
            logger.info(f"Cleaning up zombie session: {session_id}")
            
            crawler = session_data.get('crawler')
            if crawler:
                crawler.stop()
            
            sessions_to_remove.append(session_id)
    
    for session_id in sessions_to_remove:
        crawler_sessions.pop(session_id, None)

# --- VIEWS ---

@csrf_exempt
@require_http_methods(["POST"])
def start_url_crawl(request):
    data = json.loads(request.body)
    session_id = str(uuid.uuid4())
    
    # We ignore 'use_selenium' from data, as we are now pure BS4
    crawler = FastURLCrawler(
        session_id=session_id,
        base_url=data.get('url'),
        max_depth=int(data.get('max_depth', 2)),
        filters=data.get('filters', {}),
        max_workers=int(data.get('max_workers', 5))
    )
    
    crawler.r.set(f"crawler:start_time:{session_id}", time.time(), ex=86400)
    
    thread = threading.Thread(target=crawler.crawl)
    thread.daemon = True
    thread.start()
    
    return JsonResponse({'success': True, 'session_id': session_id})

@csrf_exempt
def pause_url_crawl(request):
    data = json.loads(request.body)
    r = redis.from_url(settings.REDIS_URL, decode_responses=True)
    r.set(f"crawler:status:{data.get('session_id')}", "paused")
    return JsonResponse({'status': 'paused'})

@csrf_exempt
def resume_url_crawl(request):
    data = json.loads(request.body)
    r = redis.from_url(settings.REDIS_URL, decode_responses=True)
    r.set(f"crawler:status:{data.get('session_id')}", "running")
    return JsonResponse({'status': 'resumed'})

@require_http_methods(["GET"])
def get_crawl_results(request):
    session_id = request.GET.get('session_id')
    r = redis.from_url(settings.REDIS_URL, decode_responses=True)
    
    # 1. Pop all results currently in the Redis list (Real-time streaming)
    results = []
    while r.llen(f"crawler:results:{session_id}") > 0:
        res = r.lpop(f"crawler:results:{session_id}")
        if res:
            results.append(json.loads(res))
    
    # 2. Get status and stats
    status = r.get(f"crawler:status:{session_id}") or "unknown"
    stats_raw = r.get(f"crawler:stats:{session_id}")
    stats = json.loads(stats_raw) if stats_raw else {}
    
    return JsonResponse({
        'results': results,
        'status': status,
        'stats': stats,
        'total_results': len(results)
    })

@require_http_methods(["GET"])
def get_crawl_status(request):
    session_id = request.GET.get('session_id')
    if not session_id:
        return JsonResponse({'error': 'Session ID is required'}, status=400)
    
    r = redis.from_url(settings.REDIS_URL, decode_responses=True)
    
    # Get Data from Redis
    status = r.get(f"crawler:status:{session_id}")
    stats_raw = r.get(f"crawler:stats:{session_id}")
    start_time = r.get(f"crawler:start_time:{session_id}")

    if not status:
        return JsonResponse({'error': 'Invalid session ID or session expired'}, status=404)

    stats = json.loads(stats_raw) if stats_raw else {}
    running_time = round(time.time() - float(start_time), 2) if start_time else 0

    return JsonResponse({
        'status': status,
        'stats': stats,
        'running_time': running_time,
        'session_exists': True
    })

@require_http_methods(["POST"])
@csrf_exempt
def stop_crawl(request):
    try:
        data = json.loads(request.body)
        session_id = data.get('session_id')
        
        if not session_id:
            return JsonResponse({'error': 'Session ID is required'}, status=400)
            
        r = redis.from_url(settings.REDIS_URL, decode_responses=True)
        
        # We set the status to 'stopped'. 
        r.set(f"crawler:status:{session_id}", "stopped")
        
        logger.info(f"Sent stop signal to session {session_id}")
        return JsonResponse({'success': True, 'message': 'Crawling stopped'})
        
    except Exception as e:
        logger.error(f"Failed to stop crawling: {e}")
        return JsonResponse({'error': f'Failed to stop crawling: {str(e)}'}, status=500)

@require_http_methods(["GET"])
def list_sessions(request):
    r = redis.from_url(settings.REDIS_URL, decode_responses=True)
    
    # Find all keys that represent a status
    status_keys = r.keys("crawler:status:*")
    
    sessions_info = {}
    for key in status_keys:
        session_id = key.split(":")[-1]
        status = r.get(key)
        stats_raw = r.get(f"crawler:stats:{session_id}")
        start_time = r.get(f"crawler:start_time:{session_id}")
        
        sessions_info[session_id] = {
            'status': status,
            'started_at': float(start_time) if start_time else 0,
            'stats': json.loads(stats_raw) if stats_raw else {},
            'running_time': round(time.time() - float(start_time), 2) if start_time else 0
        }
    
    return JsonResponse({
        'active_sessions': len(sessions_info),
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
def get_all_results(request):
    """Get all results for a session"""
    session_id = request.GET.get('session_id')
    
    if not session_id:
        return JsonResponse({'error': 'Session ID is required'}, status=400)
    
    if session_id not in crawler_sessions:
        return JsonResponse({'error': 'Session not found'}, status=404)
    
    session = crawler_sessions[session_id]
    
    return JsonResponse({
        'results': session.get('crawler', {}).found_links if session.get('crawler') else [],
        'stats': session.get('stats', {}),
        'status': session.get('status', 'unknown')
    })


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


    