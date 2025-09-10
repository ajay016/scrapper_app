# views.py
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from django.views.decorators.csrf import csrf_exempt
from rest_framework import status
from collections import deque
from django.utils import timezone
from bs4 import BeautifulSoup
from django.shortcuts import get_object_or_404
from urllib.parse import urljoin, urlparse
import requests
from .utils.google_search import google_search
from .utils.parser import parse_page, save_page_hierarchy
from .serializers import *
from .models import *









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
@api_view(['GET'])
@permission_classes([AllowAny])
def search_and_parse(request):
    keyword_raw = request.GET.get("q", "headphones")
    max_depth = int(request.GET.get("depth", 0))

    keyword_stripped = keyword_raw.strip()
    keyword_obj, _ = Keyword.objects.get_or_create(word=keyword_stripped)

    # Step 1: Get Google links
    links = google_search(keyword_stripped, num_results=10)

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
            child_node = parse_to_dict(child, depth=depth+1)
            if child_node:
                node["children"].append(child_node)
        return node

    for link in links:
        parsed_data = parse_page(link, current_depth=0, max_depth=max_depth)
        node = parse_to_dict(parsed_data)
        if node:
            results.append(node)

    return Response({
        "keyword": KeywordSerializer(keyword_obj).data,
        "results": results
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
