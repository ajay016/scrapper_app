from django.urls import path
from . import views





urlpatterns = [
    path('', views.home, name='home'),
    path('login-user/', views.login_view, name='login_user'),
    path('logout/', views.logout_view, name='logout'),
]
    