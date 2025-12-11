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

GLOBAL_STOP_FLAG = threading.Event()
BULK_SEARCH_STOP_FLAG = threading.Event()

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def current_user(request):
    serializer = UserSerializer(request.user)
    print('serializer.data: ', serializer.data)
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
            generator = (
                scrape_bing_results(keyword_stripped, num_results=limit)
                if engine == "bing"
                else scrape_duckduckgo_results(keyword_stripped, num_results=limit, stop_flag=GLOBAL_STOP_FLAG)
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
                    if engine_name == "duckduckgo":
                        generator = scrape_duckduckgo_results(keyword_stripped, num_results, stop_flag=BULK_SEARCH_STOP_FLAG)
                    else:
                        generator = scrape_bing_results(keyword_stripped, num_results)

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

crawler_sessions = {}

class FastURLCrawler:
    def __init__(self, session_id, base_url, max_depth=2, use_selenium=False, filters=None, max_workers=5):
        self.session_id = session_id
        self.base_url = base_url
        self.max_depth = max_depth
        self.visited_urls = set()
        self.found_links = []
        self.driver = None
        self.is_running = True
        self.base_domain = urlparse(base_url).netloc
        self.use_selenium = use_selenium
        self.filters = filters or {}
        self.max_workers = max_workers  # Parallel processing
        
        # Optimized session with connection pooling
        self.session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(pool_connections=10, pool_maxsize=20, max_retries=2)
        self.session.mount('http://', adapter)
        self.session.mount('https://', adapter)
        
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Connection': 'keep-alive',
        })
        
        self.all_unique_urls = set()
        self.url_lock = threading.Lock()  # Thread safety
        
        # Rate limiting
        self.last_request_time = 0
        self.min_request_interval = 0.05  # 50ms between requests
        
    def rate_limit(self):
        """Respectful rate limiting"""
        current_time = time.time()
        elapsed = current_time - self.last_request_time
        if elapsed < self.min_request_interval:
            time.sleep(self.min_request_interval - elapsed)
        self.last_request_time = time.time()
    
    def should_follow_link(self, link):
        """Optimized filter checking"""
        if not self.filters:
            return link.get('is_internal', False)
            
        try:
            url = link['url']
            is_internal = link.get('is_internal', False)
            
            # ⚠️ CRITICAL: NEVER follow external links
            if not is_internal:
                return False
            
            # Quick depth check first (cheapest)
            depth = link.get('depth', 0)
            depth_filter = self.filters.get('depth', 'all')
            if depth_filter != 'all':
                if depth_filter == '3' and depth < 3:
                    return False
                elif depth_filter != '3' and int(depth_filter) != depth:
                    return False
            
            # URL contains check
            url_contains = self.filters.get('urlContains', '')
            if url_contains:
                case_sensitive = self.filters.get('caseSensitive', False)
                if not case_sensitive:
                    url = url.lower()
                    url_contains = url_contains.lower()
                if url_contains not in url:
                    return False
            
            # URL excludes check
            url_excludes = self.filters.get('urlExcludes', '')
            if url_excludes:
                case_sensitive = self.filters.get('caseSensitive', False)
                excludes = [ex.strip() for ex in url_excludes.split(',') if ex.strip()]
                for exclude in excludes:
                    if not case_sensitive:
                        exclude = exclude.lower()
                    if exclude in url:
                        return False
            
            # Text contains check
            text_contains = self.filters.get('textContains', '')
            if text_contains:
                text = link.get('text', '')
                if text:
                    case_sensitive = self.filters.get('caseSensitive', False)
                    if not case_sensitive:
                        text = text.lower()
                        text_contains = text_contains.lower()
                    if text_contains not in text:
                        return False
            
            # Domain filter
            domain_filter = self.filters.get('domain', '')
            if domain_filter:
                link_domain = urlparse(url).netloc
                case_sensitive = self.filters.get('caseSensitive', False)
                if not case_sensitive:
                    link_domain = link_domain.lower()
                    domain_filter = domain_filter.lower()
                if domain_filter not in link_domain:
                    return False
            
            # Regex filter (most expensive, do last)
            regex_filter = self.filters.get('regex', '')
            if regex_filter:
                try:
                    flags = 0 if self.filters.get('caseSensitive', False) else re.IGNORECASE
                    pattern = re.compile(regex_filter, flags)
                    if not pattern.search(url):
                        return False
                except re.error:
                    pass
            
            if self.filters.get('invertFilter', False):
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error in should_follow_link: {e}")
            return False
    
    def crawl(self):
        """Optimized crawling with parallel processing"""
        try:
            if self.session_id not in crawler_sessions:
                crawler_sessions[self.session_id] = {
                    'crawler': self,
                    'results': [],
                    'started_at': time.time(),
                    'status': 'running',
                    'filters': self.filters,
                    'stats': {
                        'total_found': 0,
                        'pages_crawled': 0,
                        'beautifulsoup_success': 0,
                        'selenium_fallback': 0,
                        'errors': 0,
                        'duplicates_skipped': 0,
                        'filtered_links': 0,
                        'parallel_workers': self.max_workers
                    }
                }
            
            queue = deque([(self.base_url, 0)])
            batch_size = 10  # Process URLs in batches
            
            while queue and self.is_running:
                # Take a batch of URLs to process in parallel
                current_batch = []
                while queue and len(current_batch) < batch_size:
                    url, depth = queue.popleft()
                    if url not in self.visited_urls and depth <= self.max_depth:
                        current_batch.append((url, depth))
                
                if not current_batch:
                    continue
                
                # Process batch in parallel
                new_links = self.process_batch_parallel(current_batch)
                
                # Add new links to queue
                for link in new_links:
                    if link['url'] not in self.visited_urls and link.get('depth', 0) < self.max_depth:
                        if self.should_follow_link(link):
                            queue.append((link['url'], link.get('depth', 0) + 1))
                        else:
                            with self.url_lock:
                                crawler_sessions[self.session_id]['stats']['filtered_links'] += 1
                
                # Progress update
                if len(self.visited_urls) % 20 == 0:
                    self.add_result({
                        'type': 'progress',
                        'visited': len(self.visited_urls),
                        'found': len(self.found_links),
                        'queued': len(queue),
                        'filtered': crawler_sessions[self.session_id]['stats']['filtered_links'],
                        'message': f'Progress: {len(self.visited_urls)} pages, {len(self.found_links)} links, {len(queue)} queued'
                    })
                            
        except Exception as e:
            logger.error(f"Crawling error: {e}")
            self.add_result({
                'type': 'error',
                'message': f'Crawling error: {str(e)}'
            })
        finally:
            self.close_driver()
            if self.session_id in crawler_sessions:
                crawler_sessions[self.session_id]['status'] = 'completed'
            
            self.add_result({
                'type': 'complete',
                'message': f'Crawling completed. Visited {len(self.visited_urls)} pages, found {len(self.found_links)} links.',
                'total_links': len(self.found_links),
                'total_pages': len(self.visited_urls),
                'filtered_links': crawler_sessions[self.session_id]['stats']['filtered_links']
            })
    
    def process_batch_parallel(self, url_batch):
        """Process a batch of URLs in parallel"""
        all_new_links = []
        
        with ThreadPoolExecutor(max_workers=min(self.max_workers, len(url_batch))) as executor:
            future_to_url = {
                executor.submit(self.process_single_page, url, depth): (url, depth) 
                for url, depth in url_batch
            }
            
            for future in as_completed(future_to_url):
                url, depth = future_to_url[future]
                try:
                    new_links = future.result(timeout=15)  # 15 second timeout per page
                    all_new_links.extend(new_links)
                    
                    # Mark as visited only if successful
                    with self.url_lock:
                        self.visited_urls.add(url)
                        
                except Exception as e:
                    logger.warning(f"Failed to process {url}: {e}")
                    with self.url_lock:
                        crawler_sessions[self.session_id]['stats']['errors'] += 1
        
        return all_new_links
    
    def process_single_page(self, url, depth):
        """Process a single page - optimized version"""
        self.rate_limit()  # Respect rate limiting
        
        try:
            # Update stats
            with self.url_lock:
                crawler_sessions[self.session_id]['stats']['pages_crawled'] += 1
            
            # Try with BeautifulSoup first
            links = self.fast_process_with_beautifulsoup(url, depth)
            
            # Fallback to Selenium if needed and enabled
            if not links and self.use_selenium:
                links = self.fast_process_with_selenium(url, depth)
            
            # Filter and process found links
            filtered_links = []
            for link in links:
                with self.url_lock:
                    if link['url'] in self.all_unique_urls:
                        crawler_sessions[self.session_id]['stats']['duplicates_skipped'] += 1
                        continue
                    
                    self.all_unique_urls.add(link['url'])
                    crawler_sessions[self.session_id]['stats']['total_found'] += 1
                
                link['depth'] = depth
                link['found_at'] = time.time()
                filtered_links.append(link)
                
                # Real-time update for each link
                self.add_result({
                    'type': 'link_found',
                    'link': link,
                    'total_found': len(self.found_links) + len(filtered_links),
                    'total_visited': len(self.visited_urls) + 1
                })
            
            # Add to found links
            with self.url_lock:
                self.found_links.extend(filtered_links)
            
            return filtered_links
            
        except Exception as e:
            logger.error(f"Error processing page {url}: {e}")
            with self.url_lock:
                crawler_sessions[self.session_id]['stats']['errors'] += 1
            return []
    
    def fast_process_with_beautifulsoup(self, url, depth):
        """Optimized BeautifulSoup processing"""
        try:
            response = self.session.get(url, timeout=8, allow_redirects=True)  # Reduced timeout
            response.raise_for_status()
            
            # Quick content type check
            content_type = response.headers.get('content-type', '')
            if 'text/html' not in content_type:
                return []
            
            soup = BeautifulSoup(response.content, 'html.parser')
            links = self.fast_extract_links(soup, url)
            
            with self.url_lock:
                crawler_sessions[self.session_id]['stats']['beautifulsoup_success'] += 1
            
            return links
            
        except Exception as e:
            return []  # Silent fail, will try Selenium if enabled
    
    def fast_process_with_selenium(self, url, depth):
        """Optimized Selenium processing with faster setup"""
        driver = self.get_fast_driver()
        if not driver:
            return []
            
        try:
            driver.set_page_load_timeout(10)
            driver.get(url)
            
            # Faster waiting - only wait for body
            WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            
            # Quick scroll instead of full scroll
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight/2);")
            time.sleep(0.2)
            
            page_source = driver.page_source
            soup = BeautifulSoup(page_source, 'html.parser')
            links = self.fast_extract_links(soup, url)
            
            with self.url_lock:
                crawler_sessions[self.session_id]['stats']['selenium_fallback'] += 1
            
            return links
            
        except Exception:
            return []
        finally:
            # Don't close driver immediately, reuse it
            pass
    
    def fast_extract_links(self, soup, base_url):
        """Optimized link extraction"""
        links = []
        base_domain = self.base_domain
        seen_urls = set()
        
        for a_tag in soup.find_all('a', href=True):
            try:
                href = a_tag['href'].strip()
                if not href or href.startswith(('javascript:', 'mailto:', 'tel:', '#')):
                    continue
                
                full_url = urljoin(base_url, href)
                parsed_url = urlparse(full_url)
                
                # Quick normalization
                normalized_url = f"{parsed_url.scheme}://{parsed_url.netloc}{parsed_url.path}"
                if parsed_url.query:
                    normalized_url += f"?{parsed_url.query}"
                
                if normalized_url in seen_urls:
                    continue
                seen_urls.add(normalized_url)
                
                is_internal = parsed_url.netloc == base_domain
                
                link_text = a_tag.get_text(strip=True)[:150]  # Reduced text length
                if not link_text:
                    link_text = a_tag.get('title', '')[:150] or ''
                
                links.append({
                    'url': normalized_url,
                    'text': link_text,
                    'is_internal': is_internal,
                    'is_external': not is_internal,
                    'source_url': base_url,
                    'domain': parsed_url.netloc
                })
                
            except Exception:
                continue
                
        return links
    
    def get_fast_driver(self):
        """Get optimized Selenium driver"""
        if not self.driver:
            try:
                chrome_options = Options()
                chrome_options.add_argument("--headless")
                chrome_options.add_argument("--no-sandbox")
                chrome_options.add_argument("--disable-dev-shm-usage")
                chrome_options.add_argument("--disable-gpu")
                chrome_options.add_argument("--disable-images")  # Faster loading
                chrome_options.add_argument("--blink-settings=imagesEnabled=false")
                
                self.driver = webdriver.Chrome(options=chrome_options)
                self.driver.set_page_load_timeout(15)
            except Exception as e:
                logger.error(f"Failed to create driver: {e}")
                return None
        return self.driver
    
    def add_result(self, result):
        """Thread-safe result adding"""
        if self.session_id in crawler_sessions:
            with self.url_lock:
                crawler_sessions[self.session_id]['results'].append(result)
    
    def close_driver(self):
        """Close Selenium driver"""
        if self.driver:
            try:
                self.driver.quit()
            except:
                pass
            self.driver = None
    
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

# Update your start_url_crawl function to use FastURLCrawler
@require_http_methods(["POST"])
@csrf_exempt
def start_url_crawl(request):
    """Start a new optimized URL crawling session"""
    try:
        cleanup_old_sessions()
        
        data = json.loads(request.body)
        url = data.get('url', '').strip()
        max_depth = int(data.get('max_depth', 2))
        use_selenium = data.get('use_selenium', False)
        max_workers = int(data.get('max_workers', 5))  # New parameter
        
        filters = data.get('filters', {})
        
        if not url:
            return JsonResponse({'error': 'URL is required'}, status=400)
            
        try:
            parsed = urlparse(url)
            if not parsed.scheme or not parsed.netloc:
                return JsonResponse({'error': 'Invalid URL format'}, status=400)
        except:
            return JsonResponse({'error': 'Invalid URL format'}, status=400)
            
        session_id = str(uuid.uuid4())
        
        crawler_sessions[session_id] = {
            'crawler': None,
            'results': [],
            'started_at': time.time(),
            'status': 'starting',
            'filters': filters,
            'stats': {
                'total_found': 0,
                'pages_crawled': 0,
                'beautifulsoup_success': 0,
                'selenium_fallback': 0,
                'errors': 0,
                'duplicates_skipped': 0,
                'filtered_links': 0,
                'parallel_workers': max_workers
            }
        }
        
        # Use FastURLCrawler instead of URLCrawler
        crawler = FastURLCrawler(session_id, url, max_depth, use_selenium, filters, max_workers)
        crawler_sessions[session_id]['crawler'] = crawler
        crawler_sessions[session_id]['status'] = 'running'
        
        thread = threading.Thread(target=crawler.crawl)
        thread.daemon = True
        thread.start()
        
        logger.info(f"Started FAST crawling session {session_id} for URL: {url}")
        
        return JsonResponse({
            'success': True,
            'session_id': session_id,
            'message': 'Fast crawling started with parallel processing',
            'max_depth': max_depth,
            'max_workers': max_workers,
            'filters_applied': bool(filters)
        })
        
    except Exception as e:
        logger.error(f"Failed to start fast crawling: {e}")
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
    
    # Step 1: Clean up old sessions
    cleanup_old_sessions()
    
    # Step 2: Get session ID from query parameters
    session_id = request.GET.get('session_id')
    
    if not session_id:
        return JsonResponse({'error': 'Session ID is required'}, status=400)
    
    # Step 3: Validate if session exists
    if session_id not in crawler_sessions:
        return JsonResponse({'error': 'Invalid session ID or session expired'}, status=404)
    
    # Step 4: Get the session info
    session = crawler_sessions[session_id]
    
    # Step 5: Prepare and return the response
    return JsonResponse({
        'status': session.get('status', 'unknown'),
        'stats': session.get('stats', {}),
        'running_time': round(time.time() - session.get('started_at', time.time()), 2),
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


    