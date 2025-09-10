from django.urls import path
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)
from . import views





urlpatterns = [
    # Users starts
    path("user/", views.current_user, name="current_user"),
    # User ends
    
    # keyword search and parse starts
    path('search-keywords/', views.search_and_parse, name='search_and_parse'),
    path('save-keyword-results/', views.save_keyword_results, name='save_keyword_results'),
    path('keywords-list/', views.keywords_list, name='keywords_list'),
    # keyword search and parse ends
    
    # Projects starts
    path('projects/', views.projects, name='projects'),
    path('project/<int:pk>/', views.project_detail, name='project_detail'),
    
    path("project-list/", views.list_projects, name="list-projects"),
    
    path('user-projects/', views.user_projects, name="user-projects"),
    path('project/<int:project_id>/folders/', views.project_folders, name='project_folders'),
    # Projects ends
    
    # Project_folder starts
    path('folder/<int:folder_id>/keyword-results/', views.folder_details, name='folder_details'),
    path("folder/<int:folder_id>/delete-folder-results/", views.delete_folder_results, name="delete_folder_results"),
    # Project folder ends
    
    # token authentication
    path('token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
]
    