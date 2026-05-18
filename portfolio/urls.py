from django.urls import path
from . import views

urlpatterns = [
    path('unlock/', views.portfolio_unlock, name='portfolio_unlock'),
    path('', views.master_portfolio, name='portfolio_tracker'),
    path('zerodha/', views.zerodha_consolidated, name='zerodha_consolidated'),
    path('zerodha/<slug:slug>/', views.zerodha_detail, name='zerodha_detail'),
    path('growth/', views.portfolio_growth, name='portfolio_growth'),

    # Detail pages ("View All")
    path('epf/', views.epf_detail, name='epf_detail'),
    path('nps/', views.nps_detail, name='nps_detail'),
    path('fd/', views.fd_detail, name='fd_detail'),
    path('cash/', views.cash_detail, name='cash_detail'),
    path('bonds/', views.bonds_detail, name='bonds_detail'),
    path('crypto/', views.crypto_detail, name='crypto_detail'),
    path('commodities/', views.commodities_detail, name='commodities_detail'),

    # Actions
    path('sync-sheets/', views.sync_from_sheets, name='sync_from_sheets'),
    path('refresh-prices/', views.refresh_prices, name='refresh_prices'),
    path('take-snapshot/', views.take_snapshot_view, name='take_snapshot'),
    path('generate-insights/', views.generate_insights, name='generate_insights'),

    # EPF
    path('epf/add/', views.add_epf_entry, name='add_epf_entry'),
    path('epf/<int:pk>/edit/', views.edit_epf_entry, name='edit_epf_entry'),
    path('epf/<int:pk>/delete/', views.delete_epf_entry, name='delete_epf_entry'),

    # NPS
    path('nps/add/', views.add_nps_entry, name='add_nps_entry'),
    path('nps/<int:pk>/edit/', views.edit_nps_entry, name='edit_nps_entry'),
    path('nps/<int:pk>/delete/', views.delete_nps_entry, name='delete_nps_entry'),

    # FD
    path('fd/add/', views.add_fd, name='add_fd'),
    path('fd/<int:pk>/edit/', views.edit_fd, name='edit_fd'),
    path('fd/<int:pk>/delete/', views.delete_fd, name='delete_fd'),

    # Cash
    path('cash/add/', views.add_cash, name='add_cash'),
    path('cash/<int:pk>/edit/', views.edit_cash, name='edit_cash'),
    path('cash/<int:pk>/delete/', views.delete_cash, name='delete_cash'),

    # Bonds
    path('bond/add/', views.add_bond, name='add_bond'),
    path('bond/<int:pk>/edit/', views.edit_bond, name='edit_bond'),
    path('bond/<int:pk>/delete/', views.delete_bond, name='delete_bond'),

    # Crypto
    path('crypto/add/', views.add_crypto, name='add_crypto'),
    path('crypto/<int:pk>/edit/', views.edit_crypto, name='edit_crypto'),
    path('crypto/<int:pk>/delete/', views.delete_crypto, name='delete_crypto'),

    # Commodity
    path('commodity/add/', views.add_commodity, name='add_commodity'),
    path('commodity/<int:pk>/edit/', views.edit_commodity, name='edit_commodity'),
    path('commodity/<int:pk>/delete/', views.delete_commodity, name='delete_commodity'),

    # Goals
    path('goal/add/', views.add_goal, name='add_goal'),
    path('goal/<int:pk>/edit/', views.edit_goal, name='edit_goal'),
    path('goal/<int:pk>/delete/', views.delete_goal, name='delete_goal'),

    # US Stocks (RSU)
    path('us-stock/add/', views.add_us_stock, name='add_us_stock'),
    path('us-stock/<int:pk>/edit/', views.edit_us_stock, name='edit_us_stock'),
    path('us-stock/<int:pk>/delete/', views.delete_us_stock, name='delete_us_stock'),

    # WebAuthn (FaceID / biometric)
    path('webauthn/register/begin/', views.webauthn_register_begin, name='webauthn_register_begin'),
    path('webauthn/register/complete/', views.webauthn_register_complete, name='webauthn_register_complete'),
    path('webauthn/auth/begin/', views.webauthn_auth_begin, name='webauthn_auth_begin'),
    path('webauthn/auth/complete/', views.webauthn_auth_complete, name='webauthn_auth_complete'),
    path('webauthn/remove/', views.webauthn_remove, name='webauthn_remove'),
]
