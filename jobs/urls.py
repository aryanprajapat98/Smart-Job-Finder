from django.urls import path
from django.conf import settings
from django.conf.urls.static import static
from . import views

urlpatterns = [
    path('', views.Home, name='home'),
    path('jobs/', views.Jobs, name='jobs'),
    path('jobs/<uuid:job_id>/', views.job_details, name='job_details'),
    path('jobs/<uuid:job_id>/apply/', views.apply_job, name='apply_job'),
    path('jobs/<uuid:job_id>/save/', views.toggle_save_job, name='toggle_save_job'),
    path('jobs/<uuid:job_id>/delete/', views.delete_job, name='delete_job'),

    path('companies/', views.companies, name='companies'),
    path('companies/<uuid:company_id>/', views.company_detail, name='company_detail'),
    path('policy/', views.policy, name='policy'),

    path('login/', views.login, name='login'),
    path('signup/', views.signup_view, name='signup'),
    path('logout/', views.logout_view, name='logout'),
    path('delete-account/', views.delete_account_view, name='delete_account'),

    path('forgot-password/', views.forgot_password_view, name='forgot_password'),
    path('verify-otp/', views.verify_otp_view, name='verify_otp'),
    path('resend-otp/', views.resend_otp_view, name='resend_otp'),
    path('reset-password/<str:token>/', views.reset_password_view, name='reset_password'),

    path('google-login/', views.google_login_view, name='google_login'),
    path('google-callback/', views.google_callback_view, name='google_callback'),

    path('dashboard/', views.dashboard_view, name='dashboard'),
    path('post-job/', views.post_job, name='post_job'),
    path('jobs/<uuid:job_id>/applicants/', views.job_applicants_view, name='job_applicants'),
    path('applications/<uuid:application_id>/status/', views.update_application_status, name='update_application_status'),

    path('profile/', views.profile, name='profile'),
    path('update-profile/', views.update_profile, name='update_profile'),
    path('upload-resume/', views.upload_resume, name='upload_resume'),
    path('change-password/', views.change_password, name='change_password'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)