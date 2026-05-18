from django.conf import settings
from django.urls import path
from django.contrib.auth import views as auth_views

from . import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('hra/', views.hra_tracker, name='hra_tracker'),

    # Data entry endpoints
    path('transactions/add/', views.add_transaction, name='add_transaction'),
    path('transactions/edit/<int:pk>/', views.edit_transaction, name='edit_transaction'),
    path('transactions/delete/<int:pk>/', views.delete_transaction, name='delete_transaction'),
    path('hra/add/', views.add_hra_entry, name='add_hra_entry'),
    path('hra/edit/<int:pk>/', views.edit_hra_entry, name='edit_hra_entry'),
    path('hra/delete/<int:pk>/', views.delete_hra_entry, name='delete_hra_entry'),
    path('goals/increment/', views.add_goal_increment, name='add_goal_increment'),
    path('goals/increment/delete/<int:inc_id>/', views.delete_goal_increment, name='delete_goal_increment'),
    path('goals/adjustment/', views.add_goal_adjustment, name='add_goal_adjustment'),
    path('goals/adjustment/delete/<int:adj_id>/', views.delete_goal_adjustment, name='delete_goal_adjustment'),
    path('goals/annual/', views.set_annual_goal, name='set_annual_goal'),

    # Admin panels (superuser only)
    path('admin/monitor/', views.admin_monitor, name='admin_monitor'),
    path('admin/api/metrics/', views.server_metrics, name='server_metrics'),

    # Auth — SSO only, dev login available in DEBUG mode
    path('login/', views.login_view, name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
]

if settings.DEBUG:
    urlpatterns += [
        path('dev-login/', views.dev_login, name='dev_login'),
    ]
