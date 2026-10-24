from django.urls import path

from . import views

urlpatterns = [
    path('', views.expenses_home, name='expenses_home'),
    path('year/', views.expenses_year, name='expenses_year'),
    path('add/', views.expense_add, name='expense_add'),
    path('<int:pk>/edit/', views.expense_edit, name='expense_edit'),
    path('<int:pk>/delete/', views.expense_delete, name='expense_delete'),
    path('<int:pk>/review/', views.expense_review, name='expense_review'),
    path('ai-audit/', views.expenses_ai_audit, name='expenses_ai_audit'),

    path('settings/', views.expenses_settings, name='expenses_settings'),
    path('gmail/connect/', views.gmail_connect, name='expenses_gmail_connect'),
    path('gmail/callback/', views.gmail_callback, name='expenses_gmail_callback'),
    path('gmail/<int:pk>/sync/', views.gmail_sync, name='expenses_gmail_sync'),
    path('gmail/<int:pk>/disconnect/', views.gmail_disconnect, name='expenses_gmail_disconnect'),
    path('categories/add/', views.category_save, name='expenses_category_add'),
    path('categories/<int:pk>/', views.category_save, name='expenses_category_edit'),
    path('categories/<int:pk>/delete/', views.category_delete, name='expenses_category_delete'),
    path('cards/add/', views.source_save, name='expenses_source_add'),
    path('cards/<int:pk>/', views.source_save, name='expenses_source_edit'),
    path('rules/<int:pk>/delete/', views.rule_delete, name='expenses_rule_delete'),

    path('statements/', views.statements_list, name='expenses_statements'),
    path('statements/upload/', views.statement_upload, name='expenses_statement_upload'),
    path('statements/<int:pk>/', views.statement_detail, name='expenses_statement_detail'),
    path('statements/<int:pk>/unlock/', views.statement_unlock, name='expenses_statement_unlock'),
    path('statements/<int:pk>/paid/', views.statement_paid, name='expenses_statement_paid'),
    path('statements/<int:pk>/reconcile/', views.statement_reconcile, name='expenses_statement_reconcile'),
    path('statements/lines/<int:pk>/resolve/', views.statement_line_resolve, name='expenses_statement_line_resolve'),
]
