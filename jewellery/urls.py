from django.urls import path
from . import views

urlpatterns = [
    path('', views.jewellery_dashboard, name='jewellery_dashboard'),
    path('add/', views.add_item, name='add_jewellery'),
    path('api/search/', views.search_autocomplete, name='jewellery_autocomplete'),
    path('<int:pk>/', views.detail_item, name='jewellery_detail'),
    path('<int:pk>/edit/', views.edit_item, name='edit_jewellery'),
    path('<int:pk>/delete/', views.delete_item, name='delete_jewellery'),
    path('<int:pk>/photo/', views.serve_photo, name='jewellery_photo'),
]
