from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db.models import Q
from django.core.mail import send_mail
from django.conf import settings as django_settings
from urllib.parse import urlencode
import secrets
import random
import requests

from .models import CustomUser, Company, Job, Application, SavedJob, Resume, PasswordResetToken, OTP


# ======================================================
# HELPERS
# ======================================================
def get_current_user(request):
    """Aapka custom session-based auth — Django ke built-in auth ki jagah."""
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    try:
        return CustomUser.objects.get(id=user_id)
    except CustomUser.DoesNotExist:
        request.session.flush()
        return None


def attach_job_flags(jobs, user):
    """Har job pe is_saved / has_applied chipka deta hai (sirf is request ke liye)."""
    if not user:
        for job in jobs:
            job.is_saved = False  # type: ignore[attr-defined]
            job.has_applied = False  # type: ignore[attr-defined]
        return jobs

    saved_ids = set(SavedJob.objects.filter(user=user).values_list("job_id", flat=True))
    applied_ids = set(Application.objects.filter(user=user).values_list("job_id", flat=True))
    for job in jobs:
        job.is_saved = job.id in saved_ids  # type: ignore[attr-defined]
        job.has_applied = job.id in applied_ids  # type: ignore[attr-defined]
    return jobs


STATUS_CLASS_MAP = {
    "pending": "pending",
    "review": "review",
    "accepted": "accepted",
    "rejected": "rejected",
}


def generate_and_send_otp(email, purpose):
    """6-digit OTP banata hai, DB mein save karta hai, aur email se bhej deta hai."""
    code = str(random.randint(100000, 999999))
    OTP.objects.create(email=email, code=code, purpose=purpose)

    if purpose == "signup":
        subject = "Verify your Smart Job Finder account"
        body = f"Your verification code is: {code}\n\nThis code expires in 10 minutes."
    else:
        subject = "Your Smart Job Finder password reset code"
        body = f"Your password reset code is: {code}\n\nThis code expires in 10 minutes. If you didn't request this, ignore this email."

    send_mail(
        subject=subject,
        message=body,
        from_email=django_settings.DEFAULT_FROM_EMAIL,
        recipient_list=[email],
        fail_silently=False,
    )


# ======================================================
# HOME — login ke baad "Home" hi Dashboard ban jata hai
# ======================================================
def Home(request):
    user = get_current_user(request)
    if user:
        return redirect("dashboard")
    return render(request, "home.html")


# ======================================================
# JOBS LISTING
# ======================================================
def Jobs(request):
    user = get_current_user(request)

    query = request.GET.get("q", "")
    location = request.GET.get("location", "")

    jobs_qs = Job.objects.select_related("company").order_by("-created_at")
    if query:
        jobs_qs = jobs_qs.filter(
            Q(title__icontains=query) | Q(company__name__icontains=query) | Q(skills__icontains=query)
        )
    if location:
        jobs_qs = jobs_qs.filter(location__icontains=location)

    jobs = list(jobs_qs)
    attach_job_flags(jobs, user)
    for job in jobs:
        job.skills = job.skills_list  # type: ignore[assignment]

    return render(request, "jobs.html", {
        "jobs": jobs,
        "user": user,
        "jobs_count": len(jobs),
        "query": query,
        "location": location,
    })


# ======================================================
# COMPANIES LISTING
# ======================================================
def companies(request):
    user = get_current_user(request)

    query = request.GET.get("q", "")
    companies_qs = Company.objects.all().order_by("-created_at")
    if query:
        companies_qs = companies_qs.filter(Q(name__icontains=query) | Q(industry__icontains=query))

    companies_list = list(companies_qs)
    for c in companies_list:
        c.open_jobs_count = c.jobs.count()  # type: ignore[attr-defined]

    return render(request, "companies.html", {
        "companies": companies_list,
        "user": user,
        "companies_count": len(companies_list),
        "query": query,
    })


def company_detail(request, company_id):
    user = get_current_user(request)
    company = get_object_or_404(Company, id=company_id)

    company_jobs = list(
        Job.objects.filter(company=company).order_by("-created_at")
    )
    attach_job_flags(company_jobs, user)
    for job in company_jobs:
        job.skills = job.skills_list  # type: ignore[assignment]

    return render(request, "company_detail.html", {
        "company": company,
        "user": user,
        "jobs": company_jobs,
        "jobs_count": len(company_jobs),
    })


def policy(request):
    user = get_current_user(request)
    return render(request, "policy.html", {"user": user})


# ======================================================
# JOB DETAILS + APPLY + SAVE
# ======================================================
def job_details(request, job_id):
    job = get_object_or_404(Job.objects.select_related("company"), id=job_id)
    user = get_current_user(request)

    job.applicants_count = job.applications.count()  # type: ignore[attr-defined]
    job.company.open_jobs_count = job.company.jobs.count()  # type: ignore[attr-defined]

    if user:
        job.is_saved = SavedJob.objects.filter(user=user, job=job).exists()  # type: ignore[attr-defined]
        job.has_applied = Application.objects.filter(user=user, job=job).exists()  # type: ignore[attr-defined]
    else:
        job.is_saved = False  # type: ignore[attr-defined]
        job.has_applied = False  # type: ignore[attr-defined]

    job.skills = job.skills_list  # type: ignore[assignment]

    return render(request, "job_details.html", {"job": job, "user": user})


def apply_job(request, job_id):
    user = get_current_user(request)
    if not user:
        return redirect(f"/login/?next=/jobs/{job_id}/")

    if user.user_type == "employer":
        messages.error(request, "Employer accounts can't apply to jobs.")
        return redirect("job_details", job_id=job_id)

    job = get_object_or_404(Job, id=job_id)

    if request.method == "POST":
        already = Application.objects.filter(user=user, job=job).exists()
        if already:
            messages.info(request, "You've already applied to this job.")
        else:
            Application.objects.create(user=user, job=job, status="pending")
            messages.success(request, "Application submitted successfully!")

    return redirect("job_details", job_id=job_id)


def toggle_save_job(request, job_id):
    user = get_current_user(request)
    if not user:
        return redirect(f"/login/?next=/jobs/{job_id}/")

    job = get_object_or_404(Job, id=job_id)

    if request.method == "POST":
        saved = SavedJob.objects.filter(user=user, job=job).first()
        if saved:
            saved.delete()
        else:
            SavedJob.objects.create(user=user, job=job)

    next_url = request.POST.get("next") or request.META.get("HTTP_REFERER") or "/jobs/"
    return redirect(next_url)


def delete_job(request, job_id):
    user = get_current_user(request)
    if not user:
        return redirect("login")

    job = get_object_or_404(Job, id=job_id)

    if job.posted_by != user:
        messages.error(request, "You can only delete jobs you posted.")
        return redirect("dashboard")

    if request.method == "POST":
        job.delete()
        messages.success(request, "Job deleted successfully.")
        return redirect("dashboard")

    return redirect("job_details", job_id=job_id)


# ======================================================
# POST A JOB
# ======================================================
def post_job(request):
    user = get_current_user(request)
    if not user:
        return redirect("login")

    if user.user_type != "employer":
        messages.error(request, "Only employer accounts can post jobs.")
        return redirect("dashboard")

    if request.method == "POST":
        company_choice = request.POST.get("company_choice")

        if company_choice == "new":
            name = request.POST.get("new_company_name")
            if not name:
                messages.error(request, "Company name is required.")
                return redirect("post_job")

            company = Company.objects.create(
                name=name,
                industry=request.POST.get("new_company_industry", ""),
                size=request.POST.get("new_company_size", ""),
                location=request.POST.get("new_company_location", ""),
                website=request.POST.get("new_company_website", ""),
                tagline=request.POST.get("new_company_tagline", ""),
                created_by=user,
            )
        else:
            company_id = request.POST.get("company_id")
            if not company_id:
                messages.error(request, "Please select a company.")
                return redirect("post_job")
            company = get_object_or_404(Company, id=company_id)

        Job.objects.create(
            company=company,
            title=request.POST.get("title"),
            job_type=request.POST.get("job_type", "Full-time"),
            experience_level=request.POST.get("experience_level", ""),
            location=request.POST.get("location"),
            salary_min=request.POST.get("salary_min") or None,
            salary_max=request.POST.get("salary_max") or None,
            salary_period=request.POST.get("salary_period", "year"),
            description=request.POST.get("description", ""),
            requirements=request.POST.get("requirements", ""),
            skills=request.POST.get("skills", ""),
            deadline=request.POST.get("deadline") or None,
            posted_by=user,
        )

        messages.success(request, "Job posted successfully!")
        return redirect("dashboard")

    companies_list = Company.objects.all().order_by("name")
    return render(request, "post_job.html", {"user": user, "companies": companies_list})


# ======================================================
# DASHBOARD  (Home ka असली destination login ke baad)
# ======================================================
def dashboard_view(request):
    user = get_current_user(request)
    if not user:
        return redirect("login")

    if user.user_type == "employer":
        return employer_dashboard(request, user)
    return seeker_dashboard(request, user)


def seeker_dashboard(request, user):
    applications_count = Application.objects.filter(user=user).count()
    saved_jobs_count = SavedJob.objects.filter(user=user).count()
    shortlisted_count = Application.objects.filter(user=user, status="accepted").count()

    recommended_jobs = list(
        Job.objects.select_related("company").order_by("-created_at")[:4]
    )
    attach_job_flags(recommended_jobs, user)
    for job in recommended_jobs:
        job.skills = job.skills_list  # type: ignore[assignment]

    recent_applications = list(
        Application.objects.filter(user=user).select_related("job").order_by("-applied_at")[:5]
    )
    for app in recent_applications:
        app.status_class = STATUS_CLASS_MAP.get(app.status, "pending")  # type: ignore[attr-defined]

    context = {
        "user": user,
        "applications_count": applications_count,
        "saved_jobs_count": saved_jobs_count,
        "shortlisted_count": shortlisted_count,
        "recommended_jobs": recommended_jobs,
        "recent_applications": recent_applications,
        "profile_completion": 40,
    }
    return render(request, "dashboard.html", context)


def employer_dashboard(request, user):
    posted_jobs = list(
        Job.objects.filter(posted_by=user).select_related("company").order_by("-created_at")
    )
    posted_jobs_count = len(posted_jobs)

    total_applicants_count = Application.objects.filter(job__posted_by=user).count()
    companies_count = Company.objects.filter(created_by=user).count()

    for job in posted_jobs:
        job.applicants_count = job.applications.count()  # type: ignore[attr-defined]

    context = {
        "user": user,
        "posted_jobs": posted_jobs,
        "posted_jobs_count": posted_jobs_count,
        "total_applicants_count": total_applicants_count,
        "companies_count": companies_count,
    }
    return render(request, "employer_dashboard.html", context)


# ======================================================
# PROFILE
# ======================================================
def profile(request):
    user = get_current_user(request)
    if not user:
        return redirect("login")

    applications = list(
        Application.objects.filter(user=user).select_related("job", "job__company").order_by("-applied_at")
    )
    for app in applications:
        app.status_class = STATUS_CLASS_MAP.get(app.status, "pending")  # type: ignore[attr-defined]

    saved_jobs = list(
        Job.objects.filter(saved_by__user=user).select_related("company").order_by("-saved_by__saved_at")
    )

    resume = Resume.objects.filter(user=user).first()

    context = {
        "user": user,
        "applications": applications,
        "applications_count": len(applications),
        "saved_jobs": saved_jobs,
        "saved_jobs_count": len(saved_jobs),
        "resume": resume,
        "profile_completion": 40,
    }
    return render(request, "profile.html", context)


def update_profile(request):
    user = get_current_user(request)
    if not user:
        return redirect("login")

    if request.method == "POST":
        user.first_name = request.POST.get("first_name", user.first_name)
        user.last_name = request.POST.get("last_name", user.last_name)
        user.email = request.POST.get("email", user.email)
        user.phone = request.POST.get("phone", user.phone)
        user.save()
        messages.success(request, "Profile updated successfully.")

    return redirect("profile")


def upload_resume(request):
    user = get_current_user(request)
    if not user:
        return redirect("login")

    if request.method == "POST" and request.FILES.get("resume"):
        Resume.objects.filter(user=user).delete()
        Resume.objects.create(user=user, file=request.FILES["resume"])
        messages.success(request, "Resume uploaded successfully!")

    return redirect("profile")


def change_password(request):
    user = get_current_user(request)
    if not user:
        return redirect("login")

    if request.method == "POST":
        current = request.POST.get("current_password")
        new = request.POST.get("new_password")
        confirm = request.POST.get("confirm_password")

        if not user.check_password(current):
            messages.error(request, "Current password is incorrect.")
        elif new != confirm:
            messages.error(request, "New passwords do not match.")
        else:
            user.set_password(new)
            user.save()
            messages.success(request, "Password updated successfully.")

    return redirect("profile")


# ======================================================
# AUTH
# ======================================================
def signup_view(request):
    if request.method == "POST":
        first_name = request.POST.get("first_name")
        last_name = request.POST.get("last_name")
        email = request.POST.get("email")
        phone = request.POST.get("phone")
        password = request.POST.get("password")
        confirm_password = request.POST.get("confirm_password")
        user_type = request.POST.get("user_type", "seeker")
        if user_type not in ("seeker", "employer"):
            user_type = "seeker"

        if password != confirm_password:
            messages.error(request, "Passwords do not match.")
            return redirect("login")

        if CustomUser.objects.filter(email=email).exists():
            messages.error(request, "An account with this email already exists.")
            return redirect("login")

        user = CustomUser(
            first_name=first_name,
            last_name=last_name,
            email=email,
            phone=phone,
            user_type=user_type,
            is_email_verified=False,
        )
        user.set_password(password)
        user.save()

        generate_and_send_otp(email, "signup")
        request.session["otp_email"] = email
        request.session["otp_purpose"] = "signup"

        messages.success(request, "We've sent a verification code to your email.")
        return redirect("verify_otp")

    return redirect("login")


def login(request):
    if request.method == "POST":
        identifier = request.POST.get("identifier")
        password = request.POST.get("password")

        if not identifier or not password:
            messages.error(request, "Email/Phone aur Password dono daalo.")
            return render(request, "login.html")

        user = None
        try:
            user = CustomUser.objects.get(email=identifier)
        except CustomUser.DoesNotExist:
            try:
                user = CustomUser.objects.get(phone=identifier)
            except CustomUser.DoesNotExist:
                messages.error(request, "Koi account is email/phone se nahi mila.")
                return render(request, "login.html")

        if user.check_password(password):
            if not user.is_email_verified:
                generate_and_send_otp(user.email, "signup")
                request.session["otp_email"] = user.email
                request.session["otp_purpose"] = "signup"
                messages.info(request, "Please verify your email first. We've sent a new code.")
                return redirect("verify_otp")

            request.session["user_id"] = str(user.id)
            request.session["is_logged_in"] = True
            messages.success(request, f"Welcome back, {user.first_name or 'User'}!")
            next_url = request.GET.get("next") or request.POST.get("next")
            return redirect(next_url) if next_url else redirect("dashboard")
        else:
            messages.error(request, "Password galat hai.")
            return render(request, "login.html")

    return render(request, "login.html")


def logout_view(request):
    request.session.flush()
    return redirect("home")


def delete_account_view(request):
    if request.method == "POST":
        user_id = request.session.get("user_id")
        if not user_id:
            return redirect("login")

        try:
            user = CustomUser.objects.get(id=user_id)
        except CustomUser.DoesNotExist:
            request.session.flush()
            return redirect("login")

        password = request.POST.get("password")
        if not user.check_password(password):
            messages.error(request, "Incorrect password. Account not deleted.")
            return redirect("dashboard")

        user.delete()
        request.session.flush()
        return redirect("home")

    return redirect("dashboard")


# ======================================================
# EMPLOYER — VIEW APPLICANTS FOR A JOB
# ======================================================
def job_applicants_view(request, job_id):
    user = get_current_user(request)
    if not user:
        return redirect("login")

    job = get_object_or_404(Job.objects.select_related("company"), id=job_id)

    if job.posted_by != user:
        messages.error(request, "You can only view applicants for jobs you posted.")
        return redirect("dashboard")

    applications = list(
        Application.objects.filter(job=job).select_related("user").order_by("-applied_at")
    )
    for app in applications:
        app.status_class = STATUS_CLASS_MAP.get(app.status, "pending")  # type: ignore[attr-defined]
        app.resume = Resume.objects.filter(user=app.user).first()  # type: ignore[attr-defined]

    context = {
        "user": user,
        "job": job,
        "applications": applications,
        "applicants_count": len(applications),
    }
    return render(request, "job_applicants.html", context)


def update_application_status(request, application_id):
    user = get_current_user(request)
    if not user:
        return redirect("login")

    application = get_object_or_404(Application.objects.select_related("job"), id=application_id)

    if application.job.posted_by != user:
        messages.error(request, "You can only manage applicants for your own jobs.")
        return redirect("dashboard")

    if request.method == "POST":
        new_status = request.POST.get("status")
        if new_status in dict(Application.STATUS_CHOICES):
            application.status = new_status
            application.save()
            messages.success(request, "Application status updated.")

    return redirect("job_applicants", job_id=application.job.id)


# ======================================================
# FORGOT PASSWORD
# ======================================================
def forgot_password_view(request):
    if request.method == "POST":
        email = request.POST.get("email")

        try:
            user = CustomUser.objects.get(email=email)
        except CustomUser.DoesNotExist:
            # security ke liye: bata do success hi, taaki koi email-existence guess na kar sake
            messages.success(request, "If an account exists for that email, a code has been sent.")
            return redirect("login")

        generate_and_send_otp(email, "password_reset")
        request.session["otp_email"] = email
        request.session["otp_purpose"] = "password_reset"

        messages.success(request, "A verification code has been sent to your email.")
        return redirect("verify_otp")

    return render(request, "forgot_password.html")


def verify_otp_view(request):
    email = request.session.get("otp_email")
    purpose = request.session.get("otp_purpose")

    if not email or not purpose:
        messages.error(request, "Session expired. Please start again.")
        return redirect("login")

    if request.method == "POST":
        entered_code = request.POST.get("otp_code", "").strip()

        otp = OTP.objects.filter(email=email, purpose=purpose).order_by("-created_at").first()

        if not otp or not otp.is_valid() or otp.code != entered_code:
            messages.error(request, "Invalid or expired code. Please try again.")
            return render(request, "verify_otp.html", {"email": email})

        otp.verified = True
        otp.save()

        if purpose == "signup":
            user = get_object_or_404(CustomUser, email=email)
            user.is_email_verified = True
            user.save()

            request.session.pop("otp_email", None)
            request.session.pop("otp_purpose", None)
            request.session["user_id"] = str(user.id)
            request.session["is_logged_in"] = True

            messages.success(request, "Email verified successfully! Welcome aboard.")
            return redirect("dashboard")

        else:  # password_reset
            user = get_object_or_404(CustomUser, email=email)
            token = secrets.token_urlsafe(32)
            PasswordResetToken.objects.create(user=user, token=token)

            request.session.pop("otp_email", None)
            request.session.pop("otp_purpose", None)

            return redirect("reset_password", token=token)

    return render(request, "verify_otp.html", {"email": email})


def resend_otp_view(request):
    email = request.session.get("otp_email")
    purpose = request.session.get("otp_purpose")

    if not email or not purpose:
        messages.error(request, "Session expired. Please start again.")
        return redirect("login")

    generate_and_send_otp(email, purpose)
    messages.success(request, "A new code has been sent to your email.")
    return redirect("verify_otp")


def reset_password_view(request, token):
    try:
        reset_token = PasswordResetToken.objects.get(token=token)
    except PasswordResetToken.DoesNotExist:
        messages.error(request, "Invalid or expired reset link. Please request a new one.")
        return redirect("forgot_password")

    if not reset_token.is_valid():
        messages.error(request, "This reset link has expired. Please request a new one.")
        return redirect("forgot_password")

    if request.method == "POST":
        new_password = request.POST.get("new_password")
        confirm_password = request.POST.get("confirm_password")

        if not new_password or new_password != confirm_password:
            messages.error(request, "Passwords do not match.")
            return render(request, "reset_password.html", {"token": token})

        user = reset_token.user
        user.set_password(new_password)
        user.save()

        reset_token.used = True
        reset_token.save()

        messages.success(request, "Password reset successful. Please login with your new password.")
        return redirect("login")

    return render(request, "reset_password.html", {"token": token})


# ======================================================
# LOGIN WITH GOOGLE (manual OAuth2 — no allauth needed)
# ======================================================
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"


def google_login_view(request):
    params = {
        "client_id": django_settings.GOOGLE_CLIENT_ID,
        "redirect_uri": django_settings.GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "offline",
        "prompt": "select_account",
    }
    return redirect(f"{GOOGLE_AUTH_URL}?{urlencode(params)}")


def google_callback_view(request):
    code = request.GET.get("code")
    error = request.GET.get("error")

    if error or not code:
        messages.error(request, "Google login was cancelled or failed.")
        return redirect("login")

    # Step 1: authorization code ko access token se exchange karo
    token_response = requests.post(GOOGLE_TOKEN_URL, data={
        "code": code,
        "client_id": django_settings.GOOGLE_CLIENT_ID,
        "client_secret": django_settings.GOOGLE_CLIENT_SECRET,
        "redirect_uri": django_settings.GOOGLE_REDIRECT_URI,
        "grant_type": "authorization_code",
    })

    if token_response.status_code != 200:
        messages.error(request, "Google login failed. Please try again.")
        return redirect("login")

    access_token = token_response.json().get("access_token")
    if not access_token:
        messages.error(request, "Google login failed. Please try again.")
        return redirect("login")

    # Step 2: access token se Google profile fetch karo
    profile_response = requests.get(
        GOOGLE_USERINFO_URL,
        headers={"Authorization": f"Bearer {access_token}"},
    )
    profile = profile_response.json()

    email = profile.get("email")
    if not email:
        messages.error(request, "Could not retrieve email from Google.")
        return redirect("login")

    first_name = profile.get("given_name", "")
    last_name = profile.get("family_name", "")

    # Step 3: existing user se login karo, ya naya account bana do
    user, created = CustomUser.objects.get_or_create(
        email=email,
        defaults={
            "first_name": first_name,
            "last_name": last_name,
            "phone": "",
        },
    )
    if created:
        # Google se aaye users ke liye random unusable password (koi is se login nahi kar sakta,
        # sirf Google se hi kar sakta hai — jab tak "Change Password" se khud set na kare)
        user.set_password(secrets.token_urlsafe(24))
        user.is_email_verified = True  # Google ne already verify kar diya hai
        user.save()

    request.session["user_id"] = str(user.id)
    request.session["is_logged_in"] = True
    messages.success(request, f"Welcome, {user.first_name or 'there'}!")
    return redirect("dashboard")